"""D-10 demo guard: protects the $150 credits and keeps the live link up during judging (OWASP LLM10).

Layers, all checked before any model call:
  1. Input size: oversized images are refused (cost and latency grow with image size).
  2. Per-user rate limit: a sliding window of messages per user_ref. A user_ref comes from a session ID the
     browser supplies, so a script can mint new ones: this layer alone does NOT stop abuse (finding of 29 Oct).
  3. Per-IP rate limit (R-02): a sliding window per network address, so minting session IDs gains nothing.
  4. Global hourly cap on model calls across everyone (R-02): bounds the worst case whoever is calling and
     however many IDs or addresses they use, and survives a daily-counter reset after a restart.
  5. Daily budget: estimated USD spend and model-call count; once hit, the demo pauses politely
     instead of failing or running up the bill. The counters live in memory, so a restart (a Render free
     service sleeps after 15 minutes idle) resets them; layer 4 and the credit balance bound the damage.
     The Spend Limit on Meta's Billing page is only a notification, not a cap.
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
    ip_rate_limit: int = int(os.environ.get("LEDGERLENS_IP_RATE_LIMIT", 30))      # messages per address per window
    global_hourly_cap: int = int(os.environ.get("LEDGERLENS_GLOBAL_HOURLY_CAP", 60))  # model calls per hour, all users
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
    _ip_hits: dict = field(default_factory=lambda: defaultdict(deque))
    _global_hits: deque = field(default_factory=deque)
    _day: str = ""
    spent_usd: float = 0.0
    calls: int = 0

    def _roll_day(self) -> None:
        today = datetime.now(timezone.utc).date().isoformat()
        if today != self._day:
            self._day, self.spent_usd, self.calls = today, 0.0, 0

    @staticmethod
    def _slide(table: dict, key: str, now: float, window: float, limit: int) -> bool:
        """Records a hit and returns True if `key` is within `limit` hits per `window` seconds."""
        q = table[key]
        while q and now - q[0] > window:
            q.popleft()
        if len(q) >= limit:
            return False
        q.append(now)
        return True

    def _purge(self, now: float) -> None:
        """Minted session IDs or addresses must not grow memory without bound."""
        for table in (self._hits, self._ip_hits):
            if len(table) > 5000:
                for k in [k for k, q in table.items() if not q or now - q[-1] > self.cfg.rate_window_s]:
                    del table[k]

    def check_message(self, user_ref: str, media: bytes | None, client_ip: str | None = None) -> str | None:
        """Returns a refusal reason, or None if the message may proceed."""
        if media is not None and len(media) > self.cfg.max_image_bytes:
            return "too_large"
        now = self.clock()
        self._purge(now)
        if client_ip and not self._slide(self._ip_hits, client_ip, now, self.cfg.rate_window_s, self.cfg.ip_rate_limit):
            return "rate_limited"
        if not self._slide(self._hits, user_ref, now, self.cfg.rate_window_s, self.cfg.rate_limit):
            return "rate_limited"
        return None

    def check_budget(self) -> str | None:
        """Called once before each model call: daily budget first, then the global hourly cap (which counts the call)."""
        self._roll_day()
        if self.spent_usd >= self.cfg.daily_usd_cap or self.calls >= self.cfg.daily_call_cap:
            return "budget"
        now = self.clock()
        q = self._global_hits
        while q and now - q[0] > 3600:
            q.popleft()
        if len(q) >= self.cfg.global_hourly_cap:
            return "busy"
        q.append(now)
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
    "busy": "The live demo is busy right now. Please try again in a few minutes, or type 'demo' to explore a sample ledger.",
    "budget": ("The live demo has reached today's usage limit and is paused until tomorrow (UTC). "
               "Type 'demo' to explore a sample ledger in the meantime, or watch the demo video."),
}
