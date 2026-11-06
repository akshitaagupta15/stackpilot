import json
import pytest
from fastapi.testclient import TestClient
from app import measured
from app.benchmark.dataset import load_dataset
from app.benchmark.runner import run_benchmark, save_run
from app.main import app
from app.measured import load_measured_catalog
from app.recommend import recommend
from app.schemas import Workload

ITEMS, SHA = load_dataset()


def profile(slug, **kw):
    p = {"slug": slug, "provider": slug.split("/")[0], "context_window": 32000, "structured_output": True,
         "regions": ["us"], "languages": ["en", "hi"], "data_policy": "no_training"}
    p.update(kw)
    return p


def make_run(runs, slug, fail_first=0, hi_wrong=False, fenced=False, dry=False, n=None, ts=None, sha=None, truncate=0):
    items = ITEMS[:n] if n else ITEMS
    state = {"i": 0}

    def caller(_slug, _msgs):
        it = items[state["i"]]
        state["i"] += 1
        if state["i"] <= fail_first:
            return {"text": "", "error": "HTTP 429: busy", "latency_ms": 50.0, "input_tokens": None, "output_tokens": None}
        if state["i"] <= fail_first + truncate:
            return {"text": "Thinking Process: 1. Analyze the request", "error": None, "latency_ms": 100.0 + state["i"],
                    "input_tokens": 100, "output_tokens": 800, "finish_reason": "length"}
        exp = dict(it["expected"])
        if hi_wrong and it["language"] == "hi":
            exp["total_amount"] = 1.0
        text = json.dumps(exp, ensure_ascii=False)
        return {"text": f"```json\n{text}\n```" if fenced else text, "error": None, "latency_ms": 100.0 + state["i"],
                "input_tokens": 100, "output_tokens": 50}
    cfg = {"slug": slug, "price_input_per_mtok": 1.0, "price_output_per_mtok": 2.0, "pricing_checked_on": "2026-10-27"}
    run = run_benchmark(cfg, caller, items, "invoices_v1.jsonl", sha or SHA, dry_run=dry)
    if ts:
        run["timestamp_utc"] = ts
    return save_run(run, runs)


def profiles_file(tmp_path, *profs):
    p = tmp_path / "profiles.json"
    p.write_text(json.dumps({"models": list(profs)}), encoding="utf-8")
    return p


def test_valid_run_becomes_benchmark_entry(tmp_path):
    make_run(tmp_path / "r", "a/m")
    models, ignored = load_measured_catalog(tmp_path / "r", profiles_file(tmp_path, profile("a/m")))
    m = models[0]
    assert not ignored and m.metrics.source == "benchmark" and m.metrics.n_samples == 40
    assert m.metrics.quality == 1.0 and set(m.metrics.quality_by_language) == {"en", "hi"}
    assert m.price_input_per_mtok == 1.0 and m.source_run


def test_bad_evidence_is_ignored_with_reasons(tmp_path):
    r = tmp_path / "r"
    make_run(r, "a/dry", dry=True)
    make_run(r, "a/oldsha", sha="0" * 64)
    make_run(r, "a/noprofile")
    make_run(r, "a/small", n=5)
    pf = profiles_file(tmp_path, profile("a/dry"), profile("a/oldsha"), profile("a/small"))
    models, ignored = load_measured_catalog(r, pf)
    reasons = " | ".join(i["reason"] for i in ignored)
    assert models == [] and "dry run" in reasons and "dataset version" in reasons
    assert "model_profiles.json" in reasons and "only 5 successful" in reasons
    models, _ = load_measured_catalog(r, pf, min_items=5)
    assert [m.id for m in models] == ["a/small"]


def test_strict_quality_vs_lenient_and_failures_not_double_counted(tmp_path):
    r = tmp_path / "r"
    make_run(r, "a/fenced", fenced=True)
    make_run(r, "b/flaky", fail_first=10)
    pf = profiles_file(tmp_path, profile("a/fenced"), profile("b/flaky"))
    by = {m.id: m for m in load_measured_catalog(r, pf)[0]}
    assert by["a/fenced"].metrics.quality == 0.0 and by["a/fenced"].metrics.quality_lenient == 1.0
    f = by["b/flaky"].metrics
    assert f.reliability == 0.75 and f.quality == 1.0 and f.n_samples == 30


def test_newest_run_wins_and_pricing_override(tmp_path):
    r = tmp_path / "r"
    make_run(r, "a/m", hi_wrong=True, ts="2026-10-26T10:00:00+00:00")
    make_run(r, "a/m", ts="2026-10-27T10:00:00+00:00")
    po = {"input_per_mtok": 0.5, "output_per_mtok": 1.5, "verified_on": "2026-10-27"}
    models, ignored = load_measured_catalog(r, profiles_file(tmp_path, profile("a/m", pricing_override=po, free_tier=True)))
    assert len(models) == 1 and models[0].metrics.quality == 1.0 and models[0].price_input_per_mtok == 0.5
    assert models[0].free_tier and any("superseded" in i["reason"] for i in ignored)


def test_weak_hindi_is_caught_by_recommendation(tmp_path):
    r = tmp_path / "r"
    make_run(r, "good/m")
    make_run(r, "weakhi/m", hi_wrong=True)
    models, _ = load_measured_catalog(r, profiles_file(tmp_path, profile("good/m"), profile("weakhi/m")))
    w = Workload(name="x", monthly_requests=1000, avg_input_tokens=500, avg_output_tokens=100,
                 languages=["en", "hi"], quality_target=0.9)
    rec = recommend(w, models)
    assert [c.model_id for c in rec.ranked] == ["good/m"]
    assert any("quality" in x for rj in rec.rejected for x in rj.reasons)
    assert rec.confidence == "medium" and any("fewer than 100" in c for c in rec.caveats)


def test_api_endpoints(tmp_path, monkeypatch):
    r = tmp_path / "r"
    monkeypatch.setattr(measured, "DEFAULT_RUNS", r)
    monkeypatch.setattr(measured, "DEFAULT_PROFILES", profiles_file(tmp_path, profile("a/m")))
    c = TestClient(app)
    body = {"workload": {"name": "x", "monthly_requests": 1000, "avg_input_tokens": 500, "avg_output_tokens": 100}}
    assert c.post("/measured/recommend", json=body).status_code == 422
    make_run(r, "a/m")
    assert c.get("/measured/catalog").json()["models"][0]["id"] == "a/m"
    res = c.post("/measured/recommend", json=body)
    assert res.status_code == 200 and res.json()["picks"]["best_overall"] == "a/m"


def test_truncation_is_measured_and_called_out(tmp_path):
    r = tmp_path / "r"
    make_run(r, "a/m", truncate=36)                              # 36 of 40 answers cut off at the token limit
    models, _ = load_measured_catalog(r, profiles_file(tmp_path, profile("a/m")))
    m = models[0].metrics
    assert m.truncated_rate == 0.9 and m.max_tokens == 400 and m.quality == pytest.approx(0.1)
    rec = recommend(Workload(name="x", monthly_requests=1000, avg_input_tokens=500, avg_output_tokens=100), models)
    assert any("90% of its answers were cut off at the 400-token limit" in c for c in rec.caveats)
    make_run(tmp_path / "r2", "a/ok")                            # a clean run raises no such caveat
    ok, _ = load_measured_catalog(tmp_path / "r2", profiles_file(tmp_path, profile("a/ok")))
    assert ok[0].metrics.truncated_rate == 0.0
    assert not any("cut off" in c for c in recommend(Workload(name="x", monthly_requests=1000, avg_input_tokens=500,
                                                              avg_output_tokens=100), ok).caveats)
