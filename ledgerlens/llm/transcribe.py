"""Speech-to-text clients (D-15). Audio goes in, text comes out, and the audio is not kept by LedgerLens.

Meta's side: the Muse Voice Transcribe terms were read on 29 Oct 2026 and are summarised in EVAL_LOG
section C. Short version: Standard content is not used to train Meta models, but Meta may retain content
(no stated period) and may review it for safety and abuse. That is why only the builder's own voice
reading made-up numbers is ever sent (D-15), and why this module never logs audio or transcripts.
"""
from __future__ import annotations

import json
import os
from typing import Protocol

from .client import assert_standard_model


class Transcriber(Protocol):
    def transcribe(self, wav: bytes) -> str: ...


class MetaVoiceTranscriber:
    """POST {base}/asr/transcribe, multipart: `request` (JSON) + `audio` (WAV). Request shape from the
    Meta docs page "Speech to text" (checked 29 Oct 2026). Not yet run against the live API: see EVAL_LOG."""

    def __init__(self) -> None:
        self.model = os.environ.get("LEDGERLENS_VOICE_MODEL", "muse-voice-transcribe-1.0")
        assert_standard_model(self.model)  # a *-contributor ID is refused, same rule as the text models
        self.base = os.environ.get("META_BASE_URL", "https://api.meta.ai/v1").rstrip("/")
        self.key = os.environ.get("META_API_KEY") or os.environ["MODEL_API_KEY"]
        self.timeout_s = float(os.environ.get("LEDGERLENS_VOICE_TIMEOUT_S", 60))

    def transcribe(self, wav: bytes) -> str:
        import httpx  # imported lazily so tests run without network

        settings = {"mode": "PUSH_TO_TALK", "model": self.model, "audioEncoding": "WAV",
                    "languageBias": ["English"]}  # English only (D-15); a hint, not a lock
        r = httpx.post(
            f"{self.base}/asr/transcribe",
            headers={"Authorization": f"Bearer {self.key}", "Accept": "application/json"},
            files={"request": (None, json.dumps(settings), "application/json"),
                   "audio": ("note.wav", wav, "audio/wav")},
            timeout=self.timeout_s,
        )
        r.raise_for_status()
        return (r.json().get("transcript") or "").strip()


class FakeTranscriber:
    """Offline stand-in for tests and the skeleton. Never touches the network."""

    def __init__(self, text: str = "Sold two bags of mealie meal and one box of soap today, total four hundred and fifty kwacha.") -> None:
        self.text = text
        self.calls = 0

    def transcribe(self, wav: bytes) -> str:
        self.calls += 1
        return self.text


def make_transcriber() -> Transcriber:
    return MetaVoiceTranscriber() if os.environ.get("LEDGERLENS_MODEL_BACKEND") == "meta" else FakeTranscriber()
