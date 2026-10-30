"""Cost engine: deterministic token-based cost with low/expected/high scenarios."""
from .schemas import CostEstimate, CostScenario, ModelSpec, Workload

# (name, volume multiplier, token-size multiplier). Assumptions are explicit and editable.
SCENARIOS = [("low", 0.7, 0.9), ("expected", 1.0, 1.0), ("high", 1.4, 1.2)]


def cost_per_request(model: ModelSpec, input_tokens: float, output_tokens: float) -> float:
    return (input_tokens * model.price_input_per_mtok
            + output_tokens * model.price_output_per_mtok) / 1_000_000


def estimate_cost(model: ModelSpec, w: Workload) -> CostEstimate:
    out = []
    for name, vol_mult, tok_mult in SCENARIOS:
        per_req = cost_per_request(model, w.avg_input_tokens * tok_mult, w.avg_output_tokens * tok_mult)
        requests = round(w.monthly_requests * vol_mult)
        out.append(CostScenario(name=name, monthly_requests=requests,
                                cost_per_request_usd=round(per_req, 6),
                                monthly_cost_usd=round(per_req * requests, 2)))
    return CostEstimate(model_id=model.id, pricing_verified_on=model.pricing_verified_on, scenarios=out)
