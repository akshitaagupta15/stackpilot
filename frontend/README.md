# StackPilot frontend

Next.js (App Router) + TypeScript + Tailwind. No UI or chart libraries: the chart is plain SVG.

## Run locally
```bash
cp .env.local.example .env.local     # then edit the two values
npm install
npm run dev                          # http://localhost:3000
```
`NEXT_PUBLIC_API_URL` is the backend (local `http://127.0.0.1:8000` or the deployed URL).
`NEXT_PUBLIC_DEMO_KEY` is the public, read-only demo key. Anything starting with `NEXT_PUBLIC_` is
shipped to the browser, so never put `ADMIN_TOKEN` or a provider key there.

## Pages
- `/` recommend a model for a workload, with editable weights and cost ranges
- `/benchmarks` measured results only; shows an honest empty state when there are none
- `/gateway` send a request and see the routing path and fallback
- `/monitor` requests, success/fallback rate, latency percentiles, model health, alerts

## Deploy (Vercel)
Import the repo, set **Root Directory** to `frontend`, add the two env vars **before** the first build
(they are inlined at build time), then add the Vercel URL to `CORS_ORIGINS` on the backend.

## Known gaps
No automated frontend tests yet; CI checks that it type-checks and builds.
