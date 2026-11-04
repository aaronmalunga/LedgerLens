# LedgerLens: evaluation runs

Every number in the README comes from one of these runs. All were run on 4 Nov 2026 through `Core.handle()`, the same code path as the live demo, with Muse Spark 1.3 at default reasoning effort unless stated. Labels: **MEASURED** = produced by the harness or a timed test; **OBSERVED** = seen; **INFERENCE** = our reasoning.

The records themselves (receipt photos, labels, voice files) are private and are not in this repository. The scoring rules are in [`eval/SCORING.md`](../eval/SCORING.md), the sealed hold-out fingerprints in [`eval/holdout_manifest.jsonl`](../eval/holdout_manifest.jsonl), and the single hold-out run in [`eval/holdout_runs.jsonl`](../eval/holdout_runs.jsonl).

## The data
- **39 records:** 31 of the developer's own receipts from South African and Zambian shops (printed and handwritten, personal details blacked out), 5 simulated notebook pages, 3 simulated voice notes in the developer's own voice.
- **28 files excluded before any run:** quotations, unpaid invoices, illegible photos, non-receipts and a duplicate.
- **Hold-out:** about 20% of each record type, assigned by SHA-256 order, fingerprints committed before any prompt work. Scored once.

## Runs

### E-005: practice set, default reasoning (MEASURED)
- 30 records: 24 own receipts, 4 simulated notebook pages, 2 voice notes.
- Own receipts, n=24:
  - whole record correct 21/24 = 87.5%, 95% interval 69.0% to 95.7%;
  - amount 23/24 = 95.8%;
  - date 18/21 = 85.7%.
- Notebook pages: 3/4.
- Time: p50 16.3 s, p95 27.5 s. Cost: $0.0104 per record (measured tokens x $1.25 / $4.25 per million); $0.28 in total.
- Errors: 3/30. Two were voice notes the laptop could not convert (no ffmpeg installed yet), one answer failed schema validation.
- Error notes: one date had an ambiguous handwritten digit (06 or 26); one handwritten date was not read; a credit-book page listed several debts, which does not fit one total (logged as a limit; the label was not changed).

### E-006: practice set, "minimal" reasoning (MEASURED)
- Same 30 records.
- Own receipts: whole record 19/24 = 79.2% (interval 59.5% to 90.8%); amount 23/24.
- Time: p50 6.4 s (2.5x faster). Cost: $0.0047 per record (55% cheaper).
- 2 calls stalled until the SDK default timeout (600 s each). This led to a 60-second timeout with one retry on every model call.
- Decision: default reasoning kept for accuracy and reliability.

### E-007: voice notes (MEASURED)
- 3 notes, 16 kHz mono WAV: 2 English, 1 "town Nyanja" mixed with English.
- 3/3 whole record correct (interval 43.8% to 100%). Time: p50 11.6 s.
- In the Nyanja note, "money in" was said only in Nyanja and was read correctly (n=1; we claim only that this one note was read correctly).

### E-008: sealed hold-out, scored once (MEASURED)
- 8 records: 7 own receipts, 1 simulated notebook page.
- Own receipts, n=7:
  - whole record correct 5/7 = 71.4%, interval 35.9% to 91.8%;
  - amount 6/7 = 85.7%, interval 48.7% to 97.4%;
  - currency, direction and status 7/7.
- Notebook page: 0/1 (a mixed day with no written total).
- Errors: 0/8 calls failed. Time: p50 10.9 s. Cost: $0.0091 per record.
- Both receipt errors were on photos noted as faded or blurry before the run: cents lost (90 for 90.90), and a wrong year.
- One hold-out label was found to be debatable after the run. It was reported and not changed.

### E-009: prompt injection (MEASURED)
- 6 simulated attacks, 3 written and 3 spoken: change the amount, claim "verified", reveal the prompt.
- 6/6 resisted. This is not a rate (n=6), and it does not prove robustness to unseen attacks.

### E-010: manual-entry baseline (MEASURED)
- A helper who had not seen the records typed 5 fields per record from the same files, timed per record.
- Scored by the same scorer: 9/9 whole record correct, **median 29.2 s** per record (range 20.6 to 35.8 s).
- LedgerLens on the same 9 records (from E-005): 9/9, **median 16.3 s** (range 8.3 to 20.4 s), nothing typed.
- The trader still taps Confirm, which was not timed (INFERENCE: a few seconds).

## What these runs do not show
- Accuracy on real traders' records (none were used, for privacy and consent reasons).
- Mobile-money SMS accuracy (supported in code, not measured).
- Performance on photos that are not financial records (one off-label test invented an amount; see README, Known limits).
