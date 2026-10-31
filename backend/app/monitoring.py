"""Pure functions that turn request-log rows into dashboard numbers (no web, no DB)."""
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from .benchmark.runner import percentile


def utc(dt: datetime) -> datetime:
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)


def _r(x, nd=1):
    return None if x is None else round(x, nd)


def _rate(a: int, b: int):
    return None if b == 0 else round(a / b, 4)


def _pcts(values: list[float]) -> dict:
    return {"p50": _r(percentile(values, 50)), "p95": _r(percentile(values, 95)), "p99": _r(percentile(values, 99))}


def summarize(rows: list, hours: float) -> dict:
    n = len(rows)
    ok = [r for r in rows if r.success]
    lat = [r.latency_ms for r in ok if r.latency_ms is not None]
    costs = [r.cost_usd for r in rows if r.cost_usd is not None]
    total_cost = sum(costs)
    return {
        "requests": n,
        "success_rate": _rate(len(ok), n),
        "error_rate": _rate(n - len(ok), n),
        "fallback_rate": _rate(sum(1 for r in rows if r.fallback_used), n),
        "simulated_share": _rate(sum(1 for r in rows if r.simulated), n),
        "latency_ms": {**_pcts(lat), "n": len(lat)},
        "tokens": {"input": sum(r.input_tokens or 0 for r in rows), "output": sum(r.output_tokens or 0 for r in rows)},
        "cost_usd": {"total": round(total_cost, 6), "requests_with_cost": len(costs),
                     "avg_per_request": round(total_cost / len(costs), 6) if costs else None,
                     # a projection from this window's run-rate, not a measured month
                     "projected_30_day": round(total_cost / hours * 24 * 30, 2) if n and hours > 0 else None},
    }


def by_model(rows: list) -> list[dict]:
    served, attempts = defaultdict(list), defaultdict(lambda: {"ok": 0, "failed": 0, "skipped": 0})
    for r in rows:
        if r.success and r.served_model:
            served[r.served_model].append(r)
        for a in r.attempts or []:
            attempts[a["model"]][a["status"]] += 1
    out = []
    for m in sorted(set(served) | set(attempts)):
        rs = served.get(m, [])
        at = attempts[m]
        tried = at["ok"] + at["failed"]
        fail_rate = _rate(at["failed"], tried)
        status = ("insufficient data" if tried < 5 else "down" if fail_rate >= 0.5
                  else "degraded" if fail_rate >= 0.1 else "healthy")
        out.append({"model": m, "requests_served": len(rs),
                    "latency_ms": _pcts([r.latency_ms for r in rs if r.latency_ms is not None]),
                    "cost_usd": round(sum(r.cost_usd or 0 for r in rs), 6),
                    "attempts": tried, "failed_attempts": at["failed"], "skipped": at["skipped"],
                    "attempt_failure_rate": fail_rate, "status": status})
    return sorted(out, key=lambda x: -x["requests_served"])


def alerts(summary: dict, models: list[dict]) -> list[dict]:
    out = []
    if summary["requests"] >= 20:
        er = summary["error_rate"] or 0
        if er > 0.20:
            out.append({"level": "critical", "message": f"Error rate is {er:.0%}"})
        elif er > 0.05:
            out.append({"level": "warning", "message": f"Error rate is {er:.0%}"})
        if (summary["fallback_rate"] or 0) > 0.20:
            out.append({"level": "warning", "message": f"Fallback used on {summary['fallback_rate']:.0%} of requests"})
    for m in models:
        if m["status"] in ("down", "degraded"):
            out.append({"level": "critical" if m["status"] == "down" else "warning",
                        "message": f"{m['model']} is {m['status']} ({m['attempt_failure_rate']:.0%} of attempts failed)"})
    return out


def timeseries(rows: list, since: datetime, until: datetime, bucket: str) -> list[dict]:
    def floor(dt):
        dt = utc(dt)
        return dt.replace(minute=0, second=0, microsecond=0) if bucket == "hour" else \
            dt.replace(hour=0, minute=0, second=0, microsecond=0)
    step = timedelta(hours=1) if bucket == "hour" else timedelta(days=1)
    buckets, t = {}, floor(since)
    while t <= until:
        buckets[t] = {"bucket": t.isoformat(), "requests": 0, "failures": 0, "fallbacks": 0, "cost_usd": 0.0}
        t += step
    for r in rows:
        b = buckets.get(floor(r.created_at))
        if b is not None:
            b["requests"] += 1
            b["failures"] += 0 if r.success else 1
            b["fallbacks"] += 1 if r.fallback_used else 0
            b["cost_usd"] = round(b["cost_usd"] + (r.cost_usd or 0), 6)
    return list(buckets.values())
