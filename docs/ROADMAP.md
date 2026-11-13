# LedgerLens roadmap

Status: v1.0-hackathon is frozen (tag `v1.0-hackathon`, submitted 4 Nov 2026). This page describes v2, which is being built from user and lender feedback. Items move only when evidence supports them; every change and its reason is logged in [CHANGELOG.md](../CHANGELOG.md).

## What v2 is for
The business question is unchanged: can a small trader turn the records they already keep (notebook pages, receipts, bank or eWallet messages, voice notes) into a ledger a lender will accept, without changing how they work? v2 focuses on spaza shops in South Africa first, because a shop owner and lenders there have agreed to give feedback.

## Principles
- The model proposes; code decides. Arithmetic, matching rules and evidence tiers stay in code.
- Evidence from outside the builder: shop owners and lenders, not only our own labels.
- Evaluation always on: tests and an evaluation on simulated records run on every change; each release reports accuracy per source, cost per record, p50/p95 latency and error rate against a manual baseline.
- Consent first: real records only with written consent, minimal data, deleted when no longer needed.
- Built for low bandwidth: compress on the phone, upload once, process in the background.

## Planned work (order may change with feedback)
| Release | Content | Done when |
|---|---|---|
| v1.1 | Known-limit fixes: accept a bare number when editing an amount; tests set their own environment variables; answer HEAD requests for uptime checks; record type required at the API | Tests pass; limits table in the README updated |
| v2.0-alpha | One interface for model providers; a second provider compared with the first on the simulated set | Comparison table published |
| v2.0-beta | Corroboration: each record is checked for independent support (for example a receipt against a bank message), using plain matching rules first and the model only for unclear cases; credit file v2 with net cash flow, the share of sales backed by third-party records, declared assets, and fields for the lender to complete | Adversarial test cases pass; a lender has reviewed a sample |
| v2.0-rc | Deployment on AWS from infrastructure code, with cost and latency monitoring; consented records from a pilot shop evaluated on a hold-out frozen before tuning | Results published per source |
| v2.0 | Release, case study and a new demo video | All of the above |

## Not planned
- Credit scores or loan advice. LedgerLens describes; the lender decides.
- Moving money or drafting payments.

## Open questions
- WhatsApp as a live channel depends on business verification; until then the WhatsApp adapter is tested against recorded messages and the web chat stays live.
- Data residency for South African records (which AWS Region) will be decided and recorded before any real record is processed in the cloud.
