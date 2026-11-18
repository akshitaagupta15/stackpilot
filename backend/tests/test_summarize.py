import json
from app.benchmark.dataset import load_dataset
from app.benchmark.runner import run_benchmark
from app.benchmark.summarize import describe

ITEMS, SHA = load_dataset()


def test_summary_reports_truncation_wrong_fields_and_languages():
    n = {"i": 0}

    def caller(slug, msgs):
        it = ITEMS[n["i"]]
        n["i"] += 1
        if n["i"] == 1:      # cut off before any answer
            return {"text": "", "error": None, "latency_ms": 9000.0, "input_tokens": 200, "output_tokens": 800, "finish_reason": "length"}
        exp = dict(it["expected"])
        if n["i"] == 2:      # clean JSON, one wrong field
            exp["total_amount"] = 1.0
        return {"text": json.dumps(exp, ensure_ascii=False), "error": None, "latency_ms": 100.0 + n["i"],
                "input_tokens": 200, "output_tokens": 120, "finish_reason": "stop"}
    run = run_benchmark({"slug": "x/y", "price_input_per_mtok": 0, "price_output_per_mtok": 0}, caller, ITEMS, "invoices_v1.jsonl", SHA,
                        settings={"temperature": 0.0, "max_tokens": 2000, "timeout_s": 60.0})
    text = "\n".join(describe(run))
    assert "max_tokens=2000" in text and "40 sent, 40 answered, 0 failed" in text
    assert "clean JSON:        39/40 (97.5%)" in text and "exact match:       38/40 (95.0%)" in text
    assert "cut off at limit:  1  (en-01)" in text and "complete but wrong: en-02 (total_amount)" in text
    assert "en: clean JSON 19/20" in text and "hi: clean JSON 20/20" in text
    assert text.isascii()


def test_summary_handles_failed_requests():
    caller = lambda s, m: {"text": "", "error": "HTTP 429: busy", "latency_ms": 5.0, "input_tokens": None, "output_tokens": None}
    run = run_benchmark({"slug": "x/y", "price_input_per_mtok": 0, "price_output_per_mtok": 0}, caller, ITEMS[:3], "invoices_v1.jsonl", SHA)
    text = "\n".join(describe(run))
    assert "3 failed" in text and "no answered requests" in text and "failed requests:" in text
