"""In-memory sliding-window limiter. Correct for ONE server process; with several instances
you would move this state to Redis. Documented limitation."""
import threading
import time
from collections import defaultdict, deque


class RateLimiter:
    def __init__(self):
        self._hits: dict = defaultdict(deque)
        self._lock = threading.Lock()

    def check(self, key, limit: int, window: float = 60.0, now: float | None = None) -> float:
        """Returns 0.0 if the request is allowed (and counts it), else seconds until retry."""
        if limit <= 0:
            return 0.0
        now = time.monotonic() if now is None else now
        with self._lock:
            q = self._hits[key]
            while q and q[0] <= now - window:
                q.popleft()
            if len(q) >= limit:
                return max(0.1, q[0] + window - now)
            q.append(now)
            return 0.0

    def reset(self):
        with self._lock:
            self._hits.clear()


limiter = RateLimiter()
