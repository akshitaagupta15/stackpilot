"""Runs one model over the dataset and produces a self-contained, reproducible run record."""
import json
import math
import platform
import re
import sys
import uuid
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean
from typing import Callable

from .dataset import load_dataset
from .prompt import PROMPT_VERSION, build_messages
from .scoring import aggregate, score_item

RUNNER_VERSION = "0.1"
SETTINGS = {"temperature": 0.0, "max_tokens": 400, "timeout_s": 60.0}


def percentile(values: list[float], p: float):
    """Nearest-rank percentile. With ~40 samples P95/P99 are very noisy: say so in reports."""
    if not values:
        return None
    s = sorted(values)
    return s[max(0, math.ceil(p / 100 * len(s)) - 1)]


def load_config(path: Path, allow_placeholder: bool = False) -> list[dict]:
    cfg = json.loads(Path(path).read_text(encoding="utf-8"))["models"]
    for m in cfg:
        if str(m["slug"]).startswith("REPLACE") and not allow_placeholder:
            raise ValueError(f"Fill in a real model slug (found placeholder '{m['slug']}')")
        for k in ("price_input_per_mtok", "price_output_per_mtok"):
            if not isinstance(m.get(k), (int, float)) or m[k] < 0:
                raise ValueError(f"{m['slug']}: {k} must be a number >= 0")
        if not allow_placeholder and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(m.get("pricing_checked_on", ""))):
            raise ValueError(f"{m['slug']}: pricing_checked_on must be a date like 2026-10-19")
    return cfg


def run_benchmark(model_cfg: dict, caller: Callable[[str, list[dict]], dict], items: list[dict],
                  dataset_name: str, dataset_sha: str, note: str = "", dry_run: bool = False,
                  progress: Callable[[int, int], None] | None = None,
                  settings: dict | None = None) -> dict:
    settings = settings or SETTINGS
    p_in, p_out = model_cfg["price_input_per_mtok"], model_cfg["price_output_per_mtok"]
    rows = []
    for n, it in enumerate(items, 1):
        res = caller(model_cfg["slug"], build_messages(it["text"]))
        failed = res["error"] is not None
        cost = None
        if res["input_tokens"] is not None and res["output_tokens"] is not None:
            cost = (res["input_tokens"] * p_in + res["output_tokens"] * p_out) / 1_000_000
        score = score_item("" if failed else res["text"], it["expected"])  # failures count as wrong
        rows.append({"id": it["id"], "language": it["language"], "raw_output": res["text"],
                     "error": res["error"], "finish_reason": res.get("finish_reason"), "retries": res.get("retries", 0),
                     "latency_ms": res["latency_ms"],
                     "input_tokens": res["input_tokens"], "output_tokens": res["output_tokens"],
                     "cost_usd": cost, "score": asdict(score)})
        if progress:
            progress(n, len(items))

    ok = [r for r in rows if r["error"] is None]
    lat = [r["latency_ms"] for r in ok if r["latency_ms"] is not None]
    costs = [r["cost_usd"] for r in rows if r["cost_usd"] is not None]
    from .scoring import ItemScore
    quality = aggregate([(r["language"], ItemScore(**r["score"])) for r in rows])
    summary = {
        "quality": quality,
        "reliability": {"success_rate": round(len(ok) / len(rows), 4), "failures": len(rows) - len(ok),
                        "truncated": sum(1 for r in rows if r["finish_reason"] == "length"),
                        "retries": sum(r["retries"] for r in rows),
                        "errors": sorted({r["error"][:80] for r in rows if r["error"]})},
        "latency_ms": {"p50": percentile(lat, 50), "p95": percentile(lat, 95), "p99": percentile(lat, 99),
                       "mean": round(mean(lat), 1) if lat else None, "n": len(lat)},
        "tokens": {"avg_input": round(mean(r["input_tokens"] for r in ok if r["input_tokens"] is not None), 1)
                   if any(r["input_tokens"] is not None for r in ok) else None,
                   "avg_output": round(mean(r["output_tokens"] for r in ok if r["output_tokens"] is not None), 1)
                   if any(r["output_tokens"] is not None for r in ok) else None},
        "cost_usd": {"avg_per_request": round(mean(costs), 6) if costs else None,
                     "total": round(sum(costs), 4) if costs else None},
    }
    # The three numbers the recommendation engine consumes (Stage 3)
    summary["for_catalog"] = {"quality": quality["overall"]["field_accuracy"],
                              "latency_p95_ms": summary["latency_ms"]["p95"],
                              "reliability": summary["reliability"]["success_rate"]}
    return {"run_id": uuid.uuid4().hex[:12], "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "dry_run": dry_run, "runner_version": RUNNER_VERSION, "model": model_cfg["slug"],
            "pricing": {"input_per_mtok": p_in, "output_per_mtok": p_out,
                        "checked_on": model_cfg.get("pricing_checked_on")},
            "dataset": {"name": dataset_name, "sha256": dataset_sha, "n": len(items)},
            "prompt_version": PROMPT_VERSION, "settings": settings,
            "environment": {"python": sys.version.split()[0], "platform": platform.platform(), "note": note},
            "summary": summary, "items": rows}


def save_run(run: dict, out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = run["timestamp_utc"][:19].replace(":", "-")
    safe = re.sub(r"[^A-Za-z0-9._-]", "_", run["model"])
    path = out_dir / f"{'DRYRUN_' if run['dry_run'] else ''}{stamp}_{safe}.json"
    path.write_text(json.dumps(run, ensure_ascii=False, indent=2), encoding="utf-8")
    return path
