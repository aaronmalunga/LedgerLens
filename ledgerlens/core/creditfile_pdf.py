"""PDF renderer for the credit file (spec CREDIT_FILE_SPEC_27OCT.md, D-08, D-11).

Same rules as the HTML renderer: a pure function over the dict from build_credit_file(), no arithmetic of its own
beyond bar heights, no score, and the word 'verified' only inside 'Not verified by LedgerLens'. Built with
ReportLab (pure Python, no system libraries) so it installs the same on Windows, Linux and a host."""
from __future__ import annotations

import io
from xml.sax.saxutils import escape

from reportlab.graphics.shapes import Drawing, Line, Rect, String
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from .creditfile_html import CURRENCY_NAME, SOURCE_LABEL, TIER_NAME, _day, _money, _month, _pct

INK, MUTE, LINE = colors.HexColor("#1d2433"), colors.HexColor("#5d6678"), colors.HexColor("#dfe3ea")
TIER_COL = {"T1": colors.HexColor("#1f6f5c"), "T2": colors.HexColor("#b07a1a"), "T3": colors.HexColor("#8a4b8f")}
WARN, WARNBG = colors.HexColor("#7a3f10"), colors.HexColor("#fff3e6")

H1 = ParagraphStyle("h1", fontName="Helvetica-Bold", fontSize=20, leading=24, textColor=INK, spaceAfter=4)
H2 = ParagraphStyle("h2", fontName="Helvetica-Bold", fontSize=12, leading=15, textColor=INK, spaceBefore=12, spaceAfter=5)
BODY = ParagraphStyle("b", fontName="Helvetica", fontSize=9, leading=12.5, textColor=INK)
SUB = ParagraphStyle("s", parent=BODY, textColor=MUTE, fontSize=8.5)
BANNER = ParagraphStyle("bn", parent=BODY, fontName="Helvetica-Bold", textColor=WARN, backColor=WARNBG,
                        borderColor=colors.HexColor("#f0c9a0"), borderWidth=0.6, borderPadding=5)
CELL = ParagraphStyle("c", parent=BODY, fontSize=8, leading=10)
W = A4[0] - 30 * mm


def _p(text: str, style=BODY) -> Paragraph:
    return Paragraph(escape(str(text)), style)


def _tier_bar(shares: dict) -> Drawing:
    d = Drawing(W, 34)
    x = 0.0
    for t in ("T1", "T2", "T3"):
        w = W * _pct(shares[t]) / 100
        if w > 0:
            d.add(Rect(x, 18, w, 12, fillColor=TIER_COL[t], strokeColor=None))
        x += w
    lx = 0.0
    for t in ("T1", "T2", "T3"):
        d.add(Rect(lx, 2, 7, 7, fillColor=TIER_COL[t], strokeColor=None))
        d.add(String(lx + 10, 2, f"{t}: {shares[t] or '0%'}", fontName="Helvetica", fontSize=8, fillColor=INK))
        lx += 70
    return d


def _weeks_chart(weekly: list[dict]) -> Drawing:
    h = 70
    d = Drawing(W, h + 12)
    top = max((float(w["in"]) for w in weekly), default=0) or 1
    n = max(len(weekly), 1)
    slot = W / n
    d.add(Line(0, 10, W, 10, strokeColor=LINE))
    for i, w in enumerate(weekly):
        v = float(w["in"])
        if v <= 0:  # a week with no record: hatched outline, never a zero bar that looks like a record
            d.add(Rect(i * slot + 2, 10, slot - 4, 14, fillColor=None, strokeColor=MUTE, strokeDashArray=[2, 2]))
        else:
            d.add(Rect(i * slot + 2, 10, slot - 4, max(4, v / top * h), fillColor=TIER_COL["T1"], strokeColor=None))
    return d


def _table(rows, widths, right=(), repeat=1) -> Table:
    t = Table(rows, colWidths=widths, repeatRows=repeat)
    st = [("FONT", (0, 0), (-1, 0), "Helvetica-Bold", 8), ("TEXTCOLOR", (0, 0), (-1, 0), MUTE),
          ("LINEBELOW", (0, 0), (-1, -1), 0.4, LINE), ("VALIGN", (0, 0), (-1, -1), "TOP"),
          ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3)]
    st += [("ALIGN", (c, 0), (c, -1), "RIGHT") for c in right]
    t.setStyle(TableStyle(st))
    return t


LEGEND = [
    "T1: a record from a third party that carries a transaction ID (for example a mobile-money SMS). The strongest evidence on this page.",
    "T2: a printed receipt or an SMS with no transaction ID.",
    "T3: written or spoken by the trader (notebook page, voice note), or edited by the trader after reading. Useful, but it is the trader's own word.",
    "Edited by trader: the trader changed the amount or date, so the line counts as T3.",
    "Dashed box in the weekly chart: a week with no record at all. ZMW and ZAR are different currencies and are never added together.",
    "Entry: the line's reference, so you can ask the trader about it. Left out (section 6): kept off the totals.",
    "SIMULATED means made-up sample data, not a real trader. This file describes records; it gives no score and no loan advice.",
]


def render_pdf(cf: dict, label: str = "") -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=15 * mm, rightMargin=15 * mm, topMargin=14 * mm,
                            bottomMargin=16 * mm, title="LedgerLens credit-readiness summary", author="LedgerLens")
    s: list = []
    if label:
        s += [_p(f"{label}. Figures below come from the demo history, not from a real business.", BANNER), Spacer(1, 8)]
    s.append(_p("Credit-readiness summary", H1))
    if not cf["n_lines"]:
        s.append(_p("No confirmed, dated business entries yet, so there is nothing to summarise."))
    else:
        c = cf["coverage"]
        cur = ", ".join(f"{k} ({CURRENCY_NAME.get(k, k)})" for k in cf["currencies"])
        s.append(_p(f"Designed for lender review · Period {_day(c['first_date'])} to {_day(c['last_date'])} · Currency: {cur}", SUB))
        weeks_total = max(d["weeks_covered"] for d in cf["currencies"].values())
        weeks_with = max(d["weeks_with_sales"] for d in cf["currencies"].values())
        s.append(_p("1. Coverage: how long the records go back", H2))
        kp = [[f"{c['days_covered']} days", str(c["days_with_records"]), f"{weeks_with} of {weeks_total}",
               str(c["months_with_records"]), str(cf["n_lines"])],
              ["first to last record", "days with a record", "weeks with a recorded sale", "months with a record",
               "confirmed records counted"]]
        kt = Table([[_p(x, ParagraphStyle("k", parent=BODY, fontName="Helvetica-Bold", fontSize=13)) for x in kp[0]],
                    [_p(x, SUB) for x in kp[1]]], colWidths=[W / 5] * 5)
        kt.setStyle(TableStyle([("BOX", (0, 0), (-1, -1), 0.5, LINE), ("INNERGRID", (0, 0), (-1, -1), 0.3, LINE)]))
        s += [kt, Spacer(1, 4),
              _p("By source: " + " · ".join(f"{SOURCE_LABEL.get(k, k)} {v}" for k, v in c["records_by_source"].items()), SUB)]
        for cc, d in cf["currencies"].items():
            s.append(_p(f"2. Money in and out per month: {cc} (completed entries only)", H2))
            rows = [["Month", "Money in", "Money out", "Net"]] + [
                [_month(m), _money(cc, v["in"]), _money(cc, v["out"]), _money(cc, v["net"])] for m, v in d["months"].items()]
            s += [_table(rows, [W * .25] * 4, right=(1, 2, 3)), _p("ZMW and ZAR are never converted or mixed.", SUB)]
            s.append(KeepTogether([_p(f"3. How well is the {cc} income backed by records?", H2),
                                   _tier_bar(d["in_share_by_tier"]),
                                   _p("Shown as three separate shares, never merged into one figure. A line the trader edited counts as T3.", SUB)]))
            s.append(KeepTogether([_p(f"4. Consistency: {cc} money in per week", H2), _weeks_chart(d["weekly_in"]),
                                   _p(f"Weekly money in: min {_money(cc, d['weekly_in_min'])} · median {_money(cc, d['weekly_in_median'])} · "
                                      f"max {_money(cc, d['weekly_in_max'])}. A dashed box is a week with no record. Descriptive only, no score.", SUB)]))
        s.append(_p("5. Every line, with its source", H2))
        rows = [["Date", "Counterparty", "Amount", "Tier", "Source", "Entry"]]
        for l in cf["lines"]:
            sign = "+" if l["direction"] == "in" else "-"
            tier = l["tier"] + (" (edited)" if l.get("edited") else "")
            src = SOURCE_LABEL.get(l["source_type"], l["source_type"]) + (f" · {l['txn_id']}" if l.get("txn_id") else "")
            rows.append([_p(_day(l["date"]), CELL), _p(l.get("counterparty") or "", CELL),
                         f"{sign}{_money(l['currency'], l['amount'])}", tier, _p(src, CELL), _p(l["entry_id"], CELL)])
        s.append(_table(rows, [W * .14, W * .22, W * .13, W * .12, W * .26, W * .13], right=(2,)))
        x = cf["exclusions"]
        s += [_p("6. Left out of the figures, and why", H2),
              _p(f"{x['reserved_or_reversed']} reserved or reversed (not completed payments) · {x['personal']} marked personal · "
                 f"{x['undated']} with no date · {x['sum_mismatch_flagged']} whose lines did not add up to their total "
                 "(flagged to the trader; still counted because the trader confirmed them)", SUB)]
    s += [_p("How to read this file", H2)] + [_p(t, SUB) for t in LEGEND]
    s += [Spacer(1, 8), _p("What this file does not provide. " + cf["not_provided"], BODY)]
    footer = cf["footer"]

    def page(canvas, _doc):
        canvas.saveState()
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(MUTE)
        canvas.drawString(15 * mm, 9 * mm, footer[:150])
        canvas.drawRightString(A4[0] - 15 * mm, 9 * mm, f"Page {canvas.getPageNumber()}")
        canvas.restoreState()

    doc.build(s, onFirstPage=page, onLaterPages=page)
    return buf.getvalue()
