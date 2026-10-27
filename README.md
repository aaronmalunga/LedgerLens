# LedgerLens

**From shoebox records to a lender-ready credit file.**

A WhatsApp-first bookkeeping assistant (with a web-chat fallback) that turns small traders' receipts, mobile-money SMS and voice notes into a credit-readiness summary for informal businesses in Southern Africa. Built for the Meta Global AI Developer Hackathon (Indie track, *Build for Your World*).

> **Status: in development (build window 27 Oct to 4 Nov 2026).** Everything in this repository was written during the hackathon; the first code commit is dated 27 Oct 2026.

## How it works (so far)
- **Channel-agnostic core** (`ledgerlens/core/`): `handle(InboundEvent) -> list[OutboundMessage]`. WhatsApp and web chat are thin adapters; the eval harness calls the core directly. See decision D-06.
- **Nothing is saved without the trader's confirmation.** Each record becomes a confirm card (Confirm / Edit / Reject).
- **Code does the maths** (D-08): line-item sums, totals and the exclusion of card holds are deterministic, not model-generated.
- **Evidence tiers** (D-07): every ledger line is tagged T1 (third-party record with a transaction ID), T2 (receipt or SMS without one) or T3 (self-reported). The summary shows how much income is backed by T1/T2 evidence.
- **Standard Meta models only:** the client refuses any Contributor model ID, so trader data is never used for training.

## Run locally
```bash
pip install -r requirements.txt
python -m pytest -q
uvicorn ledgerlens.adapters.web.app:app --reload   # fake model client by default (see .env.example)
```

## Evaluation
Baseline is manual entry. Scoring rules are frozen in `eval/SCORING.md`; the hold-out is frozen per batch by SHA-256 in `eval/holdout_manifest.jsonl` before any prompt tuning. Record files and labels are never committed (`data/` is git-ignored).

```bash
python -m eval.run_eval --labels data/labels.csv --images data/images                       # dev split through Core.handle()
python -m eval.run_eval --labels data/labels.csv --images data/images --predictions data/baseline.csv   # manual-entry baseline, same scorer
python -m eval.run_eval --labels data/labels.csv --images data/images --split holdout --confirm-holdout  # once, after the freeze
```
The harness prints accuracy per source with n and a 95% Wilson interval, plus error rate, p50/p95 latency and (when prices are supplied) cost per message. Failures count as wrong answers in the same denominator. The hold-out run is logged in `eval/holdout_runs.jsonl`.

## Built with
Meta Model API (Muse Spark; Muse Voice Transcribe and SAM 3.1 planned). Code written with AI coding assistance (Claude); all design decisions are recorded with their reasoning in `DECISIONS.md`.
