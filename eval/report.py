"""Aggregation and rendering for the eval harness (D-09). Pure functions: no file or network access.

Rules enforced here, because they are easy to get wrong later:
  - accuracy is always reported with n and a 95% Wilson interval, split by source, never pooled;
  - a record the system failed to read is a wrong answer in the same denominator, never dropped;
  - per-type numbers are produced for the dev split only (F7: hold-out per type is 1-2 items, i.e. noise).
"""
from __future__ import annotations

import math
from collections import defaultdict
from statistics import median
from typing import Iterable, Optional

from eval.scoring import wilson

FIELDS = ("date", "amount", "currency", "in_out", "status", "counterparty", "txn_id")
ROW_ORDER = ("record_correct",) + FIELDS
SOURCE_ORDER = ("real_trader", "personal_proxy", "simulated", "public_benchmark")
SMALL_N = 30


def percentile(values: Iterable[float], q: float) -> Optional[float]:
    """Nearest-rank percentile (q in 0..100). Returns None for no data."""
    xs = sorted(values)
    if not xs:
        return None
    rank = max(1, math.ceil(q / 100 * len(xs)))
    return xs[rank - 1]


def tally(results: list[dict], group_key: str) -> dict[str, dict[str, tuple[int, int]]]:
    """{group: {row: (successes, n)}}. A row's n counts only records that had a gold label for it."""
    out: dict[str, dict[str, list[int]]] = defaultdict(lambda: {r: [0, 0] for r in ROW_ORDER})
    for res in results:
        g = out[res[group_key]]
        ok = res["record_ok"]
        if ok is not None:
            g["record_correct"][1] += 1
            g["record_correct"][0] += bool(ok)
        for f in FIELDS:
            v = res["field_ok"].get(f)
            if v is not None:
                g[f][1] += 1
                g[f][0] += bool(v)
    return {k: {r: (s, n) for r, (s, n) in v.items()} for k, v in out.items()}


def ops_summary(results: list[dict], price_in: Optional[float], price_out: Optional[float]) -> dict:
    n = len(results)
    outcomes: dict[str, int] = defaultdict(int)
    for r in results:
        outcomes[r["outcome"]] += 1
    lat = [r["latency_s"] for r in results if r.get("latency_s") is not None]
    toks = [r["tokens"] for r in results if r.get("tokens")]
    cost = None
    if toks and price_in is not None and price_out is not None:
        total = sum((i * price_in + o * price_out) / 1e6 for i, o in toks)
        cost = {"per_message_usd": total / len(toks), "total_usd": total, "n_with_usage": len(toks)}
    secs = [r["seconds"] for r in results if r.get("seconds") is not None]
    return {
        "n": n,
        "outcomes": dict(outcomes),
        "error_rate": (n - outcomes.get("ok", 0)) / n if n else None,
        "latency_p50_s": percentile(lat, 50), "latency_p95_s": percentile(lat, 95), "latency_n": len(lat),
        "cost": cost,
        "seconds_median": median(secs) if secs else None, "seconds_n": len(secs),
    }


def _pct(x: float) -> str:
    return f"{x * 100:.1f}%"


def _table(groups: dict[str, dict[str, tuple[int, int]]], order: tuple[str, ...], label: str) -> list[str]:
    lines = [f"| {label} | scored item | correct / n | accuracy | 95% Wilson interval |", "|---|---|---|---|---|"]
    keys = [k for k in order if k in groups] + sorted(k for k in groups if k not in order)
    for g in keys:
        for row in ROW_ORDER:
            s, n = groups[g][row]
            if n == 0:
                continue
            lo, hi = wilson(s, n)
            lines.append(f"| {g} | {row} | {s} / {n} | {_pct(s / n)} | [{_pct(lo)}, {_pct(hi)}] |")
    return lines


def render_markdown(meta: dict, by_source: dict, by_type: Optional[dict], ops: dict, skipped: dict) -> str:
    split = meta["split"]
    label = ("MEASURED on the dev split. Not a hold-out result; do not quote as final accuracy."
             if split == "dev" else "MEASURED on the frozen hold-out, scored once after the feature freeze.")
    L = [f"# LedgerLens eval: {meta['mode']}, {split} split", "", f"**Evidence label:** {label}", ""]
    if meta.get("fake_backend"):
        L += ["> **FAKE MODEL CLIENT.** These numbers describe the harness plumbing only, not the system.", ""]
    L += ["| run detail | value |", "|---|---|"]
    for k in ("started_utc", "git_commit", "scoring_py_sha256", "backend", "vision_model", "text_model",
              "records_run", "smoke_limit"):
        if meta.get(k) not in (None, ""):
            L.append(f"| {k} | {meta[k]} |")
    L += ["", "## Accuracy by source (D-09: n and 95% Wilson interval; sources are never pooled)", ""]
    L += _table(by_source, SOURCE_ORDER, "source")
    if any(n < SMALL_N for g in by_source.values() for (_, n) in g.values() if n):
        L += ["", f"Every row with n < {SMALL_N} has a wide interval: read the interval, not the point estimate."]
    if by_type is not None:
        L += ["", "## Accuracy by record type (dev split only, F7)", ""]
        L += _table(by_type, (), "type")
    L += ["", "## Operations (all sources together)", "", "| metric | value |", "|---|---|"]
    oc = ", ".join(f"{k}: {v}" for k, v in sorted(ops["outcomes"].items()))
    L.append(f"| outcomes | {oc} |")
    if ops["error_rate"] is not None:
        L.append(f"| error rate (no valid proposal) | {_pct(ops['error_rate'])} ({ops['n'] - ops['outcomes'].get('ok', 0)} of {ops['n']}) |")
    if ops["latency_n"]:
        note = " (p95 is effectively the maximum when n < 20)" if ops["latency_n"] < 20 else ""
        L.append(f"| latency p50 / p95 (core.handle, per record) | {ops['latency_p50_s']:.2f}s / {ops['latency_p95_s']:.2f}s, n={ops['latency_n']}{note} |")
    if ops["cost"]:
        c = ops["cost"]
        L.append(f"| cost per message | ${c['per_message_usd']:.5f} (measured tokens x the prices you supplied; n={c['n_with_usage']}) |")
    elif ops["latency_n"]:
        L.append("| cost per message | not computed: pass --price-in and --price-out (USD per million tokens, from the models page) |")
    if ops["seconds_n"]:
        L.append(f"| manual entry time, median | {ops['seconds_median']:.0f}s per record, n={ops['seconds_n']} |")
    if any(skipped.values()):
        L += ["", "## Not scored (counts only)", ""]
        L += [f"- {k}: {v}" for k, v in skipped.items() if v]
    return "\n".join(L) + "\n"
