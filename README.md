# LedgerLens

**From shoebox records to a lender-ready credit file.**

A WhatsApp-first bookkeeping assistant that turns small traders' receipts, notebook pages, mobile-money SMS and voice notes into a credit-readiness summary for informal businesses in Zambia and South Africa. Built for the Meta Global AI Developer Hackathon (Indie track, *Build for Your World*).

> **Channel status for this submission:** WhatsApp is the intended channel, because it is where traders already keep their records. During the build, Meta's test account blocked outgoing messages (error 131031) and the business account stayed unverified, so the WhatsApp channel could not go live in time. The live demo therefore runs on the web-chat fallback we planned from the start. It uses the same core, so moving to WhatsApp needs a new adapter, not a rebuild (see *Limits*).

> **Status: in development (build window 27 Oct to 4 Nov 2026).** Everything in this repository was written during the hackathon; the first code commit is dated 27 Oct 2026.

## How it works (so far)
- **Channel-agnostic core** (`ledgerlens/core/`): `handle(InboundEvent) -> list[OutboundMessage]`. Web chat is the adapter that ships today; WhatsApp is the planned second adapter over the same core (not built, see *Limits*). The eval harness calls the core directly. See decision D-06.
- **Nothing is saved without the trader's confirmation.** Each record becomes a confirm card (Confirm / Edit / Reject).
- **Code does the maths** (D-08): line-item sums, totals and the exclusion of card holds are deterministic, not model-generated.
- **Evidence tiers** (D-07): every ledger line is tagged T1 (third-party record with a transaction ID), T2 (receipt or SMS without one) or T3 (self-reported). The summary shows how much income is backed by T1/T2 evidence.
- **Voice notes, English only (D-15):** the browser records a note, the core transcribes it in memory with Muse Voice Transcribe, discards the audio, and sends only the text through the same confirm card (tier T3). Audio is never stored by LedgerLens (a test checks the database). Meta's terms allow it to retain and review content, so only the builder's own voice reading made-up numbers is sent, and the public web mic is off unless the operator sets `LEDGERLENS_VOICE_WEB=1`.
- **Standard Meta models only:** the client refuses any Contributor model ID, so trader data is never used for training.

## Limits, and what we would do with more resources
Every item is labelled: OBSERVED (we saw it), INFERENCE (our reasoning), HYPOTHESIS (not yet checked).

| Area | What happened in this build | What a production version would do |
|---|---|---|
| WhatsApp | Inbound messages reached the Meta test app, but outbound messages failed with error 131031 ("Business account locked") on 30 and 31 Oct, and the business portfolio stayed **unverified** after a truthful profile was completed (OBSERVED, 2 Nov). We did not submit identity or company documents for a hackathon test account. So the demo moved to the planned web-chat fallback (decision D-17). | Register the business, complete Meta business verification, then add the WhatsApp adapter over the same core, with webhook signature checks and service-message billing in place. |
| Data use on free credits | Meta's Billing page says content sent while using free credits may be used for product improvement. So no trader's or relative's record was sent to the API (D-12). Real-record results come only from the developer's own receipts, black-boxed first and sent with his consent (D-22). Income-side and voice results use simulated records, labelled as such. | Run on a paid account and confirm in Meta's written terms whether paid usage excludes content from product improvement (HYPOTHESIS: not verified in this build), then lift the gate for consented trader records. |
| Evaluation size | A small eval set built during the week (counts and 95% intervals in *Results*). No real trader income records. | A consented pilot with traders and a lender, a larger hold-out, and results by record type and photo condition. |
| Languages | English only. Bemba and Nyanja are not supported by the speech model we used (OBSERVED in the model docs, 29 Oct). | Add local-language speech and text once a model supports them, and evaluate each language separately. |
| Lender acceptance | The credit-file design is informed by conversations with a Zambian microfinance officer; no lender has accepted a file (INFERENCE that it would be useful; not tested). | Pilot with a lender and measure whether files shorten their review. |

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
Real (non-simulated) records are withheld from the model API unless `--allow-real-data` is passed (D-12: the free-credit terms say content may be used for product improvement). The harness prints accuracy per source with n and a 95% Wilson interval, plus error rate, p50/p95 latency and (when prices are supplied) cost per message. Failures count as wrong answers in the same denominator. The hold-out run is logged in `eval/holdout_runs.jsonl`.

## Built with
Meta Model API (Muse Spark; Muse Voice Transcribe built, not yet run against the live API; SAM 3.1 planned). Code written with AI coding assistance (Claude); all design decisions are recorded with their reasoning in `DECISIONS.md`.
