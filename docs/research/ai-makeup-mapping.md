# AI Makeup Mapping — Deep Research

**Status:** Pre-brainstorm research artifact
**Date:** 2026-04-12
**Audience:** Product + eng, before feature spec

> Feynman frame: *"If I can't explain why a choice wins, I haven't understood it yet."* This document explains AI makeup mapping from first principles, surveys the 2026 industry, and narrows the option space to a handful of concrete starting points for the brainstorm.

---

## TL;DR

1. **Two industries exist.** Real-time AR overlay (Perfect Corp, ModiFace, Snap, Meitu) and server-side generative AI (the research frontier). They solve different problems. nxme.ai already operates in the generative lane (FLUX.2 Flex Edit), so the AR-overlay stack is the wrong fight.
2. **GANs are dead for new builds.** BeautyGAN → EleGANt → BeautyREC are research-era. Diffusion-based transfer has dominated every metric since late 2024. Don't train a GAN.
3. **The 2026 SOTA for reference-based transfer is FLUX-Makeup** (arXiv 2508.05069, Aug 2025, Apache-2.0). It proved empirically that adding face parsers/ControlNets to FLUX Kontext *hurts* identity and transfer fidelity. This aligns with the existing lesson on PuLID: extra control signals break id weight. Simpler is better.
4. **fal.ai already hosts `image-apps-v2/makeup-application`** (preset-based, $0.04/image). This is a zero-ML-work MVP we could ship this sprint. Flow B (prompt/preset) is 10× easier than Flow A (reference-image transfer) and should come first.
5. **Fairness is a non-negotiable ship gate.** Perfect Corp preserves skin texture in only ~39% of Fitzpatrick 5-6 cases; YouCam/Snapchat documented to lighten melanin-rich undertones. Use the **Monk 10-scale (MST)**, not Fitzpatrick-6, and stratify every eval.

---

## 1. What "AI Makeup Mapping" actually is

Stripped of marketing, the feature is a function:

```
f(source_image, makeup_spec) → target_image
  where
    identity(source) ≈ identity(target)     # face is still recognizably yours
    face_shape(source) ≈ face_shape(target) # no morphing jaw/nose/eyes
    skin_tone(source) ≈ skin_tone(target)   # preserves ethnicity & undertone
    makeup_regions(target) ≈ makeup_spec    # lipstick appears where lipstick should
```

`makeup_spec` has two flavors:
- **Reference image** ("apply the makeup from *this* photo"). Flow A.
- **Prompt or preset** ("soft glam, nude lip, cat-eye"). Flow B.

Everything interesting in the research literature is a different answer to: *how do we satisfy those four approximations at the same time?* They fight each other. That's the core tension.

### The constraint triangle

```
         IDENTITY (don't drift the face)
                  /\
                 /  \
                /    \
               /      \
              /        \
    FIDELITY            REGIONALITY
  (makeup looks        (applied only to
   like real makeup)    the right regions)
```

- Push identity too hard → the makeup becomes a translucent hint (no change).
- Push fidelity → the face morphs into the reference's face (identity drift).
- Push regionality via explicit masks → stiff, painted-on look (FLUX-Makeup's ablation proved this).

The history of makeup transfer is a sequence of attempts to balance this triangle. Current best answer: *train a model with the right loss, let it learn the balance, don't over-constrain it at inference.*

---

## 2. How the industry actually solves it (two tech stacks)

### Stack A — Real-time AR overlay (30–60 fps, on-device)

Used by: **Perfect Corp / YouCam, ModiFace / L'Oréal, Snap Lens Studio, TikTok Effect House, Banuba, DeepAR, Meitu (live mode)**.

Pipeline:

```
Camera frame
   ↓
Face detector (BlazeFace / MediaPipe)
   ↓
68–468 landmark extractor (FAN, MediaPipe Face Mesh)
   ↓
3D face mesh fit (BFM / FLAME)
   ↓
Per-region texture lookup (lips, eyelids, cheeks, brows…)
   ↓
Shader blend (multiply/soft-light/overlay) with skin tone awareness
   ↓
Render to screen
```

- **Strengths:** free to run, real-time, deterministic, works offline, perfect identity preservation (it's *your* skin with a translucent shader).
- **Weaknesses:** fundamentally not photorealistic. Stays on the "CGI lipstick on a real face" side of the uncanny line. Can't do realistic eye makeup that casts micro-shadows or lipstick with real specular highlights. Struggles with side profiles, glasses, hair over the face.
- **Fairness:** multiple audits (ACM FAccT 2025, YouCam) show Eurocentric bias — preserves texture on light skin, smooths it on dark skin, lightens undertones.

**Why this isn't nxme.ai's fight:** building a competitive AR SDK takes 3–5 years and a specialized team. Perfect Corp's moat is 700+ brand SKU partnerships, not tech. We differentiate on quality-of-result, not on latency.

### Stack B — Server-side generative (1–8 s, GPU)

Used by: the entire research frontier, plus recent **Lensa-style** apps for "glow-up." Timeline:

| Year | Model | Signature idea |
|------|-------|----------------|
| 2018 | **BeautyGAN** | First real transfer; histogram matching on regions; MT-Dataset released |
| 2019 | **LADN** | Local adversarial discriminators per region |
| 2020–21 | **PSGAN / PSGAN++** | Pose/expression-robust via attention |
| 2021 | **SCGAN** | Style code disentanglement |
| 2022 | **EleGANt** | Elegant transfer via pyramid Laplacian |
| 2022 | **SSAT** | Symmetric semantic-aware transformer |
| 2023 | **BeautyREC** | Disentangled editing |
| 2024 | **Stable-Makeup** | First SD-based transfer, 20k synth pairs |
| 2024 | **SHMT** (NeurIPS) | Self-supervised, needs parser + depth at inference |
| **2025** | **FLUX-Makeup** | **FLUX.1 Kontext backbone + RefLoRAInjector, HQMT dataset (50k), Apache-2.0 — current SOTA** |

**Key insight from FLUX-Makeup paper:** they ran an ablation showing that *adding* explicit face-parsing ControlNets to FLUX Kontext *hurt* performance. The base model already understands faces well enough. Extra "help" adds noise. This is the single most important result for architecting our feature — it says *don't over-engineer*.

---

## 3. What's available RIGHT NOW (2026 practical layer)

This is the "models and settings" part of the question — what can we actually call today.

### 3.1 fal.ai — what's on the shelf

| Endpoint | Flow | Price | Identity | Control | Notes |
|----------|------|-------|----------|---------|-------|
| **`image-apps-v2/makeup-application`** | B (preset) | ~$0.04/img | Good | `style ∈ {natural, glam, smoky, bridal, korean, artistic}` × `intensity ∈ {subtle, medium, strong, dramatic}` | **Zero ML work.** MVP candidate. |
| **FLUX.2 Flex Edit** (currently used in `falai.py`) | B (prompt) | ~$0.05/img | Strong (identity-preserving edit) | Prompt + `guidance 3.5–4.5`, `steps 30–40` | Needs prompt-engineered recipe library. |
| **FLUX.1 Kontext** | B (prompt) | ~$0.04/img | Strong | Prompt | Base model that FLUX-Makeup was built on. |
| **Nano Banana** (Gemini 2.5 Flash Image) | B (prompt) | ~$0.03/img | Good | Prompt | ~2 s inference vs 5–8 s for FLUX. Worth benchmarking. |
| **FLUX.1 Fill + inpaint mask** | B (region) | ~$0.04/img | Variable | Mask + prompt | The "old way." FLUX-Makeup ablation suggests this is worse than direct Kontext. |
| **Custom model hosting** (fal Custom) | A (reference) | ~$1.50/GPU-hr + infra | Strong | Full pipeline | For self-hosted FLUX-Makeup (Apache-2.0). Q2 lane. |

### 3.2 Other hosting options

- **Replicate** — hosts stable-makeup, SHMT, various FLUX LoRAs. Higher latency than fal (cold starts).
- **HuggingFace Inference Endpoints** — can deploy FLUX-Makeup; GPU-hour billing.
- **Self-host on modal / RunPod** — cheapest at scale but adds ops surface we don't have bandwidth for.

### 3.3 Settings that matter (existing nxme.ai defaults)

From `app/generation/modules/styling.py` + memory's verified correction on FLUX.2 Flex Edit:

```
guidance_scale:        3.5–4.5   # portrait sweet spot; higher = more prompt, more drift
num_inference_steps:   30–40     # facial detail fidelity
id_weight (PuLID):     0.75–0.88 # below 0.70 breaks; above 0.90 uncanny
image_size:            square_hd # portrait_4_3 timed out on flux-pulid
```

**Implication for makeup:** because makeup *should* change the face more than pure styling, we probably want guidance at the upper end of the range (4.2–4.5) and steps at 35–40. But this needs empirical validation — one-off tests on 10–20 diverse photos before fixing.

### 3.4 Face parsing / region masks

If we ever need explicit masks (for inpainting or loss weighting), the best 2026 options:

| Tool | Regions | License | Notes |
|------|---------|---------|-------|
| **BiSeNet on CelebAMask-HQ** | 19 classes incl. lip/eye/brow | MIT | Classic baseline |
| **`jonathandinu/face-parsing` (HF)** | Same 19 classes | MIT | mit-b5 backbone, better accuracy |
| **MediaPipe Face Mesh** | 468 landmarks | Apache-2.0 | Best for derived regions (eyeshadow zone from eyelid landmarks) |
| **MICA / DECA** | 3D face reconstruction | research | For 3D mesh-aware work, overkill for MVP |

CelebAMask-HQ has no eyeshadow class — you derive it from `(l_eye + l_brow)` gap using mesh points. Blush/contour zones don't exist as classes in any public parser — you derive from landmark anchors.

**But remember FLUX-Makeup's ablation:** you probably don't need these for the generative path. Save them for evaluation, not inference.

---

## 4. Who's doing what (competitive landscape)

| Company | Tech stack | Makeup categories | Fairness | API available | Moat |
|---------|-----------|-------------------|----------|---------------|------|
| **Perfect Corp / YouCam** | AR overlay + 2025 generative ("AI Beauty Agent") | Full SKU catalog (lipstick, foundation, contour, blush, eyeshadow, liner, brows, lashes, highlighter) | Poor (~39% texture preservation FST 5-6) | YouCam Online Editor API | 705 brand clients, 1.1B downloads |
| **ModiFace** (L'Oréal) | CycleGAN + StarGAN + StyleGAN hybrid, in-browser TF.js | L'Oréal SKU catalog | Best public numbers (98.3% skin-tone detect on 1.6M eval) | Only inside L'Oréal brands | Exclusive partnerships |
| **Meitu** (450M MAU) | 3D face reconstruction + aesthetic reshape | Full + "medical-grade" features | CN-market focus | Limited intl API | China dominance |
| **Banuba SDK** | Neural nets per beauty task | Full | Moderate | Yes (commercial SDK) | Flexible third-party option |
| **Snap Lens Studio / TikTok Effect House** | AR overlay, 3D mesh | Creator-built | Creator-variable | Creator platform only | Social distribution |
| **Lensa / Remini** | SD-based glow-up avatars | Not SKU makeup | Moderate | No public API | "AI avatar" framing |
| **FaceApp** | CycleGAN + FaceNet identity | Limited makeup, more feature morph | Poor | No public API | Brand recognition |

**What nxme.ai is not going to beat:** SKU catalogs, brand partnerships, on-device real-time.
**What nxme.ai can beat:** the 2025–2026 generation already looks better than any AR overlay. If we ship the best-looking generated makeup with trend-native presets and fairness transparency, that's a real wedge.

---

## 5. Data — what exists, what's legal, what to collect

This is the part that blocks commercial shipping if handled wrong.

### 5.1 Public datasets

| Dataset | Size | Type | Demographics | License | Usable? |
|---------|------|------|--------------|---------|---------|
| **MT-Dataset** (BeautyGAN) | 3,834 | Unpaired | East Asian-heavy | Research-only (no explicit license) | ❌ Eval only |
| **LADN** | 750 | Unpaired | East Asian-heavy | Research-only | ❌ Eval only |
| **Makeup-Wild (MT-Wild)** | 772 | Unpaired, in-the-wild | Mixed | Research-only | ❌ Eval only |
| **CPM** (Color-Pattern Makeup) | 5,555 + 577 | Paired regions | Mixed | Research-only | ❌ Eval only |
| **BeautyFace** | ~3,000 | Unpaired | East Asian-heavy | Research-only | ❌ Eval only |
| **FFHQ-Makeup** (2025) | 90,000 (18k IDs × 5 styles) | **Paired via 3DMM** | FFHQ demographics | **Apache-2.0 on the makeup layer BUT parent FFHQ is CC-BY-NC-SA** | ⚠️ Research/eval only for commercial model |
| **MakeupQuad / EvoMakeup** (2025) | 10k+ quadruplets w/ text | Paired + text | Mixed | Research-only | ❌ Eval only |
| **CelebAMask-HQ** | 30k | Face parsing masks | Celebrity demographics | Non-commercial | Supporting only |
| **MST-E** (Google) | ~1k | Fairness slice | MST 1–10 stratified | **CC-BY** | ✅ Fairness eval |

### 5.2 The commercial-weights problem

*Every* public paired makeup dataset is either unpaired (weak supervision) or research-only. This means:
- We can **evaluate** models on these datasets.
- We can **train research prototypes**.
- We **cannot** ship weights fine-tuned on them in a commercial product without licensing risk.

### 5.3 What to collect in-house (if we go the training route)

Based on how Perfect Corp / ModiFace built theirs:
- **~5k paired before/after** images minimum for a useful LoRA.
- **≥50% FST 4–6** (dark-skinned subjects) — this is the fairness lever.
- **Diversity:** age (teen → 50+), lighting (studio, phone, indoor, outdoor), pose (frontal + 3/4), expression (neutral + smile), eyewear (with/without).
- **Paired means same identity, same pose, same lighting, before vs after makeup.** Synthesized pairs (3DMM-driven) are cheaper but ~10% quality gap vs. real pairs.
- **Licensing:** model release forms with explicit "AI training" clause. Not scraped, not Instagram.

### 5.4 Decision

For a first release, **we probably don't train.** We use off-the-shelf FLUX-Makeup (Apache-2.0, their HQMT training data is the vendor's problem) + preset-based Flow B via fal. In-house data collection starts only if we hit a quality ceiling we can't prompt/LoRA our way around.

---

## 6. Fairness — the ship gate

This is not optional. Three facts from the 2024–2025 audit literature:

1. **ACM FAccT 2025** confirmed Eurocentric bias in TikTok Bold Glamour filter.
2. **Perfect Corp / YouCam** preserves skin texture in only ~39% of FST 5–6 cases — actively smooths melanin-rich skin.
3. **Snapchat** documented to lighten undertones.

### What fairness discipline looks like

- **Use Monk Skin Tone (MST) 10-scale**, not Fitzpatrick-6. Google released this in 2022 specifically because Fitzpatrick collapses brown/dark skin into 1–2 bins.
- **Stratify every eval by MST bin**, not in aggregate. Report ArcFace cosine, FID, and makeup color ΔE per bin.
- **Hard thresholds:**
  - Identity ArcFace cosine similarity ≥ 0.65 on MT-test, ≥ 0.55 on Wild-MT (per model release standards).
  - **Cross-bin ArcFace gap < 0.10** (no bin degrades >10% vs best bin).
  - **Lipstick ΔE < 5** across MST 1–10 on the same preset (actual applied color must match spec).
  - Skin texture preservation binary: texture visible in ≥80% of samples across all MST bins.
- **Red-team 50 FST 5–6 photos before every model bump.** Block release on regression.
- **Transparency:** publish our fairness numbers at launch. Match ModiFace's bar, exceed Perfect Corp's.

---

## 7. Makeup taxonomy (for preset library design)

Don't build a flat list of 200 presets. Build a **(base aesthetic) × (regional variant) × (intensity)** matrix. This scales, and it maps to how users actually search ("smokey eye for a wedding").

### Evergreen bases (ship day one — 4–6 of these)

- **Clean Girl** — "no-makeup makeup," glowy skin, brushed-up brows, cream blush, nude glossy lip
- **Soft Glam** — medium coverage, defined brow, mascara, peach/pink blush, satin lip
- **Bold Glam** — full coverage, contour, winged liner, false lashes, bold lip
- **Smokey Eye** — darker eye focus, neutral lip
- **Bridal** — flawless base, long-wear, neutral-to-warm palette
- **Editorial** — artistic/avant-garde (low default priority but good for social sharing)

### 2025–2026 micro-trends (rotate quarterly — 4–6 live at a time)

- Latte Makeup (bronzy monochromatic)
- Douyin Makeup (glass skin, aegyo sal, gradient lip) — critical for Asian market
- K-beauty & J-beauty variants
- Strawberry Girl / Tomato Girl (flushed warm tones)
- Glazed Donut (extreme skin glow)
- Mob Wife (90s overlined lip, smoky brown, bronzer)
- Cherry Cola Lips
- Sunburnt Blush + faux freckles

### Regional variants (ship in phase 2 — localization)

- Douyin (CN), K-beauty (KR), J-beauty (JP), Arab / Dubai Bridal (MENA), Desi / Indian Bridal (IN/Desi diaspora), Western Soft Glam.

### Intensity axis (always present)

- `subtle` / `medium` / `strong` / `dramatic` — matches fal's preset endpoint axis exactly.

### Age layering (stretch goal)

- Same base preset tuned for 20s / 30s / 40+ (different coverage, undereye treatment, blush placement). Don't ship v1; note for roadmap.

**Trend decay ≈ 2 quarters.** Build a refresh pipeline (a content role or scheduled review), don't hardcode presets in `styling.py`.

---

## 8. Two technical flows — which first?

### Flow A: Reference-image transfer

> *"Apply the makeup from THIS photo to me."*

- **Upside:** highest "wow" for power users; enables TikTok-style "recreate this look" UGC loops.
- **Downside:** dataset problem is hard (paired training data), identity preservation under transfer is the hardest problem in the field, FLUX-Makeup self-hosting adds ops surface.

### Flow B: Prompt / preset

> *"Apply soft glam with a nude lip."*

- **Upside:** ships today. fal has a preset endpoint. FLUX.2 Flex Edit already in stack.
- **Downside:** can feel like a filter, not a creative tool. Less shareable magic.

**Recommendation: Flow B first, Flow A as phase 2.** Matches how the codebase is already structured (`styling.py` is prompt/keyword-based). Flow A becomes the premium / "Pro" feature.

---

## 9. Recommended 3-tier path (for the brainstorm)

These aren't commitments — they're the option space to argue about.

### Tier 1 — MVP this sprint (Flow B, zero ML work)

- Wire **fal.ai `image-apps-v2/makeup-application`** into `app/generation/adapters/falai.py`.
- New generation module: `app/generation/modules/makeup.py` with `MakeupModule` following the existing `StylingModule` pattern.
- Preset mapping: 6 evergreen styles × 4 intensities = 24 combos, powered by `style` and `intensity` query params, not prompts.
- Unit cost ~$0.04/image; identity handled by endpoint.
- Fairness smoke test on 30 MST-stratified images before launch.

### Tier 2 — Next sprint (Flow B, prompt-engineered)

- Extend `StylingModule` pattern with a HEX-coded recipe library (e.g., `"smokey eye + nude lip #C08478 + bronze contour"`) fed into FLUX.2 Flex Edit.
- Recipes live in `prompts/makeup_recipes.yaml` (not hardcoded — per `feedback_no_hardcoded_urls`).
- Settings: `guidance_scale=4.2`, `num_inference_steps=40`, `image_size="square_hd"` as starting point; validate empirically.
- Add trend-of-the-month slot surfaced to users.
- Benchmark **Nano Banana** as an A/B alternative — if it beats FLUX.2 Flex Edit on latency at equal identity, switch or split traffic.

### Tier 3 — Q2 (Flow A, self-hosted SOTA)

- Self-host **FLUX-Makeup** (Apache-2.0) on fal Custom Models or Replicate.
- Reference-image transfer: user uploads inspiration photo → model transfers makeup, preserves identity.
- Gate behind post-hoc `identity_checker.py` with hard ArcFace threshold.
- Premium tier / paywall candidate.
- Only pursue if Tier 1+2 hit the quality ceiling.

### Anti-patterns we explicitly reject

- ❌ Train a GAN (dominated since 2024).
- ❌ Build BiSeNet → FLUX Fill per-region inpainting pipeline (FLUX-Makeup ablation disproved the value).
- ❌ Build an AR real-time overlay (wrong fight; Perfect Corp's moat).
- ❌ Scrape Instagram for training data (licensing bomb).
- ❌ Hardcode HEX colors or preset names in Python (goes to YAML config).

---

## 10. Evaluation plan

For every tier, same eval harness:

### Metrics

- **Identity:** ArcFace cosine similarity (source vs target).
- **Identity robustness:** BlendFace secondary score; landmark consistency (per MediaPipe).
- **Image quality:** FID vs FFHQ; NIQE (no-reference); LPIPS; face-region fLPIPS.
- **Makeup fidelity:** region-specific ΔE color match (lipstick, eyeshadow); edge presence of liner/brow.
- **User preference:** pairwise win rate vs. unmodified source + vs. YouCam output (≥55% target).

### Thresholds

- ArcFace ≥ 0.65 on curated portrait set; ≥ 0.55 on wild in-the-wild set.
- FID relative gap across MST bins < 30%.
- Lipstick ΔE < 5 across MST bins on the same preset.
- User preference ≥ 55% vs. source (anything below is filter-tier, not feature-worthy).

### Eval datasets (stratified)

- MT-test, Wild-MT, LADN — for literature comparability.
- **MST-E (CC-BY)** — fairness slice across Monk 1–10.
- **In-house holdout** — ~100 stratified photos covering MST 1–10, 4 age bins, glasses/no-glasses, 3 lighting conditions.

### Hard-case subsets (tracked separately)

- Glasses, side profile, heavy occlusion, hijab, facial hair (for masculine / androgynous users), low light, motion blur.

---

## 11. Open questions for the brainstorm

These are the decisions the brainstorm should actually land.

### Product

1. **Is makeup a "mode" under the existing generation flow, or a separate flow?** (Architectural: new `MakeupModule` alongside `StylingModule`, or dedicated screen?)
2. **Reference image (Flow A) — in v1 or not?** Flow B is 10× easier. But Flow A is the viral "recreate this TikTok look" hook.
3. **Who is the primary user?** Casual glow-up seeker vs. makeup enthusiast vs. content creator? Determines preset library depth and UX.
4. **Subtle-by-default or dramatic-by-default?** Affects `intensity` preset value and user trust.
5. **How much user control?** Preset only (1 tap), preset + intensity (2 taps), preset + per-region intensity (lip/eye/cheek sliders = heavy UX), prompt input (power user only)?
6. **Male / androgynous users** — what does "no makeup" vs. "groomed look" (brow fill, lash curl, subtle contour) mean for them? Skip v1 or include?
7. **Undo / compare slider** — is before/after comparison a v1 feature?

### Engineering

1. **fal preset endpoint vs. FLUX.2 Flex Edit prompt-engineered — which Tier 1?** Preset endpoint is less work but we own less of the experience.
2. **Where does the preset library live?** `prompts/makeup_recipes.yaml` vs. database vs. Supabase config (for live updates without redeploy).
3. **Do we need a new evaluation harness or can we reuse `identity_checker.py`?** Probably extend.
4. **Latency budget.** 2 s (Nano Banana) vs 5–8 s (FLUX). UX design hinges on this.
5. **Cost ceiling per user.** At $0.04/image × N retries × free tier → what's the unit economics?

### Fairness / Trust

1. **Do we ship the fairness scorecard publicly?** (ModiFace does; Perfect Corp doesn't.) Opportunity to differentiate.
2. **What's the red-team cadence?** Every model bump? Quarterly?
3. **Consent copy.** "This modifies your face" — how do we say it without killing conversion?

### Data

1. **Ever collect in-house training data?** If yes, when (quality ceiling, resource availability)?
2. **User-opt-in training loop.** Ask users "can we use this for improvement?" — high-quality signal if consented.

---

## 12. References (citations)

### Papers

- BeautyGAN — Li et al., ACM MM 2018 — [github.com/wtjiang98/BeautyGAN_pytorch](https://github.com/wtjiang98/BeautyGAN_pytorch)
- PSGAN — Jiang et al., CVPR 2020 — [arxiv.org/abs/1909.06956](https://arxiv.org/abs/1909.06956)
- EleGANt — Yang et al., ECCV 2022 — [github.com/Chenyu-Yang-2000/EleGANt](https://github.com/Chenyu-Yang-2000/EleGANt)
- SSAT — Sun et al., AAAI 2022 — [arxiv.org/abs/2112.03631](https://arxiv.org/abs/2112.03631)
- BeautyREC — Yan et al., CVPR 2023
- Stable-Makeup — Zhang et al., SIGGRAPH 2025
- SHMT — Sun et al., NeurIPS 2024
- **FLUX-Makeup — Yang et al., arXiv:2508.05069, Aug 2025** ([arxiv.org/abs/2508.05069](https://arxiv.org/abs/2508.05069)) — **primary reference**
- FFHQ-Makeup (2025) — paired dataset
- MakeupQuad / EvoMakeup (2025)

### Fairness

- ACM FAccT 2025 — TikTok Bold Glamour filter audit
- Google Monk Skin Tone scale + MST-E dataset — [skintone.google](https://skintone.google)
- Perfect Corp transparency report (limited)
- ModiFace 98.3% skin-tone detection paper

### Infrastructure

- fal.ai `image-apps-v2/makeup-application` — [fal.ai/models](https://fal.ai/models)
- fal.ai FLUX.2 Flex Edit — current nxme.ai backbone
- Nano Banana / Gemini 2.5 Flash Image
- HuggingFace `jonathandinu/face-parsing` — mit-b5 face parser
- MediaPipe Face Mesh — [mediapipe.dev](https://mediapipe.dev)

### Internal

- `/tmp/makeup_research_commercial.md` — full competitor deep-dive
- `/tmp/makeup_research_technical.md` — full model / architecture research
- `/tmp/makeup_research_data.md` — full dataset / fairness research

---

## What this document does not do

- It does not specify the feature. That's the brainstorm's job.
- It does not commit to a tier. Tier 1 is a recommendation, not a decision.
- It does not estimate effort. Sprint planning follows the brainstorm.
- It does not resolve product questions (§11). Those are *inputs* to the brainstorm.

This is the map. The brainstorm picks the route.

---

## 13. Payments Integration — Paid-Only Commitment & Review Findings

**Added 2026-04-20.** This section captures the outcome of a `/ce:brainstorm` + document-review cycle on whether the credits-only payments engine should be pre-wired for a future paid-only make-up action. Consensus across 7 reviewers: **do not modify the payments doc now; carry all make-up-specific payment design here and resolve it in the make-up brainstorm**.

### 13.1 The commitment

Make-up is a **paid-only action** at launch. Credits sourced from the Free tier (`signup_grant`, `weekly_free_grant`) must not be spendable on make-up. Glow-up and Ada remain spendable from any credit source.

The canonical gating seam is the project's capabilities module (per `CLAUDE.md`):
- **Backend**: `Depends(require_app_feature("makeup"))` on the make-up router.
- **Mobile**: `useCapabilities().makeup_enabled` to gate UI entry points.

At Stage 2 planning time, decide the eligibility mechanism between:
- **(A) Capability-tier gate** — `makeup_enabled = True` iff user has active Pro subscription (tier-label-derived). Simplest. No ledger changes. Deprecates credits-as-cost-model for make-up entirely (make-up is free while Pro). Mid-grace and post-grace-expiry retention of make-up tracks tier label, not ledger balance.
- **(B) Ledger-source-restricted reserve** — make-up costs credits like glow-up, but `credit_reserve_v2(p_action_type='makeup')` sums only paid-source ledger entries. Requires an eligibility table, split-debit accounting, and new blocked_reason. Preserves usage-based economics but adds substantial schema surface.
- **(C) Hybrid** — capability gate for access + ledger cost for per-use debit, drawn from a unified Pro-credit pool. Capability-tier decides "can see the button"; ledger decides "how many make-ups left this cycle".

**Recommendation**: start with **(A)** for simplicity. Only move to (B) or (C) if post-launch data shows make-up is a margin-killer that requires per-use metering inside the Pro tier.

### 13.2 Shipped payments state (2026-04-20)

Already merged on `dev`:
- Migrations `0048–0061`. Don't assume a greenfield starting number — any Stage 2 migration must land at `0062+`.
- `credit_reserve` / `credit_commit` / `credit_release` / `credit_refund` RPCs already take `(UUID, UUID, TEXT action_type)` per `0049`. Action type is caller-supplied; Stage 2 MUST validate `p_action_type` at API route level (server-side constant derived from endpoint, never passed from client body).
- `credit_apply_monthly_allotment` (shipped `0050`) uses **single-row net-delta REPLACE** — the `retained_preserved` two-row pattern in earlier drafts is NOT shipped and was explicitly rejected in `0048`'s comment.
- Advisory-lock domain is `hashtextextended(user_id::text, 0)` (64-bit), not `hashtext` (32-bit). Any new Stage 2 RPC must match.
- Credit pack SKU fully removed (`0058`). No re-introduction planned.
- `credit_ledger.type` CHECK enum at Stage 2 start: `trial_grant, purchase, reserve, commit, release, refund, adjustment, signup_grant, signup_grant_suppressed_by_fingerprint, weekly_free_grant, monthly_allotment, ada_message, dispute_compensation`. Any new type for make-up must extend this with the standard DROP-ADD CONSTRAINT pattern.

### 13.3 Review findings (carry into Stage 2 brainstorm)

Seven reviewers (coherence, feasibility, product-lens, design-lens, security-lens, scope-guardian, adversarial) evaluated a draft of paid-only eligibility wiring for the payments doc. Findings below survive for Stage 2 regardless of which path (A/B/C) is chosen.

#### Product / strategic

1. **Premise needs evidence.** "Make-up must be paid-only" is stated, never defended. Stage 2 planning should produce either (a) unit-cost model showing make-up inference is materially more expensive than glow-up, or (b) funnel hypothesis that paid-only make-up converts Free users better than inclusive pricing. Without this, path (A) is the right risk-minimizing default.
2. **Debit-ordering is secondary.** Free-first vs paid-first ordering matters only if path (B) is chosen AND users can hold mixed-source balances. In path (A) the question is moot. In path (C), favor paid-first to accelerate paywall signals, not free-first.
3. **Post-grace hoarding loophole (path B/C only).** A user who churned with retained paid balance could consume make-up indefinitely while earning weekly free credits for glow-up / Ada — effectively trading one failed Pro cycle for ongoing paid-action access. Either bound paid-balance lifespan after grace expiry, or use path (A) where the tier label gates access directly.
4. **Positioning shift.** Splitting credits by source changes the mental model from "one credit pool, all actions" to "two pools, different eligibility". For a majority-female audience where copy simplicity matters, path (A) keeps the model unified: "Pro unlocks make-up; Free unlocks glow-up + Ada".

#### Feasibility

5. **Migration baseline is `0062+`**. Any eligibility schema, cost column, or new RPC must account for shipped state (`0048–0061`).
6. **Don't rewrite shipped `0050`**. The two-row `retained_preserved` REPLACE pattern was deliberately excluded. Stage 2 must either live with single-row REPLACE (path A natively avoids this issue) or propose a compensating-entry ledger audit that does not depend on two-row nets.
7. **Advisory-lock domain**: use `hashtextextended(user_id::text, 0)` consistently with `0049/0050`.
8. **Server-side `p_action_type`**: the API route must hardcode the action type string per endpoint. Do not pass through request body. This is the sole enforcement point for path-B eligibility.

#### Security

9. **`ledger_type_eligibility` (if path B/C) requires RLS** `DENY ALL FOR anon, authenticated` per the pattern shipped for `signup_grants_issued`. The table is the sole enforcement point for paid-only invariants; compromise = silent bypass.
10. **`paid_balance_milli` must not appear on `EntitlementState`**. Leaks pool composition to clients; `remaining_makeups` is sufficient.
11. **`dispute_compensation` is ambiguous**. It is written for both dispute-won refunds AND future staff apology credits. If path B/C ever extends eligibility to this type for make-up, split into distinct ledger types (`dispute_won_refund` vs `admin_goodwill_credit`) first, otherwise goodwill credits silently grant paid-only access.

#### Design (path B/C only)

12. **Entry-point gate before reserve**. A Free user should discover make-up's paid-only nature *before* tapping in and triggering a rejection. Pro-only badge or locked state on the entry point.
13. **`makeup_requires_paid_credits` empty state**. Distinct from plain `insufficient_credits`. Must not imply "out of credits" when user has free-source credits left for glow-up / Ada. Copy must remain female-first per `feedback_female_user_targeting`.
14. **Combined-state copy**. When both weekly-regen copy (paywall bottom line) AND make-up paywall fire on the same screen, information hierarchy must be resolved. "Your next free glow-up drops in 3 days" + "Make-up requires Pro" cannot render with equal prominence.
15. **Accessibility**. If mobile shows split pools via color, screen readers need explicit labels ("3 free-tier credits, 25 Pro credits"). Non-color indicator required.

#### Adversarial (path B/C only)

16. **REPLACE vs in-flight reservation race**. If path (B) is chosen, Pro subscription activation during a mid-flight glow-up reservation must specify exact transaction ordering — otherwise release after REPLACE can leave phantom free or negative paid pool balance.
17. **Reservation TTL**. Without a reaper, a crashed worker mid-reserve blocks the user's paid pool indefinitely. Path (A) avoids this because eligibility is tier-derived, not balance-derived.
18. **Eligibility-table mutation during deploy** (path B/C). A migration that flips historical-row classification during live traffic changes `free_milli / paid_milli` views of in-flight reserves retroactively. Gate all eligibility-table writes behind maintenance windows or model-classification-as-frozen-per-row.
19. **Grandfathering across resub**. When a canceled Pro user resubscribes months later on a newer `plan_versions` row, does cohort assignment preserve original price/cost? Stage 2 must pin: `subscriptions.plan_version_id` on fresh resub = original version OR current default?
20. **Lint-allowlist drift**. If a coverage test gates new ledger types against an "intentionally blocked" allowlist, any future PR can silently expand the allowlist to suppress a failing test. Back allowlist with schema-level constraint (`CHECK (delta = 0)` for audit-only types).

#### Scope

21. **Default to the smallest change.** Path (A) — capability gate via `require_app_feature` + tier lookup — is a single `features.py` entry plus one line in the make-up router. No migration. No ledger changes. No eligibility table. This is the 80/20 starting point.
22. **Re-cost `makeup_cost_milli` only if path (B/C)**. If make-up is metered, seed cost AFTER running empirical inference benchmarks across the 3 fal.ai endpoints in §3.1. Seeding 100 now (parity with glow-up) bakes in an unvalidated cost via R12's grandfathering freeze.
23. **Coverage test (path B/C) is premature.** Gating ledger-type coverage before >1 paid-only action exists enforces a generality with zero current consumers.

### 13.4 Concrete Stage 2 checklist

When the make-up brainstorm opens:

- [ ] Decide path A / B / C with an explicit rationale documented in the requirements doc.
- [ ] If path A: single capability registration + tier lookup. No migration. Skip §13.3 findings 5–11, 16–20, 22–23.
- [ ] If path B/C: start from §13.2 shipped state, land everything in `0062+`, address all §13.3 findings.
- [ ] Either path: server-side hardcoded `p_action_type` in the make-up endpoint handler (§13.3 finding 8).
- [ ] Either path: make-up module in `app/generation/modules/makeup.py` following `StylingModule` pattern (see §9 Tier 1).
- [ ] Either path: `useCapabilities().makeup_enabled` guards mobile entry.
- [ ] Document test plan for chosen path's blocked-access behavior (Free → make-up tap).
- [ ] Register any new user-owned surfaces introduced by make-up with the delete-account hard-reset registry (`docs/solutions/best-practices/account-delete-hard-reset-invariant-2026-04-18.md`).

### 13.5 Decision log

- **2026-04-20** — `/ce:brainstorm` session: user framed make-up as paid-only, free+weekly credits restricted to glow-up + Ada. Initial direction was path (B) with eligibility table + split-debit columns. Document-review (7 reviewers) converged on: (a) Stage 1 wiring is YAGNI, (b) shipped `0048–0061` diverges from plan assumptions, (c) simpler path-A alternative via capabilities module was not compared. Decision: carry all payment-specific make-up design in this file (§13), keep the payments brainstorm doc clean, resolve path A/B/C in the make-up brainstorm cycle.
