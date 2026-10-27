# Scoring rules (frozen with the first hold-out batch)

Implemented in `eval/scoring.py`. Fixed **before** any results are seen. Changing a rule after that needs a `DECISIONS.md` entry saying what changed and why.

- **Unit:** one record file (receipt, SMS, notebook page, voice note). Line items are a secondary metric.
- **Fields scored:** date, amount (total), currency, in_out, status, counterparty, txn_id. A field with no gold label is not scored.
- **amount:** currency symbols, spaces and thousands separators removed; exact match to 0.01.
- **date:** normalised to a calendar day (accepted formats in code); exact day.
- **currency, in_out, status:** exact after case-folding.
- **counterparty:** match if one name's word set contains the other's, or word-set Jaccard ≥ 0.5.
- **txn_id:** exact after removing whitespace and upper-casing.
- **Record correct:** all of date, amount, currency, in_out and status are correct.
- **Reporting (D-09):** for each field and for "record correct": successes/n, accuracy, and a 95% Wilson interval, **split by source** (real-trader / personal proxy / simulated / public benchmark). Never pooled into one headline.
- **Hold-out:** files whose SHA-256 is marked `holdout` in `eval/holdout_manifest.jsonl` are scored once, after the feature freeze (Tue 3 Nov), and that run is reported whatever the result.
- **Baseline:** manual entry, timed and error-checked against the same labels.
