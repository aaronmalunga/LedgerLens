"""R-02 (29 Oct finding): minting session IDs must not bypass the rate limit; a global cap bounds the worst case."""
from types import SimpleNamespace

from ledgerlens.adapters.web.app import client_ip
from ledgerlens.core.guard import REFUSALS, Guard, GuardConfig


def req(xff=None, host="10.0.0.9"):
    headers = {"x-forwarded-for": xff} if xff else {}
    return SimpleNamespace(headers=headers, client=SimpleNamespace(host=host))


def test_new_session_ids_from_one_address_are_still_limited():
    t = [0.0]
    g = Guard(GuardConfig(rate_limit=100, ip_rate_limit=3, rate_window_s=60), clock=lambda: t[0])
    results = [g.check_message(f"user{i}", None, "1.2.3.4") for i in range(5)]  # a script minting IDs
    assert results == [None, None, None, "rate_limited", "rate_limited"]


def test_other_addresses_are_not_affected():
    g = Guard(GuardConfig(rate_limit=100, ip_rate_limit=1, rate_window_s=60), clock=lambda: 0.0)
    assert g.check_message("a", None, "1.1.1.1") is None
    assert g.check_message("b", None, "2.2.2.2") is None
    assert g.check_message("c", None, "1.1.1.1") == "rate_limited"


def test_ip_window_slides():
    t = [0.0]
    g = Guard(GuardConfig(rate_limit=100, ip_rate_limit=1, rate_window_s=60), clock=lambda: t[0])
    assert g.check_message("a", None, "1.1.1.1") is None
    assert g.check_message("b", None, "1.1.1.1") == "rate_limited"
    t[0] = 61
    assert g.check_message("c", None, "1.1.1.1") is None


def test_no_address_falls_back_to_per_user_limit_only():
    g = Guard(GuardConfig(rate_limit=1, ip_rate_limit=1, rate_window_s=60), clock=lambda: 0.0)
    assert g.check_message("a", None, None) is None
    assert g.check_message("a", None, None) == "rate_limited"


def test_global_hourly_cap_bounds_everyone_together():
    t = [0.0]
    g = Guard(GuardConfig(global_hourly_cap=3), clock=lambda: t[0])
    assert [g.check_budget() for _ in range(4)] == [None, None, None, "busy"]
    assert "busy" in REFUSALS
    t[0] = 3601
    assert g.check_budget() is None  # the hour has passed


def test_daily_budget_still_wins_first():
    g = Guard(GuardConfig(daily_call_cap=0, global_hourly_cap=99), clock=lambda: 0.0)
    assert g.check_budget() == "budget"


def test_minted_ids_do_not_grow_memory_forever():
    t = [0.0]
    g = Guard(GuardConfig(rate_limit=5, ip_rate_limit=10**9, rate_window_s=10), clock=lambda: t[0])
    for i in range(6000):
        g.check_message(f"u{i}", None, None)
    t[0] = 1000
    g.check_message("late", None, None)
    assert len(g._hits) < 6000


def test_client_ip_ignores_forwarded_header_by_default(monkeypatch):
    monkeypatch.delenv("LEDGERLENS_PROXY_HOPS", raising=False)
    assert client_ip(req(xff="6.6.6.6")) == "10.0.0.9"


def test_client_ip_takes_the_entry_the_proxy_added_not_the_forged_one(monkeypatch):
    monkeypatch.setenv("LEDGERLENS_PROXY_HOPS", "1")
    assert client_ip(req(xff="6.6.6.6, 203.0.113.7")) == "203.0.113.7"  # attacker forged the left entry


def test_client_ip_falls_back_when_header_missing(monkeypatch):
    monkeypatch.setenv("LEDGERLENS_PROXY_HOPS", "1")
    assert client_ip(req()) == "10.0.0.9"


def test_web_endpoint_blocks_minted_sessions_from_one_address(monkeypatch):
    from fastapi.testclient import TestClient
    from ledgerlens.adapters.web import app as webapp
    monkeypatch.setattr(webapp.core, "guard", Guard(GuardConfig(rate_limit=100, ip_rate_limit=3, rate_window_s=600)))
    c = TestClient(webapp.app)
    replies = [c.post("/chat", json={"session_id": f"s{i}", "text": "hi"}).json()["messages"][0]["text"] for i in range(5)]
    assert replies[3] == REFUSALS["rate_limited"] and replies[4] == REFUSALS["rate_limited"]
    assert replies[0] != REFUSALS["rate_limited"]
