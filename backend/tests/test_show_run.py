from app.benchmark.dataset import load_dataset
from app.benchmark.runner import run_benchmark
from app.benchmark.show_run import describe


def test_describe_lists_every_item_and_flags_bad_output():
    items, sha = load_dataset()
    items = items[:2]
    caller = lambda slug, msgs: {"text": "I think the total is", "error": None, "latency_ms": 5.0,
                                 "input_tokens": 10, "output_tokens": 400}
    run = run_benchmark({"slug": "x", "price_input_per_mtok": 0, "price_output_per_mtok": 0}, caller, items, "d", sha)
    out = "\n".join(describe(run))
    assert out.count("json_valid=False") == 2 and "tokens_out=400" in out
