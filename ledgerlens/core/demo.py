"""Seeded demo ledger (D-10): SIMULATED records, so judges can explore without uploading anything
and without spending model credits. Prices calibrated loosely to JCTR Lusaka basket (May 2026)."""
from __future__ import annotations

import datetime as dt
import random

from .models import SourceType, Transaction, evidence_tier

DEMO_LABEL = "SIMULATED sample data (not a real trader)"

DEMO_TRANSACTIONS = [
    Transaction(date="2026-10-19", direction="out", amount="480.00", currency="ZMW",
                counterparty="Sample Cash & Carry", source_type=SourceType.RECEIPT, txn_id="SIM-INV-0412",
                items=[{"description": "tomatoes 30kg crate", "amount": "480.00"}]),
    Transaction(date="2026-10-19", direction="in", amount="210.00", currency="ZMW",
                counterparty="cash sales", source_type=SourceType.NOTEBOOK,
                items=[{"description": "tomatoes", "amount": "160.00"}, {"description": "onions", "amount": "50.00"}]),
    Transaction(date="2026-10-20", direction="in", amount="95.00", currency="ZMW",
                counterparty="customer (mobile money)", source_type=SourceType.SMS, txn_id="SIM-MM-77120"),
    Transaction(date="2026-10-20", direction="in", amount="180.00", currency="ZMW",
                counterparty="cash sales", source_type=SourceType.VOICE),
    Transaction(date="2026-10-21", direction="in", amount="140.00", currency="ZMW",
                counterparty="customer (mobile money)", source_type=SourceType.SMS, txn_id="SIM-MM-77391"),
]


def demo_history(seed: int = 2026) -> list[dict]:
    """16 weeks of SIMULATED history (Mon 6 Jul to Sun 25 Oct 2026), deterministic for a given seed.

    F12: the cash-flow and credit-file views need months of records, and we have no real trader's. Every row
    carries source_event_id 'demo:...' so the credit file labels it SIMULATED. It deliberately contains the
    awkward cases the file must handle: a week with no records, a hold, a reversal, personal spending, an
    undated line, a line whose items do not add up, and a trader-edited line (demoted to T3, D-13)."""
    rng = random.Random(seed)
    start = dt.date(2026, 7, 6)
    rows: list[dict] = []
    mm = inv = 0

    def add(day, direction, amount, source, cp, txn_id=None, status="completed", business=True,
            edited=False, items=None, dated=True):
        tx = Transaction(date=day if dated else None, direction=direction, amount=str(amount), currency="ZMW",
                         counterparty=cp, source_type=source, txn_id=txn_id, status=status, business=business,
                         edited=edited, items=items or [])
        n = len(rows) + 1
        rows.append({"entry_id": f"d{n:03d}", "tx": tx.model_dump(mode="json"),
                     "tier": evidence_tier(source, txn_id, edited).value, "source_event_id": f"demo:hist:{n:03d}"})

    for w in range(16):
        if w == 9:
            continue  # a week with no records: the file shows it honestly
        monday = start + dt.timedelta(days=7 * w)
        for d in range(6):
            day = monday + dt.timedelta(days=d)
            if rng.random() < 0.12:
                continue
            src = SourceType.VOICE if rng.random() < 0.25 else SourceType.NOTEBOOK
            add(day, "in", rng.randrange(80, 260, 5), src, "cash sales")
        for _ in range(rng.randint(2, 3)):
            day = monday + dt.timedelta(days=rng.randrange(0, 6))
            mm += 1
            with_id = rng.random() > 0.33
            add(day, "in", rng.randrange(40, 200, 5), SourceType.SMS, "customer (mobile money)",
                txn_id=f"SIM-MM-{mm:05d}" if with_id else None)
        inv += 1
        add(monday + dt.timedelta(days=rng.randrange(0, 3)), "out", rng.randrange(300, 700, 10),
            SourceType.RECEIPT, "Sample Wholesale (SIM)", txn_id=f"SIM-INV-{inv:04d}" if inv % 2 else None)
        add(monday + dt.timedelta(days=rng.randrange(0, 6)), "out", rng.randrange(20, 60, 5),
            SourceType.NOTEBOOK, "transport")
        # the awkward cases
        if w == 2:
            add(monday + dt.timedelta(days=3), "out", 250, SourceType.RECEIPT, "Sample Wholesale (SIM)",
                status="reserved")
        if w == 6:
            add(monday + dt.timedelta(days=2), "out", 180, SourceType.RECEIPT, "Sample Wholesale (SIM)",
                txn_id="SIM-INV-9001", status="reversed")
        if w in (4, 10):
            add(monday + dt.timedelta(days=4), "out", rng.randrange(60, 150, 10), SourceType.RECEIPT,
                "Sample Supermarket (SIM)", business=False)
        if w == 5:
            add(monday + dt.timedelta(days=1), "in", 150, SourceType.NOTEBOOK, "cash sales",
                items=[{"description": "bread", "amount": "60"}, {"description": "eggs", "amount": "70"}])
        if w == 7:
            add(None, "in", 90, SourceType.NOTEBOOK, "cash sales", dated=False)
        if w == 11:
            add(monday + dt.timedelta(days=2), "in", 185, SourceType.SMS, "customer (mobile money)",
                txn_id="SIM-MM-EDIT", edited=True)
    return rows
