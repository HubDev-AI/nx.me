---
alwaysApply: true
---

# NXME Coding Conventions

## 1. Package Research — Always Use Context7

Before using any third-party library, resolve its latest API via Context7:
1. `mcp__context7__resolve-library-id` — find the library ID
2. `mcp__context7__query-docs` — fetch current API docs

Never guess at package APIs. A stale API assumption wastes implementation cycles.

## 2. No Magic Numbers or Strings

Every literal that carries business meaning must be a named constant:

```ts
// ❌ Wrong
if (user.trialCount < 2) { ... }
if (status === 'credit_holder') { ... }

// ✅ Correct
import { UserTier } from '@/config/entitlement'
// tier limits come from TierConfig (Amendment A-2), not named constants
if (tier === UserTier.CREDIT_HOLDER) { ... }
```

This applies to: limits, counts, timeouts, thresholds, status strings, enum values, route paths, event names.

## 3. All Config in Env / App Config

No hardcoded values for anything environment-sensitive:

```python
# ❌ Wrong
MAX_UPLOAD_SIZE = 20 * 1024 * 1024
IDENTITY_THRESHOLD = 0.75

# ✅ Correct — in config/app.py (pydantic-settings)
class AppConfig(BaseSettings):
    max_upload_size_mb: int = 20
    max_image_dimension_px: int = 8192
    signed_url_expiry_seconds: int = 3600
    image_gen_cost_ceiling_usd: float = 0.05
    generation_timeout_seconds: int = 60
    credit_cost_alert_usd: float = 0.04

# Per-tier limits (concurrent generations, similarity threshold, generation quota)
# come from TierConfig (config/tiers.py, Amendment A-2) — never from AppConfig
```

Everything in `config/` is validated at startup — fail fast if a required env var is missing.

## 4. No Code Duplication

Before writing a component, hook, utility, or service function:
1. Search the codebase for existing implementations
2. If one exists — import and reuse it
3. If it's similar — extend or generalise the existing one
4. Only create new if genuinely distinct

Shared UI: `src/components/` (or `packages/ui/`)
Shared hooks: `src/hooks/`
Shared utilities: `src/lib/`
Shared types: `src/types/`
Config/constants: `src/config/`

A new file in `src/lib/` or `src/components/` requires confirming no duplicate exists first.

## 5. Config Sources (specific to NXME)

**Rule: per-tier values live in `TierConfig` (Amendment A-2), not in `AppConfig`.**

### AppConfig (`config/app.py`) — platform-wide, not tier-specific

| Field | Env Var | Default |
|-------|---------|---------|
| `max_upload_size_mb` | `MAX_UPLOAD_SIZE_MB` | 20 |
| `max_image_dimension_px` | `MAX_IMAGE_DIMENSION_PX` | 8192 |
| `signed_url_expiry_seconds` | `SIGNED_URL_EXPIRY_SECONDS` | 3600 |
| `image_gen_cost_ceiling_usd` | `IMAGE_GEN_COST_CEILING_USD` | 0.05 |
| `generation_timeout_seconds` | `GENERATION_TIMEOUT_SECONDS` | 60 |
| `credit_cost_alert_usd` | `CREDIT_COST_ALERT_USD` | 0.04 |

### TierConfig (`config/tiers.py`) — per-tier, see Amendment A-2

These are **not** in AppConfig. Read via `EntitlementService` or `tier_config.{tier}.*`:
- `generation` limit (type + value) — e.g. `TIER__TRIAL__GENERATION__LIMIT=3`
- `advisor_nudges` limit
- `max_concurrent_generations` — per-tier parallelism cap
- `identity_similarity_threshold` — per-tier identity preservation strictness
- `features` flags — `advisor_chat`, `visual_comparison`

User tier enum (`TRIAL`, `CREDIT_HOLDER`, `PREMIUM`) must be defined once in `config/tiers.py` and imported everywhere — never as raw strings.
