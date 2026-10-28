"""Scoring rules (D-09). Frozen with the first hold-out batch: changing them after seeing hold-out
results would be tuning on the test set. Any change needs a DECISIONS.md entry with the reason."""
from __future__ import annotations

import math
import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Optional

KEY_FIELDS = ("date", "amount", "currency", "in_out", "status")


def norm_amount(v) -> Optional[Decimal]:
    if v is None or str(v).strip() == "":
        return None
    s = re.sub(r"[^\d.\-]", "", str(v).replace(",", ""))
    try:
        return Decimal(s).quantize(Decimal("0.01"))
    except InvalidOperation:
        return None


def norm_date(v) -> Optional[date]:
    if v is None or str(v).strip() == "":
        return None
    if isinstance(v, date):
        return v
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%d/%m/%Y", "%d-%m-%Y", "%d/%m/%y", "%d %b %Y", "%d %B %Y"):
        try:
            return datetime.strptime(str(v).strip(), fmt).date()
        except ValueError:
            continue
    return None



def tokens(v) -> set[str]:
    return set(re.sub(r"[^a-z0-9 ]", " ", str(v or "").lower()).split())


def counterparty_match(pred, gold) -> bool:
    """Match if one name's tokens contain the other's, or token Jaccard >= 0.5."""
    p, g = tokens(pred), tokens(gold)
    if not p or not g:
        return False
    if p <= g or g <= p:
        return True
    return len(p & g) / len(p | g) >= 0.5


def txn_id_match(pred, gold) -> bool:
    clean = lambda s: re.sub(r"\s", "", str(s or "")).upper()
    return clean(pred) != "" and clean(pred) == clean(gold)


def field_correct(field: str, pred, gold) -> Optional[bool]:
    """None = not scored (no gold label for this field)."""
    if gold is None or str(gold).strip() == "":
        return None
    if field == "amount":
        return norm_amount(pred) == norm_amount(gold)
    if field == "date":
        return norm_date(pred) == norm_date(gold)
    if field == "counterparty":
        return counterparty_match(pred, gold)
    if field == "txn_id":
        return txn_id_match(pred, gold)
    return str(pred or "").strip().lower() == str(gold).strip().lower()


def wilson(successes: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """95% Wilson score interval: honest bounds for small n (a 9/10 is not '90% accurate')."""
    if n == 0:
        return (0.0, 0.0)
    p = successes / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return (max(0.0, centre - half), min(1.0, centre + half))
