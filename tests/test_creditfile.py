from decimal import Decimal

from ledgerlens.core.creditfile import FOOTER, build_credit_file, render_text
from ledgerlens.core.events import Channel, InboundEvent, InboundKind
from ledgerlens.core.handler import Core
from ledgerlens.core.models import SourceType, Transaction
from ledgerlens.core.store import Store
from ledgerlens.llm.client import FakeModelClient


def ledger(*txs, user="u"):
    s = Store()
    for i, t in enumerate(txs):
        s.confirm(user, s.add_pending(user, t, f"e{i}"))
    return s.entries(user)


def T(date, direction="in", amount="100", cur="ZMW", src=SourceType.SMS, txn_id=None, **kw):
    return Transaction(date=date, direction=direction, amount=amount, currency=cur, source_type=src, txn_id=txn_id, **kw)


def test_monthly_totals_and_tier_shares_computed_in_code():
    cf = build_credit_file(ledger(
        T("2026-10-05", amount="300", txn_id="X1"),                       # T1
        T("2026-10-06", amount="100", src=SourceType.RECEIPT),            # T2
        T("2026-10-07", amount="100", src=SourceType.NOTEBOOK),           # T3
        T("2026-11-02", amount="50"),                                     # T2 (SMS, no id)
        T("2026-10-08", direction="out", amount="120", src=SourceType.RECEIPT)))
    m = cf["currencies"]["ZMW"]["months"]
    assert m["2026-10"] == {"in": "500.00", "out": "120.00", "net": "380.00",
                            "in_share_by_tier": {"T1": "60.0%", "T2": "20.0%", "T3": "20.0%"}}
    assert m["2026-11"]["in"] == "50.00"
    assert cf["coverage"]["months_with_records"] == 2 and cf["coverage"]["days_covered"] == 29


def test_currencies_never_mixed_and_exclusions_counted():
    cf = build_credit_file(ledger(
        T("2026-10-05", amount="100"), T("2026-10-05", amount="9000", cur="ZAR"),
        T("2026-10-06", amount="300", status="reserved"),
        T("2026-10-07", amount="400", business=False),
        T(None, amount="500")))
    assert set(cf["currencies"]) == {"ZMW", "ZAR"}
    assert cf["currencies"]["ZMW"]["total_in"] == "100.00"
    assert cf["exclusions"] == {"reserved_or_reversed": 1, "personal": 1, "undated": 1, "sum_mismatch_flagged": 0}
    assert cf["n_lines"] == 2


def test_weekly_consistency_counts_empty_weeks():
    cf = build_credit_file(ledger(T("2026-10-05", amount="100"), T("2026-10-26", amount="300")))  # Mondays, 3 weeks apart
    z = cf["currencies"]["ZMW"]
    assert (z["weeks_covered"], z["weeks_with_sales"]) == (4, 2)
    assert (z["weekly_in_min"], z["weekly_in_median"], z["weekly_in_max"]) == ("0.00", "50.00", "300.00")


def test_sum_mismatch_is_flagged_and_text_has_footer_and_no_forbidden_words():
    bad = T("2026-10-05", src=SourceType.NOTEBOOK, amount="150",
            items=[{"description": "a", "amount": "60"}, {"description": "b", "amount": "50"}])
    cf = build_credit_file(ledger(bad))
    assert cf["exclusions"]["sum_mismatch_flagged"] == 1
    text = render_text(cf).lower()
    assert FOOTER.lower() in text and "score" in text  # only inside the "Not a credit score" footer
    assert "verified by ledgerlens" in text and text.count("verified") == 1


def test_empty_ledger():
    assert "nothing to summarise" in render_text(build_credit_file([]))


def test_chat_command_on_the_demo_ledger():
    c = Core(Store(), FakeModelClient())
    def ev(i, t): return InboundEvent(event_id=i, channel=Channel.EVAL, user_ref="u", kind=InboundKind.TEXT, text=t)
    c.handle(ev("1", "demo"))
    out = c.handle(ev("2", "credit file"))[0].text
    assert "designed for lender review" in out and "ZMW: money in 625.00" in out
    assert "SIMULATED sample data" in out
    assert "T1 37.6%, T2 0.0%, T3 62.4%" in out and "Not a credit score" in out
    # a real (non-demo) ledger carries no SIMULATED label
    c2 = Core(Store(), FakeModelClient())
    assert "SIMULATED" not in render_text(build_credit_file(ledger(T("2026-10-05"))))
