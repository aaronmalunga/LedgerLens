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
