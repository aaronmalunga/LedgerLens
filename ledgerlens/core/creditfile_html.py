"""HTML renderer for the credit file (spec CREDIT_FILE_SPEC_27OCT.md, D-08, D-11).

A pure function over the dict from build_credit_file(): it does no arithmetic of its own beyond bar heights,
and it escapes every string it prints. One self-contained page (inline CSS, no scripts, no external requests),
so it can be shared, printed to PDF, or opened offline. It never says 'verified' except in the footer's
'Not verified by LedgerLens', and it never shows a score."""
from __future__ import annotations

import datetime as dt
from html import escape as _e

SOURCE_LABEL = {"receipt": "Receipt photo", "sms": "Mobile-money / bank SMS", "notebook": "Notebook page",
                "voice": "Voice note"}
TIER_NAME = {"T1": "T1 third-party record with an ID", "T2": "T2 receipt or SMS without an ID",
             "T3": "T3 self-reported (notebook, voice or edited)"}
CURRENCY_NAME = {"ZMW": "kwacha", "ZAR": "rand"}
SYMBOL = {"ZMW": "K", "ZAR": "R"}

CSS = """
:root{--ink:#1d2433;--mute:#5d6678;--line:#dfe3ea;--bg:#f6f7f9;--card:#fff;--acc:#1f6f5c;--warn:#b4531a;--t1:#1f6f5c;--t2:#c7902a;--t3:#8a93a6}
@media (prefers-color-scheme:dark){:root{--ink:#e8ebf1;--mute:#9aa3b5;--line:#2b3240;--bg:#12151c;--card:#1a1f29;--acc:#4fb79d;--warn:#e08a52;--t1:#4fb79d;--t2:#d9a53a;--t3:#7d879b}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.5 -apple-system,Segoe UI,Helvetica,Arial,sans-serif}
.wrap{max-width:860px;margin:0 auto;padding:28px 16px 40px}
.banner{background:#fff3e6;border:1px solid #f0c9a0;color:#7a3f10;border-radius:8px;padding:8px 12px;font-size:13px;font-weight:600;margin-bottom:16px}
h1{font-size:24px;margin:0 0 2px}.sub{color:var(--mute);font-size:14px}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:18px 20px;margin-top:16px}
h2{font-size:13px;letter-spacing:.06em;text-transform:uppercase;color:var(--mute);margin:0 0 10px}
.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px}.k{border:1px solid var(--line);border-radius:10px;padding:10px 12px}
.k b{display:block;font-size:22px}.k span{font-size:12px;color:var(--mute)}
.scroll{overflow-x:auto}table{width:100%;border-collapse:collapse;font-size:14px}
th{text-align:left;color:var(--mute);font-weight:600;font-size:12px;border-bottom:1px solid var(--line);padding:6px 4px}
td{padding:7px 4px;border-bottom:1px solid var(--line)}td.n,th.n{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}
.bar{display:flex;height:16px;border-radius:8px;overflow:hidden;margin:6px 0 8px;background:var(--line)}.bar i{display:block}
.leg{display:flex;gap:6px 16px;font-size:13px;color:var(--mute);flex-wrap:wrap}.leg em{display:inline-block;width:10px;height:10px;border-radius:2px;margin-right:6px}
.chip{display:inline-block;font-size:11px;font-weight:700;border-radius:6px;padding:1px 7px;color:#fff}
.t1{background:var(--t1)}.t2{background:var(--t2)}.t3{background:var(--t3)}.ed{font-size:11px;color:var(--warn);font-weight:600;margin-left:6px}
.weeks{display:flex;gap:3px;align-items:flex-end;height:64px;margin-top:6px}.weeks i{flex:1;min-width:3px;background:#b9d8cf;border-radius:3px 3px 0 0}
.weeks i.z{background:repeating-linear-gradient(45deg,var(--line),var(--line) 4px,transparent 4px,transparent 8px);height:6px!important}
.note{background:rgba(31,111,92,.08);border-left:4px solid var(--acc);padding:10px 12px;border-radius:6px;font-size:14px}
.foot{margin-top:18px;font-size:13px;color:var(--mute);border-top:1px solid var(--line);padding-top:12px}
details summary{cursor:pointer;font-weight:600;color:var(--acc);margin:6px 0}
@media print{body{background:#fff}.card{break-inside:avoid;border-color:#ccc}details{display:block}details>summary{display:none}}
"""


def _money(cc: str, v: str) -> str:
    whole, _, frac = v.partition(".")
    neg = whole.startswith("-")
    whole = f"{int(whole.lstrip('-')):,}"
    return f"{'-' if neg else ''}{SYMBOL.get(cc, cc + ' ')}{whole}" + (f".{frac}" if frac and frac != "00" else "")


def _month(key: str) -> str:
    return dt.datetime.strptime(key, "%Y-%m").strftime("%b %Y")


def _day(iso: str) -> str:
    d = dt.date.fromisoformat(iso)
    return f"{d.day} {d.strftime('%b %Y')}"


def _pct(s) -> float:
    return float(s.rstrip("%")) if s else 0.0


def _tier_bar(shares: dict) -> str:
    if not any(shares.values()):
        return '<div class="sub">No money in recorded.</div>'
    bar = "".join(f'<i style="width:{_pct(shares[t])}%;background:var(--{t.lower()})"></i>' for t in ("T1", "T2", "T3"))
    leg = "".join(f'<span><em style="background:var(--{t.lower()})"></em>{_e(TIER_NAME[t])}: {_e(shares[t] or "0%")}</span>'
                  for t in ("T1", "T2", "T3"))
    return f'<div class="bar" role="img" aria-label="Share of money in by evidence tier">{bar}</div><div class="leg">{leg}</div>'


def _weeks_chart(weekly: list[dict]) -> str:
    top = max((float(w["in"]) for w in weekly), default=0) or 1
    bars = []
    for w in weekly:
        v = float(w["in"])
        label = f'Week of {_day(w["week_start"])}: {w["in"]}'
        bars.append('<i class="z" title="%s (no record)"></i>' % _e(label) if v <= 0
                    else '<i style="height:%d%%" title="%s"></i>' % (max(6, round(v / top * 100)), _e(label)))
    return f'<div class="weeks">{"".join(bars)}</div>'


def render_html(cf: dict, label: str = "") -> str:
    parts = [f"<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\">"
             f"<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">"
             f"<title>LedgerLens credit-readiness summary</title><style>{CSS}</style></head><body><div class=\"wrap\">"]
    if label:
        parts.append(f'<div class="banner">{_e(label)}. Figures below come from the demo history, not from a real business.</div>')
    parts.append("<h1>Credit-readiness summary</h1>")
    if not cf["n_lines"]:
        parts.append('<div class="card">No confirmed, dated business entries yet, so there is nothing to summarise.</div>')
    else:
        c = cf["coverage"]
        cur_names = ", ".join(f"{k} ({CURRENCY_NAME.get(k, k)})" for k in cf["currencies"])
        parts.append(f'<div class="sub">Designed for lender review &nbsp;·&nbsp; Period {_e(_day(c["first_date"]))} to '
                     f'{_e(_day(c["last_date"]))} &nbsp;·&nbsp; Currency: {_e(cur_names)}</div>')
        weeks_total = max(d["weeks_covered"] for d in cf["currencies"].values())
        weeks_with = max(d["weeks_with_sales"] for d in cf["currencies"].values())
        src = " · ".join(f"{_e(SOURCE_LABEL.get(k, k))} {v}" for k, v in c["records_by_source"].items())
        parts.append(
            '<div class="card"><h2>1. Coverage: how long the records go back</h2><div class="kpis">'
            f'<div class="k"><b>{c["days_covered"]} days</b><span>first to last record</span></div>'
            f'<div class="k"><b>{c["days_with_records"]}</b><span>days with a record</span></div>'
            f'<div class="k"><b>{weeks_with} of {weeks_total}</b><span>weeks with a recorded sale</span></div>'
            f'<div class="k"><b>{c["months_with_records"]}</b><span>months with a record</span></div>'
            f'<div class="k"><b>{cf["n_lines"]}</b><span>confirmed records counted</span></div></div>'
            f'<div class="sub" style="margin-top:8px">By source: {src}</div></div>')
        for cc, d in cf["currencies"].items():
            rows = "".join(
                f'<tr><td>{_e(_month(m))}</td><td class="n">{_e(_money(cc, v["in"]))}</td>'
                f'<td class="n">{_e(_money(cc, v["out"]))}</td><td class="n">{_e(_money(cc, v["net"]))}</td></tr>'
                for m, v in d["months"].items())
            parts.append(
                f'<div class="card"><h2>2. Money in and out per month: {_e(cc)} (completed entries only)</h2>'
                '<div class="scroll"><table><tr><th>Month</th><th class="n">Money in</th><th class="n">Money out</th>'
                f'<th class="n">Net</th></tr>{rows}</table></div>'
                '<div class="sub" style="margin-top:6px">ZMW and ZAR are never converted or mixed.</div></div>')
            parts.append(f'<div class="card"><h2>3. How well is the {_e(cc)} income backed by records?</h2>'
                         f'{_tier_bar(d["in_share_by_tier"])}'
                         '<div class="sub" style="margin-top:8px">Shown as three separate shares, never merged into one figure. '
                         'A line the trader edited counts as T3.</div></div>')
            parts.append(f'<div class="card"><h2>4. Consistency: {_e(cc)} money in per week</h2>{_weeks_chart(d["weekly_in"])}'
                         f'<div class="sub" style="margin-top:6px">Weekly money in: min {_e(_money(cc, d["weekly_in_min"]))} · '
                         f'median {_e(_money(cc, d["weekly_in_median"]))} · max {_e(_money(cc, d["weekly_in_max"]))}. '
                         'A striped bar is a week with no record. Descriptive only, no score.</div></div>')
        lines = cf["lines"]
        def row(l):
            ed = '<span class="ed">edited by trader</span>' if l.get("edited") else ""
            what = _e(l.get("counterparty") or "") or "&nbsp;"
            sign = "+" if l["direction"] == "in" else "-"
            return (f'<tr><td>{_e(_day(l["date"]))}</td><td>{what}</td>'
                    f'<td class="n">{sign}{_e(_money(l["currency"], l["amount"]))}</td>'
                    f'<td><span class="chip {l["tier"].lower()}">{_e(l["tier"])}</span>{ed}</td>'
                    f'<td>{_e(SOURCE_LABEL.get(l["source_type"], l["source_type"]))}'
                    f'{" · " + _e(l["txn_id"]) if l.get("txn_id") else ""}</td><td>{_e(l["entry_id"])}</td></tr>')
        head = '<table><tr><th>Date</th><th>Counterparty</th><th class="n">Amount</th><th>Tier</th><th>Source</th><th>Entry</th></tr>'
        first, rest = lines[:15], lines[15:]
        body = "".join(row(l) for l in first)
        more = (f'<details><summary>Show the other {len(rest)} lines</summary><div class="scroll">{head}'
                f'{"".join(row(l) for l in rest)}</table></div></details>') if rest else ""
        parts.append(f'<div class="card"><h2>5. Every line, with its source</h2><div class="scroll">{head}{body}</table></div>{more}</div>')
        x = cf["exclusions"]
        parts.append('<div class="card"><h2>6. Left out of the figures, and why</h2><div class="sub">'
                     f'{x["reserved_or_reversed"]} reserved or reversed (not completed payments) · {x["personal"]} marked personal · '
                     f'{x["undated"]} with no date · {x["sum_mismatch_flagged"]} whose lines did not add up to their total '
                     '(flagged to the trader; still counted because the trader confirmed them)</div></div>')
    parts.append(f'<div class="card note"><b>What this file does not provide.</b> {_e(cf["not_provided"])}</div>')
    parts.append(f'<div class="foot">{_e(cf["footer"])}</div></div></body></html>')
    return "".join(parts)
