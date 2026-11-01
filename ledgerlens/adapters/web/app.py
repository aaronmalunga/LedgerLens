"""Web-chat adapter (D-06): translate HTTP <-> InboundEvent/OutboundMessage, nothing else."""
from __future__ import annotations

import base64
import hashlib
import os
import uuid
from urllib.parse import quote
from typing import Optional

from fastapi import FastAPI, Request
from pathlib import Path

from fastapi.responses import HTMLResponse, Response
from pydantic import BaseModel

from ledgerlens.core.creditfile import build_credit_file
from ledgerlens.core.creditfile_html import render_html
from ledgerlens.core.creditfile_pdf import render_pdf
from ledgerlens.core.demo import DEMO_LABEL, demo_history
from ledgerlens.core.events import Channel, InboundEvent, InboundKind
from ledgerlens.core.handler import Core
from ledgerlens.core.models import SourceType
from ledgerlens.core.store import Store
from ledgerlens.llm.client import FakeModelClient, make_client
from ledgerlens.llm.transcribe import make_transcriber

CHAT_PAGE = (Path(__file__).parent / "chat.html").read_text(encoding="utf-8")

app = FastAPI(title="LedgerLens web chat")
# Voice on the public web page is OFF unless the operator turns it on (D-15): audio sent to Meta's speech
# endpoint may be retained and reviewed under Meta's terms, so only the builder's own voice goes there.
VOICE_WEB = os.environ.get("LEDGERLENS_VOICE_WEB") == "1"
core = Core(Store(os.environ.get("LEDGERLENS_DB", ":memory:")), make_client(),
            transcriber=make_transcriber() if VOICE_WEB else None)


class ChatIn(BaseModel):
    session_id: str
    message_id: Optional[str] = None
    text: Optional[str] = None
    image_b64: Optional[str] = None
    image_mime: Optional[str] = None
    audio_b64: Optional[str] = None   # WAV recorded in the browser (mono, 16-bit, 16 kHz); never stored
    audio_mime: Optional[str] = None
    button_id: Optional[str] = None
    source_hint: Optional[SourceType] = None  # receipt | sms | notebook, declared by the person


@app.get("/", response_class=HTMLResponse)
def home() -> HTMLResponse:
    return HTMLResponse(CHAT_PAGE)


@app.get("/config")
def config() -> dict:
    """Tells the page which optional inputs this deployment has switched on."""
    return {"voice": core.transcriber is not None,
            # R-13: the canned stand-in model is running, so replies are sample output, not a reading of the photo
            "demo_model": isinstance(core.model, FakeModelClient)}


def client_ip(request: Request) -> str | None:
    """Address used for the per-IP limit (R-02).

    Behind a platform proxy (Render) the socket address is the proxy's, so every visitor would share one
    address. Set LEDGERLENS_PROXY_HOPS=1 there: we then take the entry the proxy itself appended to the
    right of X-Forwarded-For. Entries to its left can be forged by the caller, so they are never used.
    With the default of 0 the header is ignored (local runs, tests).
    """
    hops = int(os.environ.get("LEDGERLENS_PROXY_HOPS", 0))
    if hops > 0:
        parts = [p.strip() for p in request.headers.get("x-forwarded-for", "").split(",") if p.strip()]
        if len(parts) >= hops:
            return parts[-hops]
    return request.client.host if request.client else None


@app.post("/chat")
def chat(body: ChatIn, request: Request) -> dict:
    if body.button_id:
        kind = InboundKind.BUTTON_REPLY
    elif body.audio_b64:
        kind = InboundKind.AUDIO
    elif body.image_b64:
        kind = InboundKind.IMAGE
    else:
        kind = InboundKind.TEXT
    ev = InboundEvent(
        event_id=body.message_id or uuid.uuid4().hex,
        channel=Channel.WEB,
        user_ref=hashlib.sha256(f"web:{body.session_id}".encode()).hexdigest()[:16],
        kind=kind, text=body.text, button_id=body.button_id,
        media=(base64.b64decode(body.audio_b64) if body.audio_b64
               else base64.b64decode(body.image_b64) if body.image_b64 else None),
        media_mime=body.audio_mime if body.audio_b64 else body.image_mime, source_hint=body.source_hint,
        client_ip=client_ip(request),
    )
    out = core.handle(ev)
    return {"messages": [m.model_dump(exclude={"attachment"}) for m in out]}


def _user_ref(session_id: str) -> str:
    return hashlib.sha256(f"web:{session_id}".encode()).hexdigest()[:16]


@app.get("/credit-file/demo", response_class=HTMLResponse)
def credit_file_demo() -> HTMLResponse:
    """The SIMULATED sample file (F12). No model call, no upload, no cost: safe to leave public."""
    return HTMLResponse(render_html(build_credit_file(demo_history()), DEMO_LABEL, "/credit-file/demo.pdf"))


@app.get("/credit-file", response_class=HTMLResponse)
def credit_file(session_id: str) -> HTMLResponse:
    """The signed-in session's own confirmed ledger. Same renderer, same numbers as the 'credit file' chat command."""
    rows = core.store.entries(_user_ref(session_id))
    demo = any(r["source_event_id"].startswith("demo:") for r in rows)
    return HTMLResponse(render_html(build_credit_file(rows), DEMO_LABEL if demo else "", f"/credit-file.pdf?session_id={quote(session_id)}"))


def _pdf(rows, label: str, name: str) -> Response:
    return Response(render_pdf(build_credit_file(rows), label), media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="{name}"'})


@app.get("/credit-file/demo.pdf")
def credit_file_demo_pdf() -> Response:
    return _pdf(demo_history(), DEMO_LABEL, "ledgerlens-credit-file-SIMULATED.pdf")


@app.get("/credit-file.pdf")
def credit_file_pdf(session_id: str) -> Response:
    rows = core.store.entries(_user_ref(session_id))
    demo = any(r["source_event_id"].startswith("demo:") for r in rows)
    return _pdf(rows, DEMO_LABEL if demo else "", "ledgerlens-credit-file.pdf")
