"""D-10 demo guard: protects the $150 credits and keeps the live link up during judging (OWASP LLM10).

Three layers, all checked before any model call:
  1. Input size: oversized images are refused (cost and latency grow with image size).
  2. Per-user rate limit: a sliding window of messages per user_ref.
  3. Daily budget: estimated USD spend and model-call count; once hit, the demo pauses politely
     instead of failing or running up the bill. A hard spend limit is also set on Meta's Billing page.
"""
from __future__ import annotations

import os
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime, timezone


def _env_float(name: str, default: float) -> float:
    return float(os.environ.get(name, default))


@dataclass
class GuardConfig:
    max_image_bytes: int = int(os.environ.get("LEDGERLENS_MAX_IMAGE_BYTES", 5 * 1024 * 1024))
    rate_limit: int = int(os.environ.get("LEDGERLENS_RATE_LIMIT", 20))           # messages...
    rate_window_s: int = int(os.environ.get("LEDGERLENS_RATE_WINDOW_S", 600))     # ...per 10 minutes
    daily_usd_cap: float = _env_float("LEDGERLENS_DAILY_USD_CAP", 5.0)
    daily_call_cap: int = int(os.environ.get("LEDGERLENS_DAILY_CALL_CAP", 1500))
    usd_per_m_input: float = _env_float("LEDGERLENS_USD_PER_M_INPUT", 1.25)       # set from the models docs
    usd_per_m_output: float = _env_float("LEDGERLENS_USD_PER_M_OUTPUT", 4.25)
    usd_per_audio_hour: float = _env_float("LEDGERLENS_USD_PER_AUDIO_HOUR", 0.18)  # Muse Voice Transcribe list price


@dataclass
class Guard:
    cfg: GuardConfig = field(default_factory=GuardConfig)
    clock: callable = time.monotonic
    _hits: dict = field(default_factory=lambda: defaultdict(deque))
    _day: str = ""
    spent_usd: float = 0.0
    calls: int = 0

    def _roll_day(self) -> None:
        today = datetime.now(timezone.utc).date().isoformat()
        if today != self._day:
            self._day, self.spent_usd, self.calls = today, 0.0, 0

    def check_message(self, user_ref: str, media: bytes | None) -> str | None:
        """Returns a refusal reason, or None if the message may proceed."""
        if media is not None and len(media) > self.cfg.max_image_bytes:
            return "too_large"
        now = self.clock()
        q = self._hits[user_ref]
        while q and now - q[0] > self.cfg.rate_window_s:
            q.popleft()
        if len(q) >= self.cfg.rate_limit:
            return "rate_limited"
        q.append(now)
        return None

    def check_budget(self) -> str | None:
        self._roll_day()
        if self.spent_usd >= self.cfg.daily_usd_cap or self.calls >= self.cfg.daily_call_cap:
            return "budget"
        return None

    def record_audio(self, seconds: float) -> float:
        """Transcription is billed per whole second of audio; it counts as one model call against the daily caps."""
        self._roll_day()
        cost = int(seconds) * self.cfg.usd_per_audio_hour / 3600
        self.spent_usd += cost
        self.calls += 1
        return cost

    def record_usage(self, input_tokens: int, output_tokens: int) -> float:
        self._roll_day()
        cost = (input_tokens * self.cfg.usd_per_m_input + output_tokens * self.cfg.usd_per_m_output) / 1e6
        self.spent_usd += cost
        self.calls += 1
        return cost


REFUSALS = {
    "too_large": "That file is too large. Please send a photo under 5 MB, or a voice note under a minute.",
    "rate_limited": "You're sending messages quickly. Please wait a few minutes and try again.",
    "budget": ("The live demo has reached today's usage limit and is paused until tomorrow (UTC). "
               "Type 'demo' to explore a sample ledger in the meantime, or watch the demo video."),
}
