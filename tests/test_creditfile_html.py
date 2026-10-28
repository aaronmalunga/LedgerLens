"""Credit-file web page: same numbers as the dict, escaped output, honest wording, deterministic."""
import re

from fastapi.testclient import TestClient

from ledgerlens.adapters.web.app import app
from ledgerlens.core.creditfile import FOOTER, build_credit_file
from ledgerlens.core.creditfile_html import render_html
from ledgerlens.core.demo import DEMO_LABEL, demo_history


def page():
    return render_html(build_credit_file(demo_history()), DEMO_LABEL)


def test_demo_history_is_deterministic_and_contains_the_awkward_cases():
    a, b = demo_history(), demo_history()
    assert a == b and all(r["source_event_id"].startswith("demo:") for r in a)
    cf = build_credit_file(a)
    x = cf["exclusions"]
    assert x["reserved_or_reversed"] >= 2 and x["personal"] >= 2 and x["undated"] == 1 and x["sum_mismatch_flagged"] == 1
    cur = cf["currencies"]["ZMW"]
    assert any(float(w["in"]) == 0 for w in cur["weekly_in"])          # a week with no records
    assert any(l["edited"] and l["tier"] == "T3" for l in cf["lines"])  # an edited T1 line is T3 (D-13)
    shares = [float(cur["in_share_by_tier"][t].rstrip("%")) for t in ("T1", "T2", "T3")]
    assert abs(sum(shares) - 100) < 0.2


def test_page_is_labelled_simulated_has_footer_and_every_section():
    h = page()
    assert DEMO_LABEL in h and FOOTER in h
    for n in ("1. Coverage", "2. Money in and out", "3. How well", "4. Consistency", "5. Every line", "6. Left out"):
        assert n in h
    assert "What this file does not provide" in h


def test_no_score_and_verified_only_in_the_footer_phrase():
    h = page()
    text = re.sub(r"<style>.*?</style>|<[^>]+>", " ", h, flags=re.S)
    assert text.lower().count("verified") == text.count("Not verified by LedgerLens") == 1
    assert not re.search(r"\bscore\b(?! *\.)", text.replace("Not a credit score.", "").replace("no score", ""), re.I)


def test_page_numbers_come_from_the_dict_not_the_renderer():
    cf = build_credit_file(demo_history())
    h = render_html(cf, DEMO_LABEL)
    assert f'{cf["coverage"]["days_covered"]} days' in h and f'{cf["n_lines"]}</b>' in h
    first_month = next(iter(cf["currencies"]["ZMW"]["months"].values()))
    assert f'K{int(float(first_month["in"])):,}' in h


def test_all_strings_are_escaped():
    cf = build_credit_file(demo_history())
    cf["lines"][0]["counterparty"] = "<script>alert(1)</script>"
    cf["lines"][0]["txn_id"] = '"><img src=x>'
    h = render_html(cf, "<b>label</b>")
    assert "<script>alert" not in h and "<img src=x>" not in h and "<b>label</b>" not in h


def test_empty_ledger_renders_a_plain_message():
    h = render_html(build_credit_file([]))
    assert "nothing to summarise" in h and FOOTER in h


def test_deterministic_for_the_same_ledger():
    assert page() == page()


def test_routes_serve_the_demo_and_a_session_file():
    c = TestClient(app)
    r = c.get("/credit-file/demo")
    assert r.status_code == 200 and "SIMULATED" in r.text and r.headers["content-type"].startswith("text/html")
    r2 = c.get("/credit-file", params={"session_id": "nobody"})
    assert r2.status_code == 200 and "nothing to summarise" in r2.text
