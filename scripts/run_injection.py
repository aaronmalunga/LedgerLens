"""Runs the six prompt-injection cases (eval/injection.py) against the live Meta model.

Run from the repo root:   python scripts\\run_injection.py
Reads .env like smoke_api.py. Sends ONLY the made-up text in eval/injection.py (6 calls, about $0.05).
Prints one PASS or FAIL line per case, a total, and the time and token counts. The key is never printed.
Cost per call is INFERENCE from token counts and list prices; the pass count is MEASURED on n=6 (not a rate).
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from eval.injection import CASES, judge  # noqa: E402
from eval.run_eval import load_env_file  # noqa: E402
from ledgerlens.llm.client import MetaModelClient  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--env-file", type=Path, default=Path(".env"))
    ap.add_argument("--effort", choices=["minimal", "low", "medium", "high", "xhigh", "max"])
    a = ap.parse_args()
    load_env_file(a.env_file)
    if a.effort:
        os.environ["LEDGERLENS_REASONING_EFFORT"] = a.effort
    if not (os.environ.get("META_API_KEY") or os.environ.get("MODEL_API_KEY")) or not os.environ.get("LEDGERLENS_VISION_MODEL"):
        print("Missing MODEL_API_KEY or LEDGERLENS_VISION_MODEL in .env")
        return 2
    client = MetaModelClient()
    print(f"model asked: {client.vision_model}  effort: {client.reasoning_effort or 'model decides'}")
    passed = 0
    for c in CASES:
        t0 = time.perf_counter()
        try:
            tx = client.extract(media=None, mime=None, text=c.text, source_hint=c.source)
        except Exception as e:
            print(f"ERROR {c.id}: {type(e).__name__}: {e}")
            continue
        ok, why = judge(c, tx)
        passed += ok
        print(f"{'PASS' if ok else 'FAIL'} {c.id:22s} {time.perf_counter() - t0:4.1f}s tokens {client.last_usage}"
              + ("" if ok else "  <- " + "; ".join(why)))
    print(f"\n{passed} of {len(CASES)} cases passed (n={len(CASES)}, SIMULATED). Not a rate: say 'n=6'.")
    return 0 if passed == len(CASES) else 1


if __name__ == "__main__":
    raise SystemExit(main())
