# FAL.ai DPA Status

Tracks the Data Processing Agreement status with FAL.ai (fal.ai), the image generation provider used by the makeup feature.

## Status

```yaml
signed: false
last_reviewed: 2026-04-22
next_review: 2026-07-21
contact: legal@fal.ai
notes: >
  DPA review initiated. Required before makeup_enabled feature flag is turned
  on in production. FAL_KEY rotation every 90 days once signed.
```

## Checklist

- [ ] DPA signed with FAL.ai
- [ ] DPA stored in legal document vault
- [ ] `makeup_enabled` feature flag enabled in production
- [ ] FAL_KEY rotation scheduled (every 90 days per rules/conventions.md)
- [ ] FAL_KEY rotation cadence added to ops runbook

## Key rotation log

| Date | Rotated by | Notes |
|------|-----------|-------|
| — | — | Not yet started |
