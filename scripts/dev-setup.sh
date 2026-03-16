#!/usr/bin/env bash
set -euo pipefail

BOLD=$(tput bold 2>/dev/null || true)
RESET=$(tput sgr0 2>/dev/null || true)
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

info()    { echo -e "${GREEN}▶ $*${NC}"; }
warn()    { echo -e "${YELLOW}⚠  $*${NC}"; }
error()   { echo -e "${RED}✗ $*${NC}"; exit 1; }
success() { echo -e "${GREEN}✓ $*${NC}"; }

echo ""
echo "${BOLD}NXME — Local Dev Setup${RESET}"
echo "────────────────────────────────────────"

# ── Prerequisites ─────────────────────────────────────────────────────────────
info "Checking prerequisites..."

command -v docker >/dev/null 2>&1          || error "Docker not found. Install: https://docs.docker.com/get-docker/"
command -v docker-compose >/dev/null 2>&1 \
  || docker compose version >/dev/null 2>&1 || error "Docker Compose not found."
command -v python3 >/dev/null 2>&1         || error "Python 3 not found."
command -v pip3 >/dev/null 2>&1            || error "pip3 not found."

PYTHON_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
if [[ "$(echo "$PYTHON_VERSION 3.12" | awk '{print ($1 >= $2)}')" != "1" ]]; then
  warn "Python $PYTHON_VERSION detected. Recommended: 3.12+"
fi

success "Prerequisites OK"

# ── Environment ───────────────────────────────────────────────────────────────
if [[ ! -f .env ]]; then
  info "Creating .env from .env.example..."
  cp .env.example .env
  warn ".env created — fill in your API keys before running the app."
  warn "Required: SUPABASE_URL, SUPABASE_ANON_KEY, SUPABASE_SERVICE_ROLE_KEY,"
  warn "          SUPABASE_JWT_SECRET, FAL_API_KEY, AWS_* keys, STRIPE_API_KEY,"
  warn "          ANTHROPIC_API_KEY, ADMIN_API_KEY, SECRET_KEY"
else
  success ".env already exists"
fi

# ── Docker services ───────────────────────────────────────────────────────────
info "Starting Docker services (Redis)..."
docker compose up -d

info "Waiting for Redis to be healthy..."
ATTEMPTS=0
until docker compose exec -T redis redis-cli ping 2>/dev/null | grep -q PONG; do
  ATTEMPTS=$((ATTEMPTS + 1))
  if [[ $ATTEMPTS -ge 20 ]]; then
    error "Redis did not become healthy after 20 attempts."
  fi
  sleep 1
done
success "Redis healthy"

# ── Python dependencies ───────────────────────────────────────────────────────
if [[ ! -d .venv ]]; then
  info "Creating Python virtual environment..."
  python3 -m venv .venv
fi

info "Installing Python dependencies..."
source .venv/bin/activate
pip install --quiet --upgrade pip
pip install --quiet -r requirements.txt

if [[ -f requirements-dev.txt ]]; then
  pip install --quiet -r requirements-dev.txt
fi
success "Python dependencies installed"

# ── Supabase migrations ───────────────────────────────────────────────────────
info "Checking Supabase connection..."
if python3 -c "
import os, sys
from dotenv import load_dotenv
load_dotenv()
url = os.getenv('SUPABASE_URL', '')
if 'CHANGE_ME' in url or not url:
    sys.exit(1)
" 2>/dev/null; then
  info "Running DB migrations via Supabase CLI (if installed)..."
  if command -v supabase >/dev/null 2>&1; then
    supabase db push --db-url "$(python3 -c "import os; from dotenv import load_dotenv; load_dotenv(); print(os.getenv('DATABASE_URL', ''))")" 2>/dev/null \
      && success "Migrations applied" || warn "Migration failed — run manually or check Supabase dashboard"
  else
    warn "Supabase CLI not installed — run migrations manually in the Supabase dashboard."
    warn "Migration files will be in: app/migrations/"
  fi
else
  warn "SUPABASE_URL not configured in .env — skipping migration."
fi

# ── Done ─────────────────────────────────────────────────────────────────────
echo ""
echo "────────────────────────────────────────"
success "Setup complete!"
echo ""
echo "  Start the API:    ./scripts/dev-start.sh"
echo "  Start the worker: source .venv/bin/activate && arq app.worker.WorkerSettings"
echo ""
echo "  API:   http://localhost:8000"
echo "  Docs:  http://localhost:8000/docs"
echo ""
warn "Remember to set ADVISOR_PERSONA_NAME in .env before implementing Story 7-2."
