"""Voice notes (D-15): audio is transcribed in memory, never stored, and the result is a T3 confirm card."""
import base64
import io
import json
import shutil
import struct
import subprocess
import sys
import types
import wave

import pytest
from fastapi.testclient import TestClient

from ledgerlens.core import audio as audio_in
from ledgerlens.core.events import Channel, InboundEvent, InboundKind, OutboundKind
from ledgerlens.core.guard import Guard, GuardConfig
from ledgerlens.core.handler import Core
from ledgerlens.core.models import SourceType, Transaction
from ledgerlens.core.store import Store
from ledgerlens.llm.client import ContributorModelError, FakeModelClient, MetaModelClient
from ledgerlens.llm.transcribe import FakeTranscriber, MetaVoiceTranscriber

USER = "v1"
MARKER = b"\x7b\x31\x7b\x32\x7b\x33\x7b\x34"  # a byte pattern we can search for in the database


def make_wav(seconds=2.0, rate=16000, channels=1, marker=True) -> bytes:
    n = int(seconds * rate)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(channels)
        w.setsampwidth(2)
        w.setframerate(rate)
        frames = bytearray()
        for i in range(n * channels):
            frames += struct.pack("<h", 800 if (i // 40) % 2 else -800)
        if marker:
            frames[200:200 + len(MARKER)] = MARKER
        w.writeframes(bytes(frames))
    return buf.getvalue()


def audio_ev(eid, data, mime="audio/wav"):
    return InboundEvent(event_id=eid, channel=Channel.EVAL, user_ref=USER, kind=InboundKind.AUDIO,
                        media=data, media_mime=mime)


class SpyModel(FakeModelClient):
    def __init__(self):
        super().__init__(Transaction(date="2026-10-29", direction="in", amount="450", currency="ZMW",
                                     source_type=SourceType.NOTEBOOK))  # wrong type on purpose: core must override
        self.seen = []

    def extract(self, **kw):
        self.seen.append(kw)
        return super().extract(**kw)


def voice_core(**kw):
    model = kw.pop("model", None) or SpyModel()
    tr = kw.pop("transcriber", None) or FakeTranscriber()
    return Core(Store(), model, transcriber=tr, **kw), model, tr


def test_voice_note_becomes_a_t3_confirm_card_with_the_transcript():
    c, model, tr = voice_core()
    out = c.handle(audio_ev("a1", make_wav()))
    assert out[0].kind == OutboundKind.CONFIRM_CARD
    assert "I heard:" in out[0].text and "mealie meal" in out[0].text
    assert "Evidence: T3" in out[0].text  # voice is self-reported (D-07), set by code not by the model
    assert tr.calls == 1


def test_extraction_gets_text_only_never_the_audio():
    c, model, _ = voice_core()
    c.handle(audio_ev("a2", make_wav()))
    seen = model.seen[0]
    assert seen["media"] is None and seen["mime"] is None
    assert seen["source_hint"] == SourceType.VOICE
    assert "Transcript:" in seen["text"] and "Note received on" in seen["text"]


def test_audio_bytes_are_not_stored_anywhere_in_the_database():
    c, _, _ = voice_core()
    wav = make_wav()
    pid = c.handle(audio_ev("a3", wav))[0].buttons[0].id.split(":")[1]
    c.handle(InboundEvent(event_id="a3b", channel=Channel.EVAL, user_ref=USER, kind=InboundKind.BUTTON_REPLY,
                          button_id=f"confirm:{pid}"))
    dump = "\n".join(c.store.db.iterdump())
    # iterdump writes BLOBs as X'HEX' and text as-is, so look for the marker in every form it could take
    needles = [MARKER.hex(), MARKER.hex().upper(), base64.b64encode(MARKER).decode(),
               base64.b64encode(wav[:48]).decode(), "RIFF", "WAVE"]
    assert MARKER in wav  # the marker really is inside the audio we sent
    assert not [n for n in needles if n in dump]
    assert len(c.store.entries(USER)) == 1  # the text ledger entry is what stays
    assert c.store.entries(USER)[0]["tx"]["source_type"] == "voice"


def test_voice_is_off_when_no_transcriber_is_configured():
    model = SpyModel()
    c = Core(Store(), model)
    out = c.handle(audio_ev("a4", make_wav()))
    assert "switched off" in out[0].text and model.seen == []


def test_non_wav_is_refused_without_conversion_and_nothing_is_sent():
    c, model, tr = voice_core()
    out = c.handle(audio_ev("a5", b"OggS" + b"\x00" * 200, "audio/ogg"))
    assert "WAV" in out[0].text and tr.calls == 0 and model.seen == []


@pytest.mark.parametrize("kw", [dict(rate=44100), dict(channels=2)])
def test_wrong_wav_format_is_refused_without_conversion(kw):
    c, _, tr = voice_core()
    out = c.handle(audio_ev("a6", make_wav(**kw)))
    assert out[0].kind == OutboundKind.TEXT and tr.calls == 0


def test_too_long_is_refused(monkeypatch):
    monkeypatch.setenv("LEDGERLENS_MAX_AUDIO_SECONDS", "1")
    c, _, tr = voice_core()
    out = c.handle(audio_ev("a7", make_wav(seconds=2)))
    assert "too long" in out[0].text and tr.calls == 0


def test_silence_or_empty_transcript_is_handled():
    c, model, _ = voice_core(transcriber=FakeTranscriber(text="  "))
    out = c.handle(audio_ev("a8", make_wav()))
    assert out[0].kind == OutboundKind.TEXT and model.seen == []


def test_transcriber_failure_is_a_friendly_message_not_a_crash():
    class Boom:
        def transcribe(self, wav):
            raise RuntimeError("503")
    c, model, _ = voice_core(transcriber=Boom())
    out = c.handle(audio_ev("a9", make_wav()))
    assert "couldn't turn that voice note into text" in out[0].text and model.seen == []


def test_audio_seconds_count_against_the_daily_budget():
    g = Guard(GuardConfig(usd_per_audio_hour=0.18))
    c, _, _ = voice_core(guard=g)
    c.handle(audio_ev("a10", make_wav(seconds=2)))
    assert g.calls == 1 and abs(g.spent_usd - 2 * 0.18 / 3600) < 1e-12


def test_budget_exhausted_blocks_voice_before_any_upload():
    g = Guard(GuardConfig(daily_call_cap=0))
    c, _, tr = voice_core(guard=g)
    out = c.handle(audio_ev("a11", make_wav()))
    assert "usage limit" in out[0].text and tr.calls == 0


# --- the Meta client and prompt ---
def test_meta_transcriber_request_shape(monkeypatch):
    monkeypatch.setenv("META_API_KEY", "k")
    monkeypatch.delenv("LEDGERLENS_VOICE_MODEL", raising=False)
    cap = {}

    class R:
        def raise_for_status(self): pass
        def json(self): return {"transcript": " sold soap ", "audioDurationMs": 2000, "turns": []}

    def post(url, **kw):
        cap.update(url=url, **kw)
        return R()

    monkeypatch.setitem(sys.modules, "httpx", types.SimpleNamespace(post=post))
    assert MetaVoiceTranscriber().transcribe(b"WAVBYTES") == "sold soap"
    assert cap["url"] == "https://api.meta.ai/v1/asr/transcribe"
    assert cap["headers"]["Authorization"] == "Bearer k"
    name, body, ctype = cap["files"]["request"]
    settings = json.loads(body)
    assert ctype == "application/json" and settings["model"] == "muse-voice-transcribe-1.0"
    assert settings["audioEncoding"] == "WAV" and settings["mode"] == "PUSH_TO_TALK"
    assert cap["files"]["audio"][1] == b"WAVBYTES"
    assert "sessionId" not in cap["url"]  # no user identifier goes to Meta


def test_contributor_voice_model_is_refused(monkeypatch):
    monkeypatch.setenv("META_API_KEY", "k")
    monkeypatch.setenv("LEDGERLENS_VOICE_MODEL", "muse-voice-transcribe-1.0-contributor")
    with pytest.raises(ContributorModelError):
        MetaVoiceTranscriber()


def test_voice_prompt_addendum_only_for_voice(monkeypatch):
    cap = {}

    class Completions:
        def create(self, **kw):
            cap.update(kw)
            msg = types.SimpleNamespace(content=json.dumps({"date": "2026-10-29", "direction": "in", "amount": "450",
                                                            "currency": "ZMW", "source_type": "voice"}))
            return types.SimpleNamespace(choices=[types.SimpleNamespace(message=msg)], usage=None)

    class OpenAI:
        def __init__(self, **kw):
            self.chat = types.SimpleNamespace(completions=Completions())

    monkeypatch.setitem(sys.modules, "openai", types.SimpleNamespace(OpenAI=OpenAI))
    monkeypatch.setenv("LEDGERLENS_VISION_MODEL", "muse-spark-1.3")
    monkeypatch.setenv("META_API_KEY", "k")
    m = MetaModelClient()
    m.extract(media=None, mime=None, text="Note received on 2026-10-29. Transcript: sold soap", source_hint=SourceType.VOICE)
    assert "TRANSCRIPT of a spoken note" in cap["messages"][0]["content"]
    m.extract(media=None, mime=None, text="R10 received", source_hint=SourceType.SMS)
    assert "TRANSCRIPT" not in cap["messages"][0]["content"]


# --- conversion (only where the caller opts in) ---
needs_ffmpeg = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")


@needs_ffmpeg
def test_opus_voice_note_converts_when_allowed(tmp_path):
    src = tmp_path / "in.wav"
    src.write_bytes(make_wav(seconds=1.5, rate=24000))
    subprocess.run(["ffmpeg", "-v", "error", "-i", str(src), "-c:a", "libopus", str(tmp_path / "n.ogg")], check=True)
    wav, seconds = audio_in.to_wav((tmp_path / "n.ogg").read_bytes(), allow_conversion=True)
    assert 1.2 < seconds < 1.8
    assert audio_in.wav_info(wav) == (pytest.approx(seconds, abs=0.01), 16000)


@needs_ffmpeg
def test_stereo_44k_wav_converts_when_allowed():
    wav, seconds = audio_in.to_wav(make_wav(seconds=1, rate=44100, channels=2), allow_conversion=True)
    assert audio_in.wav_info(wav)[1] == 16000 and 0.8 < seconds < 1.2


def test_playlist_or_script_is_never_handed_to_ffmpeg():
    for blob in (b"#EXTM3U\nfile:///etc/passwd\n", b"concat:/etc/passwd", b"\x00" * 64):
        with pytest.raises(audio_in.AudioError):
            audio_in.to_wav(blob, allow_conversion=True)


# --- web adapter: voice is off unless the operator switches it on ---
def test_web_voice_is_off_by_default_and_on_when_configured():
    import base64
    from ledgerlens.adapters.web import app as webapp
    client = TestClient(webapp.app)
    body = {"session_id": "sv", "message_id": "w-v1", "audio_b64": base64.b64encode(make_wav()).decode(), "audio_mime": "audio/wav"}
    assert client.get("/config").json()["voice"] is False
    assert "switched off" in client.post("/chat", json=body).json()["messages"][0]["text"]
    webapp.core.transcriber = FakeTranscriber()
    try:
        assert client.get("/config").json()["voice"] is True
        body["message_id"] = "w-v2"
        msgs = client.post("/chat", json=body).json()["messages"]
        assert "I heard:" in msgs[0]["text"]
        assert webapp.core.allow_audio_conversion is False  # public endpoint never shells out to ffmpeg
    finally:
        webapp.core.transcriber = None
