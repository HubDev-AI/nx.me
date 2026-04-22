# AI Makeup Rollout Runbook

Controls staged rollout of the Makeup feature via `MAKEUP_ROLLOUT_PCT` env var.

---

## Launch-Gate Invariants

**All must be true before bumping `MAKEUP_ROLLOUT_PCT` above 0:**

- [ ] Unit 7c fully merged AND deployed to prod (not just staging) — self-serve biometric deletion (`DELETE /v1/users/me/makeup-data`) is non-optional during ramp window
- [ ] `DELETE /v1/users/me/makeup-data` verified in prod on a dev account:
  - Accept consent → generate → call endpoint → assert biometric fields NULL + `users.makeup_opted_out=true`
  - Log verification timestamp + verifier handle below
- [ ] `docs/operational/fal-dpa-status.md` shows `signed: true` AND `covers_art_9: true`
- [ ] Sentry biometric redaction verified in prod (Unit 7a) via synthetic exception round-trip
- [ ] Unit 13 red-team verdict is PROCEED or PROCEED WITH RESTRICTIONS
- [ ] `FEATURE_MAKEUP_ENABLED=true` deployed to production

**Verification log (fill in before first bump):**

| Date | Verifier | Verification | Notes |
|------|----------|-------------|-------|
| — | — | `DELETE /v1/users/me/makeup-data` prod check | PENDING |

---

## Rollout Steps

```
0 % → 10 % → 50 % → 100 %
```

Each step: deploy the new PCT, watch metrics for 24h before advancing.

### Set PCT in production

```bash
# Staging test first
MAKEUP_ROLLOUT_PCT=10 make up

# Production (replace with your infra's env-var update mechanism)
# Example: update fly.io secret, then deploy
fly secrets set MAKEUP_ROLLOUT_PCT=10
fly deploy
```

### Success criteria per step

| Metric | Threshold |
|--------|-----------|
| `makeup_failed_non_retryable_rate` | < 1 % of jobs |
| `makeup_generate_latency` p95 | < 30 s |
| `makeup_fair_use_hit_rate` | < 5 % of Pro users per day |
| `makeup_paywall_conversion_rate` | > 0 % (tracking, not a gate) |
| Sentry error rate on makeup routes | < baseline + 0.5 % |

---

## Rollback

```bash
# Instant: locks makeup for everyone, in-flight jobs complete normally
MAKEUP_ROLLOUT_PCT=0 # deploy

# Full kill-switch (403 FEATURE_DISABLED on all makeup routes)
FEATURE_MAKEUP_ENABLED=false # deploy
```

No DB migration needed. Both wiring paths survive rollback.

---

## Cohort Assignment

`hash(user_id) % 100 < MAKEUP_ROLLOUT_PCT`

- Stable: a user in-cohort at 10 % stays in-cohort at 50 % (monotonically inclusive)
- Deterministic: MD5 of user_id, last 128-bit integer mod 100
- Implementation: `app/entitlement/tier._in_rollout_cohort`

---

## Preset Rotation Cadence

- v1: YAML PRs only (direct edits to `prompts/makeup_presets.yaml`)
- v2 (deferred): user's own photo pre-rendered per preset
- Review cadence: quarterly (add to ops calendar)

---

## FAL_KEY Rotation

Per `rules/conventions.md`: every 90 days from first production use.

| Date | Rotated by | Notes |
|------|-----------|-------|
| — | — | First rotation pending DPA sign-off |

---

## Post-Launch Monitoring (30-day review)

- [ ] Fairness canary cron passes (3 fixture images × pinned fal endpoint version daily)
- [ ] Cap-hit rate review: if > 5 % of Pro users hit cap, tune `MAKEUP_FAIR_USE_DAILY_CAP`
- [ ] Cost review: inference cost ≤ $0.04 × 1.5 average per generation
- [ ] ArcFace / ΔE drift alert from canary — triggers Unit 13 re-run if > 1 month since last red-team
