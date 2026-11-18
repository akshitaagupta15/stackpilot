# StackPilot (work in progress)

Evidence-driven AI stack optimization: define a workload, filter models by hard constraints, rank feasible models with visible, editable weights, and compare cost ranges with stated assumptions.

## Status
- [x] Cost engine (low / expected / high scenarios)
- [x] Recommendation engine (hard constraints → normalization → weighted score, deterministic)
- [x] FastAPI: `/health`, `/catalog`, `/cost`, `/recommend`
- [x] Benchmark Lab: invoice extraction benchmarks with measured model outputs
- [x] Benchmark reporting and summarization
- [ ] Gateway with fallback routing + request logging
- [ ] Dashboard (Next.js)
- [ ] Deployment

## Benchmark Lab

The benchmark runner evaluates model performance on an English and Hindi invoice extraction dataset.

- **Dataset:** `invoices_v1.jsonl` (40 invoices: 20 English and 20 Hindi).
- **Prompt version:** `extract_v2`.
- **Extraction fields:** invoice number, invoice date, vendor name, total amount, and currency.
- **Evaluation:** exact match, field accuracy, valid JSON, clean JSON, latency, truncation, retries, and token usage.
- **Reports:** saved under `backend/benchmark_runs/`.

### Benchmark limitations

### Benchmark results

Two full-dataset runs were conducted using Nemotron 3.5 Lightning (free),
the same 40-invoice dataset, and prompt version `extract_v2`.

| Metric | 6 Nov (800 tokens) | 18 Nov (2000 tokens) |
|---|---:|---:|
| Clean JSON | 4/40 (10%) | 39/40 (97.5%) |
| Exact match | 4/40 (10%) | 39/40 (97.5%) |
| Field accuracy | 10% | 97.5% |
| Truncated responses | 36 | 1 |
| English field accuracy | 20% | 100% |
| Hindi field accuracy | 0% | 95% |
| Mean latency | 9.23 sec | 6.65 sec |

The 18 November run used `max_tokens=2000`, a 60-second timeout,
and temperature 0.0. It completed all 40 requests without failures or retries.
One Hindi invoice (`hi-19`) was truncated.

The results show a substantial improvement under the 2000-token configuration.
However, token limit alone cannot be confirmed as the only cause.
The latency p95 is based on only 40 samples and should be treated as indicative.


- Results are specific to the model endpoint, prompt, dataset, and run settings.
- A successful benchmark does not establish production readiness.
- Free-model quota errors and request failures must be distinguished from extraction-quality failures.
- The benchmark dataset is limited to 40 invoices and is not representative of every real-world invoice format.
## Run

```bash
cd backend
pip install -r requirements.txt
python -m pytest -q
uvicorn app.main:app --reload
```

API documentation: `http://localhost:8000/docs`

## Live Backend API

Live API (demo, simulated data): https://stackpilot-b9fp.onrender.com/ready

Note: The free instance sleeps when idle, so the first request can take a while.

All dashboard data in the public demo is simulated and labelled as such.

## Important limitations

- `catalog.json` prices and metrics are **illustrative placeholders** (`pricing_verified_on: "ILLUSTRATIVE"`, `source: "estimated"`). Replace them with real, dated prices and benchmark output.
- The API reports this in `caveats` and lowers `confidence` accordingly.
- Benchmark measurements do not automatically replace illustrative catalog metrics unless explicitly integrated into the recommendation pipeline.
- The Nemotron free endpoint has usage and quota limitations. Do not send confidential or personal invoice data to it.
