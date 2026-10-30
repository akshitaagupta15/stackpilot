import json
import httpx
import pytest
from pathlib import Path
from app.benchmark.dataset import load_dataset
from app.benchmark.openrouter import call_model
from app.benchmark.runner import load_config, percentile, run_benchmark, save_run

MSGS = [{"role": "system", "content": "s"}, {"role": "user", "content": "u"}]


def client_with(handler):
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_percentile_nearest_rank():
    v = list(range(1, 101))
    assert percentile(v, 50) == 50 and percentile(v, 95) == 95 and percentile([], 95) is None


def test_call_model_success_parses_text_and_usage():
    def h(req):
        assert req.headers["authorization"] == "Bearer k"
        return httpx.Response(200, json={"choices": [{"message": {"content": "hi"}}],
                                         "usage": {"prompt_tokens": 10, "completion_tokens": 3}})
    r = call_model(client_with(h), "k", "m", MSGS)
    assert r["text"] == "hi" and r["error"] is None and (r["input_tokens"], r["output_tokens"]) == (10, 3)


def test_call_model_failures_become_data_not_exceptions():
    assert "429" in call_model(client_with(lambda r: httpx.Response(429, text="slow down")), "k", "m", MSGS)["error"]
    assert "API error" in call_model(client_with(lambda r: httpx.Response(200, json={"error": {"message": "x"}})), "k", "m", MSGS)["error"]
    assert call_model(client_with(lambda r: httpx.Response(200, json={"weird": 1})), "k", "m", MSGS)["error"]

    def boom(req):
        raise httpx.ReadTimeout("t")
    assert call_model(client_with(boom), "k", "m", MSGS)["error"] == "timeout"


def test_config_rejects_placeholders_and_bad_prices(tmp_path):
    p = tmp_path / "c.json"
    p.write_text(json.dumps({"models": [{"slug": "REPLACE_X", "price_input_per_mtok": 0, "price_output_per_mtok": 0}]}))
    with pytest.raises(ValueError):
        load_config(p)
    assert load_config(p, allow_placeholder=True)
    p.write_text(json.dumps({"models": [{"slug": "a/b", "price_input_per_mtok": 1, "price_output_per_mtok": 2,
                                         "pricing_checked_on": "yesterday"}]}))
    with pytest.raises(ValueError):
        load_config(p)


def test_run_counts_failures_cost_and_saves(tmp_path):
    items, sha = load_dataset()
    items = items[:4]
    truth = {"".join(i["text"]): i["expected"] for i in items}
    calls = {"n": 0}

    def caller(slug, msgs):
        calls["n"] += 1
        it = items[calls["n"] - 1]
        if calls["n"] == 4:
            return {"text": "", "error": "timeout", "latency_ms": 100.0, "input_tokens": None, "output_tokens": None}
        return {"text": json.dumps(it["expected"], ensure_ascii=False), "error": None,
                "latency_ms": 100.0 * calls["n"], "input_tokens": 1000, "output_tokens": 100}

    cfg = {"slug": "x/y", "price_input_per_mtok": 2.0, "price_output_per_mtok": 10.0, "pricing_checked_on": "2026-10-19"}
    run = run_benchmark(cfg, caller, items, "invoices_v1.jsonl", sha)
    s = run["summary"]
    assert s["reliability"]["success_rate"] == 0.75 and s["reliability"]["failures"] == 1
    assert s["quality"]["overall"]["exact_match_rate"] == 0.75   # the failure counts as wrong
    assert s["cost_usd"]["avg_per_request"] == pytest.approx(0.003)  # (1000*2 + 100*10)/1e6
    assert s["latency_ms"]["n"] == 3 and s["for_catalog"]["reliability"] == 0.75
    assert run["dataset"]["sha256"] == sha and run["items"][0]["raw_output"]
    path = save_run(run, tmp_path)
    assert json.loads(path.read_text(encoding="utf-8"))["run_id"] == run["run_id"]
