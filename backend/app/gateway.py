"""Routing core: pure logic, no web framework, no database. The provider call is injected."""
from dataclasses import dataclass, field
from time import perf_counter
from typing import Callable


@dataclass
class RouteResult:
    ok: bool
    text: str = ""
    served_model: str | None = None
    attempts: list = field(default_factory=list)
    fallback_used: bool = False
    latency_ms: float | None = None   # latency of the call that served the request
    total_ms: float = 0.0             # time spent across all attempts
    input_tokens: int | None = None
    output_tokens: int | None = None
    cost_usd: float | None = None
    reason: str = ""


def compatibility_problems(profile: dict | None, cfg: dict) -> list[str]:
    """Fail closed: a model with no profile is never used."""
    if profile is None:
        return ["no entry in model_profiles.json"]
    problems = []
    if cfg.get("data_sensitivity") == "high" and profile.get("data_policy") != "no_training":
        problems.append("data policy not acceptable for sensitive data")
    regions = cfg.get("regions") or []
    if regions and not set(regions) & set(profile.get("regions", [])):
        problems.append("not available in required region(s)")
    if cfg.get("require_structured_output") and not profile.get("structured_output"):
        problems.append("no structured-output support")
    return problems


def estimate_cost(profile: dict | None, input_tokens, output_tokens) -> float | None:
    po = (profile or {}).get("pricing_override")
    if not po or input_tokens is None or output_tokens is None:
        return None
    return (input_tokens * po["input_per_mtok"] + output_tokens * po["output_per_mtok"]) / 1_000_000


def route(cfg: dict, profiles: dict, messages: list[dict], call: Callable) -> RouteResult:
    primary = cfg["primary"]
    order = [primary] + [m for m in cfg.get("fallbacks", []) if m != primary]
    attempts, total = [], 0.0
    for slug in order:
        problems = compatibility_problems(profiles.get(slug), cfg)
        if problems:
            attempts.append({"model": slug, "status": "skipped", "detail": "; ".join(problems)})
            continue
        t0 = perf_counter()
        res = call(slug, messages, cfg.get("max_tokens", 800))
        total += res.get("latency_ms") or (perf_counter() - t0) * 1000
        if res["error"] is None:
            attempts.append({"model": slug, "status": "ok", "latency_ms": res.get("latency_ms")})
            used_fallback = slug != primary
            reason = ("primary model served the request" if not used_fallback else
                      f"fallback {slug} served the request after: " +
                      "; ".join(f"{a['model']} {a['status']}" for a in attempts[:-1]))
            return RouteResult(ok=True, text=res["text"], served_model=slug, attempts=attempts,
                               fallback_used=used_fallback, latency_ms=res.get("latency_ms"), total_ms=total,
                               input_tokens=res.get("input_tokens"), output_tokens=res.get("output_tokens"),
                               cost_usd=estimate_cost(profiles.get(slug), res.get("input_tokens"), res.get("output_tokens")),
                               reason=reason)
        attempts.append({"model": slug, "status": "failed", "detail": str(res["error"])[:200],
                         "latency_ms": res.get("latency_ms")})
    return RouteResult(ok=False, attempts=attempts, total_ms=total,
                       reason="no compatible model could serve the request")
