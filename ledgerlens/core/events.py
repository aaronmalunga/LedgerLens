"""Channel-neutral messages (D-06). Adapters translate to and from these; the core sees nothing else."""
from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, field_validator

from .models import SourceType


class Channel(str, Enum):
    WHATSAPP = "whatsapp"
    WEB = "web"
    EVAL = "eval"


class InboundKind(str, Enum):
    TEXT = "text"
    IMAGE = "image"
    AUDIO = "audio"
    DOCUMENT = "document"
    BUTTON_REPLY = "button_reply"


class InboundEvent(BaseModel):
    event_id: str = Field(description="Channel message ID, used for idempotent dedupe")
    channel: Channel
    user_ref: str = Field(description="Pseudonymous hash of the sender; never a raw phone number")
    kind: InboundKind
    text: Optional[str] = None
    media: Optional[bytes] = None
    media_mime: Optional[str] = None
    button_id: Optional[str] = None
    source_hint: Optional[SourceType] = Field(
        default=None, description="What the sender says this image is (receipt, notebook, sms). Declared by the person, not guessed by the model.")
    client_ip: Optional[str] = Field(default=None, description="Network address the adapter saw, used only for rate limiting; never stored.")
    received_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


MAX_BUTTONS = 3  # WhatsApp interactive reply-button limit; the core designs to the tightest channel.


class Button(BaseModel):
    id: str
    title: str = Field(max_length=20)


class OutboundKind(str, Enum):
    TEXT = "text"
    CONFIRM_CARD = "confirm_card"
    DOCUMENT = "document"


class OutboundMessage(BaseModel):
    kind: OutboundKind
    text: str
    buttons: list[Button] = Field(default_factory=list)
    attachment: Optional[bytes] = None
    attachment_name: Optional[str] = None

    @field_validator("buttons")
    @classmethod
    def _max_buttons(cls, v: list[Button]) -> list[Button]:
        if len(v) > MAX_BUTTONS:
            raise ValueError(f"at most {MAX_BUTTONS} buttons (WhatsApp limit)")
        return v
