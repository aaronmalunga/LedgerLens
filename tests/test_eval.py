"""Eval harness tests: the rules that protect the evidence (frozen hold-out, honest denominators, consent)."""
import csv
import hashlib
import json
import sys

import pytest
from pydantic import ValidationError

from eval import freeze_holdout as fh
from eval import run_eval
from eval.report import percentile
from eval.scoring import wilson
from ledgerlens.core.models import SourceType, Transaction

COLUMNS = ["file", "source", "type", "date", "item", "qty", "amount", "currency", "in_out", "counterparty",
           "status", "has_txn_id", "sum_correct", "personal_proxy", "photo_condition", "consent", "holdout", "txn_id"]


def tx(amount="100.00", date="2026-10-20", direction="out", currency="ZAR", cp="Shop", status="completed"):
    return Transaction(date=date, direction=direction, amount=amount, currency=currency, counterparty=cp,
                       status=status, source_type=SourceType.RECEIPT)


class Scripted:
    """Returns a prepared Transaction per image bytes; remembers every call so tests can prove what was sent."""
    vision_model = "test-vision"
    text_model = "test-text"

    def __init__(self, by_bytes=None, exc=None):
        self.by_bytes, self.exc, self.seen = by_bytes or {}, exc, []

    def extract(self, *, media, mime, text, source_hint):
        self.seen.append(media)
        if self.exc:
            raise self.exc
        return self.by_bytes[media]


def gold_row(file, **kw):
    base = dict(file=file, source="SIMULATED", type="receipt", date="2026-10-20", amount="100.00", currency="ZAR",
                in_out="out", counterparty="Shop", status="completed")
    base.update(kw)
    return base


def setup(tmp_path, rows, contents, splits, bom=False):
    """contents: {file: bytes}; splits: {file: 'dev'|'holdout'|None (None = not in the manifest)}."""
    images = tmp_path / "images"
    images.mkdir()
    for fn, b in contents.items():
        (images / fn).write_bytes(b)
    labels = tmp_path / "labels.csv"
    with labels.open("w", newline="", encoding="utf-8-sig" if bom else "utf-8") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS)
        w.writeheader()
        w.writerows({c: r.get(c, "") for c in COLUMNS} for r in rows)
    manifest = tmp_path / "manifest.jsonl"
    with manifest.open("w") as m:
        for fn, s in splits.items():
            if s:
                m.write(json.dumps({"sha256": hashlib.sha256(contents[fn]).hexdigest(), "type": "receipt",
                                    "split": s, "batch": "b1", "frozen_at": "x"}) + "\n")
    return images, labels, manifest


def go(tmp_path, images, labels, manifest, client, *extra, monkeypatch=None):
    if monkeypatch:
        monkeypatch.setattr(run_eval, "HOLDOUT_LOG", tmp_path / "holdout_runs.jsonl")
    a = run_eval.parse_args(["--labels", str(labels), "--images", str(images), "--manifest", str(manifest),
                             "--out-dir", str(tmp_path / "res"), *extra])
    return run_eval.run(a, client_factory=lambda: client)


def test_dev_run_never_sends_holdout_files_to_the_model(tmp_path, monkeypatch):
    c = {"a.jpg": b"A", "b.jpg": b"B", "h.jpg": b"H"}
    rows = [gold_row(f) for f in c]
    images, labels, manifest = setup(tmp_path, rows, c, {"a.jpg": "dev", "b.jpg": "dev", "h.jpg": "holdout"})
    client = Scripted({b"A": tx(), b"B": tx(), b"H": tx()})
    md, payload = go(tmp_path, images, labels, manifest, client, monkeypatch=monkeypatch)
    assert b"H" not in client.seen and len(client.seen) == 2
    assert payload["skipped"]["in other split"] == 1
    assert "Evidence label:** MEASURED on the dev split" in md


def test_accuracy_counts_and_wilson_interval_by_source(tmp_path, monkeypatch):
    c = {"a.jpg": b"A", "b.jpg": b"B", "c.jpg": b"C", "p.jpg": b"P"}
    rows = [gold_row("a.jpg"), gold_row("b.jpg"), gold_row("c.jpg"),
            gold_row("p.jpg", source="real", personal_proxy="Y", consent="Y")]
    images, labels, manifest = setup(tmp_path, rows, c, {k: "dev" for k in c})
    client = Scripted({b"A": tx(), b"B": tx(), b"C": tx(amount="999.00"), b"P": tx()})
    md, payload = go(tmp_path, images, labels, manifest, client, "--allow-real-data", monkeypatch=monkeypatch)
    lo, hi = wilson(2, 3)
    assert f"| simulated | record_correct | 2 / 3 | 66.7% | [{lo * 100:.1f}%, {hi * 100:.1f}%] |" in md
    assert "| simulated | amount | 2 / 3 |" in md and "| simulated | currency | 3 / 3 |" in md
    assert "| personal_proxy | record_correct | 1 / 1 |" in md  # separate row: sources are never pooled
    assert "real_trader" not in md


def test_failures_stay_in_the_denominator(tmp_path, monkeypatch):
    c = {"a.jpg": b"A", "b.jpg": b"B"}
    images, labels, manifest = setup(tmp_path, [gold_row(f) for f in c], c, {k: "dev" for k in c})
    err = ValidationError.from_exception_data("Transaction", [])
    md, payload = go(tmp_path, images, labels, manifest, Scripted(exc=err), monkeypatch=monkeypatch)
    assert "| simulated | record_correct | 0 / 2 |" in md
    assert payload["ops"]["outcomes"] == {"schema_invalid": 2}
    assert payload["ops"]["error_rate"] == 1.0


def test_oversized_photo_shows_up_as_refused_not_hidden(tmp_path, monkeypatch):
    c = {"big.jpg": b"x" * (5 * 1024 * 1024 + 1)}
    images, labels, manifest = setup(tmp_path, [gold_row("big.jpg")], c, {"big.jpg": "dev"})
    client = Scripted()
    _, payload = go(tmp_path, images, labels, manifest, client, monkeypatch=monkeypatch)
    assert payload["ops"]["outcomes"] == {"refused": 1} and client.seen == []


def test_unfrozen_file_is_refused_before_any_model_call(tmp_path, monkeypatch):
    c = {"a.jpg": b"A", "new.jpg": b"N"}
    images, labels, manifest = setup(tmp_path, [gold_row(f) for f in c], c, {"a.jpg": "dev", "new.jpg": None})
    client = Scripted({b"A": tx()})
    with pytest.raises(run_eval.HarnessError, match="not in the hold-out manifest"):
        go(tmp_path, images, labels, manifest, client, monkeypatch=monkeypatch)
    assert client.seen == []


def test_csv_holdout_column_must_agree_with_manifest(tmp_path, monkeypatch):
    c = {"a.jpg": b"A"}
    images, labels, manifest = setup(tmp_path, [gold_row("a.jpg", holdout="Y")], c, {"a.jpg": "dev"})
    with pytest.raises(run_eval.HarnessError, match="disagrees with the manifest"):
        go(tmp_path, images, labels, manifest, Scripted({b"A": tx()}), monkeypatch=monkeypatch)


def test_holdout_needs_confirmation_and_is_scored_once(tmp_path, monkeypatch):
    c = {"h.jpg": b"H"}
    images, labels, manifest = setup(tmp_path, [gold_row("h.jpg")], c, {"h.jpg": "holdout"})
    client = Scripted({b"H": tx()})
    with pytest.raises(run_eval.HarnessError, match="--confirm-holdout"):
        go(tmp_path, images, labels, manifest, client, "--split", "holdout", monkeypatch=monkeypatch)
    md, payload = go(tmp_path, images, labels, manifest, client, "--split", "holdout", "--confirm-holdout",
                     monkeypatch=monkeypatch)
    assert "by record type" not in md  # F7: no per-type numbers on a tiny hold-out
    log = [json.loads(x) for x in (tmp_path / "holdout_runs.jsonl").read_text().splitlines()]
    assert len(log) == 1 and log[0]["rerun"] is False and log[0]["n_records"] == 1
    with pytest.raises(run_eval.HarnessError, match="already been scored"):
        go(tmp_path, images, labels, manifest, client, "--split", "holdout", "--confirm-holdout")
    go(tmp_path, images, labels, manifest, client, "--split", "holdout", "--confirm-holdout", "--rerun-holdout")
    assert json.loads((tmp_path / "holdout_runs.jsonl").read_text().splitlines()[-1])["rerun"] is True


def test_holdout_refuses_fake_client_and_limit(tmp_path, monkeypatch):
    from ledgerlens.llm.client import FakeModelClient
    c = {"h.jpg": b"H"}
    images, labels, manifest = setup(tmp_path, [gold_row("h.jpg")], c, {"h.jpg": "holdout"})
    with pytest.raises(run_eval.HarnessError, match="fake client"):
        go(tmp_path, images, labels, manifest, FakeModelClient(), "--split", "holdout", "--confirm-holdout",
           monkeypatch=monkeypatch)
    with pytest.raises(run_eval.HarnessError, match="--limit"):
        go(tmp_path, images, labels, manifest, Scripted(), "--split", "holdout", "--confirm-holdout", "--limit", "1",
           monkeypatch=monkeypatch)


def test_records_without_consent_are_never_sent(tmp_path, monkeypatch):
    c = {"ok.jpg": b"K", "no.jpg": b"N"}
    rows = [gold_row("ok.jpg", source="real", personal_proxy="N", consent="yes, verbal"),
            gold_row("no.jpg", source="real", personal_proxy="N", consent="")]
    images, labels, manifest = setup(tmp_path, rows, c, {k: "dev" for k in c})
    client = Scripted({b"K": tx()})
    _, payload = go(tmp_path, images, labels, manifest, client, "--allow-real-data", monkeypatch=monkeypatch)
    assert client.seen == [b"K"]
    assert payload["skipped"]["no consent recorded (never sent to a model)"] == 1


def test_data_use_gate_withholds_real_records_by_default(tmp_path, monkeypatch):
    c = {"r.jpg": b"R", "s.jpg": b"S"}
    rows = [gold_row("r.jpg", source="real", personal_proxy="Y", consent="Y"), gold_row("s.jpg")]
    images, labels, manifest = setup(tmp_path, rows, c, {k: "dev" for k in c})
    client = Scripted({b"R": tx(), b"S": tx()})
    md, payload = go(tmp_path, images, labels, manifest, client, monkeypatch=monkeypatch)
    assert client.seen == [b"S"]  # the simulated record only
    assert any("data-use gate" in k and v == 1 for k, v in payload["skipped"].items())
    assert "personal_proxy" not in md
    client2 = Scripted({b"R": tx(), b"S": tx()})
    go(tmp_path, images, labels, manifest, client2, "--allow-real-data", monkeypatch=monkeypatch)
    assert sorted(client2.seen) == [b"R", b"S"]


@pytest.mark.parametrize("row, msg", [
    (dict(source="real", personal_proxy=""), "blank personal_proxy"),
    (dict(date="3 Feb"), "cannot be parsed"),
    (dict(amount="R??"), "cannot be parsed"),
    (dict(source="mystery"), "unknown source"),
])
def test_bad_labels_are_refused_not_guessed(tmp_path, monkeypatch, row, msg):
    c = {"a.jpg": b"A"}
    images, labels, manifest = setup(tmp_path, [gold_row("a.jpg", **row)], c, {"a.jpg": "dev"})
    with pytest.raises(run_eval.HarnessError, match=msg):
        go(tmp_path, images, labels, manifest, Scripted({b"A": tx()}), monkeypatch=monkeypatch)


def test_record_row_convention_and_ambiguity(tmp_path):
    header = gold_row("a.jpg", amount="150.00")
    item1 = gold_row("a.jpg", item="tomatoes", amount="60.00")
    item2 = gold_row("a.jpg", item="onions", amount="90.00")
    _, labels, _ = setup(tmp_path, [item1, header, item2], {"a.jpg": b"A"}, {"a.jpg": "dev"})
    (g,) = run_eval.load_gold(labels)
    assert g.fields["amount"] == "150.00"  # the blank-item row is the record total, whatever the row order
    tmp2 = tmp_path / "t2"
    tmp2.mkdir()
    _, labels2, _ = setup(tmp2, [item1, item2], {"a.jpg": b"A"}, {"a.jpg": "dev"})
    with pytest.raises(run_eval.HarnessError, match="exactly one row with a blank `item`"):
        run_eval.load_gold(labels2)
    tmp3 = tmp_path / "t3"
    tmp3.mkdir()
    _, labels3, _ = setup(tmp3, [item1], {"a.jpg": b"A"}, {"a.jpg": "dev"})
    assert len(run_eval.load_gold(labels3)) == 1  # a single row is its own record row


def test_excel_bom_csv_loads(tmp_path):
    _, labels, _ = setup(tmp_path, [gold_row("a.jpg")], {"a.jpg": b"A"}, {"a.jpg": "dev"}, bom=True)
    assert run_eval.load_gold(labels)[0].file == "a.jpg"


def test_freeze_holdout_reads_excel_bom_csv(tmp_path, monkeypatch):
    c = {f"f{i}.jpg": bytes([i]) for i in range(5)}
    images, labels, _ = setup(tmp_path, [gold_row(f) for f in c], c, {}, bom=True)
    monkeypatch.setattr(fh, "MANIFEST", tmp_path / "m.jsonl")
    monkeypatch.setattr(sys, "argv", ["freeze_holdout", "--labels", str(labels), "--images", str(images), "--batch", "b1"])
    fh.main()
    assert len((tmp_path / "m.jsonl").read_text().splitlines()) == 5


def test_baseline_mode_scores_listed_files_with_the_same_scorer(tmp_path, monkeypatch):
    c = {"a.jpg": b"A", "b.jpg": b"B", "c.jpg": b"C"}
    images, labels, manifest = setup(tmp_path, [gold_row(f) for f in c], c, {k: "dev" for k in c})
    base = tmp_path / "baseline.csv"
    base.write_text("file,date,amount,currency,in_out,counterparty,status,txn_id,seconds\n"
                    "a.jpg,2026-10-20,100.00,ZAR,out,Shop,completed,,40\n"
                    "b.jpg,2026-10-20,90.00,ZAR,out,Shop,completed,,60\n", encoding="utf-8")
    md, payload = go(tmp_path, images, labels, manifest, Scripted(), "--predictions", str(base), monkeypatch=monkeypatch)
    assert "| simulated | record_correct | 1 / 2 |" in md
    assert "median | 50s per record, n=2" in md
    assert payload["skipped"]["not in the baseline CSV"] == 1


def test_cost_is_only_reported_from_supplied_prices(tmp_path, monkeypatch):
    c = {"a.jpg": b"A"}
    images, labels, manifest = setup(tmp_path, [gold_row("a.jpg")], c, {"a.jpg": "dev"})

    class WithUsage(Scripted):
        def extract(self, **kw):
            t = super().extract(**kw)
            self.last_usage = (1000, 200)
            return t

    md, _ = go(tmp_path, images, labels, manifest, WithUsage({b"A": tx()}), monkeypatch=monkeypatch)
    assert "not computed" in md
    md2, _ = go(tmp_path, images, labels, manifest, WithUsage({b"A": tx()}), "--price-in", "1", "--price-out", "5",
                monkeypatch=monkeypatch)
    assert "$0.00200" in md2  # (1000*1 + 200*5) / 1e6


def test_percentile_nearest_rank():
    assert percentile([], 50) is None
    assert percentile([1, 2, 3, 4], 50) == 2 and percentile([1, 2, 3, 4], 95) == 4
