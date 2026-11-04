# LedgerLens

**From shoebox records to a lender-ready credit file.**

[![CI](https://github.com/aaronmalunga/LedgerLens/actions/workflows/ci.yml/badge.svg)](https://github.com/aaronmalunga/LedgerLens/actions/workflows/ci.yml) · MIT licence · Meta Global AI Developer Hackathon, Indie track, *Build for Your World*

Informal traders in Zambia and South Africa already keep records: till slips, receipt books filled in by hand, notebook pages, mobile-money messages, voice notes. Lenders cannot use them, so traders with real trading histories stay "credit invisible". **LedgerLens turns those records, as they are, into a ledger the trader confirms and a credit file a microfinance officer can read**, with every line's source and evidence strength shown. It is a WhatsApp-first design; the live demo runs on its planned web-chat fallback (see [Limits](#limits-and-what-we-would-do-with-more-resources)).

**Live demo:** https://ledgerlens-demo-us.onrender.com/ (send made-up records only; the free host sleeps after 15 minutes, so the first reply can take about a minute) · **Video (3 min):** *link added at submission*

## Results at a glance
All numbers are MEASURED by the evaluation harness on 4 Nov 2026 through the same code path as the demo. n is small: read the 95% interval, not the point estimate.

| What | Result | n | Run |
|---|---|---|---|
| **Sealed hold-out, own real receipts: whole record correct** (date, amount, currency, in/out, status) | **5/7 = 71.4%** [35.9%, 91.8%] | 7 | E-008 (scored once) |
| Sealed hold-out: total amount correct | 6/7 = 85.7% [48.7%, 97.4%] | 7 | E-008 |
| Practice set, own real receipts: whole record / amount | 21/24 = 87.5% [69.0%, 95.7%] / 23/24 = 95.8% | 24 | E-005 |
| Voice notes (own voice, made-up numbers; 2 English, 1 "town Nyanja") | 3/3 correct [43.8%, 100%] | 3 | E-007 |
| Prompt-injection cases (3 written, 3 spoken) | 6/6 passed | 6 | E-009 |
| Latency per record (default effort) | p50 16.3 s (practice), 10.9 s (hold-out) | 30, 8 | E-005, E-008 |
| Cost per record | about $0.01 (measured tokens x $1.25 / $4.25 per M) | 27 | E-005 |
| Reasoning effort "minimal" vs default | 2.5x faster, 55% cheaper, 79.2% vs 87.5% whole-record, 2 stalled calls in 30 | 30 | E-006 vs E-005 |
| Manual-entry baseline (a person typing the same fields) | *pending* | 10 | - |

Receipts are the developer's own (South African and Zambian shops, printed and handwritten), standing in for traders' expense records; they were black-boxed before use. Income-side records are simulated and labelled as such.

## Architecture
![LedgerLens architecture](docs/architecture.svg)

1. **One channel-agnostic core** (`ledgerlens/core/`): `Core.handle(InboundEvent) -> list[OutboundMessage]`. The web chat is a thin adapter; WhatsApp would be a second one. The evaluation harness calls the same `handle()`, so what is measured is what is demoed (D-06).
2. **Meta models extract; code decides.** Muse Spark 1.3 returns a schema-constrained `Transaction`. Line sums, totals and card holds are computed in code (D-08), and the evidence tier is a deterministic rule, never a model output (D-07).
3. **Evidence tiers.** T1 third-party record with a transaction ID; T2 receipt or SMS without one; T3 self-reported (notebook, voice). A trader's edit to amount or date demotes the line to T3 (D-13).
4. **Nothing is saved without the trader.** Each record becomes a confirm card (Confirm / Edit / Reject).
5. **A descriptive credit file** (HTML and PDF): monthly in/out, the share of income backed by T1/T2 evidence, provenance per line, and no credit score (D-11). Example: `/credit-file/demo` on the live site.

## Use of Meta models
| Model | Where | How it is used | Evidence |
|---|---|---|---|
| **Muse Spark 1.3** (Meta Model API) | `ledgerlens/llm/client.py` | Reads receipt photos, handwritten pages and transcripts into a JSON schema (`response_format: json_schema`), temperature 0; standard model only (the client refuses any `*-contributor` ID) | E-005, E-008 |
| Muse Spark reasoning effort | env `LEDGERLENS_REASONING_EFFORT` | Measured default vs minimal on the same 30 records; default chosen for accuracy and reliability | E-006 |
| **Muse Voice Transcribe** (Meta Model API) | `ledgerlens/llm/transcribe.py` | Voice note -> text in memory; audio never stored; text goes through the same confirm card | E-007 |
| Muse Spark Open (open weights, via Baseten) | planned comparison | Same SIMULATED records, side by side (D-18); the route for lenders who must keep data in-country | *in progress* |

**Why Meta's models matter here:** one multimodal model reads print, handwriting and screenshots without a parser per format; schema-constrained output keeps the pipeline deterministic; and Meta's open-weights models give a path to run the same extraction where financial data must stay in-country.

## How it was evaluated
- **Baseline: manual entry**, scored by the same scorer (`--predictions`).
- **Answer key first.** Each record was labelled by a person from the paper record ("label what is written"). Labels drafted with AI help were checked line by line by the developer; that check caught 4 mis-sorted files and 2 misread values before any run.
- **Frozen hold-out.** About 20% of each record type was assigned by SHA-256 order, the fingerprints were committed to git (`eval/holdout_manifest.jsonl`) before any prompt work, and the hold-out was scored once (`eval/holdout_runs.jsonl`). Files later re-boxed for privacy were re-frozen before any run, and that is logged.
- **Reporting rules** (`eval/SCORING.md`, frozen): per source, n and a 95% Wilson interval; simulated and real records never pooled; failures count as wrong in the same denominator; latency p50/p95, error rate and cost per record from measured tokens.
- **Every error explained** in `EVAL_LOG` (kept with the project notes): e.g. a faded receipt lost its cents (90 for 90.90), a blurry one its year; one hold-out label of ours was found to be debatable after the run and was reported, not changed.

Reproduce (needs your own key in `.env` and your own labelled records in `data/`, which is git-ignored):
```bash
python -m eval.run_eval --labels data/labels.csv --images data/images --allow-real-data --price-in 1.25 --price-out 4.25          # practice split
python -m eval.run_eval --labels data/labels.csv --images data/images --split holdout --confirm-holdout --allow-real-data       # once
python scripts/run_injection.py                                                                                                    # 6 injection cases
```

## Security, privacy and governance
| Area | Control |
|---|---|
| Data use on free credits | Meta's Billing page says content sent on free credits may be used for product improvement, so no trader's or relative's record was sent (D-12). Real-record results come only from the developer's own receipts, black-boxed and sent with his consent (D-22). |
| Personal data in images | Names, phone numbers, card digits, signatures and addresses covered with solid boxes before use; image metadata stripped (verified: 0 files with EXIF); a second full-zoom privacy pass before the final freeze. |
| Voice | Only the builder's own voice reading made-up numbers; audio converted and transcribed in memory and never stored (a test checks the database); public web microphone off by default (D-15). |
| Public endpoint | Per-IP limit (30 messages / 10 min), global cap (60 model calls / hour), $3 daily spend cap, 5 MB image and 60 s audio limits, proxy-aware client IP (D-10, D-21). |
| Model safety | Standard models only; schema-constrained output; totals and tiers computed in code, so an injected "this is verified" cannot raise a tier; 6/6 prompt-injection cases passed (E-009, n=6). |
| Operations | 60 s timeout and one retry on model calls; errors logged as class and HTTP status only, never content; API key trimmed and held in the host's secret store. |
| Repository | CI fails if any image, audio, label CSV, database or `.env` file is tracked; real data lives only on the developer's laptop and is deleted after judging (by 16 Nov 2026). |
| Decisions | ~25 decisions recorded with options, trade-offs and reversal conditions: [docs/DECISIONS.md](docs/DECISIONS.md). |

## Limits, and what we would do with more resources
OBSERVED = we saw it; INFERENCE = our reasoning; HYPOTHESIS = not yet checked.

| Area | What happened in this build | What a production version would do |
|---|---|---|
| WhatsApp | Inbound messages reached the Meta test app; outbound failed with error 131031 ("Business account locked"), and the business portfolio stayed unverified after a truthful profile (OBSERVED). No identity or company documents were submitted for a test account, so the demo uses the planned web-chat fallback (D-17). | Register the business, complete verification, add the WhatsApp adapter over the same core with webhook signature checks. |
| Data use on free credits | See Security. Income-side and voice results use simulated records. | Paid account; confirm in Meta's terms whether paid usage excludes content from product improvement (HYPOTHESIS); then consented trader records. |
| Evaluation size | 39 records; 7 real receipts in the hold-out, so intervals are wide. Mobile-money SMS is supported in code but **not yet measured**. No real trader income records. | A consented pilot with traders: 30+ records per source, income side, SMS, results by photo condition. |
| Languages | English, plus one "town Nyanja" note (code-switched with English) read correctly, including money-in said only in Nyanja (n=1). Urban speech in Southern Africa usually mixes languages; KZN and Gauteng Zulu differ. | Test per language and region, scoring locally spoken fields separately. |
| One record per photo | Credit-book pages and mixed sales/expense days do not fit one total (one hold-out error came from this). | A multi-entry record type. |
| Evidence tier depends on the declared record type | A handwritten page sent as "Receipt" got T2 instead of T3 (OBSERVED). | Flag a mismatch between the declared type and the image. |
| Hosting region | From Frankfurt (EU) every model call returned HTTP 404; the same code worked from South Africa and from US East (OBSERVED, 3 Nov). The live demo runs in US East (D-25). | Check where each AI service is offered before choosing a region; keep a second region ready. |
| Live host | Free tier sleeps after 15 min (about 1 min to wake); its disk is wiped on restart, so demo entries are temporary. | Paid instance and a managed database with deletion controls. |
| Lender acceptance | Designed with input from a Zambian microfinance officer; no lender has used a file yet (INFERENCE that it would help). | Pilot: measure review time per credit file. |

## Run locally
```bash
pip install -r requirements.txt          # Python 3.12+; ffmpeg for voice files other than 16 kHz WAV
python -m pytest -q                      # 104 tests
uvicorn ledgerlens.adapters.web.app:app --reload   # fake model by default; set LEDGERLENS_MODEL_BACKEND=meta and a key (see .env.example)
```

## Repository map
| Path | What it holds |
|---|---|
| `ledgerlens/core/` | Core logic: handler, models, checks, evidence tiers, guard, audio, store, credit file (HTML, PDF) |
| `ledgerlens/llm/` | Meta model clients (extraction, transcription) |
| `ledgerlens/adapters/web/` | FastAPI app and chat page |
| `eval/` | Harness, frozen scoring rules, hold-out manifest and run log, injection cases |
| `scripts/` | API smoke test, injection runner |
| `tests/` | 104 automated tests |
| `docs/` | Decision log, architecture diagram |

## Built during the hackathon
Before 27 Oct 2026 the repository held only an empty README; all code, evaluation and data work was done between 27 Oct and 4 Nov 2026. Code was written with AI coding assistance (Claude); every design decision and every error is recorded with its reasoning.
