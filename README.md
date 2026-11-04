<p align="center"><img src="docs/banner.svg" alt="LedgerLens: from shoebox records to a lender-ready credit file" width="100%"></p>

<p align="center">
<a href="https://ledgerlens-demo-us.onrender.com/"><img src="https://img.shields.io/badge/live%20demo-open-1E5E5B?style=flat-square" alt="Live demo"></a>
<a href="https://youtu.be/nxw78IfoQV0"><img src="https://img.shields.io/badge/demo%20video-3%20min-B08A1E?style=flat-square" alt="Demo video"></a>
<a href="https://github.com/aaronmalunga/LedgerLens/actions/workflows/ci.yml"><img src="https://img.shields.io/github/actions/workflow/status/aaronmalunga/LedgerLens/ci.yml?branch=main&style=flat-square&label=tests&color=1E5E5B" alt="Tests"></a>
<a href="LICENSE"><img src="https://img.shields.io/badge/licence-MIT-0F2A24?style=flat-square" alt="MIT licence"></a>
</p>

<p align="center">
<a href="#the-problem">Problem</a> &nbsp;·&nbsp;
<a href="#how-it-works">How it works</a> &nbsp;·&nbsp;
<a href="#results">Results</a> &nbsp;·&nbsp;
<a href="#use-of-meta-models">Meta models</a> &nbsp;·&nbsp;
<a href="#how-it-was-evaluated">Evaluation</a> &nbsp;·&nbsp;
<a href="#security-privacy-and-governance">Security</a> &nbsp;·&nbsp;
<a href="#known-limits">Limits</a> &nbsp;·&nbsp;
<a href="#run-it-locally">Run locally</a> &nbsp;·&nbsp;
<a href="docs/DECISIONS.md">Decisions</a>
</p>

---

**LedgerLens turns the records small traders already keep into a ledger the trader confirms and a credit file a lender can read.** A trader sends a photo of a receipt or notebook page, a mobile-money SMS, or a voice note. Meta's Muse Spark 1.3 reads it, code checks the arithmetic and grades the evidence, and nothing is saved until the trader confirms. The result is a descriptive credit file that shows where every number came from.

Meta Global AI Developer Hackathon 2026 · Indie track · *Build for Your World*

| Try it | |
|---|---|
| **Live demo** | [ledgerlens-demo-us.onrender.com](https://ledgerlens-demo-us.onrender.com/). Send made-up records only. The free host sleeps after 15 minutes, so the first reply can take about a minute. |
| **Sample credit file** | [/credit-file/demo](https://ledgerlens-demo-us.onrender.com/credit-file/demo) (simulated trader), with a PDF download |
| **Demo video** | [3 minutes on YouTube](https://youtu.be/nxw78IfoQV0) |

## The problem
Spaza shops in South Africa and ka-ntemba kiosks in Zambia keep records: receipt books, till slips, notebooks, mobile-money messages, voice notes. Lenders cannot use them, so traders with real trading histories stay credit-invisible.

- 76% of Zambia's employed people work informally (ZamStats Labour Force Survey 2022: 2,496,963 of 3,273,123).
- 5.7 million South Africans are in informal employment (Stats SA, Quarterly Labour Force Survey, Q4 2025).

LedgerLens does not ask the trader to change how they work. It reads what they already have.

## How it works
<p align="center"><img src="docs/architecture.svg" alt="Inputs, channels and the evaluation harness all call one core, which uses Muse Spark 1.3 and Muse Voice Transcribe and writes the ledger and credit file" width="100%"></p>

1. **One core for every channel.** `Core.handle(InboundEvent) -> list[OutboundMessage]` in `ledgerlens/core/`. The web chat is a thin adapter, WhatsApp would be a second one, and the evaluation harness calls the same `handle()`. What is measured is what is demoed (D-06).
2. **The model reads; code decides.** Muse Spark 1.3 returns a schema-constrained `Transaction`. Line sums and totals are computed in code (D-08), and the evidence tier is a deterministic rule, never a model output (D-07).
3. **Evidence tiers.** **T1**: a third-party record with a transaction ID. **T2**: a receipt, or an SMS without an ID. **T3**: self-reported (notebook, voice). If the trader edits an amount or date, the line becomes T3 (D-13).
4. **The trader confirms.** Every record becomes a card with Confirm, Edit and Reject.
5. **A descriptive credit file** (web page and PDF): monthly money in and out, the share of income backed by T1 and T2 evidence, and the source of every line. It gives no score and no loan advice (D-11).

## Results
All numbers are MEASURED by the evaluation harness on 4 Nov 2026, through the same code path as the demo. Samples are small, so the 95% Wilson interval matters more than the point estimate.

| What | Result | n | Run |
|---|---|---|---|
| **Sealed hold-out, real receipts: whole record correct** (date, amount, currency, direction, status) | **5/7 = 71.4%** [35.9%, 91.8%] | 7 | E-008, scored once |
| Sealed hold-out: total amount correct | 6/7 = 85.7% [48.7%, 97.4%] | 7 | E-008 |
| Practice set, real receipts: whole record / amount | 21/24 = 87.5% [69.0%, 95.7%] / 23/24 = 95.8% | 24 | E-005 |
| Voice notes (2 English, 1 "town Nyanja" mixed with English) | 3/3 [43.8%, 100%] | 3 | E-007 |
| Prompt-injection attacks (3 written, 3 spoken) | 6/6 resisted | 6 | E-009 |
| **Against manual entry:** a person typing the same 5 fields | person: 9/9, **median 29 s** per record; LedgerLens: 9/9, **median 16.3 s**, nothing typed | 9 | E-010 vs E-005 |
| Latency per record | p50 16.3 s, p95 27.5 s (practice); p50 10.9 s (hold-out) | 30, 7 | E-005, E-008 |
| Errors | 0/7 on the hold-out; 3/30 in practice (2 were a missing audio tool on the laptop) | | E-005, E-008 |
| Cost per record | about $0.01 (measured tokens x $1.25 / $4.25 per million); $0.28 for the whole practice run | 27 | E-005 |
| Reasoning effort "minimal" vs default | 2.5x faster, 55% cheaper, but 79.2% vs 87.5% whole record and 2 stalled calls in 30; default kept | 30 | E-006 vs E-005 |

The receipts are the developer's own, from South African and Zambian shops, printed and handwritten, black-boxed before use. They stand in for traders' expense records. Income-side records are simulated and labelled SIMULATED.

## Use of Meta models
| Model | Where | How it is used | Evidence |
|---|---|---|---|
| **Muse Spark 1.3** (Meta Model API) | `ledgerlens/llm/client.py` | Reads receipt photos, handwritten pages and transcripts into a JSON schema (`response_format: json_schema`), temperature 0. Standard model only: the client refuses any `*-contributor` ID. | E-005, E-008 |
| Muse Spark reasoning effort | `LEDGERLENS_REASONING_EFFORT` | Default and minimal measured on the same 30 records; default chosen for accuracy and reliability | E-006 |
| **Muse Voice Transcribe** (Meta Model API) | `ledgerlens/llm/transcribe.py` | Voice note to text, in memory; the audio is never stored; the text goes through the same confirm card. Read a code-switched Nyanja note correctly, including "money in" said only in Nyanja. | E-007 |
| Meta AI | demo video | The two shop illustrations, labelled as AI-generated | |
| Muse Spark Open (open weights) | not run | Planned side-by-side on the same simulated records (D-18); the one-time hackathon key for the hosted endpoint expired before use. It remains the route for lenders who must keep data in-country. | roadmap |

**Why Meta's models fit:** one multimodal model reads print, handwriting and screenshots without a parser per format. Schema-constrained output keeps the pipeline deterministic enough to test and audit. Open weights give a path to run the same extraction where financial data must stay in-country (POPIA in South Africa, the Data Protection Act in Zambia).

## How it was evaluated
- **Baseline: manual entry.** A helper who had not seen the records typed the same fields from the same files, scored by the same scorer.
- **Answer key first.** Every record was labelled by a person from the paper record before any run. Labels drafted with AI help were checked line by line; that check caught 4 mis-sorted files and 2 misread values.
- **Sealed hold-out.** About 20% of each record type was assigned by SHA-256 order. The fingerprints were committed to git (`eval/holdout_manifest.jsonl`) before any prompt work, and the hold-out was scored once (`eval/holdout_runs.jsonl`). Files re-boxed later for privacy were re-frozen before any run, and that is logged.
- **Reporting rules** (`eval/SCORING.md`, frozen): per source, n and a 95% Wilson interval; simulated and real records never pooled; failures count as wrong in the same denominator; latency, error rate and cost from measured values.
- **Every error explained.** For example, a faded receipt lost its cents (90 for 90.90) and a blurry one its year. One hold-out label of ours was found to be debatable after the run; it was reported, not changed.

Reproduce (needs your own key in `.env` and your own labelled records in `data/`, which git ignores):
```bash
python -m eval.run_eval --labels data/labels.csv --images data/images --allow-real-data --price-in 1.25 --price-out 4.25
python -m eval.run_eval --labels data/labels.csv --images data/images --split holdout --confirm-holdout --allow-real-data
python scripts/run_injection.py
```

## Security, privacy and governance
| Area | Control |
|---|---|
| Data use on free credits | Meta's Billing page says content sent on free credits may be used for product improvement, so no trader's or relative's record was sent (D-12). Real-record results come only from the developer's own receipts, black-boxed and sent with his consent (D-22). |
| Personal data in images | Names, phone numbers, card digits, signatures and addresses covered with solid boxes; image metadata stripped (0 files with EXIF); a second full-zoom privacy pass before the final freeze. |
| Voice | Only the developer's own voice reading made-up numbers; audio transcribed in memory and never stored (a test checks the database); the public web microphone is off (D-15). |
| Public endpoint | 30 messages per 10 minutes per IP, 60 model calls per hour in total, a $3 daily spend cap, 5 MB image and 60 s audio limits (D-10, D-21). |
| Model safety | Standard models only; schema-constrained output; totals and tiers computed in code, so an injected "this is verified" cannot raise a tier; 6/6 injection cases resisted (E-009). |
| Operations | 60 s timeout and one retry on model calls; errors logged as class and HTTP status only, never content; the API key lives in the host's secret store. |
| Repository | CI fails if any image, audio, label file, database or `.env` file is tracked. Real data stays on the developer's laptop and is deleted after judging. |
| Decisions | About 25 decisions recorded with options, trade-offs and reversal conditions: [docs/DECISIONS.md](docs/DECISIONS.md). |

## Known limits
OBSERVED: seen in this build. INFERENCE: our reasoning. HYPOTHESIS: not yet checked.

| Area | What happened | What a production version would do |
|---|---|---|
| WhatsApp | Inbound messages reached the Meta test app; outbound failed with error 131031 ("Business account locked") and the business stayed unverified (OBSERVED). The demo runs on the planned web-chat fallback (D-17). | Register the business, complete verification, add the WhatsApp adapter over the same core. |
| Evaluation size | 39 records; 7 real receipts in the hold-out, so intervals are wide. Mobile-money SMS is supported but not yet measured. No real trader income records. | A consented pilot: 30+ records per source, income side included. |
| Off-label images | A social-media screenshot produced an invented amount (R15) with tier T2. The sum check warned, and nothing is saved unless the trader confirms (OBSERVED, n=1). Prompts were not changed after the hold-out was scored. | An "is this a financial record?" field, evaluated on a set of non-records. |
| Editing | After Edit, the chat expects `amount 40`. A bare `40`, or the example copied with its quote marks, is not understood (OBSERVED). | Accept a bare number, strip quotes, offer tappable choices. |
| Declared record type | A handwritten page sent as "Receipt" got T2 instead of T3 (OBSERVED). | Flag a mismatch between the declared type and the image. |
| One record per photo | Credit-book pages and mixed sales/expense days do not fit one total (one hold-out error). | A multi-entry record type. |
| Languages | English plus one town Nyanja note (n=1). Urban speech mixes languages, and regions differ. | Test per language and region. |
| Hosting region | From Frankfurt every model call returned HTTP 404; from South Africa and US East it worked (OBSERVED). The demo runs in US East (D-25). | Check where each AI service is offered before choosing a region. |
| Live host | Free tier sleeps after 15 minutes and wipes its disk on restart, so demo entries are temporary. | A paid instance and a managed database with deletion controls. |
| Lender acceptance | Designed with input from a Zambian microfinance officer; no lender has used a file yet (INFERENCE). | A pilot that measures review time per credit file. |

## Run it locally
```bash
pip install -r requirements.txt                    # Python 3.12+; ffmpeg for voice files other than 16 kHz WAV
python -m pytest -q                                # 104 tests
uvicorn ledgerlens.adapters.web.app:app --reload   # sample replies by default; set LEDGERLENS_MODEL_BACKEND=meta and a key (see .env.example)
```

## Repository map
| Path | What it holds |
|---|---|
| `ledgerlens/core/` | Handler, models, checks, evidence tiers, guard, audio, store, credit file (HTML and PDF) |
| `ledgerlens/llm/` | Meta model clients for extraction and transcription |
| `ledgerlens/adapters/web/` | FastAPI app and chat page |
| `eval/` | Harness, frozen scoring rules, hold-out manifest and run log, injection cases |
| `scripts/` | API smoke test, injection runner |
| `tests/` | 104 automated tests |
| `docs/` | Decision log, architecture diagram, banner, logo |

## Built during the hackathon
Before 27 Oct 2026 the repository held only an empty README. All code, evaluation and data work was done between 27 Oct and 4 Nov 2026, with AI coding assistance (Claude). Every design decision and every error is recorded with its reasoning.

Licence: [MIT](LICENSE) · Aaron Malunga
