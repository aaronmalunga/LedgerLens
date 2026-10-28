"""Web-chat adapter (D-06): translate HTTP <-> InboundEvent/OutboundMessage, nothing else."""
from __future__ import annotations

import base64
import hashlib
import os
import uuid
from typing import Optional

from fastapi import FastAPI
from pathlib import Path

from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from ledgerlens.core.creditfile import build_credit_file
from ledgerlens.core.creditfile_html import render_html
from ledgerlens.core.demo import DEMO_LABEL, demo_history
from ledgerlens.core.events import Channel, InboundEvent, InboundKind
from ledgerlens.core.handler import Core
from ledgerlens.core.models import SourceType
from ledgerlens.core.store import Store
from ledgerlens.llm.client import make_client

CHAT_PAGE = (Path(__file__).parent / "chat.html").read_text(encoding="utf-8")

app = FastAPI(title="LedgerLens web chat")
core = Core(Store(os.environ.get("LEDGERLENS_DB", ":memory:")), make_client())


class ChatIn(BaseModel):
    session_id: str
    message_id: Optional[str] = None
    text: Optional[str] = None
    image_b64: Optional[str] = None
    image_mime: Optional[str] = None
    button_id: Optional[str] = None
    source_hint: Optional[SourceType] = None  # receipt | sms | notebook, declared by the person


@app.get("/", response_class=HTMLResponse)
def home() -> HTMLResponse:
    return HTMLResponse(CHAT_PAGE)


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
        media_mime=body.image_mime, source_hint=body.source_hint,
    )
    out = core.handle(ev)
    return {"messages": [m.model_dump(exclude={"attachment"}) for m in out]}


def _user_ref(session_id: str) -> str:
    return hashlib.sha256(f"web:{session_id}".encode()).hexdigest()[:16]


@app.get("/credit-file/demo", response_class=HTMLResponse)
def credit_file_demo() -> HTMLResponse:
    """The SIMULATED sample file (F12). No model call, no upload, no cost: safe to leave public."""
    return HTMLResponse(render_html(build_credit_file(demo_history()), DEMO_LABEL))


@app.get("/credit-file", response_class=HTMLResponse)
def credit_file(session_id: str) -> HTMLResponse:
    """The signed-in session's own confirmed ledger. Same renderer, same numbers as the 'credit file' chat command."""
    rows = core.store.entries(_user_ref(session_id))
    demo = any(r["source_event_id"].startswith("demo:") for r in rows)
    return HTMLResponse(render_html(build_credit_file(rows), DEMO_LABEL if demo else ""))
