"""Freeze the hold-out, batch by batch (P2, accepted 27 Oct).

Usage (from the repo root; data/ is git-ignored and never committed):
    python eval/freeze_holdout.py --labels data/labels.csv --images data/images --batch b1
    python eval/freeze_holdout.py ... --batch b5 --all-holdout   # late batch, after tuning ends

What it does:
  1. Hashes each record file (SHA-256 of the bytes). File names are NOT stored: they may hold names.
  2. Skips files already in the manifest (each file is frozen exactly once).
  3. Per record type, tops the hold-out up so it is ~20% of everything seen of that type so far.
     Which files go to the hold-out is decided by hash order: reproducible, and not chosen by eye.
  4. Appends to eval/holdout_manifest.jsonl (commit this BEFORE tuning on the batch) and writes the
     split back into the labels CSV's `holdout` column.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

MANIFEST = Path(__file__).parent / "holdout_manifest.jsonl"
FRACTION = 0.2


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_manifest(path: Path = MANIFEST) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def assign(new: dict[str, str], existing: list[dict], all_holdout: bool = False) -> dict[str, str]:
    """new: {sha: type}. Returns {sha: 'holdout'|'dev'}."""
    if all_holdout:
        return {h: "holdout" for h in new}
    seen = defaultdict(lambda: [0, 0])  # type -> [total, holdout]
    for r in existing:
        seen[r["type"]][0] += 1
        seen[r["type"]][1] += r["split"] == "holdout"
    by_type = defaultdict(list)
    for h, t in new.items():
        by_type[t].append(h)
    out = {}
    for t, hashes in by_type.items():
        total, held = seen[t]
        total += len(hashes)
        target = round(total * FRACTION)
        need = max(0, min(len(hashes), target - held))
        for i, h in enumerate(sorted(hashes)):
            out[h] = "holdout" if i < need else "dev"
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--labels", required=True, type=Path)
    ap.add_argument("--images", required=True, type=Path)
    ap.add_argument("--batch", required=True)
    ap.add_argument("--all-holdout", action="store_true")
    a = ap.parse_args()

    with a.labels.open(newline="", encoding="utf-8-sig") as f:  # utf-8-sig: Excel saves a BOM that breaks the `file` header
        rows = list(csv.DictReader(f))
        fields = list(rows[0].keys()) if rows else []
    file_type = {r["file"]: r["type"] for r in rows}
    file_hash = {fn: sha256(a.images / fn) for fn in file_type}

    existing = load_manifest()
    frozen = {r["sha256"]: r["split"] for r in existing}
    new = {h: file_type[fn] for fn, h in file_hash.items() if h not in frozen}
    split = assign(new, existing, a.all_holdout)

    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with MANIFEST.open("a", encoding="utf-8") as m:
        for h, s in split.items():
            m.write(json.dumps({"sha256": h, "type": new[h], "split": s, "batch": a.batch, "frozen_at": now}) + "\n")
    frozen.update(split)

    for r in rows:
        r["holdout"] = "Y" if frozen[file_hash[r["file"]]] == "holdout" else "N"
    with a.labels.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)

    held = sum(1 for s in split.values() if s == "holdout")
    print(f"batch {a.batch}: {len(split)} new files, {held} to hold-out, {len(split) - held} to dev. "
          f"Commit eval/holdout_manifest.jsonl now, before any tuning.")


if __name__ == "__main__":
    main()
