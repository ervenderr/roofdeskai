import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request

from .config import settings

_hits: dict[str, deque] = defaultdict(deque)


def allow(key: str, limit: int, now: float | None = None, window: float = 60.0) -> bool:
    """Sliding-window limiter. shortcut: in-process, so per instance; move to Redis/edge rules if scaled out."""
    now = time.monotonic() if now is None else now
    q = _hits[key]
    while q and q[0] <= now - window:
        q.popleft()
    if len(q) >= limit:
        return False
    q.append(now)
    return True


def chat_rate_limit(request: Request) -> None:
    ip = request.client.host if request.client else "unknown"
    if not allow(ip, settings.chat_rate_per_min):
        raise HTTPException(429, "Too many messages, please slow down.")
