"""The channel-agnostic core (D-06): handle(InboundEvent) -> list[OutboundMessage]."""
from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation

from ledgerlens.llm.client import ModelClient
from ledgerlens.llm.transcribe import Transcriber

from . import audio as audio_in

from .checks import check_transaction
from .creditfile import build_credit_file, render_text
from .demo import DEMO_LABEL, DEMO_TRANSACTIONS
from .guard import REFUSALS, Guard
from .events import Button, InboundEvent, InboundKind, OutboundKind, OutboundMessage
from .models import SourceType, Transaction, evidence_tier
from .store import Store

HELP = ("I'm LedgerLens. Send me a photo of a receipt or notebook page, a mobile-money SMS, "
        "or a voice note about a sale. I'll read it, you confirm it, and I keep your ledger. "
        "Type 'summary' for your totals. "
        "Demo notice: please send sample or made-up records only, never your real ones.")
OUT_OF_SCOPE = ("Sorry, I can only help with your business records: receipts, payments, sales "
                "and your ledger. " + HELP)
SMS_HINT = re.compile(r"(\b[RK] ?\d|ZMW|ZAR|reserved|purchase|txn|trans(action)?\s*id|ref(erence)?|received|sent|paid|airtel|mtn|momo|balance)", re.I)
EDIT_PATTERN = re.compile(r"^\s*(amount|date|counterparty)\s+(.+)$", re.I)


class Core:
    def __init__(self, store: Store, model: ModelClient, guard: Guard | None = None,
                 transcriber: Transcriber | None = None, allow_audio_conversion: bool = False) -> None:
        self.store = store
        self.model = model
        self.guard = guard or Guard()
        self.transcriber = transcriber  # None = voice notes are off in this deployment
        self.allow_audio_conversion = allow_audio_conversion  # ffmpeg for non-WAV audio: off on the public web endpoint

    def handle(self, ev: InboundEvent) -> list[OutboundMessage]:
        if not self.store.mark_processed(ev.event_id):
            return []  # duplicate delivery: already answered once
        if reason := self.guard.check_message(ev.user_ref, ev.media):
            return [_text(REFUSALS[reason])]
        if ev.kind == InboundKind.BUTTON_REPLY:
            return self._button(ev)
        if ev.kind == InboundKind.IMAGE:
            return self._propose(ev, ev.source_hint or SourceType.RECEIPT)
        if ev.kind == InboundKind.AUDIO:
            return self._voice(ev)
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
        if body.lower() in {"credit file", "creditfile", "file"}:
            rows = self.store.entries(ev.user_ref)
            demo = any(r["source_event_id"].startswith("demo:") for r in rows)  # F12: label simulated history
            return [_text(render_text(build_credit_file(rows), DEMO_LABEL if demo else ""))]
        if body.lower() == "demo":
            return [_text(self._seed_demo(ev))]
        pid = self.store.latest_awaiting_edit(ev.user_ref)
        if pid and (m := EDIT_PATTERN.match(body)):
            return self._apply_edit(ev, pid, m.group(1).lower(), m.group(2).strip())
        if SMS_HINT.search(body):
            return self._propose(ev, SourceType.SMS)
        return [_text(OUT_OF_SCOPE)]  # narrow scope: WhatsApp terms 4.7

    # --- voice (D-15): transcribe in memory, drop the audio, keep only the text ---
    def _voice(self, ev: InboundEvent) -> list[OutboundMessage]:
        if self.transcriber is None:
            return [_text("Voice notes are switched off in this demo. Please send a photo or an SMS instead.")]
        if reason := self.guard.check_budget():
            return [_text(REFUSALS[reason])]
        try:
            wav, seconds = audio_in.to_wav(ev.media or b"", allow_conversion=self.allow_audio_conversion)
        except audio_in.AudioError as e:
            return [_text(audio_in.user_message(e))]
        try:
            transcript = self.transcriber.transcribe(wav)
        except Exception:
            return [_text("I couldn't turn that voice note into text. Please try again, or type the sale.")]
        finally:
            del wav  # the audio lives only in this call; nothing below keeps it
        self.guard.record_audio(seconds)
        transcript = (transcript or "").strip()
        if not transcript:
            return [_text(audio_in.user_message(audio_in.AudioError("empty")))]
        # From here the event is plain text: the audio bytes are not carried forward or stored.
        text_ev = ev.model_copy(update={"kind": InboundKind.TEXT, "media": None, "media_mime": None,
                                        "text": f"Note received on {ev.received_at.date().isoformat()}. Transcript: {transcript}"})
        return self._propose(text_ev, SourceType.VOICE, heard=transcript)

    def _propose(self, ev: InboundEvent, source: SourceType, heard: str | None = None) -> list[OutboundMessage]:
        if reason := self.guard.check_budget():
            return [_text(REFUSALS[reason])]
        try:
            tx = self.model.extract(media=ev.media, mime=ev.media_mime, text=ev.text, source_hint=source)
            # Only the trader's own edit may set `edited`, and only the trader's declared record type sets
            # `source_type` (D-14): the evidence tier follows from these two, so the model must not choose it.
            tx = tx.model_copy(update={"edited": False, "source_type": source})
            usage = getattr(self.model, "last_usage", None)
            if usage:
                self.guard.record_usage(*usage)
        except Exception:
            return [_text("I couldn't read that one. Could you send a clearer photo, or type the amount and date?")]
        pid = self.store.add_pending(ev.user_ref, tx, ev.event_id)
        return [_confirm_card(pid, tx, heard)]

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
                new_amount = Decimal(value.replace(",", ""))
                tx = tx.model_copy(update={"amount": new_amount, "edited": tx.edited or new_amount != tx.amount})
            elif field == "date":
                new = Transaction.model_validate({**tx.model_dump(), "date": value})
                tx = new.model_copy(update={"edited": tx.edited or new.date != tx.date})
            else:
                tx = tx.model_copy(update={"counterparty": value})
        except (InvalidOperation, ValueError):
            return [_text(f"I couldn't use '{value}' as the {field}. Try again.")]
        self.store.update_pending(ev.user_ref, pid, tx, "awaiting_confirm")
        return [_confirm_card(pid, tx)]

    def _seed_demo(self, ev: InboundEvent) -> str:
        if self.store.entries(ev.user_ref):
            return "Your session already has entries, so I didn't add the sample. Type 'summary'."
        for i, tx in enumerate(DEMO_TRANSACTIONS):
            pid = self.store.add_pending(ev.user_ref, tx, f"demo:{ev.event_id}:{i}")
            self.store.confirm(ev.user_ref, pid)
        return f"Loaded a sample ledger: {DEMO_LABEL}. Type 'summary' to see it."

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


def _confirm_card(pid: str, tx: Transaction, heard: str | None = None) -> OutboundMessage:
    issues = check_transaction(tx)
    tier = evidence_tier(tx.source_type, tx.txn_id, tx.edited)
    arrow = "Money in" if tx.direction.value == "in" else "Money out"
    lines = ([f"I heard: \u201c{heard[:300]}\u201d"] if heard else []) + [f"{arrow}: {tx.currency} {tx.amount}",
             f"Date: {tx.date or 'not found'}",
             f"Who: {tx.counterparty or 'not found'}",
             f"Evidence: {tier.value}" + (f" (ref {tx.txn_id})" if tx.txn_id else "")
             + (" - you edited this, so it counts as self-reported" if tx.edited else "")]
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
