# StackPilot (work in progress)

Evidence-driven AI stack optimization: define a workload, filter models by hard constraints,
rank the feasible ones with visible, editable weights, and see cost ranges with stated assumptions.

## Status
- [x] Cost engine (low / expected / high scenarios)
- [x] Recommendation engine (hard constraints -> normalization -> weighted score, fully deterministic)
- [x] FastAPI: `/health`, `/catalog`, `/cost`, `/recommend`
- [ ] Benchmark Lab (replaces the *estimated* metrics with measured ones)
- [ ] Gateway with fallback routing + request logging
- [ ] Dashboard (Next.js)
- [ ] Deployment

## Run
```bash
cd backend
pip install -r requirements.txt
python -m pytest -q
uvicorn app.main:app --reload     # docs at http://localhost:8000/docs
```

## Important limitations
- `catalog.json` prices and metrics are **illustrative placeholders** (`pricing_verified_on: "ILLUSTRATIVE"`,
  `source: "estimated"`). Replace them with real, dated prices and benchmark output.
  The API reports this in `caveats` and lowers `confidence` accordingly.
