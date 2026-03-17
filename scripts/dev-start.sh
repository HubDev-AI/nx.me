#!/usr/bin/env bash
set -euo pipefail

# Ensure Docker services are running
if ! docker compose ps --services --filter status=running 2>/dev/null | grep -q redis; then
  echo "▶ Starting Docker services..."
  docker compose up -d
fi

# Activate venv if not already active
if [[ -z "${VIRTUAL_ENV:-}" ]]; then
  if [[ -f .venv/bin/activate ]]; then
    source .venv/bin/activate
  else
    echo "✗ Virtual env not found. Run: ./scripts/dev-setup.sh" >&2
    exit 1
  fi
fi

echo ""
echo "▶ Starting NXME API (hot-reload)..."
echo "  API:  http://localhost:8000"
echo "  Docs: http://localhost:8000/docs"
echo ""
echo "  Start the ARQ worker in a second terminal:"
echo "  arq app.worker_settings.WorkerSettings"
echo ""

uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
