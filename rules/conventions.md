# Conventions

Cross-cutting invariants. Violating any of these requires explicit user approval.

## Code

- **No magic strings/numbers** — literals go in named constants, config, or env.
- **No env fallbacks** — fail fast if a required env var is missing.
- **Always reuse** — check for existing components/hooks/utilities before writing new ones.

## Python

- **Always use `uv`** for Python packages (never `pip` / `pip3`).

## Git / workflow

- **Branch workflow** — never push directly to `dev` / `main`; feature branch → PR → merge.
- **Verification before "done"** — run the Verification Loop in `CLAUDE.md`; no "looks right" claims.

## UX

- **Infinite scroll** for all pagination (no load-more buttons).

## Feature gating

- Use `useCapabilities()` in mobile UI and `Depends(require_app_feature("..."))` on backend routers.
- Never read raw `features.X` for gating outside the capabilities module. See `app/features/README.md`.

## Secret rotation

- **FAL_KEY** — rotate every 90 days (aligns with biometric purge TTL). Track status in `docs/operational/fal-dpa-status.md`.

## Infrastructure

- **Redis AOF persistence required** — makeup quota counters (makeup:quota:*, makeup:analyze_rate:*) are used for fair-use enforcement. Redis must be configured with `appendonly yes` in all non-development environments to survive restarts without losing rate-limit state.
