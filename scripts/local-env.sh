#!/usr/bin/env bash
# Generate .env with local Supabase CLI defaults.
# These keys are well-known defaults that ship with every local Supabase instance.
set -euo pipefail

ENV_FILE="${1:-.env}"

if [[ -f "$ENV_FILE" ]]; then
  echo ".env already exists — skipping generation."
  exit 0
fi

cat > "$ENV_FILE" <<'EOF'
# ── App ───────────────────────────────────────────────────────────────────────
APP_ENV=development
SECRET_KEY=local-dev-secret-key-change-in-production
ADMIN_API_KEY=local-dev-admin-key

# ── Local Supabase (supabase start) ──────────────────────────────────────────
SUPABASE_URL=http://127.0.0.1:54321
SUPABASE_ANON_KEY=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZS1kZW1vIiwicm9sZSI6ImFub24iLCJleHAiOjE5ODM4MTI5OTZ9.CRXP1A7WOeoJeXxjNni43kdQwgnWNReilDMblYTn_I0
SUPABASE_SERVICE_ROLE_KEY=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZS1kZW1vIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImV4cCI6MTk4MzgxMjk5Nn0.EGIM96RAZx35lJzdJsyH-qQwv8Hdp7fsn3W0YpN81IU
SUPABASE_JWT_SECRET=super-secret-jwt-token-with-at-least-32-characters-long
DATABASE_URL=postgresql://postgres:postgres@127.0.0.1:54322/postgres

# ── Redis ─────────────────────────────────────────────────────────────────────
REDIS_URL=redis://:localdev@localhost:6379/0

# ── Adapters (all mocked for local dev — no external API calls) ──────────────
ADAPTER__NSFW_ADAPTER=mock
ADAPTER__FACE_ANALYSIS_ADAPTER=mock
ADAPTER__IMAGE_GENERATION_ADAPTER=mock
ADAPTER__LLM_ADAPTER=mock
ADAPTER__PAYMENT_ADAPTER=mock
ADAPTER__STORAGE_ADAPTER=supabase

# ── External APIs (fill in to use real adapters) ──────────────────────────────
FAL_API_KEY=
AWS_ACCESS_KEY_ID=
AWS_SECRET_ACCESS_KEY=
AWS_REGION=us-east-1
STRIPE_API_KEY=
STRIPE_WEBHOOK_SECRET=
ANTHROPIC_API_KEY=
EOF

echo ".env generated with local Supabase defaults."
echo "All adapters set to mock — edit .env to use real APIs."
