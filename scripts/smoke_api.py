"""One-call check that the Meta Model API key, model name and structured output work.

Run from the repo root:
    python scripts\\smoke_api.py                 # text only: a made-up mobile-money SMS
    python scripts\\smoke_api.py --image path\\to\\simulated_page.jpg   # optional image call

Reads .env (LEDGERLENS_MODEL_BACKEND=meta, MODEL_API_KEY, LEDGERLENS_VISION_MODEL).
Sends ONLY made-up data. Prints the parsed transaction, latency and token counts. The key is never printed.
"""
from __future__ import annotations

import argparse
import mimetypes
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from eval.run_eval import load_env_file  # noqa: E402
from ledgerlens.core.models import SourceType  # noqa: E402
from ledgerlens.llm.client import MetaModelClient  # noqa: E402

SAMPLE_SMS = ("SIMULATED. You have received K250.00 from CHANDA B. Txn ID 99887766. "
              "Date 27/10/2026 14:05. New balance K1,250.00.")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--image", type=Path)
    ap.add_argument("--env-file", type=Path, default=Path(".env"))
    a = ap.parse_args()
    load_env_file(a.env_file)
    missing = [k for k in ("LEDGERLENS_VISION_MODEL",) if not os.environ.get(k)]
    if not (os.environ.get("META_API_KEY") or os.environ.get("MODEL_API_KEY")):
        missing.append("MODEL_API_KEY")
    if missing:
        print("Missing in .env:", ", ".join(missing))
        return 2
    client = MetaModelClient()
    print(f"model: {client.vision_model}  base_url: {client.client.base_url}")
    if a.image:
        media = a.image.read_bytes()
        mime = mimetypes.guess_type(a.image.name)[0] or "image/jpeg"
        args = dict(media=media, mime=mime, text=None, source_hint=SourceType.NOTEBOOK)
    else:
        args = dict(media=None, mime=None, text=SAMPLE_SMS, source_hint=SourceType.SMS)
    t0 = time.perf_counter()
    try:
        tx = client.extract(**args)
    except Exception as e:  # show the provider's message, it names the problem
        print(f"FAILED after {time.perf_counter() - t0:.1f}s: {type(e).__name__}: {e}")
        return 1
    dt = time.perf_counter() - t0
    print(f"OK in {dt:.1f}s; tokens (in, out): {getattr(client, 'last_usage', None)}")
    print(tx.model_dump_json(indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
