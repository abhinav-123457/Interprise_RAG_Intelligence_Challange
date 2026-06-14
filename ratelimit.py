"""
ratelimit.py — Simple in-memory per-user sliding-window rate limiter.

Protects against abuse / runaway cost (OWASP LLM10). RATE_LIMIT_MAX queries per
RATE_LIMIT_WINDOW seconds per user. In-process (fine for a single Space); back
with Redis for multi-instance prod — same interface.
"""
import time
from collections import defaultdict, deque

from config import RATE_LIMIT_MAX, RATE_LIMIT_WINDOW

_calls = defaultdict(deque)


def check(user, max_calls=RATE_LIMIT_MAX, window=RATE_LIMIT_WINDOW):
    """Return (allowed: bool, retry_after_seconds: int). Records the call when allowed."""
    now = time.time()
    dq = _calls[user]
    while dq and now - dq[0] > window:
        dq.popleft()
    if len(dq) >= max_calls:
        retry = int(window - (now - dq[0])) + 1
        return False, retry
    dq.append(now)
    return True, 0


def reset(user=None):
    """Clear limiter state (testing / admin)."""
    if user is None:
        _calls.clear()
    else:
        _calls.pop(user, None)


if __name__ == "__main__":
    reset("demo")
    allowed = sum(check("demo")[0] for _ in range(RATE_LIMIT_MAX + 3))
    print(f"allowed {allowed}/{RATE_LIMIT_MAX + 3} (limit {RATE_LIMIT_MAX}/{RATE_LIMIT_WINDOW}s)")