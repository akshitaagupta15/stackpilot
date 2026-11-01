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

Live Backend API

Live API (demo, simulated data): https://stackpilot-b9fp.onrender.com/ready

Note: The free instance sleeps when idle, so the first request can take a while.

All dashboard data in the public demo is simulated and labelled as such.
```

## Important limitations
- `catalog.json` prices and metrics are **illustrative placeholders** (`pricing_verified_on: "ILLUSTRATIVE"`,
  `source: "estimated"`). Replace them with real, dated prices and benchmark output.
  The API reports this in `caveats` and lowers `confidence` accordingly.
