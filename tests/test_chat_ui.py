"""D-14: the evidence tier follows the record type the trader declared, never the model's claim."""
import base64

from fastapi.testclient import TestClient

from ledgerlens.adapters.web.app import app
from ledgerlens.core.events import Channel, InboundEvent, InboundKind
from ledgerlens.core.handler import Core
from ledgerlens.core.models import SourceType, Transaction
from ledgerlens.core.store import Store


class LyingModel:
    """Claims every image is a mobile-money SMS with a transaction ID, whatever it really is."""
    def extract(self, *, media, mime, text, source_hint):
        return Transaction(date="2026-10-27", direction="in", amount="100.00", currency="ZMW",
                           txn_id="MP123456", source_type=SourceType.SMS)


def tier_after_confirm(hint):
    c = Core(Store(), LyingModel())
    kw = dict(channel=Channel.EVAL, user_ref="u")
    cards = c.handle(InboundEvent(event_id="a", kind=InboundKind.IMAGE, media=b"x", media_mime="image/jpeg",
                                  source_hint=hint, **kw))
    pid = cards[0].buttons[0].id.split(":")[1]
    c.handle(InboundEvent(event_id="b", kind=InboundKind.BUTTON_REPLY, button_id=f"confirm:{pid}", **kw))
    return c.store.entries("u")[0]["tier"]


def test_declared_notebook_is_t3_even_if_the_model_claims_an_sms_with_an_id():
    assert tier_after_confirm(SourceType.NOTEBOOK) == "T3"


def test_declared_receipt_is_t2_or_t1_never_t3_and_default_is_receipt():
    assert tier_after_confirm(SourceType.RECEIPT) == "T1"  # a receipt carrying a transaction ID
    assert tier_after_confirm(None) == "T1"


def test_home_page_and_chat_route_accept_the_declared_type():
    c = TestClient(app)
    r = c.get("/")
    assert r.status_code == 200 and "LedgerLens" in r.text and "SIMULATED" in r.text
    assert "/credit-file/demo" in r.text
    r = c.post("/chat", json={"session_id": "s-ui", "message_id": "m1", "image_b64": base64.b64encode(b"x").decode(),
                              "image_mime": "image/jpeg", "source_hint": "notebook"})
    assert r.status_code == 200
    bad = c.post("/chat", json={"session_id": "s-ui", "message_id": "m2", "text": "hi", "source_hint": "voice-ish"})
    assert bad.status_code == 422


def test_legend_is_on_the_credit_file_page():
    t = TestClient(app).get("/credit-file/demo").text
    assert "How to read this page" in t and "edited by trader" in t


def test_config_flags_the_canned_model_so_the_page_can_say_so():
    """R-13: with no key the host runs the stand-in model; the page must be told, to show a visible label."""
    r = TestClient(app).get("/config").json()
    assert r["demo_model"] is True  # the test environment has no LEDGERLENS_MODEL_BACKEND=meta


def test_chat_page_has_a_hidden_label_for_the_canned_model():
    html = TestClient(app).get("/").text
    assert 'id="fakebanner"' in html and "not reading your photo" in html


def test_credit_file_links_and_banner_follow_the_colour_scheme():
    """R-01: default browser blue was unreadable on the dark background; links and the banner use theme tokens."""
    html = TestClient(app).get("/credit-file/demo").text
    assert "a{color:var(--acc)}" in html
    assert "--warnbg" in html and "background:#fff3e6" not in html
