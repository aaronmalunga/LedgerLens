"""The channel-agnostic core (D-06): handle(InboundEvent) -> list[OutboundMessage]."""
from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation

from ledgerlens.llm.client import ModelClient

from .checks import check_transaction
from .events import Button, InboundEvent, InboundKind, OutboundKind, OutboundMessage
from .models import SourceType, Transaction, evidence_tier
from .store import Store

HELP = ("I'm LedgerLens. Send me a photo of a receipt or notebook page, a mobile-money SMS, "
        "or a voice note about a sale. I'll read it, you confirm it, and I keep your ledger. "
        "Type 'summary' for your totals.")
OUT_OF_SCOPE = ("Sorry, I can only help with your business records: receipts, payments, sales "
                "and your ledger. " + HELP)
SMS_HINT = re.compile(r"(\b[RK] ?\d|ZMW|ZAR|reserved|purchase|txn|trans(action)?\s*id|ref(erence)?|received|sent|paid|airtel|mtn|momo|balance)", re.I)
EDIT_PATTERN = re.compile(r"^\s*(amount|date|counterparty)\s+(.+)$", re.I)


class Core:
    def __init__(self, store: Store, model: ModelClient) -> None:
        self.store = store
        self.model = model

    def handle(self, ev: InboundEvent) -> list[OutboundMessage]:
        if not self.store.mark_processed(ev.event_id):
            return []  # duplicate delivery: already answered once
        if ev.kind == InboundKind.BUTTON_REPLY:
            return self._button(ev)
        if ev.kind == InboundKind.IMAGE:
            return self._propose(ev, SourceType.RECEIPT)
        if ev.kind == InboundKind.AUDIO:
            return [_text("Voice notes are coming soon (planned for this build). For now, send a photo or SMS.")]
        if ev.kind == InboundKind.TEXT:
            return self._text(ev)
        return [_text(HELP)]

    # --- text: commands, edits, pasted SMS, scope guard ---
    def _text(self, ev: InboundEvent) -> list[OutboundMessage]:
        body = (ev.text or "").strip()
        if body.lower() in {"hi", "hello", "help", "start"}:
            return [_text(HELP)]
        if body.lower() == "summary":
            return [_text(self._summary(ev.user_ref))]
        pid = self.store.latest_awaiting_edit(ev.user_ref)
        if pid and (m := EDIT_PATTERN.match(body)):
            return self._apply_edit(ev, pid, m.group(1).lower(), m.group(2).strip())
        if SMS_HINT.search(body):
            return self._propose(ev, SourceType.SMS)
        return [_text(OUT_OF_SCOPE)]  # narrow scope: WhatsApp terms 4.7

    def _propose(self, ev: InboundEvent, source: SourceType) -> list[OutboundMessage]:
        try:
            tx = self.model.extract(media=ev.media, mime=ev.media_mime, text=ev.text, source_hint=source)
        except Exception:
            return [_text("I couldn't read that one. Could you send a clearer photo, or type the amount and date?")]
        pid = self.store.add_pending(ev.user_ref, tx, ev.event_id)
        return [_confirm_card(pid, tx)]

    def _button(self, ev: InboundEvent) -> list[OutboundMessage]:
        action, _, pid = (ev.button_id or "").partition(":")
        got = self.store.get_pending(ev.user_ref, pid)
        if not got:
            return [_text("That entry is no longer waiting for you.")]
        tx, _, _ = got
        if action == "confirm":
            entry_id = self.store.confirm(ev.user_ref, pid)
            return [_text(f"Saved to your ledger (entry {entry_id}).")]
        if action == "reject":
            self.store.drop_pending(ev.user_ref, pid)
            return [_text("Discarded. Nothing was saved.")]
        if action == "edit":
            self.store.update_pending(ev.user_ref, pid, tx, "awaiting_edit")
            return [_text("What should change? Reply like: 'amount 120.50', 'date 2026-10-27' or 'counterparty Shoprite'.")]
        return [_text(HELP)]

    def _apply_edit(self, ev: InboundEvent, pid: str, field: str, value: str) -> list[OutboundMessage]:
        tx, _, _ = self.store.get_pending(ev.user_ref, pid)
        try:
            if field == "amount":
                tx = tx.model_copy(update={"amount": Decimal(value.replace(",", ""))})
            elif field == "date":
                tx = Transaction.model_validate({**tx.model_dump(), "date": value})
            else:
                tx = tx.model_copy(update={"counterparty": value})
        except (InvalidOperation, ValueError):
            return [_text(f"I couldn't use '{value}' as the {field}. Try again.")]
        self.store.update_pending(ev.user_ref, pid, tx, "awaiting_confirm")
        return [_confirm_card(pid, tx)]

    def _summary(self, user_ref: str) -> str:
        totals = self.store.totals(user_ref)
        if not totals:
            return "Your ledger is empty so far. Send a receipt or SMS to start."
        lines = []
        for cur, t in totals.items():
            backed = t["in_by_tier"]["T1"] + t["in_by_tier"]["T2"]
            share = f"{(backed / t['in'] * 100):.0f}%" if t["in"] else "n/a"
            lines.append(f"{cur}: money in {t['in']:.2f}, money out {t['out']:.2f}, "
                         f"net {t['in'] - t['out']:.2f}. Income backed by receipts/SMS: {share}.")
        return "\n".join(lines)


def _text(s: str) -> OutboundMessage:
    return OutboundMessage(kind=OutboundKind.TEXT, text=s)


def _confirm_card(pid: str, tx: Transaction) -> OutboundMessage:
    issues = check_transaction(tx)
    tier = evidence_tier(tx.source_type, tx.txn_id)
    arrow = "Money in" if tx.direction.value == "in" else "Money out"
    lines = [f"{arrow}: {tx.currency} {tx.amount}",
             f"Date: {tx.date or 'not found'}",
             f"Who: {tx.counterparty or 'not found'}",
             f"Evidence: {tier.value}" + (f" (ref {tx.txn_id})" if tx.txn_id else "")]
    if tx.status.value == "reserved":
        lines.append("Note: this is a card hold, not a completed payment. It won't count in totals.")
    lines += [f"⚠ {i.message}" for i in issues]
    lines.append("Is this right?")
    return OutboundMessage(
        kind=OutboundKind.CONFIRM_CARD, text="\n".join(lines),
        buttons=[Button(id=f"confirm:{pid}", title="Confirm"),
                 Button(id=f"edit:{pid}", title="Edit"),
                 Button(id=f"reject:{pid}", title="Reject")],
    )
