"""CSV reading that survives Excel in South African / Zambian regional settings.

Those settings make Excel save with semicolons as the separator and a comma as the decimal mark
("349,00"). Left alone, our reader would see one giant column, or worse read 349,00 as 34,900
(norm_amount treats a comma as a thousands separator). This module:
  - detects the delimiter from the header line (comma or semicolon);
  - when the file uses semicolons, reads a decimal comma in `amount` as a decimal point;
  - lets freeze_holdout write the file back with the SAME delimiter, so Excel keeps opening it cleanly.
Reads utf-8-sig because Excel adds a BOM.
"""
from __future__ import annotations

import csv
import re
from pathlib import Path

_DECIMAL_COMMA = re.compile(r"\s*\d[\d .]*,\d{1,2}\s*")


def detect_delimiter(path: Path) -> str:
    with path.open(encoding="utf-8-sig") as f:
        header = f.readline()
    return ";" if header.count(";") > header.count(",") else ","


def fix_amount(value: str, delimiter: str) -> str:
    """'1 234,50' or '349,00' -> '1234.50' / '349.00', only in semicolon files. Anything else is unchanged."""
    if delimiter == ";" and value and _DECIMAL_COMMA.fullmatch(value):
        return value.replace(" ", "").replace(".", "").replace(",", ".")
    return value


def read_dicts(path: Path) -> tuple[list[dict], list[str], str]:
    delim = detect_delimiter(path)
    with path.open(newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f, delimiter=delim)
        fields = [c.strip() for c in (reader.fieldnames or [])]
        reader.fieldnames = fields
        rows = []
        for r in reader:
            row = {k: (v or "").strip() for k, v in r.items() if k}
            if "amount" in row:
                row["amount"] = fix_amount(row["amount"], delim)
            rows.append(row)
    return rows, fields, delim
