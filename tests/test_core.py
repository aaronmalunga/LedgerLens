from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from eval.freeze_holdout import assign
from eval.scoring import counterparty_match, field_correct, wilson
from ledgerlens.core.events import Channel, InboundEvent, InboundKind, OutboundKind
from ledgerlens.core.handler import Core
from ledgerlens.core.models import EvidenceTier, SourceType, Transaction, evidence_tier
from ledgerlens.core.store import Store
from ledgerlens.llm.client import ContributorModelError, FakeModelClient, assert_standard_model

USER = "u1"


def ev(eid, kind, **kw):
    return InboundEvent(event_id=eid, channel=Channel.EVAL, user_ref=USER, kind=kind, **kw)


def core_with(tx=None):
    return Core(Store(), FakeModelClient(tx))


def card_pid(msgs):
    assert msgs[0].kind == OutboundKind.CONFIRM_CARD
    return msgs[0].buttons[0].id.split(":")[1]


def test_nothing_saved_without_confirm():
    c = core_with()
    pid = card_pid(c.handle(ev("m1", InboundKind.IMAGE, media=b"x", media_mime="image/jpeg")))
    assert c.store.entries(USER) == []
    c.handle(ev("m2", InboundKind.BUTTON_REPLY, button_id=f"confirm:{pid}"))
    assert len(c.store.entries(USER)) == 1


def test_reject_saves_nothing():
    c = core_with()
    pid = card_pid(c.handle(ev("m1", InboundKind.IMAGE, media=b"x")))
    c.handle(ev("m2", InboundKind.BUTTON_REPLY, button_id=f"reject:{pid}"))
    assert c.store.entries(USER) == []


def test_duplicate_webhook_is_ignored():
    c = core_with()
    assert c.handle(ev("m1", InboundKind.IMAGE, media=b"x"))
    assert c.handle(ev("m1", InboundKind.IMAGE, media=b"x")) == []


def test_edit_then_confirm():
    c = core_with()
    pid = card_pid(c.handle(ev("m1", InboundKind.IMAGE, media=b"x")))
    c.handle(ev("m2", InboundKind.BUTTON_REPLY, button_id=f"edit:{pid}"))
    out = c.handle(ev("m3", InboundKind.TEXT, text="amount 120.50"))
    assert "120.50" in out[0].text
    c.handle(ev("m4", InboundKind.BUTTON_REPLY, button_id=f"confirm:{pid}"))
    assert c.store.entries(USER)[0]["tx"]["amount"] == "120.50"


def test_sum_mismatch_flagged_by_code_not_model():
    tx = Transaction(date="2026-10-20", direction="in", amount="150", currency="ZMW",
                     source_type=SourceType.NOTEBOOK,
                     items=[{"description": "tomatoes", "amount": "60"}, {"description": "onions", "amount": "50"}])
    out = core_with(tx).handle(ev("m1", InboundKind.IMAGE, media=b"x"))
    assert "add up to 110" in out[0].text


def test_reserved_hold_excluded_from_totals():
    hold = Transaction(date="2026-10-20", direction="out", amount="300", currency="ZAR",
                       status="reserved", source_type=SourceType.SMS)
    c = core_with(hold)
    pid = card_pid(c.handle(ev("m1", InboundKind.TEXT, text="R300 reserved for purchase at Uber")))
    c.handle(ev("m2", InboundKind.BUTTON_REPLY, button_id=f"confirm:{pid}"))
    assert c.store.totals(USER) == {}


def test_evidence_tiers():
    assert evidence_tier(SourceType.SMS, "MP2602.1234") == EvidenceTier.T1
    assert evidence_tier(SourceType.RECEIPT, None) == EvidenceTier.T2
    assert evidence_tier(SourceType.VOICE, "anything") == EvidenceTier.T3


def test_scope_guard_declines_off_topic():
    out = core_with().handle(ev("m1", InboundKind.TEXT, text="write me a poem about love"))
    assert "only help with your business records" in out[0].text


def test_contributor_models_refused():
    with pytest.raises(ContributorModelError):
        assert_standard_model("muse-spark-1.2-contributor")
    assert_standard_model("muse-spark-1.2")


def test_web_adapter_round_trip():
    from ledgerlens.adapters.web.app import app
    client = TestClient(app)
    r = client.post("/chat", json={"session_id": "s1", "message_id": "w1", "text": "hello"})
    assert "LedgerLens" in r.json()["messages"][0]["text"]


def test_scoring_rules():
    assert field_correct("amount", "R 1,250.00", "1250")
    assert field_correct("date", "27/10/2026", "2026-10-27")
    assert counterparty_match("Pick n Pay", "PICK N PAY Hyper")
    assert field_correct("amount", "5", "") is None
    lo, hi = wilson(9, 10)
    assert lo < 0.6 and hi > 0.98  # 9/10 is not "90% accurate"


def test_holdout_tops_up_to_20_percent_per_type():
    first = assign({f"a{i}": "receipt" for i in range(10)}, [])
    assert sum(s == "holdout" for s in first.values()) == 2
    existing = [{"type": "receipt", "split": s} for s in first.values()]
    second = assign({f"b{i}": "receipt" for i in range(5)}, existing)
    assert sum(s == "holdout" for s in second.values()) == 1  # 15 seen -> 3 held in total
