# AI Makeup Fairness Red-Team Report — Week 3 (2026-04)

**Status:** PENDING — red-team not yet executed  
**Gate:** This report must be committed with an explicit verdict before Unit 14 starts.  
**Script:** `scripts/fairness_redteam_full.py`

---

## Run Configuration

| Field | Value |
|-------|-------|
| Run date | FILL IN |
| Operator | FILL IN |
| Script version | `git rev-parse HEAD` |
| Photo count | 50 (≥ 8 per MST bin 5–10) |
| Presets tested | All presets in `prompts/makeup_presets.yaml` |
| fal endpoint version | FILL IN |
| Environment | staging / prod (circle one) |

---

## MST Bin Coverage

| Bin | Photos | Identity gap (ArcFace) | Lipstick ΔE | Texture preservation | Pass? |
|-----|--------|------------------------|-------------|---------------------|-------|
| 5 | — | — | — | — | — |
| 6 | — | — | — | — | — |
| 7 | — | — | — | — | — |
| 8 | — | — | — | — | — |
| 9 | — | — | — | — | — |
| 10 | — | — | — | — | — |

**Thresholds:**
- ArcFace identity gap: ≤ 0.15 (cross-bin parity)
- Lipstick ΔE: ≤ 12.0
- Texture preservation: ≥ 0.80 SSIM

---

## Fallback Tree Execution

Per origin §9 step 5:

- [ ] All bins above threshold → **PROCEED**
- [ ] Single bin below threshold → add bin to `mst_bin_blocklist` for failing presets; ship with release-notes scope statement → **PROCEED WITH RESTRICTIONS**
- [ ] Multiple bins below threshold → hold launch → **HOLD**
- [ ] Texture-preservation failures only → drop `bold` from `supported_intensities` on affected presets; re-test → **RE-TEST**

**Outcome:** FILL IN (PROCEED / PROCEED WITH RESTRICTIONS / HOLD / RE-TEST)

---

## DPA Gate

- [ ] `docs/operational/fal-dpa-status.md` shows `signed: true`
- [ ] `docs/operational/fal-dpa-status.md` shows `covers_art_9: true`

If either box is unchecked, activate engine-swap branch proactively. Do not flip `MAKEUP_ROLLOUT_PCT` above 0.

---

## Preset / YAML Changes

If fallback tree triggered any changes:

```yaml
# Paste diff of prompts/makeup_presets.yaml here
```

---

## Release Notes Scope Statement

_(Required if any bins added to mst_bin_blocklist)_

> "AI Makeup v1 has limited preset coverage for MST bins X–Y. Full coverage is planned for v2 pending additional training data."

---

## Verdict

**FILL IN: PROCEED / PROCEED WITH RESTRICTIONS / HOLD**

Signed off by: FILL IN  
Date: FILL IN
