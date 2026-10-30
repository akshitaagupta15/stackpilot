"""Command-line entry point.
  python -m app.benchmark.run --config benchmark_models.json --limit 3     (real, small smoke test)
  python -m app.benchmark.run --config benchmark_models.json               (real, full dataset)
  python -m app.benchmark.run --dry-run                                    (fake, no key, no internet)
The API key is read from the OPENROUTER_API_KEY environment variable, never from a file."""
import argparse
import os
import random
import sys
import time
from pathlib import Path

import httpx

from .dataset import load_dataset
from .openrouter import call_model
from .prompt import build_messages
from .runner import load_config, run_benchmark, save_run


def make_dry_caller(items):
    rng = random.Random(7)
    answers = {build_messages(it["text"])[1]["content"]: it["expected"] for it in items}
    import json

    def caller(slug, messages):
        if rng.random() < 0.1:
            return {"text": "", "error": "simulated timeout", "latency_ms": 60000.0,
                    "input_tokens": None, "output_tokens": None}
        exp = dict(answers[messages[1]["content"]])
        if rng.random() < 0.15:
            exp["total_amount"] = round(exp["total_amount"] * 0.82, 2)
        return {"text": json.dumps(exp, ensure_ascii=False), "error": None,
                "latency_ms": round(rng.uniform(400, 1800), 1), "input_tokens": 420, "output_tokens": 70}
    return caller


def select_items(items: list[dict], limit: int | None = None, every: int | None = None) -> list[dict]:
    """--every N keeps every Nth item, so a small sample still mixes English and Hindi."""
    if every and every > 1:
        items = items[::every]
    return items[:limit] if limit else items


def with_retries(caller, retries: int, wait: float, sleep=time.sleep):
    """Retry only rate-limit errors (429). Latency reported is that of the final attempt, not the waiting.
    NOTE: every attempt may count against a free-tier daily quota."""
    def wrapped(slug, msgs):
        attempts = 0
        while True:
            res = dict(caller(slug, msgs))
            res["retries"] = attempts
            err = res.get("error") or ""
            if err and ("429" in err or "rate-limited" in err) and attempts < retries:
                attempts += 1
                sleep(wait)
                continue
            return res
    return wrapped


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="benchmark_models.example.json")
    ap.add_argument("--limit", type=int, default=None, help="only first N items (cheap smoke test)")
    ap.add_argument("--every", type=int, default=None, help="keep every Nth item (mixes languages)")
    ap.add_argument("--delay", type=float, default=0.0, help="seconds to wait between requests (free-tier rate limits)")
    ap.add_argument("--max-tokens", type=int, default=400, help="cap on tokens the model may write")
    ap.add_argument("--timeout", type=float, default=60.0, help="seconds before a request counts as failed")
    ap.add_argument("--retries", type=int, default=0, help="retry rate-limited (429) requests this many times")
    ap.add_argument("--retry-wait", type=float, default=20.0, help="seconds to wait before each retry")
    ap.add_argument("--dry-run", action="store_true", help="simulate model replies; no key needed")
    ap.add_argument("--note", default="", help="e.g. 'run from Meerut, India on home wifi'")
    ap.add_argument("--out", default="benchmark_runs")
    a = ap.parse_args()

    items, sha = load_dataset()
    items = select_items(items, a.limit, a.every)
    models = load_config(Path(a.config), allow_placeholder=a.dry_run)

    client = None
    if a.dry_run:
        caller = make_dry_caller(items)
    else:
        key = os.environ.get("OPENROUTER_API_KEY")
        if not key:
            print("OPENROUTER_API_KEY is not set. See the instructions, or use --dry-run.")
            return 1
        client = httpx.Client()
        def caller(slug, msgs):
            if a.delay:
                time.sleep(a.delay)
            return call_model(client, key, slug, msgs, max_tokens=a.max_tokens, timeout=a.timeout)
        caller = with_retries(caller, a.retries, a.retry_wait)

    for m in models:
        print(f"\n>>> {m['slug']}  ({len(items)} items){'  [DRY RUN - fake data]' if a.dry_run else ''}")
        run = run_benchmark(m, caller, items, "invoices_v1.jsonl", sha, a.note, a.dry_run,
                            progress=lambda n, t: print(f"    {n}/{t}", end="\r"),
                            settings={"temperature": 0.0, "max_tokens": a.max_tokens, "timeout_s": a.timeout})
        path = save_run(run, Path(a.out))
        s = run["summary"]
        q = s["quality"]["overall"]
        print(f"    field_accuracy={q['field_accuracy']:.3f}  exact={q['exact_match_rate']:.3f}  "
              f"valid_json={q['json_valid_rate']:.3f}  clean_json={q['clean_json_rate']:.3f}  "
              f"success={s['reliability']['success_rate']:.3f}  truncated={s['reliability']['truncated']}  retries={s['reliability']['retries']}")
        print(f"    latency p50={s['latency_ms']['p50']}ms p95={s['latency_ms']['p95']}ms  "
              f"avg_cost/request=${s['cost_usd']['avg_per_request']}  total=${s['cost_usd']['total']}")
        print(f"    saved: {path}")
    if client:
        client.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
