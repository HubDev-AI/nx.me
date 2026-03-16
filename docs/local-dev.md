---
status: complete
pass: 1
feature: "nxme"
created: "2026-03-15T21:30:00.000Z"
last_updated: "2026-03-16T01:30:00.000Z"
---

# Local Dev — NXME

## Quick Start

```bash
cp .env.example .env        # fill in API keys (see Environment Variables below)
./scripts/dev-setup.sh      # first-time setup
./scripts/dev-start.sh      # start the API (hot-reload)

# Second terminal — ARQ worker:
source .venv/bin/activate
arq app.worker.WorkerSettings
```

---

## Services

| Service | Image | Port | Purpose |
|---------|-------|------|---------|
| Redis | `redis:7.2-alpine` | 6379 | ARQ job queue + tier/entitlement cache |

**Local Supabase CLI** provides real Postgres, Auth, and Storage locally:
```bash
supabase start   # starts local Supabase (DB + Auth + Storage)
```
- Supabase Studio: `http://127.0.0.1:54323`
- API URL: `http://127.0.0.1:54321` (use as `SUPABASE_URL`)
- Get keys: `supabase status` → copy `anon key`, `service_role key`, `JWT secret`

External services that can't run locally use real APIs with test/dev credentials:
- **fal.ai** — dev API key (real generations, billed per call)
- **AWS Rekognition** — dev IAM user with Rekognition-only policy
- **Stripe** — test mode (`sk_test_*` keys)
- **Anthropic** — dev API key

To run without any external API calls, switch adapters to `mock` in `.env`:
```bash
ADAPTER__NSFW_ADAPTER=mock
ADAPTER__FACE_ANALYSIS_ADAPTER=mock
ADAPTER__IMAGE_GENERATION_ADAPTER=mock
ADAPTER__LLM_ADAPTER=mock
ADAPTER__PAYMENT_ADAPTER=mock
# ADAPTER__STORAGE_ADAPTER defaults to "supabase" (local CLI) — use "local" for offline dev
```

---

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `APP_ENV` | `development` | Runtime environment |
| `SECRET_KEY` | — | JWT signing key (32+ chars) |
| `ADMIN_API_KEY` | — | `X-Admin-Key` for `/admin/*` endpoints (tier CRUD) |
| `SUPABASE_URL` | — | Supabase project URL |
| `SUPABASE_ANON_KEY` | — | Public anon key (client-safe) |
| `SUPABASE_SERVICE_ROLE_KEY` | — | Service role key (server-only) |
| `SUPABASE_JWT_SECRET` | — | JWT secret from Supabase Settings → API |
| `REDIS_URL` | `redis://localhost:6379/0` | Local Docker Redis |
| `FAL_API_KEY` | — | fal.ai image generation |
| `AWS_ACCESS_KEY_ID` | — | AWS credentials for Rekognition |
| `AWS_SECRET_ACCESS_KEY` | — | AWS credentials for Rekognition |
| `AWS_REGION` | `us-east-1` | AWS region |
| `STRIPE_API_KEY` | — | Stripe secret key (`sk_test_*`) |
| `STRIPE_WEBHOOK_SECRET` | — | Stripe webhook signing secret |
| `ANTHROPIC_API_KEY` | — | Claude API key |
| `ADVISOR_PERSONA_NAME` | `TBD` | Advisor character name — set before Story 7-2 |
| `ADVISOR_CONTEXT_MEMORY_LIMIT` | `20` | Top-K memories per advisor turn |
| `MAX_UPLOAD_SIZE_MB` | `20` | Image upload size cap |
| `MAX_IMAGE_DIMENSION_PX` | `8192` | Max image dimension (pre-decode check) |
| `SIGNED_URL_EXPIRY_SECONDS` | `3600` | Supabase Storage signed URL TTL |
| `IMAGE_GEN_COST_CEILING_USD` | `0.05` | Abort generation if cost estimate exceeds this |
| `GENERATION_TIMEOUT_SECONDS` | `60` | ARQ job hard timeout |
| `CREDIT_COST_ALERT_USD` | `0.04` | Alert threshold for credit cost |
| `ADAPTER__*_ADAPTER` | (see .env.example) | Swap providers without code changes |

---

## Scripts

| Script | Purpose |
|--------|---------|
| `./scripts/dev-setup.sh` | First-time setup: prereqs, .env, Docker, Python venv, DB migrations |
| `./scripts/dev-start.sh` | Daily start: ensures Docker is up, activates venv, starts API with hot-reload |
| `./scripts/dev-reset.sh` | Clean slate: removes Docker volumes, venv, and .env |

---

## Common Tasks

**View Redis data:**
```bash
docker compose exec redis redis-cli
> KEYS *
> GET tier:default
> KEYS concurrent:*
```

**Tail API logs:**
```bash
./scripts/dev-start.sh   # logs stream to stdout
```

**Tail ARQ worker logs:**
```bash
source .venv/bin/activate
arq app.worker.WorkerSettings --verbose
```

**Stripe webhook forwarding (local testing):**
```bash
stripe listen --forward-to localhost:8000/webhooks/stripe
# copy the webhook secret to STRIPE_WEBHOOK_SECRET in .env
```

**Reset Redis only (keep Supabase data):**
```bash
docker compose restart redis
```

**Run a single migration manually:**
```bash
source .venv/bin/activate
python -m app.migrations.run --target 0001_initial
```

---

## Troubleshooting

| Issue | Fix |
|-------|-----|
| `redis-cli ping` returns nothing | `docker compose up -d` then wait 5s |
| `ModuleNotFoundError` | `source .venv/bin/activate && pip install -r requirements.txt` |
| Supabase auth fails | Check `SUPABASE_JWT_SECRET` matches your project's JWT secret |
| `CHANGE_ME` in .env causes startup crash | Fill in all required vars — app validates at startup |
| Adapter import error | Ensure `ADAPTER__*` values are valid provider names (see .env.example comments) |
