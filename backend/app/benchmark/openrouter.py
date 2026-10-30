"""Thin OpenRouter client. Never raises on model/network failure: failures are returned as data,
because failure rate is itself a benchmark metric."""
import time
import httpx

URL = "https://openrouter.ai/api/v1/chat/completions"


def call_model(client: httpx.Client, api_key: str, model: str, messages: list[dict],
               temperature: float = 0.0, max_tokens: int = 400, timeout: float = 60.0) -> dict:
    start = time.perf_counter()
    out = {"text": "", "error": None, "latency_ms": None, "input_tokens": None, "output_tokens": None,
           "finish_reason": None}
    try:
        r = client.post(URL, headers={"Authorization": f"Bearer {api_key}"}, timeout=timeout,
                        json={"model": model, "messages": messages,
                              "temperature": temperature, "max_tokens": max_tokens})
        out["latency_ms"] = round((time.perf_counter() - start) * 1000, 1)
        if r.status_code != 200:
            out["error"] = f"HTTP {r.status_code}: {r.text[:200]}"
            return out
        data = r.json()
        if data.get("error"):
            out["error"] = f"API error: {str(data['error'])[:200]}"
            return out
        out["text"] = data["choices"][0]["message"].get("content") or ""
        out["finish_reason"] = data["choices"][0].get("finish_reason")  # "length" = cut off by max_tokens
        usage = data.get("usage") or {}
        out["input_tokens"] = usage.get("prompt_tokens")
        out["output_tokens"] = usage.get("completion_tokens")
    except httpx.TimeoutException:
        out["error"] = "timeout"
        out["latency_ms"] = round((time.perf_counter() - start) * 1000, 1)
    except (httpx.HTTPError, ValueError, KeyError, IndexError, TypeError) as e:
        out["error"] = f"{type(e).__name__}: {e}"
    return out
