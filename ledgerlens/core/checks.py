"""Deterministic checks on model output (D-08): code does the maths, the model only proposes."""
from __future__ import annotations

from decimal import Decimal

from .models import Transaction, ValidationIssue

TOLERANCE = Decimal("0.01")


def check_transaction(tx: Transaction) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    if tx.amount <= 0:
        issues.append(ValidationIssue(code="non_positive_amount", message="Amount must be above zero."))
    if tx.items:
        line_sum = sum((i.amount for i in tx.items), Decimal("0"))
        if abs(line_sum - tx.amount) > TOLERANCE:
            issues.append(ValidationIssue(
                code="sum_mismatch",
                message=f"Items add up to {line_sum}, but the total says {tx.amount}.",
            ))
    if tx.date is None:
        issues.append(ValidationIssue(code="missing_date", message="No date found."))
    return issues


# LL-002: checks that would make the ledger wrong block a confirm. The rest stay warnings on the card
# (a missing date or an items/total mismatch is shown to the trader, but they can still confirm).
BLOCKING_CODES = frozenset({"non_positive_amount"})


def blocking_issues(tx: Transaction) -> list[ValidationIssue]:
    return [i for i in check_transaction(tx) if i.code in BLOCKING_CODES]


class ConfirmBlocked(Exception):
    """Raised by the store when a pending entry fails a blocking check."""

    def __init__(self, issues: list[ValidationIssue]):
        super().__init__(" ".join(i.message for i in issues))
        self.issues = issues
