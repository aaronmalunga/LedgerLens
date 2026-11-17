# Known issues (code review, 15 Nov 2026)

These were found by reading and running v1.0-hackathon after the hackathon. None is fixed yet. Each will be fixed test-first in v2, and the fixes marked "v2 entry" come before any new feature. The demo holds made-up data only.

Labels: **OBSERVED** means reproduced in a local run. **READ** means found by reading the code and not yet reproduced.

| # | What goes wrong | Where | Evidence | Planned fix | Priority |
|---|---|---|---|---|---|
| 1 | The same record sent twice is saved twice and counted twice | `core/handler.py`, `core/store.py` | OBSERVED: one R100 receipt sent and confirmed twice shows money out 200.00 | Fingerprint each file; warn when reference, or date, amount and counterparty, match an existing line; the trader can override | v2 entry |
| 2 | A zero or negative amount can be confirmed, which flips the totals | `core/handler.py`, `core/checks.py`, `core/store.py` | OBSERVED: editing an amount to -5000 and confirming is accepted | Checks that make a ledger wrong block the confirm; the rest stay warnings | v2 entry |
| 3 | Two quick taps on Confirm could save one record twice | `core/store.py` | READ | Make confirm a single transaction | v2 entry |
| 4 | The top evidence grade is given to any record on which the model reads a reference number; nothing checks that number against a second source | `core/models.py` | READ | Until corroboration exists, the grade means "carries a reference number", not "verified". In v2 the top grade needs a matching independent record | v2 entry |
| 5 | The browser chooses the session identifier, and it appears in the credit-file link | `adapters/web/app.py` | READ | Server-issued sessions with expiry; nothing identifying in links. Required before any real record | Before real data |
| 6 | A message is marked as handled before the work is done, so a retry after a failure would be dropped | `core/handler.py` | READ | Mark handled only after a reply exists. Matters once a channel retries deliveries | Before WhatsApp |
| 7 | Malformed upload data is decoded before its size is checked | `adapters/web/app.py` | READ | Validate and cap size first; answer with a 400 error | Low |

Also missing from v1's evaluation, by the project's own rule that the model must beat a simpler method: a text-recognition-plus-rules baseline. The v1 records are deleted after judging, as promised, so the baseline will be run on the v2 evaluation set, on the same records as the model, before any v2 accuracy figure is published.
