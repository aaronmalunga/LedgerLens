"""Credit-readiness summary (spec CREDIT_FILE_SPEC_27OCT.md, D-08, D-07).

Pure functions over the confirmed ledger. Every number is computed here, by code; nothing is a score, and the
word "verified" is never used. ZMW and ZAR are kept apart and never converted. Reserved/reversed holds,
personal-flagged entries and undated entries are left out of the figures and counted in `exclusions`.
"""
from __future__ import annotations

import datetime as dt
from collections import defaultdict
from decimal import Decimal
from statistics import median
from typing import Optional

from .checks import check_transaction
from .models import EvidenceTier, Status, Transaction

FOOTER = "Prepared from records the trader confirmed. Not verified by LedgerLens. Not a credit score."
NOT_PROVIDED = ("ID, proof of residence, guarantor, collateral, business registration, tax clearance and "
                "bank statements. The lender will still ask for these.")
TIERS = [t.value for t in EvidenceTier]


def _q(x: Decimal) -> str:
    return f"{x:.2f}"


def _week_start(d: dt.date) -> dt.date:
    return d - dt.timedelta(days=d.weekday())


def build_credit_file(entries: list[dict]) -> dict:
    """entries: Store.entries() rows ({entry_id, tx (dict), tier, source_event_id})."""
    excl = {"reserved_or_reversed": 0, "personal": 0, "undated": 0, "sum_mismatch_flagged": 0}
    lines = []
    for e in entries:
        tx = Transaction.model_validate(e["tx"])
        if any(i.code == "sum_mismatch" for i in check_transaction(tx)):
            excl["sum_mismatch_flagged"] += 1  # counted for honesty; the line still counts (trader confirmed it)
        if tx.status != Status.COMPLETED:
            excl["reserved_or_reversed"] += 1
        elif not tx.business:
            excl["personal"] += 1
        elif tx.date is None:
            excl["undated"] += 1
        else:
            lines.append((e, tx))

    out: dict = {"footer": FOOTER, "not_provided": NOT_PROVIDED, "exclusions": excl, "n_lines": len(lines)}
    if not lines:
        out.update(coverage=None, currencies={})
        return out

    dates = [tx.date for _, tx in lines]
    first, last = min(dates), max(dates)
    by_source: dict[str, int] = defaultdict(int)
    for _, tx in lines:
        by_source[tx.source_type.value] += 1
    out["coverage"] = {
        "first_date": first.isoformat(), "last_date": last.isoformat(),
        "days_covered": (last - first).days + 1, "days_with_records": len(set(dates)),
        "months_with_records": len({(d.year, d.month) for d in dates}),
        "records_by_source": dict(sorted(by_source.items())),
    }

    cur: dict[str, dict] = {}
    for cc in sorted({tx.currency for _, tx in lines}):
        mine = [(e, tx) for e, tx in lines if tx.currency == cc]
        months: dict[str, dict] = {}
        weekly_in: dict[dt.date, Decimal] = defaultdict(Decimal)
        tier_in = {t: Decimal("0") for t in TIERS}
        for e, tx in mine:
            m = months.setdefault(tx.date.strftime("%Y-%m"),
                                  {"in": Decimal("0"), "out": Decimal("0"), "in_by_tier": {t: Decimal("0") for t in TIERS}})
            m[tx.direction.value] += tx.amount
            if tx.direction.value == "in":
                m["in_by_tier"][e["tier"]] += tx.amount
                tier_in[e["tier"]] += tx.amount
                weekly_in[_week_start(tx.date)] += tx.amount
        total_in = sum(tier_in.values(), Decimal("0"))
        # weekly consistency over every week from first to last record, including empty weeks
        w, weeks = _week_start(first), []
        while w <= _week_start(last):
            weeks.append(weekly_in.get(w, Decimal("0")))
            w += dt.timedelta(days=7)
        cur[cc] = {
            "months": {k: {"in": _q(v["in"]), "out": _q(v["out"]), "net": _q(v["in"] - v["out"]),
                           "in_share_by_tier": _shares(v["in_by_tier"], v["in"])} for k, v in sorted(months.items())},
            "total_in": _q(total_in),
            "in_share_by_tier": _shares(tier_in, total_in),
            "weeks_covered": len(weeks), "weeks_with_sales": sum(1 for x in weeks if x > 0),
            "weekly_in_min": _q(min(weeks)), "weekly_in_median": _q(median(weeks)), "weekly_in_max": _q(max(weeks)),
        }
    out["currencies"] = cur
    out["lines"] = [{"entry_id": e["entry_id"], "date": tx.date.isoformat(), "currency": tx.currency,
                     "direction": tx.direction.value, "amount": _q(tx.amount), "tier": e["tier"],
                     "source_type": tx.source_type.value} for e, tx in sorted(lines, key=lambda x: (x[1].date, x[0]["entry_id"]))]
    return out


def _shares(by_tier: dict[str, Decimal], total: Decimal) -> dict[str, Optional[str]]:
    if total <= 0:
        return {t: None for t in TIERS}
    return {t: f"{(by_tier[t] / total * 100):.1f}%" for t in TIERS}


def render_text(cf: dict, label: str = "") -> str:
    """Plain-text version for chat. The PDF/web renderers will read the same dict."""
    if not cf["n_lines"]:
        return "No confirmed, dated business entries yet, so there is nothing to summarise."
    c = cf["coverage"]
    L = ["CREDIT-READINESS SUMMARY, designed for lender review" + (f" ({label})" if label else ""),
         f"Period: {c['first_date']} to {c['last_date']} ({c['days_covered']} days; records on {c['days_with_records']} days, "
         f"in {c['months_with_records']} month(s))",
         "Records by source: " + ", ".join(f"{k} {v}" for k, v in c["records_by_source"].items())]
    for cc, d in cf["currencies"].items():
        L.append(f"\n{cc}: money in {d['total_in']}")
        for m, v in d["months"].items():
            L.append(f"  {m}: in {v['in']}, out {v['out']}, net {v['net']}")
        s = d["in_share_by_tier"]
        L.append(f"  Money in by evidence: T1 {s['T1']}, T2 {s['T2']}, T3 {s['T3']}")
        L.append(f"  Weeks with a recorded sale: {d['weeks_with_sales']} of {d['weeks_covered']} "
                 f"(weekly in: min {d['weekly_in_min']}, median {d['weekly_in_median']}, max {d['weekly_in_max']})")
    x = cf["exclusions"]
    L.append(f"\nLeft out: {x['reserved_or_reversed']} hold(s)/reversal(s), {x['personal']} personal, {x['undated']} undated. "
             f"Flagged sum mismatches: {x['sum_mismatch_flagged']}.")
    L.append("T1 = third-party record with an ID; T2 = receipt or SMS without an ID; T3 = self-reported.")
    L.append("Not provided by LedgerLens: " + cf["not_provided"])
    L.append(cf["footer"])
    return "\n".join(L)
