import json
import sys

from app.benchmark import run as run_module

DAILY = {"text": "", "latency_ms": 900.0, "input_tokens": None, "output_tokens": None, "finish_reason": None,
         "error": 'HTTP 429: {"error":{"message":"Rate limit exceeded: free-models-per-day. Add 10 credits to unlock 1000"}}'}


def test_daily_limit_stops_the_whole_run_without_saving(tmp_path, monkeypatch, capsys):
    cfg = tmp_path / "m.json"
    cfg.write_text(json.dumps({"models": [{"slug": "a/b:free", "price_input_per_mtok": 0, "price_output_per_mtok": 0,
                                           "pricing_checked_on": "2026-11-02"}]}))
    calls = []
    monkeypatch.setattr(run_module, "call_model", lambda *a, **k: (calls.append(1), DAILY)[1])
    monkeypatch.setenv("OPENROUTER_API_KEY", "k")
    monkeypatch.setattr(sys, "argv", ["run", "--config", str(cfg), "--limit", "5", "--retries", "3",
                                      "--retry-wait", "0", "--out", str(tmp_path / "runs")])
    assert run_module.main() == 2
    assert len(calls) == 1                         # one request, then stop: no retries, no further invoices
    assert not (tmp_path / "runs").exists()        # no junk run file
    assert "free daily limit" in capsys.readouterr().out
