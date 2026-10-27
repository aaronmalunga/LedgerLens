"""Web-chat adapter (D-06): translate HTTP <-> InboundEvent/OutboundMessage, nothing else."""
from __future__ import annotations

import base64
import hashlib
import os
import uuid
from typing import Optional

from fastapi import FastAPI
from pydantic import BaseModel

from ledgerlens.core.events import Channel, InboundEvent, InboundKind
from ledgerlens.core.handler import Core
from ledgerlens.core.store import Store
from ledgerlens.llm.client import make_client

app = FastAPI(title="LedgerLens web chat")
core = Core(Store(os.environ.get("LEDGERLENS_DB", ":memory:")), make_client())


class ChatIn(BaseModel):
    session_id: str
    message_id: Optional[str] = None
    text: Optional[str] = None
    image_b64: Optional[str] = None
    image_mime: Optional[str] = None
    button_id: Optional[str] = None


@app.post("/chat")
def chat(body: ChatIn) -> dict:
    if body.button_id:
        kind = InboundKind.BUTTON_REPLY
    elif body.image_b64:
        kind = InboundKind.IMAGE
    else:
        kind = InboundKind.TEXT
    ev = InboundEvent(
        event_id=body.message_id or uuid.uuid4().hex,
        channel=Channel.WEB,
        user_ref=hashlib.sha256(f"web:{body.session_id}".encode()).hexdigest()[:16],
        kind=kind, text=body.text, button_id=body.button_id,
        media=base64.b64decode(body.image_b64) if body.image_b64 else None,
        media_mime=body.image_mime,
    )
    out = core.handle(ev)
    return {"messages": [m.model_dump(exclude={"attachment"}) for m in out]}
