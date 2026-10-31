"""Fill the database with SIMULATED traffic so a public demo dashboard is never empty.
Run:  python -m app.seed_demo --reset
Everything it writes is flagged simulated=True and says 'seeded demo data' in routing_reason."""
import argparse
import hashlib
import math
import random
import secrets
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete
from sqlalchemy.orm import Session

from .db import ApiKey, RequestLog, get_engine

PROJECT = "demo"
# model: (median latency ms, failure probability, $ per 1M input, $ per 1M output)
MODELS = {"demo/quality-large": (1500, 0.04, 3.0, 15.0), "demo/fast-small": (600, 0.01, 0.25, 1.25),
          "demo/backup-open": (1100, 0.02, 0.6, 0.8)}
ROUTES = [(0.55, "demo/quality-large", "demo/fast-small"), (0.45, "demo/fast-small", "demo/backup-open")]


def _call(rng, model, outage):
    median, p_fail, _, _ = MODELS[model]
    if outage and model == "demo/quality-large":
        p_fail = 0.6
    lat = round(rng.lognormvariate(math.log(median), 0.35), 1)
    return (rng.random() >= p_fail), lat


def seed(session: Session, n: int = 600, now: datetime | None = None, rng_seed: int = 42) -> int:
    rng = random.Random(rng_seed)
    now = now or datetime.now(timezone.utc)
    outage_start = now - timedelta(hours=30)           # a 3-hour incident "yesterday"
    outage_end = outage_start + timedelta(hours=3)
    rows = []
    for _ in range(n):
        while True:                                     # more traffic in daytime hours (UTC 4-16)
            ts = now - timedelta(seconds=rng.uniform(0, 7 * 86400))
            if rng.random() < (0.9 if 4 <= ts.hour <= 16 else 0.25):
                break
        outage = outage_start <= ts <= outage_end
        primary, fallback = ROUTES[0][1:] if rng.random() < ROUTES[0][0] else ROUTES[1][1:]
        attempts, served, lat, ok_total = [], None, None, 0.0
        for model in (primary, fallback):
            ok, l = _call(rng, model, outage)
            ok_total += l
            attempts.append({"model": model, "status": "ok" if ok else "failed", "latency_ms": l})
            if ok:
                served, lat = model, l
                break
        tin, tout = rng.randint(400, 1600), rng.randint(50, 300)
        cost = None if served is None else (tin * MODELS[served][2] + tout * MODELS[served][3]) / 1e6
        rows.append(RequestLog(
            request_id="seed" + uuid.uuid4().hex[:12], created_at=ts, project=PROJECT, api_key_id=0,
            policy_name="default", served_model=served, attempts=attempts, success=served is not None,
            fallback_used=served is not None and served != primary, simulated=True, latency_ms=lat,
            total_ms=round(ok_total, 1), input_tokens=tin if served else None, output_tokens=tout if served else None,
            cost_usd=cost, routing_reason="seeded demo data"))
    session.add_all(rows)
    session.commit()
    return len(rows)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=600)
    ap.add_argument("--reset", action="store_true", help="delete previous demo data and demo key first")
    a = ap.parse_args()
    with Session(get_engine()) as s:
        if a.reset:
            s.execute(delete(RequestLog).where(RequestLog.project == PROJECT))
            s.execute(delete(ApiKey).where(ApiKey.project == PROJECT))
            s.commit()
        count = seed(s, a.n)
        key = None
        if not s.query(ApiKey).filter(ApiKey.project == PROJECT).first():
            key = "sp_demo_" + secrets.token_urlsafe(16)
            s.add(ApiKey(name="demo-viewer", project=PROJECT, key_hash=hashlib.sha256(key.encode()).hexdigest()))
            s.commit()
    print(f"seeded {count} simulated requests for project '{PROJECT}'")
    print(f"demo API key (shown once): {key}" if key else "demo key already exists (use --reset to make a new one)")


if __name__ == "__main__":
    main()
