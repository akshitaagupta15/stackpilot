from app.benchmark.run import with_retries

OK = {"text": "{}", "error": None, "latency_ms": 5.0, "input_tokens": 1, "output_tokens": 1}
RL = {"text": "", "error": "HTTP 429: rate-limited upstream", "latency_ms": 1.0, "input_tokens": None, "output_tokens": None}


def make(seq):
    calls = {"n": 0}

    def caller(slug, msgs):
        calls["n"] += 1
        return seq[min(calls["n"] - 1, len(seq) - 1)]
    return caller, calls


def test_retries_until_success_and_records_count():
    caller, calls = make([RL, RL, OK])
    waits = []
    res = with_retries(caller, retries=3, wait=7, sleep=waits.append)("m", [])
    assert res["error"] is None and res["retries"] == 2 and calls["n"] == 3 and waits == [7, 7]


def test_gives_up_after_limit():
    caller, calls = make([RL])
    res = with_retries(caller, retries=1, wait=0, sleep=lambda s: None)("m", [])
    assert res["error"] and res["retries"] == 1 and calls["n"] == 2


def test_other_errors_not_retried():
    caller, calls = make([{**RL, "error": "HTTP 401: bad key"}])
    res = with_retries(caller, retries=5, wait=0, sleep=lambda s: None)("m", [])
    assert calls["n"] == 1 and res["retries"] == 0


def test_daily_limit_is_never_retried_and_aborts():
    import pytest
    from app.benchmark.run import DailyLimitReached
    daily = {**RL, "error": 'HTTP 429: {"error":{"message":"Rate limit exceeded: free-models-per-day. Add 10 credits"}}'}
    caller, calls = make([daily, OK])
    with pytest.raises(DailyLimitReached):
        with_retries(caller, retries=5, wait=0, sleep=lambda s: None)("m", [])
    assert calls["n"] == 1


def test_retry_budget_is_shared_across_the_whole_run():
    caller, calls = make([RL])                      # always rate-limited
    wrapped = with_retries(caller, retries=3, wait=0, sleep=lambda s: None, budget=4)
    results = [wrapped("m", []) for _ in range(3)]
    assert [r["retries"] for r in results] == [3, 1, 0]   # 4 retries in total, then none
    assert calls["n"] == 3 + 4                             # 3 first attempts + exactly the budgeted retries
