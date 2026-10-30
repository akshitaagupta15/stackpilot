import httpx
from app.benchmark.dataset import load_dataset
from app.benchmark.openrouter import call_model
from app.benchmark.runner import run_benchmark


def test_finish_reason_parsed_and_truncation_counted():
    h = lambda req: httpx.Response(200, json={"choices": [{"message": {"content": "thinking..."}, "finish_reason": "length"}],
                                              "usage": {"prompt_tokens": 5, "completion_tokens": 400}})
    r = call_model(httpx.Client(transport=httpx.MockTransport(h)), "k", "m", [{"role": "user", "content": "u"}], max_tokens=400)
    assert r["finish_reason"] == "length"
    items, sha = load_dataset()
    caller = lambda slug, msgs: r
    cfg = {"slug": "x", "price_input_per_mtok": 0, "price_output_per_mtok": 0}
    run = run_benchmark(cfg, caller, items[:3], "d", sha, settings={"temperature": 0.0, "max_tokens": 1500, "timeout_s": 90.0})
    assert run["summary"]["reliability"]["truncated"] == 3
    assert run["settings"]["max_tokens"] == 1500
