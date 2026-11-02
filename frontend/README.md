# StackPilot frontend

Next.js (App Router) + TypeScript + Tailwind. No UI or chart libraries: the chart is plain SVG.

## How it talks to the backend
The browser only calls this site (`/api/...`). `next.config.mjs` forwards those calls to the backend
(`BACKEND_URL`). Because the login cookie then belongs to this site, login works in Safari and other
browsers that block third-party cookies. The login cookie is `HttpOnly`, so page scripts cannot read it.

## Run locally
```bash
cp .env.local.example .env.local     # then edit the values
npm install
npm run dev                          # http://localhost:3000
```
- Local backend: start it with `COOKIE_SECURE=0` (plain http), e.g. PowerShell `$env:COOKIE_SECURE="0"` before `uvicorn`.
- Live backend: set `BACKEND_URL` to its URL. If login does not stick on `http://localhost`, use Chrome or Edge.
- `NEXT_PUBLIC_DEMO_KEY` is the public, read-only demo key. `NEXT_PUBLIC_*` values are shipped to the browser,
  so never put `ADMIN_TOKEN` or a provider key there.

## Pages
- `/` recommend a model for a workload (weights, cost ranges, illustrative or measured data)
- `/benchmarks` measured results only; honest empty state when there are none
- `/gateway` send a request, optionally with your own key and policy, and see the routing path
- `/monitor` public demo monitoring (simulated traffic)
- `/signup`, `/login` accounts
- `/dashboard`, `/dashboard/[id]` your projects: API keys, routing policies, and your own usage

## Deploy (Vercel)
Import the repo, set **Root Directory** to `frontend`, and add `BACKEND_URL` (your Render URL) and
`NEXT_PUBLIC_DEMO_KEY` **before the first build** (both are read at build time).
No CORS setup is needed for the site itself, because the browser talks to the same origin.
Note: Vercel's documentation gives different proxy timeouts (30 s and 120 s). A sleeping free backend can take
about a minute to wake, so the app pings it on page load, and the first request after a long pause can still be slow.

## Known gaps
No automated frontend tests yet; CI checks that it type-checks and builds.
