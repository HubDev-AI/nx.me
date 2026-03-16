#!/usr/bin/env bash
set -euo pipefail

BOLD=$(tput bold 2>/dev/null || true)
RESET=$(tput sgr0 2>/dev/null || true)
RED='\033[0;31m'
NC='\033[0m'

echo ""
echo "${BOLD}NXME — Dev Reset${RESET}"
echo "This will destroy all local Docker volumes (Redis data) and your .env file."
echo -n "Continue? [y/N] "
read -r CONFIRM
if [[ ! "$CONFIRM" =~ ^[Yy]$ ]]; then
  echo "Aborted."
  exit 0
fi

echo "▶ Stopping and removing containers + volumes..."
docker compose down -v

echo "▶ Removing virtual environment..."
rm -rf .venv

echo "▶ Removing .env..."
rm -f .env

echo ""
echo -e "${RED}✓ Reset complete.${NC} Run ./scripts/dev-setup.sh to start fresh."
