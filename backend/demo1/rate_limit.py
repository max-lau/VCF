"""
Per-tenant rate limiting for ParaIQ AI endpoints.
Sliding window, in-memory. For multi-worker, migrate to Redis.

Usage:
    from backend.demo1.rate_limit import check_rate_limit
    check_rate_limit(firm_id, endpoint="ai")  # raises 429 if exceeded
"""
import time
import threading
from collections import deque
from fastapi import HTTPException

LIMITS = {
    "ai":      {"max_requests": 60,  "window_seconds": 60},
    "export":  {"max_requests": 20,  "window_seconds": 60},
    "default": {"max_requests": 200, "window_seconds": 60},
}

_lock: threading.Lock = threading.Lock()
_windows: dict = {}


def _get_window(firm_id: str, endpoint: str) -> deque:
    key = (firm_id, endpoint)
    if key not in _windows:
        _windows[key] = deque()
    return _windows[key]


def check_rate_limit(firm_id: str, endpoint: str = "default") -> None:
    cfg    = LIMITS.get(endpoint, LIMITS["default"])
    max_r  = cfg["max_requests"]
    window = cfg["window_seconds"]
    now    = time.monotonic()
    cutoff = now - window
    with _lock:
        dq = _get_window(firm_id, endpoint)
        while dq and dq[0] < cutoff:
            dq.popleft()
        if len(dq) >= max_r:
            retry = int(window - (now - dq[0]))
            raise HTTPException(
                status_code=429,
                detail=f"Rate limit exceeded: {max_r} req/{window}s. Retry in {retry}s."
            )
        dq.append(now)


def get_usage(firm_id: str, endpoint: str = "ai") -> dict:
    cfg    = LIMITS.get(endpoint, LIMITS["default"])
    window = cfg["window_seconds"]
    now    = time.monotonic()
    cutoff = now - window
    with _lock:
        dq = _get_window(firm_id, endpoint)
        recent = sum(1 for t in dq if t >= cutoff)
    return {
        "firm_id": firm_id, "endpoint": endpoint,
        "requests_in_window": recent, "limit": cfg["max_requests"],
        "window_s": window, "remaining": max(0, cfg["max_requests"] - recent),
    }
