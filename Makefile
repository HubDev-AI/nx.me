.PHONY: up down reset nuke nuke-keep migrate worker test lint format

# ── Start everything (first-time safe) ────────────────────────────────────────
up: .venv .env
	@docker compose up -d
	@echo "▶ Starting local Supabase..."
	@supabase start -x realtime,imgproxy,edge-runtime,logflare,vector,supavisor 2>/dev/null || true
	@.venv/bin/pip install -q -r requirements.txt -r requirements-dev.txt
	@.venv/bin/python -m app.migrations.run
	@echo ""
	@echo "  API:    http://localhost:8000"
	@echo "  Docs:   http://localhost:8000/docs"
	@echo "  Studio: http://localhost:54323"
	@echo ""
	@echo "  Run 'make worker' in another terminal for background jobs."
	@echo ""
	.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

# ── Stop everything ───────────────────────────────────────────────────────────
down:
	docker compose down
	supabase stop 2>/dev/null || true

# ── Nuke and rebuild ──────────────────────────────────────────────────────────
reset:
	docker compose down -v
	supabase stop --no-backup 2>/dev/null || true
	rm -rf .venv .env
	@echo "Reset complete. Run 'make up' to start fresh."

# ── Wipe all test data (no restart needed) ───────────────────────────────────
nuke:
	.venv/bin/python scripts/nuke-data.py

nuke-keep:
	.venv/bin/python scripts/nuke-data.py --keep-demo

# ── Run DB migrations ─────────────────────────────────────────────────────────
migrate:
	.venv/bin/python -m app.migrations.run

# ── ARQ background worker (run in separate terminal) ──────────────────────────
worker:
	.venv/bin/arq app.worker_settings.WorkerSettings

# ── Tests ─────────────────────────────────────────────────────────────────────
test:
	PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/pytest tests/ -x -q

# ── Lint & Format ────────────────────────────────────────────────────────
lint:
	.venv/bin/ruff check app/ tests/

format:
	.venv/bin/ruff format app/ tests/

# ── Internal targets ──────────────────────────────────────────────────────────
.venv:
	python3 -m venv .venv
	.venv/bin/pip install -q --upgrade pip

.env:
	@./scripts/local-env.sh
