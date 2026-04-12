# AGENTS.md — `app/` (backend)

Python 3.12, FastAPI, ARQ worker, Supabase Postgres.
Root CLAUDE.md covers project-wide rules — this file is for backend-specific context only.

## Layout

- `main.py` — FastAPI app entry (`uvicorn app.main:app`)
- `api/` — route modules (auth, analyses, generation, advisor, posts, social, payment, webhooks, …)
- `services/` — business logic (called by routes, isolated from HTTP)
- `repositories/` — DB access (Supabase client wrappers)
- `db/` — schemas, query helpers
- `config/` — `AppConfig` (env-driven) + `tiers.py` (`TierConfig` for entitlement limits)
- `migrations/` — SQL migrations, runner at `migrations/run.py`
- `worker_settings.py` — ARQ task queue config (run via `make worker`)
- `features/`, `generation/`, `advisor/`, `face_analysis/`, `image_pipeline/`, `entitlement/`, `payment/` — domain modules
- Tests live at project root in `tests/`, **not** `app/tests/`

## Commands (from project root)

- `make up` — Supabase + API (serves on `:8000`)
- `make worker` — ARQ background worker (separate terminal)
- `make migrate` — apply migrations via `app/migrations/run.py`
- `make test` — pytest with `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1` (avoids global plugin conflicts)
- `make lint` / `make format` — ruff check / format over `app/ tests/`
- `make nuke` / `make nuke-keep` — wipe test data (keep demo accounts with `-keep`)

## pytest

Config in `pytest.ini`: `asyncio_mode = auto`, `--cov=app`, loads `pytest_asyncio` explicitly via `-p`. Prefer `make test` over bare `pytest`.

## Env

- `app/.env` (local values) + `app/.env.example` (placeholders)
- Never add fallback defaults for required env vars — fail fast.
- When adding/changing any env var, sync: `app/.env`, `app/.env.example`, `scripts/local-env.sh`, plus mobile equivalents if the value crosses the boundary.

## Conventions

- Config via `AppConfig` / `TierConfig` — no hardcoded limits, timeouts, or URLs.
- Behind proxies, **do not trust raw `X-Forwarded-For`** for rate limiting or auth. Use a trusted proxy strategy or socket IP.
- Async HTTP: use `httpx` + `PyJWK` (not `PyJWKClient` — it's urllib-based and blocks async handlers).
- If using PyJWT with non-HS256 algorithms, ensure `cryptography` is installed in `.venv` (not just system Python).
- Package management: `uv add <package>` — never `pip install`.

## Debugging paid-API flows

Never re-trigger a fal.ai / LLM call to diagnose — each retry costs real money. Inspect stored analyses/jobs in Supabase + tail `make worker` logs. Only regenerate as a last resort after log/DB inspection is exhausted.
