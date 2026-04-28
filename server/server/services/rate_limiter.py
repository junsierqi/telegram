"""Token-bucket per-session / per-key rate limiter (M93).

Enforces caps on the dispatcher's hot paths so a misbehaving client can't
flood the server. Buckets are addressed by (op_name, key); the key is
typically a session_id for authenticated requests or a phone_number /
username for pre-authenticated requests.

Default limits (RPS unless noted, with a small burst):

    op                       rate     burst
    message_send             5/s      10
    register_request         3/min    5
    phone_otp_request        2/min    3
    presence_query_request   5/s      10

Tunables can be overridden via RateLimiter.configure(op, rate, burst).
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Callable, Optional


@dataclass
class RateConfig:
    """rate = tokens added per second; burst = bucket capacity."""
    rate: float
    burst: float

    @classmethod
    def per_minute(cls, count: float, *, burst: Optional[float] = None) -> "RateConfig":
        return cls(rate=count / 60.0, burst=burst if burst is not None else count)


# Default knobs. None of these require external configuration; operators can
# call rate_limiter.configure(...) at startup to tune.
DEFAULT_LIMITS: dict[str, RateConfig] = {
    "message_send":            RateConfig(rate=5.0,  burst=10.0),
    "register_request":        RateConfig.per_minute(3.0, burst=5.0),
    "phone_otp_request":       RateConfig.per_minute(2.0, burst=3.0),
    "phone_otp_verify_request": RateConfig.per_minute(20.0, burst=20.0),
    "presence_query_request":  RateConfig(rate=5.0,  burst=10.0),
    "message_send_attachment": RateConfig(rate=2.0,  burst=4.0),
}


class RateLimiter:
    """Thread-safe token-bucket store. `try_acquire(op, key)` returns True
    if the bucket had a token, False if rate-limited.

    Buckets are lazily created on first access. They never expire because
    cleaning them up adds complexity for no real benefit at this scale —
    a per-IP key with a long-idle client just sits at full capacity.
    """

    def __init__(self, *, clock: Optional[Callable[[], float]] = None) -> None:
        self._clock = clock or time.monotonic
        self._configs: dict[str, RateConfig] = dict(DEFAULT_LIMITS)
        self._lock = threading.Lock()
        # (op, key) -> [tokens_remaining, last_refill_at]
        self._buckets: dict[tuple[str, str], list[float]] = {}

    def configure(self, op: str, rate: float, burst: float) -> None:
        with self._lock:
            self._configs[op] = RateConfig(rate=rate, burst=burst)

    def get_config(self, op: str) -> Optional[RateConfig]:
        return self._configs.get(op)

    def try_acquire(self, op: str, key: str, *, cost: float = 1.0) -> bool:
        """Returns True if `cost` tokens were available + deducted; False
        otherwise. An op with no configured limit is always allowed."""
        config = self._configs.get(op)
        if config is None:
            return True
        if not key:
            # No key → can't do per-key bucketing; let it through. The
            # alternative (single global bucket) creates head-of-line
            # blocking. Caller should pass a meaningful key.
            return True
        now = self._clock()
        bucket_key = (op, key)
        with self._lock:
            bucket = self._buckets.get(bucket_key)
            if bucket is None:
                bucket = [config.burst, now]
                self._buckets[bucket_key] = bucket
            tokens, last_refill = bucket
            elapsed = max(0.0, now - last_refill)
            tokens = min(config.burst, tokens + elapsed * config.rate)
            if tokens >= cost:
                bucket[0] = tokens - cost
                bucket[1] = now
                return True
            # Persist the (partial) refill anyway so retries don't always
            # see a stale window.
            bucket[0] = tokens
            bucket[1] = now
            return False

    def reset(self) -> None:
        """Wipe every bucket — useful between tests."""
        with self._lock:
            self._buckets.clear()

    def describe(self) -> str:
        return (
            f"rate limiter — {len(self._configs)} configured ops, "
            f"{len(self._buckets)} active buckets"
        )
