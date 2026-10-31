"""Provider selection. Without OPENROUTER_API_KEY (or with DEMO_MODE=1) a free simulator is used,
so a public demo can never spend money."""
import os
from dataclasses import dataclass
from typing import Callable

import httpx

from .benchmark.openrouter import call_model


@dataclass
class Provider:
    call: Callable   # (slug, messages, max_tokens) -> dict like call_model()
    simulated: bool


def _simulated(slug: str, messages: list[dict], max_tokens: int) -> dict:
    if "fail" in slug:  # lets you demo fallback: any model slug containing "fail" is "down"
        return {"text": "", "error": "simulated outage", "latency_ms": 5.0,
                "input_tokens": None, "output_tokens": None, "finish_reason": None}
    n_in = sum(len(m["content"]) for m in messages) // 4 + 1
    return {"text": "[simulated reply]", "error": None, "latency_ms": 100.0 + (len(slug) * 37 % 400),
            "input_tokens": n_in, "output_tokens": 5, "finish_reason": "stop"}


_client: httpx.Client | None = None


def get_provider() -> Provider:
    global _client
    key = os.environ.get("OPENROUTER_API_KEY")
    if not key or os.environ.get("DEMO_MODE") == "1":
        return Provider(_simulated, True)
    if _client is None:
        _client = httpx.Client()
    return Provider(lambda slug, msgs, mt: call_model(_client, key, slug, msgs, max_tokens=mt), False)
