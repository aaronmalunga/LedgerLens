"""Excel in SA/Zambia locales saves semicolon CSVs with decimal commas. Guard against silent 100x errors."""
import csv
import subprocess
import sys
from pathlib import Path

from eval import csvio
from eval.scoring import norm_amount, norm_date

ROOT = Path(__file__).resolve().parents[1]


def write(path, text, bom=True):
    path.write_text(text, encoding="utf-8-sig" if bom else "utf-8", newline="")


def test_semicolon_file_is_detected_and_decimal_comma_fixed(tmp_path):
    p = tmp_path / "l.csv"
    write(p, "file;amount;date\na.jpeg;349,00;2026/10/12\nb.jpeg;1 234,50;2026-10-14\nc.jpeg;680;2026-10-15\n")
    rows, fields, delim = csvio.read_dicts(p)
    assert delim == ";" and fields == ["file", "amount", "date"]
    assert [r["amount"] for r in rows] == ["349.00", "1234.50", "680"]
    assert str(norm_amount(rows[0]["amount"])) == "349.00"  # not 34900.00


def test_comma_file_is_left_alone(tmp_path):
    p = tmp_path / "l.csv"
    write(p, 'file,amount\na.jpeg,"1,234.50"\nb.jpeg,349.00\n')
    rows, _, delim = csvio.read_dicts(p)
    assert delim == "," and [r["amount"] for r in rows] == ["1,234.50", "349.00"]


def test_slash_iso_date_parses():
    assert str(norm_date("2026/10/12")) == "2026-10-12"
    assert str(norm_date("12/10/2026")) == "2026-10-12"  # day-first still works


def test_freeze_keeps_the_semicolon_delimiter(tmp_path):
    images = tmp_path / "images"
    images.mkdir()
    (images / "a.jpeg").write_bytes(b"A")
    labels = tmp_path / "labels.csv"
    write(labels, "file;type;holdout\na.jpeg;notebook;\n")
    manifest = ROOT / "eval" / "holdout_manifest.jsonl"
    before = manifest.read_text() if manifest.exists() else None
    try:
        r = subprocess.run([sys.executable, str(ROOT / "eval" / "freeze_holdout.py"), "--labels", str(labels),
                            "--images", str(images), "--batch", "t"], capture_output=True, text=True, cwd=tmp_path)
        assert r.returncode == 0, r.stderr
        text = labels.read_text(encoding="utf-8-sig")
        assert text.splitlines()[0] == "file;type;holdout" and ";" in text.splitlines()[1]
    finally:
        if before is None:
            manifest.unlink(missing_ok=True)
        else:
            manifest.write_text(before)
