# Deploying the StackPilot backend

Target: a Docker web service on **Render** (free instance) + a managed **Postgres** (e.g. Neon).
Free tiers change; check each provider's current limits before relying on them.

> Render's free web services spin down after ~15 minutes without traffic, so the first request after
> a pause is slow (a cold start). They also have no persistent disk, which is why production uses
> Postgres and not SQLite.

## 1. Create the database
1. Create a Postgres project (Neon: neon.com) and copy its connection string, which looks like
   `postgresql://USER:PASSWORD@HOST/DBNAME?sslmode=require`.
2. Keep it secret. It goes only into Render's environment settings, never into git.

## 2. Create the web service on Render
1. New -> **Web Service** -> connect the GitHub repo.
2. Language: **Docker**. **Root Directory: `backend`** (that is where the Dockerfile lives).
3. Instance type: Free. **Health Check Path: `/health`** (kept shallow on purpose; `/ready` also checks the database).
4. Add environment variables:

| Variable | Value | Why |
|---|---|---|
| `DATABASE_URL` | the Postgres connection string | persistence |
| `ADMIN_TOKEN` | a long random string (`python -c "import secrets;print(secrets.token_urlsafe(32))"`) | protects `/admin/*` |
| `DEMO_MODE` | `1` | forces the built-in simulator: the public deployment can never spend money |
| `SEED_DEMO_ON_START` | `1` | fills the dashboard with clearly-labelled simulated traffic |
| `DEMO_VIEWER_KEY` | `sp_demo_` + random text | a deliberately public, read-only key for the `demo` project (the frontend ships it) |
| `CORS_ORIGINS` | your frontend URL(s), comma-separated | set after the frontend is deployed |
| `RATE_LIMIT_PER_MIN`, `DAILY_LIMIT` | e.g. `20`, `500` | abuse protection |

Do **not** set `OPENROUTER_API_KEY` on the public service.

## 3. Verify
- `https://<service>.onrender.com/health` -> `{"status":"ok"}`
- `/ready` -> `"database":"ok"`
- `/docs` -> interactive API
- `/monitor/summary?hours=168` with header `X-API-Key: <DEMO_VIEWER_KEY>` -> ~4000 simulated requests

## 4. Things baked into the image
`model_profiles.json` and `benchmark_runs/` are copied into the image. Commit them and redeploy to
publish new benchmark results. The demo gateway policy needs the `demo/fail-model` and `demo/backup`
entries from `model_profiles.demo.json` to be present in `model_profiles.json`.

## Known limitations
- Rate limiting is in-process memory: correct for one instance only (use Redis for several).
- Tables are created at startup with `create_all`; there are no migrations yet (add Alembic before changing the schema in production).
- Monitoring aggregates up to 50,000 rows in Python; move to SQL aggregation for larger volumes.
- All dashboard data in the demo is simulated and labelled as such.
