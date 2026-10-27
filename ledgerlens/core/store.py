"""SQLite store: processed events (idempotency), pending proposals, confirmed ledger."""
from __future__ import annotations

import json
import sqlite3
import uuid
from decimal import Decimal
from typing import Optional

from .models import Direction, EvidenceTier, Status, Transaction, evidence_tier

SCHEMA = """
CREATE TABLE IF NOT EXISTS processed_events (event_id TEXT PRIMARY KEY);
CREATE TABLE IF NOT EXISTS pending (
    pending_id TEXT PRIMARY KEY, user_ref TEXT NOT NULL, tx_json TEXT NOT NULL,
    state TEXT NOT NULL DEFAULT 'awaiting_confirm', source_event_id TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS ledger (
    entry_id TEXT PRIMARY KEY, user_ref TEXT NOT NULL, tx_json TEXT NOT NULL,
    direction TEXT NOT NULL, amount TEXT NOT NULL, currency TEXT NOT NULL,
    status TEXT NOT NULL, tier TEXT NOT NULL, source_event_id TEXT NOT NULL
);
"""


class Store:
    def __init__(self, path: str = ":memory:") -> None:
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.db.executescript(SCHEMA)

    # idempotency: WhatsApp can deliver the same webhook more than once
    def mark_processed(self, event_id: str) -> bool:
        """Returns False if this event was already handled."""
        try:
            with self.db:
                self.db.execute("INSERT INTO processed_events VALUES (?)", (event_id,))
            return True
        except sqlite3.IntegrityError:
            return False

    def add_pending(self, user_ref: str, tx: Transaction, source_event_id: str) -> str:
        pid = uuid.uuid4().hex[:8]
        with self.db:
            self.db.execute(
                "INSERT INTO pending (pending_id, user_ref, tx_json, source_event_id) VALUES (?,?,?,?)",
                (pid, user_ref, tx.model_dump_json(), source_event_id),
            )
        return pid

    def get_pending(self, user_ref: str, pending_id: str) -> Optional[tuple[Transaction, str, str]]:
        row = self.db.execute(
            "SELECT tx_json, state, source_event_id FROM pending WHERE user_ref=? AND pending_id=?",
            (user_ref, pending_id),
        ).fetchone()
        if not row:
            return None
        return Transaction.model_validate_json(row[0]), row[1], row[2]

    def latest_awaiting_edit(self, user_ref: str) -> Optional[str]:
        row = self.db.execute(
            "SELECT pending_id FROM pending WHERE user_ref=? AND state='awaiting_edit' ORDER BY rowid DESC LIMIT 1",
            (user_ref,),
        ).fetchone()
        return row[0] if row else None

    def update_pending(self, user_ref: str, pending_id: str, tx: Transaction, state: str) -> None:
        with self.db:
            self.db.execute(
                "UPDATE pending SET tx_json=?, state=? WHERE user_ref=? AND pending_id=?",
                (tx.model_dump_json(), state, user_ref, pending_id),
            )

    def drop_pending(self, user_ref: str, pending_id: str) -> None:
        with self.db:
            self.db.execute("DELETE FROM pending WHERE user_ref=? AND pending_id=?", (user_ref, pending_id))

    def confirm(self, user_ref: str, pending_id: str) -> Optional[str]:
        """The only path into the ledger: an explicit trader confirmation."""
        got = self.get_pending(user_ref, pending_id)
        if not got:
            return None
        tx, _, source_event_id = got
        entry_id = uuid.uuid4().hex[:8]
        tier = evidence_tier(tx.source_type, tx.txn_id, tx.edited)
        with self.db:
            self.db.execute(
                "INSERT INTO ledger VALUES (?,?,?,?,?,?,?,?,?)",
                (entry_id, user_ref, tx.model_dump_json(), tx.direction.value, str(tx.amount),
                 tx.currency, tx.status.value, tier.value, source_event_id),
            )
            self.db.execute("DELETE FROM pending WHERE user_ref=? AND pending_id=?", (user_ref, pending_id))
        return entry_id

    def totals(self, user_ref: str) -> dict:
        """Deterministic summary (D-08). Reserved holds are excluded from totals."""
        rows = self.db.execute(
            "SELECT direction, amount, currency, status, tier FROM ledger WHERE user_ref=?", (user_ref,)
        ).fetchall()
        out: dict = {}
        for direction, amount, currency, status, tier in rows:
            if status != Status.COMPLETED.value:
                continue
            c = out.setdefault(currency, {"in": Decimal("0"), "out": Decimal("0"),
                                          "in_by_tier": {t.value: Decimal("0") for t in EvidenceTier}})
            amt = Decimal(amount)
            c[direction] += amt
            if direction == Direction.IN.value:
                c["in_by_tier"][tier] += amt
        return out

    def entries(self, user_ref: str) -> list[dict]:
        rows = self.db.execute(
            "SELECT entry_id, tx_json, tier, source_event_id FROM ledger WHERE user_ref=? ORDER BY rowid",
            (user_ref,),
        ).fetchall()
        return [{"entry_id": r[0], "tx": json.loads(r[1]), "tier": r[2], "source_event_id": r[3]} for r in rows]
