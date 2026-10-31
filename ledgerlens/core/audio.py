"""Audio intake for voice notes (D-15): validate, optionally convert, measure. Nothing here stores audio.

Meta's speech endpoint takes RIFF/WAVE, mono, 16-bit PCM, 16 or 24 kHz (docs, checked 29 Oct 2026).
The web page records in that format in the browser, so the public endpoint never needs ffmpeg.
Other formats (WhatsApp voice notes are OGG/Opus, phone recorders give M4A) are converted with ffmpeg
only when the caller opts in (`allow_conversion`): the eval harness and the future WhatsApp adapter do,
the public web endpoint does not, because parsing untrusted media is an attack surface.
"""
from __future__ import annotations

import io
import os
import shutil
import subprocess
import wave

ACCEPTED_RATES = (16000, 24000)


class AudioError(ValueError):
    """The voice note cannot be used. `code` picks the message the trader sees."""

    def __init__(self, code: str, detail: str = "") -> None:
        super().__init__(f"{code}: {detail}" if detail else code)
        self.code = code


MESSAGES = {
    "unsupported": ("I can't open that audio format here. Please record the note again with the microphone "
                    "button, or send it as a WAV file."),
    "too_long": "That voice note is too long. Please keep it under {max_s} seconds.",
    "empty": "I couldn't hear anything in that voice note. Please try again closer to the microphone.",
    "no_converter": ("I can only take WAV voice notes in this setup. Please use the microphone button "
                     "or send a WAV file."),
}


def max_seconds() -> int:
    return int(os.environ.get("LEDGERLENS_MAX_AUDIO_SECONDS", 60))


def user_message(err: AudioError) -> str:
    return MESSAGES.get(err.code, MESSAGES["unsupported"]).format(max_s=max_seconds())


def is_riff_wave(data: bytes) -> bool:
    return len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WAVE"


def wav_info(data: bytes) -> tuple[float, int]:
    """Seconds and sample rate of a WAV that meets Meta's format. Raises AudioError otherwise."""
    try:
        with wave.open(io.BytesIO(data), "rb") as w:
            ok = (w.getnchannels() == 1 and w.getsampwidth() == 2 and w.getframerate() in ACCEPTED_RATES
                  and w.getcomptype() == "NONE")
            frames, rate = w.getnframes(), w.getframerate()
    except (wave.Error, EOFError):
        raise AudioError("unsupported", "not a readable PCM WAV")
    if not ok:
        raise AudioError("unsupported", "WAV is not mono 16-bit PCM at 16 or 24 kHz")
    return frames / rate, rate


# Containers we are willing to hand to ffmpeg. Anything else (playlists, scripts, unknown) is refused
# before ffmpeg sees it; ffmpeg is also told to read from the pipe only.
def _sniff_container(d: bytes) -> bool:
    return (d[:4] == b"OggS" or d[4:8] == b"ftyp" or d[:3] == b"ID3" or d[:4] == b"fLaC"
            or d[:4] == b"RIFF" or d[:4] == b"\x1aE\xdf\xa3" or (len(d) > 2 and d[0] == 0xFF and d[1] & 0xE0 == 0xE0))


def to_wav(data: bytes, *, allow_conversion: bool) -> tuple[bytes, float]:
    """Returns (wav_bytes, seconds) in Meta's format, or raises AudioError. Pure function: stores nothing."""
    if is_riff_wave(data):
        try:
            seconds, _ = wav_info(data)
            return _bounded(data, seconds)
        except AudioError:
            if not allow_conversion:
                raise  # e.g. stereo or 44.1 kHz WAV: needs conversion, which this caller did not opt into
    elif not allow_conversion:
        raise AudioError("no_converter")
    if not _sniff_container(data):
        raise AudioError("unsupported", "unrecognised container")
    exe = shutil.which("ffmpeg")
    if not exe:
        raise AudioError("no_converter", "ffmpeg not installed")
    limit = max_seconds()
    try:
        p = subprocess.run(
            [exe, "-v", "error", "-nostdin", "-protocol_whitelist", "pipe", "-i", "pipe:0",
             "-t", str(limit + 1), "-vn", "-ac", "1", "-ar", "16000", "-f", "s16le", "pipe:1"],
            input=data, capture_output=True, timeout=30, check=False)
    except subprocess.TimeoutExpired:
        raise AudioError("unsupported", "conversion timed out")
    if p.returncode != 0 or not p.stdout:
        raise AudioError("unsupported", "ffmpeg could not decode")
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:  # raw PCM -> a seekable WAV with a correct header
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16000)
        w.writeframes(p.stdout)
    wav = buf.getvalue()
    return _bounded(wav, len(p.stdout) / 2 / 16000)


def _bounded(wav: bytes, seconds: float) -> tuple[bytes, float]:
    if seconds <= 0.2:
        raise AudioError("empty")
    if seconds > max_seconds():
        raise AudioError("too_long")
    return wav, seconds
