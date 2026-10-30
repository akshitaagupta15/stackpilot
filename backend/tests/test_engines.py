import pytest
from fastapi.testclient import TestClient
from app.catalog import load_catalog
from app.cost import estimate_cost
from app.main import app
from app.recommend import recommend
from app.schemas import Weights, Workload

MODELS = {m.id: m for m in load_catalog()}

SUPPORT = Workload(name="support", monthly_requests=80_000, avg_input_tokens=1500,
                   avg_output_tokens=300, languages=["en", "hi"], requires_structured_output=True,
                   data_sensitivity="high", p95_latency_ms=2000, monthly_budget_usd=700)


def test_cost_math_exact():
    w = Workload(name="x", monthly_requests=1000, avg_input_tokens=1000, avg_output_tokens=500)
    exp = next(s for s in estimate_cost(MODELS["alpha-large"], w).scenarios if s.name == "expected")
    # (1000*3 + 500*15) / 1e6 = 0.0105 per request
    assert exp.cost_per_request_usd == pytest.approx(0.0105)
    assert exp.monthly_cost_usd == pytest.approx(10.5)


def test_scenarios_ordered():
    s = estimate_cost(MODELS["alpha-small"], SUPPORT).scenarios
    assert [x.name for x in s] == ["low", "expected", "high"]
    assert s[0].monthly_cost_usd < s[1].monthly_cost_usd < s[2].monthly_cost_usd


def test_hard_constraints_reject_with_reasons():
    rec = recommend(SUPPORT, list(MODELS.values()))
    rej = {r.model_id: r.reasons for r in rec.rejected}
    assert any("structured" in r for r in rej["gamma-open-70b"])
    assert any("sensitive" in r for r in rej["beta-mini"])
    assert any("language" in r for r in rej["gamma-open-8b"])
    assert "alpha-large" not in rej or any("latency" in r or "budget" in r for r in rej["alpha-large"])


def test_picks_and_fallback_differ_by_provider():
    rec = recommend(SUPPORT, list(MODELS.values()))
    assert rec.picks["best_overall"] == rec.ranked[0].model_id
    fb = rec.picks["fallback"]
    if fb:
        assert MODELS[fb].provider != MODELS[rec.picks["best_overall"]].provider


def test_weights_change_ranking_and_normalize():
    w = Workload(name="x", monthly_requests=10_000, avg_input_tokens=500, avg_output_tokens=200)
    cheap = recommend(w, list(MODELS.values()), Weights(quality=0, cost=1, latency=0, reliability=0))
    qual = recommend(w, list(MODELS.values()), Weights(quality=1, cost=0, latency=0, reliability=0))
    assert cheap.ranked[0].model_id == "gamma-open-8b"
    assert qual.ranked[0].model_id == "alpha-large"
    assert sum(cheap.weights_used.model_dump().values()) == pytest.approx(1.0)


def test_no_feasible_models():
    w = Workload(name="x", monthly_requests=1000, avg_input_tokens=100, avg_output_tokens=100,
                 quality_target=0.99)
    rec = recommend(w, list(MODELS.values()))
    assert rec.ranked == [] and rec.picks["best_overall"] is None


def test_zero_weights_rejected():
    with pytest.raises(ValueError):
        recommend(SUPPORT, list(MODELS.values()), Weights(quality=0, cost=0, latency=0, reliability=0))


def test_api_endpoints():
    c = TestClient(app)
    assert c.get("/health").json() == {"status": "ok"}
    assert len(c.get("/catalog").json()) == 6
    r = c.post("/recommend", json={"workload": SUPPORT.model_dump()})
    assert r.status_code == 200 and r.json()["picks"]["best_overall"]
    assert c.post("/recommend", json={"workload": SUPPORT.model_dump(),
          "weights": {"quality": 0, "cost": 0, "latency": 0, "reliability": 0}}).status_code == 422
