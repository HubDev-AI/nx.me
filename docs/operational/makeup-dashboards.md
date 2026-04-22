# AI Makeup Monitoring Dashboards

Reference for oncall and rollout operators. Update links when monitoring infra lands.

---

## Primary Metrics

| Metric | Description | Alert threshold |
|--------|-------------|----------------|
| `makeup_generate_latency` p95 | End-to-end generation time | > 30 s |
| `makeup_failed_non_retryable_rate` | Jobs reaching terminal failure | > 1 % |
| `makeup_fair_use_hit_rate` | Pro users hitting daily cap | > 5 % |
| `makeup_retention_cohort_tag` | Cohort retention tag | — (tracking) |
| `makeup_paywall_conversion_rate` | Paywall tap → Pro subscribe within 24 h | — (tracking vs glowup baseline) |

## Dashboard Links

_(Stub — replace with real URLs when monitoring infra is wired)_

| Dashboard | URL | Owner |
|-----------|-----|-------|
| Makeup generation latency | _TBD_ | Platform |
| Makeup error rates | _TBD_ | Platform |
| Fair-use cap hit rate | _TBD_ | Platform |
| Paywall conversion funnel | _TBD_ | Growth |
| Fairness canary (daily ArcFace/ΔE) | _TBD_ | ML Infra |

## Sentry

- Project: `nxme-backend`
- Filter: `tags.feature:makeup`
- Alert: error rate delta > 0.5 % vs 7-day baseline on `/v1/uploads/*/makeup/*`

## Fairness Canary

Cron: daily at 03:00 UTC  
Script: `scripts/fairness_redteam_full.py --dry-run` (3 fixture photos, pinned endpoint version)  
Alert: ArcFace gap > 0.15 OR ΔE > 12 on any fixture → page on-call + freeze ramp

## Key Operational Signals (oncall checklist)

1. p95 latency > 30 s for 5 min → check fal endpoint status + worker queue depth
2. Non-retryable rate spike → check `makeup_failure_reason` distribution in job rows
3. Cap-hit rate > 5 % → review `MAKEUP_FAIR_USE_DAILY_CAP` setting
4. Fairness canary alert → freeze ramp + notify ML team; re-run full red-team before next bump
