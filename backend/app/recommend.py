"""Deterministic, explainable recommendation: hard-constraint filter -> normalize -> weighted score.
No LLM is involved in ranking."""
from .cost import estimate_cost
from .schemas import Candidate, ModelSpec, Recommendation, Rejection, Weights, Workload


def effective_quality(m: ModelSpec, w: Workload) -> float:
    """Worst measured quality across the languages the workload needs (falls back to overall)."""
    vals = [m.metrics.quality_by_language[l] for l in w.languages if l in m.metrics.quality_by_language]
    return min(vals) if vals else m.metrics.quality


def check_constraints(m: ModelSpec, w: Workload, expected_cost: float) -> list[str]:
    reasons = []
    if m.context_window < w.avg_input_tokens + w.avg_output_tokens:
        reasons.append("context window too small")
    if w.requires_structured_output and not m.structured_output:
        reasons.append("no structured-output support")
    missing = [l for l in w.languages if l not in m.languages]
    if missing:
        reasons.append(f"unsupported language(s): {', '.join(missing)}")
    if w.regions and not set(w.regions) & set(m.regions):
        reasons.append("not available in required region(s)")
    if w.data_sensitivity == "high" and m.data_policy != "no_training":
        reasons.append("data policy not acceptable for sensitive data")
    if w.quality_target is not None and effective_quality(m, w) < w.quality_target:
        reasons.append(f"quality {effective_quality(m, w):.2f} below target {w.quality_target:.2f}")
    if w.p95_latency_ms is not None and m.metrics.latency_p95_ms > w.p95_latency_ms:
        reasons.append(f"P95 latency {m.metrics.latency_p95_ms:.0f}ms above target {w.p95_latency_ms:.0f}ms")
    if w.monthly_budget_usd is not None and expected_cost > w.monthly_budget_usd:
        reasons.append(f"expected cost ${expected_cost:,.0f} exceeds budget ${w.monthly_budget_usd:,.0f}")
    return reasons


def _lower_is_better(value: float, lo: float, hi: float) -> float:
    return 1.0 if hi == lo else (hi - value) / (hi - lo)


def recommend(w: Workload, models: list[ModelSpec], weights: Weights | None = None) -> Recommendation:
    weights = weights or Weights()
    total = weights.quality + weights.cost + weights.latency + weights.reliability
    if total <= 0:
        raise ValueError("at least one weight must be positive")
    nw = {k: v / total for k, v in weights.model_dump().items()}

    feasible, rejected, costs = [], [], {}
    for m in models:
        costs[m.id] = next(s.monthly_cost_usd for s in estimate_cost(m, w).scenarios if s.name == "expected")
        reasons = check_constraints(m, w, costs[m.id])
        (rejected.append(Rejection(model_id=m.id, reasons=reasons)) if reasons else feasible.append(m))

    ranked: list[Candidate] = []
    if feasible:
        c = [costs[m.id] for m in feasible]
        l = [m.metrics.latency_p95_ms for m in feasible]
        for m in feasible:
            parts = {
                "quality": effective_quality(m, w),
                "cost": _lower_is_better(costs[m.id], min(c), max(c)),
                "latency": _lower_is_better(m.metrics.latency_p95_ms, min(l), max(l)),
                "reliability": m.metrics.reliability,
            }
            score = sum(nw[k] * parts[k] for k in parts)
            top = max(parts, key=lambda k: nw[k] * parts[k])
            ranked.append(Candidate(
                model_id=m.id, score=round(score, 4),
                breakdown={k: round(v, 4) for k, v in parts.items()},
                expected_monthly_cost_usd=costs[m.id],
                explanation=f"Score {score:.3f}; strongest weighted contribution: {top}."))
        ranked.sort(key=lambda r: r.score, reverse=True)

    by_id = {m.id: m for m in feasible}
    picks: dict[str, str | None] = {k: None for k in
        ("best_overall", "cheapest", "highest_quality", "lowest_latency", "fallback")}
    if ranked:
        picks["best_overall"] = ranked[0].model_id
        picks["cheapest"] = min(ranked, key=lambda r: r.expected_monthly_cost_usd).model_id
        picks["highest_quality"] = max(ranked, key=lambda r: effective_quality(by_id[r.model_id], w)).model_id
        picks["lowest_latency"] = min(ranked, key=lambda r: by_id[r.model_id].metrics.latency_p95_ms).model_id
        top_provider = by_id[ranked[0].model_id].provider
        picks["fallback"] = next((r.model_id for r in ranked[1:]
                                  if by_id[r.model_id].provider != top_provider), None)

    caveats = []
    if any(m.metrics.source == "estimated" for m in feasible):
        caveats.append("Some quality/latency/reliability figures are estimates, not benchmark results.")
    if any(m.pricing_verified_on == "ILLUSTRATIVE" for m in feasible):
        caveats.append("Pricing data is illustrative; verify against provider pricing pages.")
    if any(m.metrics.source == "benchmark" and m.metrics.n_samples < 100 for m in feasible):
        caveats.append("Benchmarks used fewer than 100 samples per model; P95 latency and small quality gaps are noisy.")
    if any(m.free_tier for m in feasible):
        caveats.append("Some metrics were measured on a rate-limited free tier and may not reflect production.")
    if not ranked:
        caveats.append("No model satisfies all hard constraints; see rejection reasons.")
    elif picks["fallback"] is None:
        caveats.append("No policy-compatible fallback from a different provider.")
    n_bench = sum(1 for m in feasible if m.metrics.source == "benchmark")
    all_bench = bool(feasible) and n_bench == len(feasible)
    strong = all_bench and all(m.metrics.n_samples >= 100 for m in feasible)
    confidence = "high" if strong else "medium" if n_bench else "low"
    return Recommendation(ranked=ranked, rejected=rejected, picks=picks,
                          weights_used=Weights(**nw), confidence=confidence, caveats=caveats)
