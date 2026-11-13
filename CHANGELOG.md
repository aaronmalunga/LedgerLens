# Changelog

All notable changes to LedgerLens. Each entry says what changed, why (with the evidence that asked for it), and whether evaluation results changed. Claims follow the labels used in the README: MEASURED, OBSERVED, USER-REPORTED, HYPOTHESIS, INFERENCE.

## [Unreleased] (v2, started 10 Nov 2026)
### Added
- README "Status and history" section separating the frozen hackathon version from ongoing work.
- This changelog.
- Public roadmap for v2: `docs/ROADMAP.md`.
- Archived the README as submitted: `docs/archive/README_v1.0-hackathon.md`.

### Planned (not yet built; order may change with lender and trader feedback)
- Evidence from users: interview with a consenting spaza shop owner (South Africa); lender feedback on the credit file (one Zambian credit officer so far, USER-REPORTED).
- A new evaluation set collected with written consent, with a hold-out frozen before tuning; results reported per source.
- Credit file v2: net cash flow, share of sales backed by third-party records, declared assets, fields for the lender to complete (from lender feedback, USER-REPORTED, n=1).

## [v1.0-hackathon] - 2026-11-04
Submitted to the Meta Global AI Developer Hackathon 2026 (Indie track). Built 27 Oct to 4 Nov 2026.
- Reads receipts, notebook pages, mobile-money SMS and voice notes (Muse Spark 1.3, Muse Voice Transcribe) into a fixed schema; code does the arithmetic and assigns evidence tiers; nothing is saved until the trader confirms.
- Credit file as a web page and PDF; describes, never scores.
- Evaluation with a hold-out frozen in git before tuning; results in `docs/EVALUATION.md`.
- Demo guard (per-IP and global caps), prompt-injection tests, web chat on a free host.
