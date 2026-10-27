"""Eval harness (D-06, D-09): accuracy by source with Wilson intervals, scored per eval/SCORING.md.

Run from the repo root (data/ is git-ignored; nothing here writes record data anywhere tracked):

    python -m eval.run_eval --labels data/labels.csv --images data/images
        Dev split. Each record goes through Core.handle(), the same path the demo uses, so the
        numbers describe the system being demoed. Needs LEDGERLENS_MODEL_BACKEND=meta for real numbers.

    python -m eval.run_eval --labels data/labels.csv --images data/images --predictions data/baseline.csv
        Scores the manual-entry baseline with the SAME scorer. Only files listed in the baseline
        CSV are scored. Optional `seconds` column gives the median entry time.

    python -m eval.run_eval ... --split holdout --confirm-holdout
        The one hold-out run, after the feature freeze (Tue 3 Nov). Logged in eval/holdout_runs.jsonl.

Labels CSV convention (see eval/SCORING.md, "Unit: one record file"):
    * One row per record file with `item` BLANK carries the record-level gold: total `amount`,
      date, currency, in_out, status, counterparty (and optionally txn_id).
    * Extra rows for the same file with `item` filled are line items (secondary metric, not scored here).
    * A file with a single row is treated as its own record row even if `item` is filled.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # so `python eval/run_eval.py` works too

from pydantic import ValidationError  # noqa: E402

from eval.freeze_holdout import MANIFEST, load_manifest, sha256  # noqa: E402
from eval.report import FIELDS, ops_summary, render_markdown, tally  # noqa: E402
from eval.scoring import KEY_FIELDS, field_correct, norm_amount, norm_date  # noqa: E402
from ledgerlens.core.events import Channel, InboundEvent, InboundKind, OutboundKind  # noqa: E402
from ledgerlens.core.guard import REFUSALS, Guard, GuardConfig  # noqa: E402
from ledgerlens.core.handler import Core  # noqa: E402
from ledgerlens.core.models import Transaction  # noqa: E402
from ledgerlens.core.store import Store  # noqa: E402
from ledgerlens.llm.client import FakeModelClient, make_client  # noqa: E402

HOLDOUT_LOG = Path(__file__).parent / "holdout_runs.jsonl"
SCORING_PY = Path(__file__).parent / "scoring.py"
REQUIRED_COLUMNS = ("file", "source", "type", "date", "amount", "currency", "in_out", "status")
IMAGE_MIME = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".webp": "image/webp",
              ".heic": "image/heic"}
AUDIO_MIME = {".ogg": "audio/ogg", ".opus": "audio/ogg", ".m4a": "audio/mp4", ".mp3": "audio/mpeg",
              ".wav": "audio/wav"}


class HarnessError(Exception):
    """A problem with the data or the invocation. Exit code 2; nothing is sent to any model."""


@dataclass
class Gold:
    file: str
    source: str          # real_trader | personal_proxy | simulated | public_benchmark
    type: str
    fields: dict         # gold value per scored field ('' = no gold label, so not scored)
    consent_ok: bool
    csv_holdout: str     # the CSV's own holdout column (Y/N/''), cross-checked against the manifest


def _yes(v: str) -> bool:
    return (v or "").strip().lower().startswith(("y", "true", "1"))


def source_category(source: str, personal_proxy: str) -> str:
    s = (source or "").strip().lower().replace("-", "_").replace(" ", "_")
    if s in {"simulated", "sim"}:
        return "simulated"
    if s in {"benchmark", "public", "public_benchmark"}:
        return "public_benchmark"
    if s in {"real", "real_trader"}:
        p = (personal_proxy or "").strip().lower()
        if not p:
            raise HarnessError("a `real` row has a blank personal_proxy: set Y (supermarket slips, "
                               "cousin's bank notifications) or N (a trader's own record). "
                               "Guessing would inflate the real_trader numbers.")
        return "personal_proxy" if _yes(p) else "real_trader"
    raise HarnessError(f"unknown source {source!r}: use real, SIMULATED or benchmark")


def load_gold(path: Path) -> list[Gold]:
    with path.open(newline="", encoding="utf-8-sig") as f:  # utf-8-sig: Excel adds a BOM
        reader = csv.DictReader(f)
        missing = [c for c in REQUIRED_COLUMNS if c not in (reader.fieldnames or [])]
        if missing:
            raise HarnessError(f"{path} is missing column(s): {', '.join(missing)}")
        rows = [(i + 2, {k: (v or "").strip() for k, v in r.items() if k}) for i, r in enumerate(reader)]
    by_file: dict[str, list[tuple[int, dict]]] = {}
    for line, r in rows:
        if r["file"]:
            by_file.setdefault(r["file"], []).append((line, r))
    gold, problems = [], []
    for fn, group in by_file.items():
        headers = [x for x in group if not x[1].get("item")]
        if len(headers) == 1:
            line, r = headers[0]
        elif len(group) == 1:
            line, r = group[0]
        else:
            problems.append(f"{fn}: needs exactly one row with a blank `item` (the record total); "
                            f"found {len(headers)} among {len(group)} rows")
            continue
        for fld, norm in (("amount", norm_amount), ("date", norm_date)):
            if r[fld] and norm(r[fld]) is None:  # an unparseable gold would score None == None as correct
                problems.append(f"line {line} ({fn}): gold {fld} {r[fld]!r} cannot be parsed")
        try:
            cat = source_category(r["source"], r.get("personal_proxy", ""))
        except HarnessError as e:
            problems.append(f"line {line} ({fn}): {e}")
            continue
        consent_ok = cat in {"simulated", "public_benchmark"} or _yes(r.get("consent", ""))
        fields = {f: r.get(f, "") for f in FIELDS}
        gold.append(Gold(fn, cat, r["type"], fields, consent_ok, r.get("holdout", "").upper()))
    if problems:
        raise HarnessError("label problems (fix in the CSV, then re-run):\n  - " + "\n  - ".join(problems[:20])
                           + (f"\n  ... and {len(problems) - 20} more" if len(problems) > 20 else ""))
    return gold


def resolve_splits(gold: list[Gold], images: Path, manifest: list[dict]) -> dict[str, tuple[str, str]]:
    """file -> (sha256, split) from the frozen manifest. Refuses unfrozen, missing or inconsistent files."""
    frozen = {m["sha256"]: m["split"] for m in manifest}
    out, missing, unfrozen, conflict = {}, [], [], []
    for g in gold:
        p = images / g.file
        if not p.is_file():
            missing.append(g.file)
            continue
        h = sha256(p)
        if h not in frozen:
            unfrozen.append(g.file)
            continue
        out[g.file] = (h, frozen[h])
        if g.csv_holdout in {"Y", "N"} and (g.csv_holdout == "Y") != (frozen[h] == "holdout"):
            conflict.append(g.file)
    errs = []
    if missing:
        errs.append(f"{len(missing)} labelled file(s) not found in {images}: {', '.join(missing[:5])}")
    if unfrozen:
        errs.append(f"{len(unfrozen)} file(s) are not in the hold-out manifest ({', '.join(unfrozen[:5])}): "
                    "run eval/freeze_holdout.py for the batch and commit the manifest BEFORE evaluating (P2)")
    if conflict:
        errs.append(f"{len(conflict)} file(s) have a `holdout` column that disagrees with the manifest "
                    f"({', '.join(conflict[:5])}): the manifest wins; re-run freeze_holdout.py to resync")
    if errs:
        raise HarnessError("\n".join(errs))
    return out


def tx_to_pred(tx: Transaction) -> dict:
    return {"date": tx.date.isoformat() if tx.date else None, "amount": str(tx.amount),
            "currency": tx.currency, "in_out": tx.direction.value, "status": tx.status.value,
            "counterparty": tx.counterparty, "txn_id": tx.txn_id}


def score(gold_fields: dict, pred: Optional[dict]) -> tuple[dict, Optional[bool]]:
    """Per-field correctness (None = not scored). No prediction = every scored field wrong, not dropped.
    Record correct = every KEY field that HAS a gold label is correct (SCORING.md: unlabelled = not scored)."""
    p = pred or {}
    field_ok = {f: field_correct(f, p.get(f), gold_fields.get(f, "")) for f in FIELDS}
    key = [field_ok[f] for f in KEY_FIELDS if field_ok[f] is not None]
    return field_ok, (all(key) if key else None)


class Recorder:
    """Wraps the model client so the harness can see the proposal, the exception and the token usage
    while the call still goes through Core.handle()."""

    def __init__(self, inner) -> None:
        self.inner = inner
        self.reset()

    def reset(self) -> None:
        self.exc: Optional[BaseException] = None
        self.last_usage = None

    def extract(self, **kw):
        self.reset()
        if hasattr(self.inner, "last_usage"):
            self.inner.last_usage = None
        try:
            tx = self.inner.extract(**kw)
        except Exception as e:
            self.exc = e
            raise
        self.last_usage = getattr(self.inner, "last_usage", None)
        return tx


def build_event(path: Path, ref: str, sha: str) -> InboundEvent:
    ext = path.suffix.lower()
    base = dict(event_id=f"eval-{sha[:16]}", channel=Channel.EVAL, user_ref=ref)
    if ext in IMAGE_MIME:
        return InboundEvent(kind=InboundKind.IMAGE, media=path.read_bytes(), media_mime=IMAGE_MIME[ext], **base)
    if ext in AUDIO_MIME:
        return InboundEvent(kind=InboundKind.AUDIO, media=path.read_bytes(), media_mime=AUDIO_MIME[ext], **base)
    if ext == ".txt":
        return InboundEvent(kind=InboundKind.TEXT, text=path.read_text(encoding="utf-8"), **base)
    raise HarnessError(f"unsupported file type {ext!r} for {path.name}")


def run_through_core(core: Core, rec: Recorder, ev: InboundEvent) -> tuple[Optional[dict], str, float, Optional[tuple]]:
    rec.reset()
    t0 = time.perf_counter()
    msgs = core.handle(ev)
    dt = time.perf_counter() - t0
    card = next((m for m in msgs if m.kind == OutboundKind.CONFIRM_CARD), None)
    if card:
        pid = card.buttons[0].id.split(":", 1)[1]
        tx = core.store.get_pending(ev.user_ref, pid)[0]
        return tx_to_pred(tx), "ok", dt, rec.last_usage
    if rec.exc is not None:
        kind = "schema_invalid" if isinstance(rec.exc, (ValidationError, json.JSONDecodeError)) else "model_error"
        return None, kind, dt, None
    if msgs and msgs[0].text in REFUSALS.values():
        return None, "refused", dt, None
    return None, "no_proposal", dt, None  # e.g. voice notes before the voice feature exists


def load_env_file(path: Path) -> None:
    """Minimal .env reader (no new dependency). Never overrides variables already set."""
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip("'\""))


def _git_commit() -> str:
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True,
                              cwd=Path(__file__).parent, timeout=5).stdout.strip() or "unknown"
    except Exception:
        return "unknown"


def parse_args(argv) -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--labels", required=True, type=Path)
    ap.add_argument("--images", required=True, type=Path)
    ap.add_argument("--manifest", type=Path, default=MANIFEST)
    ap.add_argument("--split", choices=["dev", "holdout"], default="dev")
    ap.add_argument("--confirm-holdout", action="store_true", help="required for --split holdout")
    ap.add_argument("--rerun-holdout", action="store_true", help="allow a second hold-out run (logged as a rerun)")
    ap.add_argument("--allow-real-data", action="store_true",
                    help="send real (non-simulated) records to the model API. OFF by default: D-12, free-credit terms")
    ap.add_argument("--predictions", type=Path, help="score a manual-entry CSV instead of calling the model")
    ap.add_argument("--sources", help="comma list: real_trader,personal_proxy,simulated,public_benchmark")
    ap.add_argument("--limit", type=int, help="smoke test: only the first N records (by hash order)")
    ap.add_argument("--price-in", type=float, help="USD per million input tokens (from the models page)")
    ap.add_argument("--price-out", type=float, help="USD per million output tokens (from the models page)")
    ap.add_argument("--out-dir", type=Path, default=Path("data/results"))
    ap.add_argument("--env-file", type=Path, default=Path(".env"))
    return ap.parse_args(argv)


def load_predictions(path: Path) -> dict[str, dict]:
    with path.open(newline="", encoding="utf-8-sig") as f:
        rows = [{k: (v or "").strip() for k, v in r.items() if k} for r in csv.DictReader(f)]
    if rows and "file" not in rows[0]:
        raise HarnessError(f"{path} needs a `file` column")
    return {r["file"]: r for r in rows if r.get("file")}


def run(a: argparse.Namespace, client_factory: Optional[Callable] = None) -> tuple[str, dict]:
    if a.split == "holdout" and not a.confirm_holdout:
        raise HarnessError("hold-out is scored once, after the feature freeze. Add --confirm-holdout if that is now.")
    if a.split == "holdout" and a.limit:
        raise HarnessError("--limit cannot be used with the hold-out: a partial run would use up the one-shot.")
    rerun = False
    if a.split == "holdout" and not a.predictions and HOLDOUT_LOG.exists() and HOLDOUT_LOG.read_text().strip():
        if not a.rerun_holdout:
            raise HarnessError("the hold-out has already been scored (eval/holdout_runs.jsonl). "
                               "Report that result; --rerun-holdout is for infrastructure failures only and is logged.")
        rerun = True

    gold = load_gold(a.labels)
    splits = resolve_splits(gold, a.images, load_manifest(a.manifest))
    want_sources = set(a.sources.split(",")) if a.sources else None
    baseline = load_predictions(a.predictions) if a.predictions else None

    skipped = {"in other split": 0, "excluded by --sources": 0, "no consent recorded (never sent to a model)": 0,
               "withheld by the data-use gate (D-12; pass --allow-real-data only if the terms allow it)": 0,
               "not in the baseline CSV": 0}
    chosen = []
    for g in gold:
        sha, split = splits[g.file]
        if split != a.split:
            skipped["in other split"] += 1
        elif want_sources and g.source not in want_sources:
            skipped["excluded by --sources"] += 1
        elif baseline is not None and g.file not in baseline:
            skipped["not in the baseline CSV"] += 1
        elif baseline is None and not g.consent_ok:
            skipped["no consent recorded (never sent to a model)"] += 1
        elif baseline is None and not a.allow_real_data and g.source in {"real_trader", "personal_proxy"}:
            skipped["withheld by the data-use gate (D-12; pass --allow-real-data only if the terms allow it)"] += 1
        else:
            chosen.append((sha, g))
    chosen.sort(key=lambda x: x[0])  # hash order: deterministic, not hand-picked
    if a.limit:
        chosen = chosen[: a.limit]
    if not chosen:
        raise HarnessError(f"no records to score in the {a.split} split after filtering: {skipped}")

    meta = {"mode": "manual baseline" if baseline is not None else "model via Core.handle()",
            "split": a.split, "started_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "git_commit": _git_commit(), "scoring_py_sha256": sha256(SCORING_PY),
            "records_run": len(chosen), "smoke_limit": a.limit}
    results = []
    if baseline is not None:
        meta["backend"] = "none (human entry)"
        for sha, g in chosen:
            row = baseline[g.file]
            pred = {f: row.get(f) or None for f in FIELDS}
            fo, ro = score(g.fields, pred)
            sec = float(row["seconds"]) if row.get("seconds") else None
            results.append(dict(file=g.file, sha=sha[:12], source=g.source, type=g.type, outcome="ok",
                                field_ok=fo, record_ok=ro, pred=pred, latency_s=None, tokens=None, seconds=sec))
    else:
        inner = (client_factory or _default_factory(a))()
        meta["fake_backend"] = isinstance(inner, FakeModelClient)
        meta["backend"] = "fake" if meta["fake_backend"] else "meta"
        meta["vision_model"] = getattr(inner, "vision_model", "")
        meta["text_model"] = getattr(inner, "text_model", "")
        if a.split == "holdout" and meta["fake_backend"]:
            raise HarnessError("refusing to spend the hold-out on the fake client")
        rec = Recorder(inner)
        # Rate limit and budget are lifted for the eval (a batch run is not a user session); the image size
        # limit stays on purpose, so a photo the demo would refuse shows up as `refused` instead of being hidden.
        core = Core(Store(), rec, Guard(GuardConfig(rate_limit=10**9, daily_usd_cap=1e12, daily_call_cap=10**9)))
        for i, (sha, g) in enumerate(chosen, 1):
            ev = build_event(a.images / g.file, f"eval-{sha[:12]}", sha)
            pred, outcome, dt, usage = run_through_core(core, rec, ev)
            fo, ro = score(g.fields, pred)
            results.append(dict(file=g.file, sha=sha[:12], source=g.source, type=g.type, outcome=outcome,
                                field_ok=fo, record_ok=ro, pred=pred, latency_s=dt, tokens=usage, seconds=None))
            print(f"[{i}/{len(chosen)}] {g.source:<14} {outcome:<14} {dt:5.1f}s", file=sys.stderr)

    by_source = tally(results, "source")
    by_type = tally(results, "type") if a.split == "dev" else None
    ops = ops_summary(results, a.price_in, a.price_out)
    md = render_markdown(meta, by_source, by_type, ops, skipped)
    payload = {"meta": meta, "skipped": skipped, "ops": ops, "by_source": by_source, "records": results}

    a.out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    stem = a.out_dir / f"{'baseline' if baseline is not None else 'model'}_{a.split}_{stamp}"
    stem.with_suffix(".json").write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    stem.with_suffix(".md").write_text(md, encoding="utf-8")  # counts only: safe to paste into the README

    if a.split == "holdout" and baseline is None:
        entry = {"ts": meta["started_utc"], "git_commit": meta["git_commit"], "scoring_py_sha256": meta["scoring_py_sha256"],
                 "backend": meta["backend"], "vision_model": meta["vision_model"], "text_model": meta["text_model"],
                 "n_records": len(results), "rerun": rerun}
        with HOLDOUT_LOG.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
        md += "\nHold-out run logged in eval/holdout_runs.jsonl: commit it.\n"
    return md, payload


def _default_factory(a: argparse.Namespace) -> Callable:
    load_env_file(a.env_file)
    return make_client


def main(argv=None, client_factory: Optional[Callable] = None) -> int:
    a = parse_args(argv)
    try:
        md, _ = run(a, client_factory)
    except HarnessError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2
    print(md)
    return 0


if __name__ == "__main__":
    sys.exit(main())
