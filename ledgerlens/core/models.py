"""Ledger domain model. Evidence tiers per D-07."""
from __future__ import annotations

import datetime as dt
from decimal import Decimal
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class Direction(str, Enum):
    IN = "in"    # money received (sale)
    OUT = "out"  # money paid (stock purchase, expense)


class Status(str, Enum):
    COMPLETED = "completed"
    RESERVED = "reserved"  # a card hold: not a completed payment, never counted in totals
    REVERSED = "reversed"


class SourceType(str, Enum):
    RECEIPT = "receipt"
    SMS = "sms"
    NOTEBOOK = "notebook"
    VOICE = "voice"


class EvidenceTier(str, Enum):
    T1 = "T1"  # third-party record with a transaction ID
    T2 = "T2"  # printed receipt or SMS without an ID
    T3 = "T3"  # self-reported: voice note, notebook page


def evidence_tier(source: SourceType, txn_id: Optional[str], edited: bool = False) -> EvidenceTier:
    """Deterministic, not model-decided (D-07 + D-08). A trader-edited amount or date no longer matches the
    third-party record, so the line is self-reported: T3 (D-13, closes review finding F3)."""
    if edited or source in (SourceType.VOICE, SourceType.NOTEBOOK):
        return EvidenceTier.T3
    return EvidenceTier.T1 if txn_id else EvidenceTier.T2


class LineItem(BaseModel):
    description: str
    qty: Optional[Decimal] = None
    amount: Decimal


class Transaction(BaseModel):
    """What extraction proposes. Nothing becomes a ledger entry until the trader confirms it."""
    date: Optional[dt.date] = None
    direction: Direction
    amount: Decimal = Field(description="Total in minor-unit-safe decimal")
    currency: str = Field(pattern=r"^(ZMW|ZAR)$")
    counterparty: Optional[str] = None
    items: list[LineItem] = Field(default_factory=list)
    status: Status = Status.COMPLETED
    txn_id: Optional[str] = None
    source_type: SourceType
    business: bool = True  # business vs personal (open product question; default business)
    edited: bool = False  # set only by the core when the trader changes amount or date; never by the model


class ValidationIssue(BaseModel):
    code: str
    message: str
