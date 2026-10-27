"""Seeded demo ledger (D-10): SIMULATED records, so judges can explore without uploading anything
and without spending model credits. Prices calibrated loosely to JCTR Lusaka basket (May 2026)."""
from __future__ import annotations

from .models import SourceType, Transaction

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
