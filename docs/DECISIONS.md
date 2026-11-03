# LedgerLens: decision log (public summary)

Every significant choice in this build was recorded as a decision with the options considered, the trade-offs, the reasoning, and the condition that would reverse it. This is the public summary; dates are 2026, times SAST.

| # | Decision | Why | Status |
|---|---|---|---|
| D-06 | One channel-agnostic core (`handle(InboundEvent) -> list[OutboundMessage]`); WhatsApp and web chat are thin adapters; the eval harness calls the core directly | The same logic is tested, demoed and evaluated; changing channel means a new adapter, not a rebuild | Accepted 27 Oct, built |
| D-07 | Every ledger line carries an evidence tier: T1 third-party record with a transaction ID, T2 receipt or SMS without one, T3 self-reported (notebook, voice) | A lender needs to know how much income is backed by third-party evidence | Accepted 27 Oct, built |
| D-08 | Code computes the numbers (sums, totals, card holds); the model only extracts and explains | Arithmetic must be deterministic and checkable, not generated | Accepted 27 Oct, built |
| D-09 | Results reported per source with n and a 95% Wilson interval; scoring rules frozen with the hold-out (`eval/SCORING.md`) | Small samples need honest uncertainty; rules cannot move after the results are seen | Accepted 27 Oct, built |
| D-10 | Demo guard: 5 MB image limit, per-user rate limit, daily cost and call caps, a SIMULATED sample ledger | A public link with a paid API behind it must not be drainable | Accepted 27 Oct, built; hardened in D-21 |
| D-11 | The credit file is descriptive (what the records show, with tiers and provenance), never a credit score or a lending recommendation | Scoring people is a regulated, high-stakes decision this build cannot validate | Accepted, built |
| D-12 | While the account runs on free credits, no trader's or relative's real record is sent to the Meta Model API; the eval harness withholds real records unless `--allow-real-data` is passed | Meta's Billing page says content sent on free credits may be used for product improvement; people consented to processing, not to that | Accepted 27 Oct, built; narrowed by D-22 |
| D-13 | A trader's edit to amount or date demotes the line to T3 | An edited figure no longer matches the third-party record | Accepted 27 Oct, built |
| D-14 | The trader declares the record type; the model never chooses the evidence tier | Keeps the tier rule deterministic. Known gap: a mis-declared type raises the tier (see README, Limits) | Accepted 27 Oct, built |
| D-15 | Voice notes in English: only the builder's own voice reading made-up numbers is sent to the API; audio is transcribed in memory and never stored; public web mic off by default | A voice identifies a person; the API terms allow retention and human review | Accepted 29 Oct, built |
| D-16 | Live demo on Render's free tier | $0, deploys from GitHub; accepted trade-off: sleeps after 15 min idle | Accepted 31 Oct; region changed by D-25 |
| D-17 | WhatsApp go/no-go with three gates (outbound template, reply inside 24 h, webhook) and a stop-loss | Find a platform wall early instead of losing build days to it | Closed 2 Nov: no-go. Outbound locked (error 131031) and the test business account unverified; the demo runs on the planned web-chat fallback |
| D-18 | Compare Muse Spark with an open or small model on the same allowed eval set | Cost, latency and accuracy trade-off | Proposed; not run before submission |
| D-19 | WhatsApp used as a test setup only; no business verification for a hackathon test account | No registered business exists for this build | In force |
| D-20 | The platform business profile states only true facts; no identity or company documents sent | Honest representation to the platform; data minimisation | In force |
| D-21 | Demo guard hardening: per-IP limit (30 per 10 min), global cap (60 model calls per hour), proxy-aware client IP | A browser-supplied session ID alone could be bypassed by a script | Accepted 31 Oct, built |
| D-22 | The first eval mixes the developer's own receipts (black-boxed first, sent with his consent) with SIMULATED records; results reported per source | Real-world evidence on the demoed model without sending anyone else's data | Accepted 2 Nov |
| D-23 | The developer's AI coding assistant may view the developer's own black-boxed images to sort receipts from quotations and invoices | Accuracy on handwritten slips; only the developer's own records; already black-boxed | Accepted 3 Nov |
| D-24 | Stress test: do quotations and unpaid invoices get accepted as payments? | A lender's real worry is padded records | Proposed |
| D-25 | Move the live host from Frankfurt to US East | Model calls from the EU host failed with HTTP 404 while the same code worked from South Africa and from US East (OBSERVED 3 Nov) | Accepted 3 Nov |

Claim labels used across the repo: MEASURED, OBSERVED, USER-REPORTED, HYPOTHESIS, INFERENCE. Only MEASURED results are published as results.
