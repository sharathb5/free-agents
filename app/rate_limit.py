from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import Dict, Tuple


@dataclass(frozen=True)
class RateRule:
    key: str
    limit: int
    window_seconds: int


class SimpleRateLimiter:
    def __init__(self, rules: Dict[str, RateRule]):
        self._rules = rules
        self._state: Dict[Tuple[str, str], Tuple[int, float]] = {}
        self._lock = asyncio.Lock()

    async def allow(self, rule_key: str, client_id: str) -> bool:
        rule = self._rules[rule_key]
        now = time.monotonic()
        key = (rule_key, client_id)
        async with self._lock:
            remaining, reset_at = self._state.get(key, (rule.limit, now + rule.window_seconds))
            if now >= reset_at:
                remaining = rule.limit
                reset_at = now + rule.window_seconds
            if remaining <= 0:
                self._state[key] = (0, reset_at)
                return False
            self._state[key] = (remaining - 1, reset_at)
            return True
