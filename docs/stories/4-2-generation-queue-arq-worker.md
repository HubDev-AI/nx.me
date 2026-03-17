---
id: "4-2-generation-queue-arq-worker"
status: ready
created: 2026-03-17
---

# Story: Generation Queue & ARQ Worker

## User Story

As the platform, I need an async priority job queue with per-tier lanes, credit lifecycle management, and a stuck-job watchdog, so that glow-up generation scales to 10k concurrent requests without dropping jobs or permanently consuming credits on failure.

## Acceptance Criteria

- Given three queue lanes (`generation:premium`, `generation:credit`, `generation:trial`), When an ARQ Worker with explicit queue ordering is started, Then premium jobs are always processed before credit jobs, which are processed before trial jobs — verified by asserting order under mixed-lane load.
- Given 12,000 simultaneous generation requests, When submitted, Then zero HTTP 5xx responses occur; excess requests are queued and all clients receive a queued-status response within ≤5s (AC-NFR6).
- Given a job that exceeds `GENERATION_TIMEOUT_SECONDS + 30`, When the stuck-job watchdog runs, Then the job transitions to `status='failed'`, `failure_reason='GENERATION_TIMEOUT'`, and the credit reservation is released — credits are never permanently consumed by a stuck job (AC-D2).
- Given the `GlowUpGeneratorPort` Protocol, When a mock implementing it is injected, Then `process_generation_job` completes the full lifecycle (reserve → generate → identity check → commit/release) using only the port interface — no direct fal.ai API calls in the worker function.
- Given rolling 24h cost average exceeding `IMAGE_GEN_COST_CEILING_USD`, When the circuit breaker checks, Then new `TRIAL` lane enqueues are throttled and an alert is emitted (AC-A6, AC-NFR9).

## Architecture Guardrails

### Technology Stack

- **Backend:** Python 3.12 + FastAPI
- **Job Queue:** ARQ 0.27.0 (async Redis-based job queue with priority lanes)
- **AI Generation:** fal-client 0.13.1 (fal.ai REST client)
- **Identity Check:** insightface 0.7.3 (ArcFace buffalo_l model, CPU inference)
- **ONNX Runtime:** onnxruntime 1.24.3 (required by insightface for model inference)
- **Numerical:** numpy 2.4.3 (already pinned in requirements.txt)
- **Image processing:** Pillow 12.1.1 (already pinned in requirements.txt)
- **NSFW screening:** AWS Rekognition via boto3 1.42.68 (already pinned)
- **Database:** Supabase PostgreSQL via supabase-py 2.15.1 (pinned in requirements.txt)
- **Cache/Queue:** Redis 7.x via redis-py 5.2.1 (pinned in requirements.txt)
- **Config:** pydantic-settings 2.9.1 (pinned in requirements.txt)

### Non-Negotiable Boundaries

- **C-1 LOCKED:** AI modifies only hair, eyebrows, style, lighting -- bone structure, nose, jaw, and face shape are immutable at generation prompt level and validated post-generation via identity similarity score.
- **C-2 LOCKED:** No attractiveness score or ranking in any API response, UI element, or data model field.
- **DD-5 LOCKED:** Image-to-image diffusion only; text-to-image generation is prohibited.
- **AC-A1:** Reserve-before-enqueue for all credit and trial consumption.
- **AC-D1:** All entitlement checks route through `EntitlementService`; no handler reads subscription or credit fields directly.
- **ADR-1:** ArcFace embeddings are ephemeral -- computed in-worker, never persisted.
- **NXME is NOT a beauty filter:** Never smooth skin, remove freckles, or retouch. Styling only. The PuLID output is the final image -- no post-processing face enhancement model.

### Generation Pipeline (Full Lifecycle)

```
User selfie (in raw-selfies bucket)
    |
[1] Adaptive crop (if face < 25% of image area)
    |
[2] Build prompt (mode + face analysis → keywords)
    |
[3] Compute adaptive parameters (face size, symmetry, keyword count)
    |
[4] Call primary model (Flux PuLID)
    |
[5] NSFW screen output (Rekognition) -- on generated image before commit
    |
[6] ArcFace identity check
    |  → If fail → retry once with conservative params
    |  → If still fail → IDENTITY_PRESERVATION_FAILED, release credit
    |
[7] Optional: minimal color/exposure normalization (Pillow, non-destructive)
    |
[8] Write to generated-images bucket
    |
[9] Commit credit, job → COMPLETED
```

### Model Selection Priority

| Priority | Model | Endpoint | When Used | Cost |
|----------|-------|----------|-----------|------|
| 1 | Flux PuLID | `fal-ai/flux-pulid` | Default pipeline | ~$0.035 |
| 2 | Flux Dev img2img + IP-Adapter | `fal-ai/flux-general/image-to-image` | PuLID circuit breaker open | ~$0.026 |
| 3 | InstantID (SDXL) | `fal-ai/instantid` | Both Flux models down | ~$0.02 |

**NO enhancement pass.** Face Enhancement model REMOVED -- it strips freckles, moles, and skin texture (beauty filter behavior). PuLID output is the final image.

### Generation Parameters by Model

| Parameter | PuLID | Flux Dev img2img | InstantID |
|-----------|-------|------------------|-----------|
| identity control | `id_weight=0.85` | IP-Adapter `scale=0.6` | `controlnet_conditioning_scale=0.80` |
| guidance_scale | 4.0 | 4.5 | 5.0 |
| steps | 30 | 35 | 30 |
| strength/denoise | N/A (text-driven) | 0.55 | N/A |
| resolution | 1024x1024 (`square_hd`) | 1024x1024 | 1024x1024 |
| negative prompt | Shared (prompts/glowup_negative.txt) | Shared | Shared |

### PuLID API Call Shape

```python
{
    "prompt": "{identity_phrase} with better styling: {keywords}...",
    "reference_image_url": "{signed_url_to_source_selfie}",
    "id_weight": 0.85,           # Adaptive: 0.80-0.93
    "guidance_scale": 4.0,        # Adaptive: 3.5-4.8
    "num_inference_steps": 30,
    "negative_prompt": "smooth skin, airbrushed skin, ...",
    "image_size": "square_hd",    # 1024x1024
}
```

### Flux Dev img2img API Call Shape (Fallback 1)

```python
{
    "prompt": "{identity_phrase} with better styling: {keywords}...",
    "image_url": "{signed_url_to_source_selfie}",
    "strength": 0.55,             # Adaptive: 0.40-0.60
    "guidance_scale": 4.5,
    "num_inference_steps": 35,
    "negative_prompt": "smooth skin, airbrushed skin, ...",
    "ip_adapters": [{
        "path": "h94/IP-Adapter-FaceID",
        "image_url": "{signed_url_to_source_selfie}",
        "scale": 0.6,
    }],
}
```

### InstantID API Call Shape (Fallback 2)

```python
{
    "prompt": "same person, dramatic style makeover, {keywords}...",
    "face_image_url": "{signed_url_to_source_selfie}",
    "controlnet_conditioning_scale": 0.80,
    "guidance_scale": 5.0,
    "num_inference_steps": 30,
    "negative_prompt": "smooth skin, airbrushed skin, ...",
    "width": 1024,
    "height": 1024,
}
```

### Prompt System

#### Three Modes

**Mode: everyday** (default, keyword_count <= 2)
```
{identity_phrase} with better styling: {keywords}. Natural daylight photography, relaxed and approachable. Keep all natural skin exactly as it is — every freckle, mole, pore, and skin detail stays. Improve only hair, grooming, and clothing. Looks like their best casual day, not a photoshoot.
```

**Mode: polished** (keyword_count 3-4)
```
{identity_phrase} styled for a professional headshot: {keywords}. Clean portrait photography with flattering lighting. All natural skin features preserved — freckles, moles, pores, texture unchanged. Only styling, grooming, and lighting are improved. Confident and camera-ready.
```

**Mode: editorial** (keyword_count >= 5)
```
{identity_phrase} in a high-end editorial photoshoot: {keywords}. Magazine quality, dramatic lighting, fashion-forward. Natural skin fully preserved — freckles, moles, texture, pores all visible. The styling is elevated, the skin is untouched.
```

**InstantID positive prompt** (fallback 2 only):
```
same person, dramatic style makeover, {improvement_keywords}, professional magazine photoshoot, editorial portrait photography, perfect studio lighting, DSLR quality, sharp focus, natural skin texture with visible pores and freckles, fashion editorial style
```

**Shared negative prompt** (all models):
```
smooth skin, airbrushed skin, beauty filter, skin retouch, porcelain skin, plastic skin, doll-like, freckle removal, mole removal, skin smoothing, beauty enhancement, face tune, filtered skin, flawless skin, perfect skin, glass skin, distorted face, asymmetric eyes, extra fingers, deformed hands, blurry, low resolution, cartoon, anime, painting, illustration, 3d render, oversaturated, neon colors, watermark, text, different person, altered bone structure
```

Templates are loaded from `prompts/glowup_{mode}.txt` files at runtime. The `{identity_phrase}` placeholder is replaced with a randomly selected identity phrase per generation. The `{keywords}` placeholder is replaced with the extracted allowlisted keywords.

#### Mode Selection Logic

```python
def select_mode(keyword_count: int) -> str:
    if keyword_count <= 2:
        return "everyday"
    if keyword_count <= 4:
        return "polished"
    return "editorial"
```

#### Identity Phrase Rotation

Templates use `{identity_phrase}` instead of hardcoded "This same person". Randomly selected per generation:

```python
_IDENTITY_PHRASES = [
    "This same person",
    "The same individual",
    "Clearly the same person",
    "This exact person",
    "Recognizably the same face",
    "The same person, unmistakably",
]
```

#### Style Theme Injection

When `keyword_count <= 4`, inject ONE random style theme:

```python
_STYLE_THEMES = [
    "modern clean aesthetic",
    "relaxed streetwear vibe",
    "elegant and refined",
    "minimal and sharp",
    "warm and approachable",
    "contemporary and bold",
]
```

Appended to keyword list (does not count toward `MAX_PROMPT_KEYWORDS`).

#### Face Shape to Prompt Keyword Mapping

| Face Shape | Keywords |
|------------|----------|
| Round | "layered hairstyle with volume on top, angular accessories, contoured jawline" |
| Oval | "versatile styling, soft waves, editorial portrait" |
| Square | "textured layers, softening styles, rounded accessories" |
| Heart | "side-swept styles, jaw-width accessories, forehead-balancing fringe" |
| Oblong | "width-adding layers, horizontal emphasis, wide frames" |

Symmetry score influences lighting keyword:
- High (>0.85) -> "dramatic directional lighting"
- Lower -> "soft even lighting, flattering angles"

#### Anti-Repetition System

Tracks recent keyword sets in Redis (`prompt:recent:{user_id}`, list of last 5 keyword hashes, TTL 24h). If the same keyword set was used in the last 3 generations:
1. Shuffle keyword order (models weight earlier tokens differently)
2. Swap one keyword with its synonym from the allowlist
3. Inject a different style theme than the last one used

#### Keyword Extraction from Recommendations

Extract allowed keywords from face analysis recommendation suggestion_text. Filter against the 74-keyword allowlist (`prompts/keyword_allowlist.py`). Max `MAX_PROMPT_KEYWORDS=6` keywords. Hair keywords placed first (most visible change). Priority order: hair > grooming > eyebrows > facial_hair > clothing > lighting.

If > 5 keywords, drop the least impactful (lighting keywords dropped first).

#### Keyword Allowlist (74 keywords across 8 categories)

**Source:** `prompts/keyword_allowlist.py`

- **Hair (30):** textured crop, side part, slicked back, pompadour, layered cut, curtain bangs, tapered fade, undercut, shorter sides, longer top, voluminous blowout, soft waves, defined curls, straightened, well-groomed hair, polished hairstyle, neat hairline, healthy shine, bob cut, pixie cut, buzz cut, french crop, middle part, messy bun, high ponytail, braided style, beach waves, afro texture, twisted locs, silk press
- **Eyebrows (8):** refined eyebrow arch, groomed eyebrows, natural brow shape, defined brows, trimmed brows, filled brows, soft brow arch, structured brows
- **Facial hair (7):** clean shaven, neat stubble, trimmed beard, defined beard line, groomed mustache, shaped goatee, well-maintained facial hair
- **Clothing (10):** fitted blazer, crisp white shirt, leather jacket, turtleneck, denim jacket, linen shirt, tailored suit, casual streetwear, athleisure, smart casual
- **Accessories (8):** statement necklace, minimal earrings, rectangular glasses, round glasses, aviator sunglasses, watch, scarf, headband
- **Lighting (8):** improved lighting, soft natural lighting, golden hour glow, studio lighting, even skin lighting, warm tones, cool tones, balanced exposure
- **Grooming (3):** well-rested appearance, brighter eyes, healthy complexion

**Blocked (never allowed):** clear skin, even complexion, reduced blemishes, moisturized skin, skin glow, smooth skin, poreless, dewy skin, glass skin, skin resurfacing, anti-aging, wrinkle reduction, pore minimizing, skin brightening, complexion evening

**Safe extension keywords** (weak-transformation boost only): elevated style, refined look, fashion-forward, magazine cover ready, red carpet styling, freshly styled, sharp dressed, well-coordinated outfit, professional grooming, editorial quality

### Adaptive Generation Parameters

#### Signals

| Signal | Source | Range | Purpose |
|--------|--------|-------|---------|
| `face_ratio` | face bbox area / image area | 0.0-1.0 | How much of the image is face |
| `symmetry_score` | FaceAnalysisService | 0.0-1.0 | Facial symmetry |
| `keyword_count` | allowlist extraction | 1-6 | How many styling changes requested |

#### Parameter Ranges (hard limits)

| Parameter | Min | Max | Danger zone |
|-----------|-----|-----|-------------|
| `id_weight` | 0.80 | 0.93 | >0.93 = near-identical output; <0.80 = identity risk |
| `guidance_scale` | 3.5 | 4.8 | >4.8 = artifacts; <3.5 = ignores prompt |

**Tradeoff rule:** `id_weight + guidance_scale` should sum to roughly 4.85 +/- 0.3. If one goes up, the other goes down.

#### Adaptive Rules (PuLID)

```python
def compute_adaptive_params(
    face_ratio: float,
    symmetry_score: float,
    keyword_count: int,
) -> dict:
    # Base values
    id_weight = 0.86
    guidance = 4.0

    # Keyword scaling
    if keyword_count >= 5:
        id_weight = 0.82
        guidance = 4.5
    elif keyword_count == 3 or keyword_count == 4:
        id_weight = 0.85
        guidance = 4.0
    elif keyword_count <= 2:
        id_weight = 0.87
        guidance = 3.8

    # Symmetry adjustment: low symmetry → tighten identity
    if symmetry_score < 0.75:
        id_weight = min(id_weight + 0.04, 0.93)
        guidance = max(guidance - 0.2, 3.5)

    # Face size adjustment
    if face_ratio < 0.15:
        id_weight = min(id_weight + 0.02, 0.93)

    # Clamp to safe ranges
    id_weight = max(0.80, min(0.93, round(id_weight, 2)))
    guidance = max(3.5, min(4.8, round(guidance, 1)))

    return {
        "id_weight": id_weight,
        "guidance_scale": guidance,
        "num_inference_steps": 30,
    }
```

#### Adaptive Rules (Flux Dev Fallback)

Same signals, adjusts `strength` instead of `id_weight`:
- keyword_count >= 5 -> `strength = 0.58`
- keyword_count 3-4 -> `strength = 0.52`
- keyword_count <= 2 -> `strength = 0.45`
- Low symmetry -> `strength -= 0.05`
- Clamped to [0.40, 0.60]

### Candidate Scoring and Selection (Wow Score)

```python
def compute_wow_score(
    arcface_score: float,
    keyword_count: int,
    id_weight_used: float,
    threshold: float = 0.80,
) -> float:
    """Score a candidate's visual impact. Higher = better glow-up."""
    # Identity band reward: peaks at 0.85, drops off toward edges
    sweet_spot = 0.85
    identity_score = max(0, 1.0 - abs(arcface_score - sweet_spot) * 6.0)

    # More keywords = more styling intent = reward
    styling_intent = min(keyword_count / 6.0, 1.0)

    # Lower id_weight used = model had more freedom = reward
    freedom_score = 1.0 - ((id_weight_used - 0.80) / 0.13)
    freedom_score = max(0, min(1.0, freedom_score))

    return (
        identity_score * 0.50
        + styling_intent * 0.25
        + freedom_score * 0.25
    )
```

| Score | Meaning | Action |
|-------|---------|--------|
| >= 0.70 | Strong glow-up | Accept immediately |
| 0.50 - 0.70 | Decent glow-up | Accept (normal) |
| 0.30 - 0.50 | Weak glow-up | Generate second candidate |
| < 0.30 | Near-identical or too different | Generate second candidate |

#### Second Candidate Generation

When `wow_score < 0.50` OR (`arcface_score > 0.93` AND `keyword_count >= 3`):
1. Keep original candidate (it passed ArcFace)
2. Generate ONE more with boosted params: `id_weight -= 0.04`, `guidance_scale += 0.3`, add one safe extension keyword
3. Score both with `compute_wow_score()`
4. Select HIGHER wow_score, provided it passes ArcFace threshold
5. If second fails ArcFace, use first (safe fallback)

**Cost impact:** Second candidate fires ~10-15% of the time. Adds ~$0.035. Weighted average: ~$0.044. Under ceiling.

#### Borderline Wow Boost

When first candidate has `0.45 <= wow_score <= 0.60` AND `arcface_score > 0.85`:
- `id_weight -= 0.03`, `guidance_scale += 0.2`
- Add 1 safe extension keyword
- Generate second candidate with these params

### Identity Preservation

#### Three Layers

| Layer | Mechanism | What it catches |
|-------|-----------|-----------------|
| 1. Model conditioning | `id_weight=0.85` (PuLID) / IP-Adapter / ControlNet | Face consistency during generation |
| 2. ArcFace post-check | Cosine similarity >= 0.80 | Identity drift the model missed |
| 3. Prompt design | "same person" + skin preservation instructions | Guides model away from face modification |

#### ArcFace Implementation

- **Model:** `insightface` buffalo_l, CPU, pre-loaded at worker startup (same pattern as MediaPipe preload in lifespan)
- **Ephemeral:** embeddings discarded after comparison (ADR-1)
- **Threshold:** `IDENTITY_SIMILARITY_THRESHOLD` per-tier from `tiers` table (default 0.80)
- **Face detection on output:** No face detected -> treat as identity failure

#### Identity Retry Strategy

```
Attempt 1:
  id_weight = adaptive (0.80-0.93)
  guidance_scale = adaptive (3.5-4.8)
  All extracted keywords (up to 6)
  → ArcFace check → if pass: proceed to wow scoring

Attempt 2 (conservative):
  id_weight = min(attempt1 + 0.10, 0.95)
  guidance_scale = attempt1 - 0.5
  Top 3 keywords only (drop least-confident)
  Downgrade mode: editorial → polished, polished → everyday
  → ArcFace check → if pass: done
  → if fail: IDENTITY_PRESERVATION_FAILED, release credit, retry_eligible: true
```

#### Identity Preservation Check (TOCTOU-safe)

1. fal.ai delivers the generated image URL
2. Worker writes the generated image to NXME Supabase Storage first (`generated-images` bucket)
3. ArcFace embedding computed by fetching BOTH source (from `raw-selfies`) and generated (from `generated-images`) from NXME-controlled storage -- never from fal.ai CDN
4. `identity_similarity_score` computed. If < threshold: blocked, credit released, `failure_reason = 'IDENTITY_PRESERVATION_FAILED'`
5. If storage fetch fails during check: `failure_reason = 'PROVIDER_ERROR'`, credit released

### Face Crop Strategy

| Face ratio | Action | Reason |
|-----------|--------|--------|
| > 0.40 | No crop | Face fills frame |
| 0.15 - 0.40 | Crop to head+shoulders (face bbox * 2.0x padding) | Model needs focus |
| < 0.15 | Crop to head only (face bbox * 1.5x padding) | Face is tiny |

Config: `FACE_CROP_THRESHOLD=0.25` (crop if face < 25% of image), `FACE_CROP_MIN_CONFIDENCE=0.85`.

After generation + identity check, if cropped: composite generated glow-up back into original frame using feathered mask and color-matched blending.

```python
def compute_crop(image_size, face_bbox, face_confidence):
    img_w, img_h = image_size
    fx, fy, fw, fh = face_bbox
    face_ratio = (fw * fh) / (img_w * img_h)

    if face_ratio > 0.40 or face_confidence < 0.85:
        return None

    cx, cy = fx + fw / 2, fy + fh / 2
    pad = 2.0 if face_ratio > 0.15 else 1.5
    crop_size = min(max(fw, fh) * pad, min(img_w, img_h))

    x1 = max(0, int(cx - crop_size / 2))
    y1 = max(0, int(cy - crop_size / 2))
    x2 = min(img_w, int(cx + crop_size / 2))
    y2 = min(img_h, int(cy + crop_size / 2))
    return (x1, y1, x2, y2)

def composite_glowup(original_img, generated_img, crop_box, face_bbox):
    x1, y1, x2, y2 = crop_box
    crop_w, crop_h = x2 - x1, y2 - y1
    result = generated_img.resize((crop_w, crop_h), Image.LANCZOS)
    result = match_color_stats(result, original_img.crop(crop_box))
    face_size = max(face_bbox[2], face_bbox[3])
    feather_px = max(15, int(face_size * 0.08))
    mask = create_feathered_mask(crop_w, crop_h, feather_px)
    canvas = original_img.copy()
    canvas.paste(result, (x1, y1), mask)
    return canvas
```

### Post-Processing (Minimal, Non-Destructive)

After PuLID generation and ArcFace check, ONE optional step:

**Color/exposure normalization** using Pillow only (no AI model):
```python
def normalize_output(source_img, generated_img):
    src_brightness = ImageStat.Stat(source_img).mean[0]
    gen_brightness = ImageStat.Stat(generated_img).mean[0]
    if abs(src_brightness - gen_brightness) > 20:
        factor = max(0.8, min(1.2, src_brightness / max(gen_brightness, 1)))
        generated_img = ImageEnhance.Brightness(generated_img).enhance(factor)
    return generated_img
```

**NOT allowed:** Any AI-based face enhancement, skin smoothing, blemish removal, sharpening beyond Pillow basics.

### NSFW Screening on Generated Output (Correction #13)

Run Rekognition on fal.ai result BEFORE commit. Reuses existing `NSFWScreenerPort` from `app/image_pipeline/nsfw_screener.py`. If explicit: quarantine the generated image, set `failure_reason = 'NSFW_QUARANTINE'`, release credit.

### Transformation Module Architecture

```python
# app/generation/modules/base.py
@dataclass(frozen=True)
class TransformationOutput:
    prompt_fragment: str
    negative_fragment: str
    keywords_used: list[str]
    wow_weight: float

class TransformationModule(Protocol):
    @property
    def slug(self) -> str: ...
    @property
    def display_name(self) -> str: ...
    def is_applicable(self, analysis_result) -> bool: ...
    def build_output(self, analysis_result, mode: str) -> TransformationOutput: ...
    def get_allowed_keywords(self) -> frozenset[str]: ...
    def get_blocked_keywords(self) -> frozenset[str]: ...
    def adjust_params(self, base_params: dict) -> dict: ...

# app/generation/modules/registry.py
_MODULES: dict[str, TransformationModule] = {}
def register(module: TransformationModule) -> None: ...
def get_active_modules(analysis_result, enabled_slugs: list[str]) -> list[TransformationModule]: ...

# app/generation/modules/styling.py
class StylingModule:
    slug = "styling"
    display_name = "Style Glow-Up"
    # is_applicable → True always
    # build_output → extract keywords, select lighting, load template, return TransformationOutput
    # get_allowed_keywords → from prompts.keyword_allowlist.ALLOWED_KEYWORDS
    # get_blocked_keywords → from prompts.keyword_allowlist.BLOCKED_KEYWORDS
    # adjust_params → pass-through (styling uses default adaptive params)
```

Modules register at import time. Config: `ENABLED_TRANSFORMATION_MODULES="styling"` (comma-separated).

### `GlowUpGeneratorPort` Protocol (Amended by A-3)

```python
# app/generation/ports.py
from typing import Protocol
from dataclasses import dataclass

@dataclass(frozen=True)
class GenerationOptions:
    model: str                        # "flux-pulid", "flux-general", "instantid"
    id_weight: float | None = None    # PuLID only
    guidance_scale: float = 4.0
    num_inference_steps: int = 30
    strength: float | None = None     # Flux Dev only
    ip_adapter_scale: float | None = None  # Flux Dev only
    controlnet_scale: float | None = None  # InstantID only
    negative_prompt: str = ""
    image_size: str = "square_hd"     # PuLID uses this
    width: int = 1024                 # InstantID uses explicit
    height: int = 1024

@dataclass(frozen=True)
class GenerationResult:
    image_url: str                    # fal.ai CDN URL of generated image
    model_used: str                   # Which model was actually used
    inference_time_ms: int | None = None
    estimated_cost_usd: float | None = None

class GlowUpGeneratorPort(Protocol):
    async def generate(
        self,
        source_image_url: str,
        prompt: str,
        options: GenerationOptions,
    ) -> GenerationResult: ...
```

### `FalAiAdapter` (Amended by A-3)

```python
# app/generation/adapters/falai.py
class FalAiAdapter:
    """Implements GlowUpGeneratorPort via fal.ai REST API.

    Uses fal-client for API calls. Handles model-specific parameter mapping.
    Retries with fal.ai idempotency key (= glow_up_jobs.idempotency_key).
    """
    def __init__(self, api_key: str) -> None: ...

    async def generate(
        self,
        source_image_url: str,
        prompt: str,
        options: GenerationOptions,
    ) -> GenerationResult:
        # Map GenerationOptions to model-specific fal.ai API params
        # PuLID: reference_image_url, id_weight, image_size
        # Flux Dev: image_url, strength, ip_adapters
        # InstantID: face_image_url, controlnet_conditioning_scale, width, height
        ...
```

### `MockGeneratorAdapter`

```python
# app/generation/adapters/mock.py
class MockGeneratorAdapter:
    """Mock for local dev. Returns a static image URL.
    Selected when ADAPTER__IMAGE_GENERATION_ADAPTER=mock.
    """
    async def generate(self, source_image_url, prompt, options) -> GenerationResult:
        return GenerationResult(
            image_url=source_image_url,  # return source as "generated"
            model_used="mock",
            inference_time_ms=100,
            estimated_cost_usd=0.0,
        )
```

### `IdentityPreservationChecker`

```python
# app/generation/identity_checker.py
class IdentityPreservationChecker:
    """ArcFace-based identity verification between source and generated images.

    Uses insightface buffalo_l model. Pre-loaded at worker startup.
    Embeddings are ephemeral (ADR-1).
    """
    def __init__(self) -> None:
        # Lazy-load insightface FaceAnalysis with buffalo_l
        ...

    def preload(self) -> None:
        """Pre-load the model at worker startup."""
        ...

    def check(
        self,
        source_image_bytes: bytes,
        generated_image_bytes: bytes,
        threshold: float,
    ) -> IdentityCheckResult:
        """Compare source and generated faces.

        Returns IdentityCheckResult with similarity score and pass/fail.
        """
        ...

@dataclass(frozen=True)
class IdentityCheckResult:
    similarity_score: float       # 0.0-1.0 cosine similarity
    passed: bool                  # score >= threshold
    source_face_detected: bool
    generated_face_detected: bool
```

### `PromptBuilder`

```python
# app/generation/prompt_builder.py
class PromptBuilder:
    """Builds generation prompts from face analysis + transformation modules.

    Handles: mode selection, keyword extraction, identity phrase rotation,
    style theme injection, anti-repetition, face shape keyword mapping.
    """
    def __init__(self, redis_client) -> None: ...

    async def build(
        self,
        analysis_result: AnalysisResult,
        face_ratio: float,
        enabled_modules: list[str],
    ) -> PromptResult: ...

@dataclass(frozen=True)
class PromptResult:
    prompt: str
    negative_prompt: str
    adaptive_params: dict           # {id_weight, guidance_scale, num_inference_steps}
    mode: str                       # "everyday", "polished", "editorial"
    keywords_used: list[str]
    keyword_count: int
```

### ARQ Queue Configuration

Three separate queues for priority:

| Lane | Priority | Tier |
|------|----------|------|
| `generation:premium` | Highest | PREMIUM |
| `generation:credit` | Medium | CREDIT_HOLDER |
| `generation:trial` | Lowest | TRIAL |

ARQ Worker configured with explicit queue ordering:
```python
class WorkerSettings:
    functions = [process_generation_job]
    cron_jobs = [cron(watchdog_stuck_jobs, second=0)]  # Every 60s
    queue_read_limit = 10
    queues = ['generation:premium', 'generation:credit', 'generation:trial']
    max_jobs = 10
    job_timeout = settings.GENERATION_TIMEOUT_SECONDS + 30
```

ARQ processes queues in declared order -- premium always checked first.

**Lane fairness (Correction #3):** After processing N premium jobs, drain at least 1 credit job (weighted round-robin). Implementation: track `premium_consecutive` counter in worker state; after N premium jobs (N = queue_read_limit), force-read one from `generation:credit` before returning to priority order.

### Job Lifecycle State Machine

```
PENDING → QUEUED → PROCESSING → COMPLETED
                              ↘ FAILED → credit released
                              ↘ CANCELLED → credit released
```

### Stuck-Job Watchdog

ARQ cron job, runs every 60 seconds:

```python
async def watchdog_stuck_jobs(ctx):
    threshold = timedelta(seconds=settings.GENERATION_TIMEOUT_SECONDS + 30)
    cutoff = datetime.now(tz=timezone.utc) - threshold
    # SELECT id, credit_reservation_id FROM glow_up_jobs
    # WHERE status = 'processing' AND updated_at < cutoff
    # For each: transition to FAILED, failure_reason='GENERATION_TIMEOUT', release credit
```

### Cost Tracking and Circuit Breaker

**Cost tracking (Correction #6):** `estimated_cost_usd DECIMAL(6,4)` column on `glow_up_jobs` table. Record fal.ai reported cost per job.

**Rolling 24h cost counter (Correction #7):** Redis `INCR cost:24h:{hour_bucket}` with 1-hour TTL buckets, summed at enqueue time. Checked before new enqueues.

**Circuit breaker (Correction #4):** After 5 consecutive fal.ai failures within 60s, open circuit for 120s. Return `PROVIDER_ERROR` immediately without calling fal.ai. Log alert.

**Cost ceiling (AC-5):** Rolling 24h average > `IMAGE_GEN_COST_CEILING_USD` ($0.06) -> throttle TRIAL lane. Rolling > `CREDIT_COST_ALERT_USD` ($0.05) -> emit alert.

**Emergency stop (Correction #8):** `GENERATION_EMERGENCY_STOP: bool = False` in config. Redis-backed for instant toggle: `SET generation:emergency_stop 1`. Checked before enqueue.

**Per-user daily cap (Correction #9):** `MAX_GENERATIONS_PER_USER_PER_DAY: int = 50`. Independent of tier limits.

### Hard Queue Depth Limit (Correction #2)

If total queued jobs > `MAX_QUEUE_DEPTH` (config, default 15,000), return 503 immediately. Check via Redis `LLEN` on all three queue keys.

### fal.ai Health Probe (Correction #5)

Periodic (every 30s) lightweight API call from one worker. Used to determine circuit breaker recovery.

### `process_generation_job` Worker Function

```python
# app/generation/worker.py
async def process_generation_job(ctx: dict, job_id: str) -> None:
    """ARQ worker function: full generation lifecycle.

    Steps:
    1. Fetch job + analysis data from DB
    2. INCR concurrent counter (atomic, Correction #15)
    3. Fetch source image from storage
    4. Build prompt via PromptBuilder (mode, keywords, adaptive params)
    5. Crop source if needed
    6. Call GlowUpGeneratorPort.generate()
    7. Download generated image from fal.ai URL
    8. NSFW screen generated output (Correction #13)
    9. Write generated to generated-images bucket
    10. ArcFace identity check
    11. If fail: retry once with conservative params
    12. If still fail: IDENTITY_PRESERVATION_FAILED, release credit
    13. Wow scoring + optional second candidate
    14. Optional color normalization
    15. Update glow_up_jobs row: status=completed, scores, image refs
    16. Commit credit reservation
    17. DECR concurrent counter

    On ANY exception:
    - Classify failure_reason
    - Update job to failed
    - Release credit reservation
    - DECR concurrent counter
    - If UNKNOWN: trigger alarm
    """
```

### Concurrent Guard (Correction #15)

Replace read-only check with atomic INCR at API layer:

```python
# At enqueue time (API handler, story 4-3):
key = f"concurrent:{user_id}"
current = await redis.incr(key)
await redis.expire(key, settings.GENERATION_TIMEOUT_SECONDS + 30)
if current > tier.max_concurrent_generations:
    await redis.decr(key)
    raise ConcurrentLimitError()
```

Worker also INCRs at job start, DECRs at job end (success or failure). The TTL ensures leaked counters expire.

### `glow_up_jobs` Table Schema

```sql
CREATE TABLE glow_up_jobs (
    id                          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    idempotency_key             TEXT UNIQUE NOT NULL,
    analysis_id                 UUID NOT NULL REFERENCES analyses(id),
    user_id                     UUID NOT NULL REFERENCES users(id),
    status                      TEXT NOT NULL DEFAULT 'pending'
                                CHECK (status IN ('pending','queued','processing','completed','failed','cancelled')),
    failure_reason              TEXT
                                CHECK (failure_reason IN (
                                    'FACE_VALIDATION_FAILED','GENERATION_TIMEOUT','NSFW_QUARANTINE',
                                    'IDENTITY_PRESERVATION_FAILED','PROVIDER_ERROR','UNKNOWN'
                                ) OR failure_reason IS NULL),
    original_image_id           UUID REFERENCES images(id),
    generated_image_id          UUID REFERENCES images(id),
    identity_similarity_score   FLOAT,
    identity_preserved          BOOLEAN,
    credit_reservation_id       UUID REFERENCES credit_reservations(id),
    user_tier_at_enqueue        TEXT NOT NULL CHECK (user_tier_at_enqueue IN ('TRIAL','CREDIT_HOLDER','PREMIUM')),
    estimated_cost_usd          DECIMAL(6,4),
    created_at                  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at                  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at                TIMESTAMPTZ
);
CREATE INDEX idx_jobs_user_id ON glow_up_jobs (user_id, created_at DESC);
CREATE INDEX idx_jobs_status ON glow_up_jobs (status) WHERE status IN ('pending','queued','processing');
CREATE INDEX idx_jobs_watchdog ON glow_up_jobs (updated_at) WHERE status = 'processing';
```

Note: `estimated_cost_usd DECIMAL(6,4)` added per Correction #6. The architecture schema does not include this column -- it is an amendment from the corrections review.

### `prompt_experiments` Table Schema (A/B Testing)

```sql
CREATE TABLE prompt_experiments (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    job_id          UUID NOT NULL REFERENCES glow_up_jobs(id),
    prompt_mode     TEXT NOT NULL,
    prompt_template TEXT NOT NULL,
    keyword_count   INT NOT NULL,
    arcface_score   FLOAT,
    wow_score       FLOAT,
    retry_count     INT NOT NULL DEFAULT 0,
    generation_ms   INT,
    estimated_cost  DECIMAL(6,4),
    model_used      TEXT NOT NULL,
    outcome         TEXT NOT NULL,
    candidate_count INT NOT NULL DEFAULT 1,
    selected_candidate INT NOT NULL DEFAULT 1,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_prompt_exp_mode ON prompt_experiments (prompt_mode, created_at DESC);
```

### `analyses` Table Schema (existing, for reference)

```sql
CREATE TABLE analyses (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id             UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    status              TEXT NOT NULL DEFAULT 'pending'
                        CHECK (status IN ('pending', 'processing', 'completed', 'failed')),
    original_image_id   UUID REFERENCES images(id),
    face_shape          TEXT CHECK (face_shape IN ('oval', 'round', 'square', 'heart', 'oblong')),
    symmetry_score      FLOAT CHECK (symmetry_score BETWEEN 0.0 AND 1.0),
    recommendations     JSONB,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

### Config Constants (from `app/config.py`)

| Setting | Default | Purpose |
|---------|---------|---------|
| `FAL_API_KEY` | "" | fal.ai authentication |
| `ADAPTER__IMAGE_GENERATION_ADAPTER` | "mock" | Generator adapter selection |
| `IMAGE_GEN_COST_CEILING_USD` | 0.06 | 24h rolling avg ceiling |
| `GENERATION_TIMEOUT_SECONDS` | 60 | Job timeout |
| `CREDIT_COST_ALERT_USD` | 0.05 | Alert threshold |
| `GENERATION_OUTPUT_RESOLUTION` | 1024 | Output image size |
| `IDENTITY_MAX_RETRIES` | 1 | Max identity check retries |
| `MAX_PROMPT_KEYWORDS` | 6 | Max keywords in prompt |
| `FACE_CROP_THRESHOLD` | 0.25 | Crop if face < 25% of image |
| `IDENTITY_SIMILARITY_THRESHOLD` | 0.80 | Global default (per-tier overrides) |
| `MAX_CONCURRENT_GENERATIONS_PER_USER` | 3 | Global ceiling |
| `ENABLED_TRANSFORMATION_MODULES` | "styling" | Active modules |
| `SIGNED_URL_EXPIRY_SECONDS` | 3600 | For fetching source images |

**New config values to add:**

| Setting | Default | Purpose |
|---------|---------|---------|
| `GENERATION_EMERGENCY_STOP` | False | Redis-backed kill switch |
| `MAX_QUEUE_DEPTH` | 15000 | Hard queue depth limit |
| `MAX_GENERATIONS_PER_USER_PER_DAY` | 50 | Per-user daily cap |
| `FAL_CIRCUIT_BREAKER_THRESHOLD` | 5 | Consecutive failures to open |
| `FAL_CIRCUIT_BREAKER_WINDOW_SECONDS` | 60 | Failure window |
| `FAL_CIRCUIT_BREAKER_COOLDOWN_SECONDS` | 120 | Open duration |
| `FAL_HEALTH_PROBE_INTERVAL_SECONDS` | 30 | Health probe frequency |
| `WORKER_LANE_FAIRNESS_THRESHOLD` | 10 | Premium jobs before draining credit |

### Error Classification

| failure_reason | When | Credit impact |
|---------------|------|---------------|
| `GENERATION_TIMEOUT` | Job stuck > GENERATION_TIMEOUT_SECONDS + 30 | Released |
| `IDENTITY_PRESERVATION_FAILED` | ArcFace < threshold after retry | Released |
| `NSFW_QUARANTINE` | Generated output failed NSFW screen | Released |
| `PROVIDER_ERROR` | fal.ai API error, storage error | Released |
| `FACE_VALIDATION_FAILED` | No face detected in source | Released |
| `UNKNOWN` | Any unclassified exception | Released + CloudWatch alarm |

**On ALL failure paths, credits are released.** No code path permanently consumes credits on failure.

### Structured Logging Contract

Every generation-related log event MUST include `job_id` (= `glow_up_jobs.idempotency_key`) as a top-level structured field:

```python
logger.info(
    "Generation completed",
    extra={
        "job_id": idempotency_key,
        "user_id": str(user_id),
        "tier": user_tier_at_enqueue,
        "duration_ms": duration_ms,
        "identity_similarity_score": score,
        "cost_estimate_usd": cost,
        "model_used": model_used,
    },
)
```

### File Structure

```
app/
  generation/
    __init__.py
    ports.py                    # GlowUpGeneratorPort, GenerationOptions, GenerationResult
    worker.py                   # process_generation_job ARQ function, watchdog_stuck_jobs
    worker_settings.py          # ARQ WorkerSettings class
    prompt_builder.py           # PromptBuilder, PromptResult, mode selection, keyword extraction
    identity_checker.py         # IdentityPreservationChecker, IdentityCheckResult
    face_cropper.py             # compute_crop, composite_glowup, match_color_stats
    color_normalizer.py         # normalize_output
    cost_tracker.py             # CostTracker — Redis 24h rolling cost, circuit breaker
    models.py                   # JobStatus enum, failure reasons, shared dataclasses
    adapters/
      __init__.py
      falai.py                  # FalAiAdapter
      mock.py                   # MockGeneratorAdapter
    modules/
      __init__.py               # Registers all modules at import
      base.py                   # TransformationModule protocol, TransformationOutput
      registry.py               # Module registry
      styling.py                # StylingModule (MVP)
  migrations/
    0006_glow_up_jobs.sql       # glow_up_jobs + prompt_experiments tables
```

### Port/Adapter Resolution Pattern (from story 3-1)

```python
def _get_generator_adapter() -> GlowUpGeneratorPort:
    if settings.ADAPTER__IMAGE_GENERATION_ADAPTER == "falai":
        from app.generation.adapters.falai import FalAiAdapter
        return FalAiAdapter(api_key=settings.FAL_API_KEY)
    from app.generation.adapters.mock import MockGeneratorAdapter
    return MockGeneratorAdapter()
```

Lazy imports inside the factory function. The adapter is resolved once at worker startup and reused.

## Verified Interfaces

### EntitlementService.check (app/entitlement/service.py)

- **Source:** `app/entitlement/service.py:171`
- **Signature:** `async def check(self, user_id: UUID, action: str) -> EntitlementResult`
- **Plan match:** Matches

### EntitlementService.similarity_threshold (app/entitlement/service.py)

- **Source:** `app/entitlement/service.py:287-289`
- **Signature:** `async def similarity_threshold(self, user_id: UUID) -> float`
- **Plan match:** Matches -- returns `float((await self._get_tier(user_id)).identity_similarity_threshold)`

### EntitlementService.max_concurrent (app/entitlement/service.py)

- **Source:** `app/entitlement/service.py:283-285`
- **Signature:** `async def max_concurrent(self, user_id: UUID) -> int`
- **Plan match:** Matches

### CreditLedger.reserve (app/entitlement/ledger.py)

- **Source:** `app/entitlement/ledger.py:52-74`
- **Signature:** `def reserve(self, user_id: UUID) -> UUID`
- **Plan match:** Matches -- returns reservation_id UUID. RPC-only (CS-1).

### CreditLedger.release (app/entitlement/ledger.py)

- **Source:** `app/entitlement/ledger.py:76-96`
- **Signature:** `def release(self, reservation_id: UUID) -> None`
- **Plan match:** Matches -- raises ValueError if already resolved. RPC-only (CS-1).

### CreditLedger.commit (app/entitlement/ledger.py)

- **Source:** `app/entitlement/ledger.py:98-117`
- **Signature:** `def commit(self, reservation_id: UUID) -> None`
- **Plan match:** Matches -- raises ValueError if already resolved. RPC-only (CS-1).

### NSFWScreenerPort.screen (app/image_pipeline/nsfw_screener.py)

- **Source:** `app/image_pipeline/nsfw_screener.py:47-49`
- **Signature:** `async def screen(self, image_bytes: bytes) -> NSFWResult`
- **Plan match:** Matches -- returns NSFWResult(is_explicit, confidence, labels, screened)

### FaceAnalysisService.analyze (app/face_analysis/service.py)

- **Source:** `app/face_analysis/service.py:96-138`
- **Signature:** `async def analyze(self, image_storage_key: str) -> AnalysisResult`
- **Plan match:** Matches -- returns AnalysisResult(face_shape, symmetry_score, recommendations)

### ImagePipeline.process (app/image_pipeline/pipeline.py)

- **Source:** `app/image_pipeline/pipeline.py:74-181`
- **Signature:** `async def process(self, file_bytes: bytes, content_type: str, user_id: str) -> ProcessedImage`
- **Plan match:** Matches

### Settings (app/config.py)

- **Source:** `app/config.py:22,31,33,55-61`
- **Signatures:**
  - `FAL_API_KEY: str = ""`
  - `ADAPTER__IMAGE_GENERATION_ADAPTER: str = "mock"`
  - `IMAGE_GEN_COST_CEILING_USD: float = 0.06`
  - `GENERATION_TIMEOUT_SECONDS: int = 60`
  - `CREDIT_COST_ALERT_USD: float = 0.05`
  - `GENERATION_OUTPUT_RESOLUTION: int = 1024`
  - `IDENTITY_MAX_RETRIES: int = 1`
  - `MAX_PROMPT_KEYWORDS: int = 6`
  - `FACE_CROP_THRESHOLD: float = 0.25`
  - `IDENTITY_SIMILARITY_THRESHOLD: float = 0.80`
  - `MAX_CONCURRENT_GENERATIONS_PER_USER: int = 3`
  - `ENABLED_TRANSFORMATION_MODULES: str = "styling"`
- **Plan match:** Matches

### get_supabase_service (app/db/client.py)

- **Source:** `app/db/client.py:10`
- **Signature:** `def get_supabase_service() -> Client`
- **Plan match:** Matches

### app/main.py lifespan (app/main.py)

- **Source:** `app/main.py:22-63`
- **Signature:** `async def lifespan(app: FastAPI) -> AsyncIterator[None]`
- **Plan match:** Matches -- this story adds insightface preload in the same pattern as MediaPipe preload

### Tier Constants (app/constants/tiers.py)

- **Source:** `app/constants/tiers.py:5-13`
- **Signatures:** `TRIAL`, `CREDIT_HOLDER`, `PREMIUM` string constants + `TIER_ID_TRIAL`, `TIER_ID_CREDIT_HOLDER`, `TIER_ID_PREMIUM` UUID strings
- **Plan match:** Matches -- used for queue lane routing (`user_tier_at_enqueue`)

### AnalysisResult (app/face_analysis/models.py)

- **Source:** `app/face_analysis/models.py:43-48`
- **Signature:** `class AnalysisResult` with `face_shape: FaceShape`, `symmetry_score: float`, `recommendations: list[Suggestion]`
- **Plan match:** Matches -- PromptBuilder consumes this

### FaceShape (app/face_analysis/models.py)

- **Source:** `app/face_analysis/models.py:17-24`
- **Signature:** `class FaceShape(StrEnum)` with `OVAL`, `ROUND`, `SQUARE`, `HEART`, `OBLONG`
- **Plan match:** Matches -- used in face shape to keyword mapping

### Suggestion (app/face_analysis/models.py)

- **Source:** `app/face_analysis/models.py:33-39`
- **Signature:** `class Suggestion` with `rank: int`, `category: str`, `suggestion_text: str`, `rationale: str`
- **Plan match:** Matches -- PromptBuilder extracts keywords from `suggestion_text`

### Keyword Allowlist (prompts/keyword_allowlist.py)

- **Source:** `prompts/keyword_allowlist.py:1-82`
- **Signatures:** `ALLOWED_KEYWORDS: frozenset[str]` (74 keywords), `BLOCKED_KEYWORDS: frozenset[str]`, `SAFE_EXTENSION_KEYWORDS: frozenset[str]`, category frozensets (`HAIR_KEYWORDS`, etc.)
- **Plan match:** Matches

### GlowUpGeneratorPort (interface contract -- this story defines it)

- **Source:** Not yet implemented -- this story creates it
- **Signature:** `async def generate(self, source_image_url: str, prompt: str, options: GenerationOptions) -> GenerationResult`
- **Plan match:** UNVERIFIED -- source not yet implemented, using plan contract

### process_generation_job (interface contract -- this story defines it)

- **Source:** Not yet implemented -- this story creates it
- **Signature:** `async def process_generation_job(ctx: dict, job_id: str) -> None`
- **Plan match:** UNVERIFIED -- source not yet implemented, using plan contract

## Tasks

- [x] Task 1: Create migration `app/migrations/0006_glow_up_jobs.sql` -- glow_up_jobs table + prompt_experiments table + indexes
  - Maps to: AC-1 (queue lanes reference user_tier_at_enqueue), AC-3 (watchdog queries glow_up_jobs), AC-5 (estimated_cost_usd column)
  - Files: `app/migrations/0006_glow_up_jobs.sql`

- [x] Task 2: Create `app/generation/ports.py` and `app/generation/models.py` -- GlowUpGeneratorPort protocol, GenerationOptions, GenerationResult, JobStatus enum, failure reason constants, IdentityCheckResult
  - Maps to: AC-4 (port interface)
  - Files: `app/generation/__init__.py`, `app/generation/ports.py`, `app/generation/models.py`

- [x] Task 3: Create `app/generation/modules/` -- TransformationModule protocol, registry, StylingModule
  - Maps to: AC-4 (prompt built via module system, not hardcoded)
  - Files: `app/generation/modules/__init__.py`, `app/generation/modules/base.py`, `app/generation/modules/registry.py`, `app/generation/modules/styling.py`

- [x] Task 4: Create `app/generation/prompt_builder.py` -- PromptBuilder with mode selection, keyword extraction, identity phrase rotation, style theme injection, anti-repetition, face shape mapping
  - Maps to: AC-4 (prompt built from analysis data), AC-5 (adaptive params for cost control)
  - Files: `app/generation/prompt_builder.py`

- [x] Task 5: Create `app/generation/adapters/` -- FalAiAdapter (fal-client), MockGeneratorAdapter
  - Maps to: AC-4 (no direct fal.ai calls in worker), AC-5 (cost tracking via adapter)
  - Files: `app/generation/adapters/__init__.py`, `app/generation/adapters/falai.py`, `app/generation/adapters/mock.py`

- [x] Task 6: Create `app/generation/identity_checker.py` -- IdentityPreservationChecker with ArcFace buffalo_l, preload, check
  - Maps to: AC-3 (identity check triggers credit release on failure), AC-4 (identity check in lifecycle)
  - Files: `app/generation/identity_checker.py`

- [x] Task 7: Create `app/generation/face_cropper.py` -- compute_crop, composite_glowup, match_color_stats, create_feathered_mask
  - Maps to: AC-4 (face crop in lifecycle)
  - Files: `app/generation/face_cropper.py`

- [x] Task 8: Create `app/generation/color_normalizer.py` -- normalize_output (Pillow brightness matching)
  - Maps to: AC-4 (post-processing in lifecycle)
  - Files: `app/generation/color_normalizer.py`

- [x] Task 9: Create `app/generation/cost_tracker.py` -- CostTracker (Redis 24h rolling cost, circuit breaker, emergency stop, queue depth check, per-user daily cap, fal.ai health probe)
  - Maps to: AC-2 (queue depth limit, zero 5xx), AC-5 (cost circuit breaker throttles trial lane)
  - Files: `app/generation/cost_tracker.py`

- [x] Task 10: Create `app/generation/worker.py` -- process_generation_job ARQ function, watchdog_stuck_jobs cron function
  - Maps to: AC-1 (processes from priority lanes), AC-3 (watchdog releases stuck credits), AC-4 (full lifecycle via port), AC-5 (cost tracking per job)
  - Files: `app/generation/worker.py`

- [x] Task 11: Create `app/generation/worker_settings.py` -- ARQ WorkerSettings with queue ordering, cron jobs, lane fairness
  - Maps to: AC-1 (priority ordering), AC-2 (queue capacity), AC-3 (watchdog cron)
  - Files: `app/generation/worker_settings.py`

- [x] Task 12: Add new config values to `app/config.py` and update `requirements.txt` with arq, fal-client, insightface, onnxruntime
  - Maps to: AC-1, AC-2, AC-3, AC-5 (all features need config)
  - Files: `app/config.py`, `requirements.txt`

## must_haves

truths:
  - "GlowUpGeneratorPort is a Protocol class with async def generate(self, source_image_url: str, prompt: str, options: GenerationOptions) -> GenerationResult"
  - "FalAiAdapter implements GlowUpGeneratorPort and maps GenerationOptions to model-specific fal.ai API parameters for flux-pulid, flux-general/image-to-image, and instantid"
  - "MockGeneratorAdapter implements GlowUpGeneratorPort and returns source_image_url as the generated image"
  - "process_generation_job calls GlowUpGeneratorPort.generate() and never imports fal_client or calls fal.ai directly"
  - "process_generation_job on success: commits credit reservation via CreditLedger.commit(reservation_id) and updates glow_up_jobs.status to 'completed'"
  - "process_generation_job on ANY failure: releases credit reservation via CreditLedger.release(reservation_id) and updates glow_up_jobs.status to 'failed' with failure_reason"
  - "watchdog_stuck_jobs selects glow_up_jobs WHERE status='processing' AND updated_at < NOW() - (GENERATION_TIMEOUT_SECONDS + 30s) and transitions each to status='failed' with failure_reason='GENERATION_TIMEOUT' and releases the credit reservation"
  - "ARQ WorkerSettings.queues is ['generation:premium', 'generation:credit', 'generation:trial'] in that exact order"
  - "IdentityPreservationChecker.check() returns IdentityCheckResult with similarity_score and passed=True when score >= threshold"
  - "PromptBuilder.build() returns PromptResult with prompt, negative_prompt, adaptive_params, mode, keywords_used"
  - "PromptBuilder uses identity phrase rotation from _IDENTITY_PHRASES list and style theme injection when keyword_count <= 4"
  - "compute_adaptive_params returns id_weight clamped to [0.80, 0.93] and guidance_scale clamped to [3.5, 4.8]"
  - "NSFW screening runs on the generated output image before credit commit using NSFWScreenerPort.screen()"
  - "CostTracker checks rolling 24h cost and throttles TRIAL lane when average exceeds IMAGE_GEN_COST_CEILING_USD"
  - "glow_up_jobs table has estimated_cost_usd DECIMAL(6,4) column"
  - "StylingModule implements TransformationModule protocol with slug='styling' and loads templates from prompts/glowup_{mode}.txt"

artifacts:
  - path: "app/migrations/0006_glow_up_jobs.sql"
    contains: ["glow_up_jobs", "prompt_experiments", "estimated_cost_usd", "idx_jobs_watchdog", "idx_jobs_status"]
  - path: "app/generation/__init__.py"
  - path: "app/generation/ports.py"
    contains: ["GlowUpGeneratorPort", "GenerationOptions", "GenerationResult", "Protocol", "generate", "source_image_url"]
  - path: "app/generation/models.py"
    contains: ["JobStatus", "IdentityCheckResult", "GENERATION_TIMEOUT", "IDENTITY_PRESERVATION_FAILED", "PROVIDER_ERROR", "NSFW_QUARANTINE"]
  - path: "app/generation/worker.py"
    contains: ["process_generation_job", "watchdog_stuck_jobs", "GlowUpGeneratorPort", "CreditLedger", "NSFWScreenerPort"]
  - path: "app/generation/worker_settings.py"
    contains: ["WorkerSettings", "generation:premium", "generation:credit", "generation:trial", "cron"]
  - path: "app/generation/prompt_builder.py"
    contains: ["PromptBuilder", "PromptResult", "select_mode", "compute_adaptive_params", "_IDENTITY_PHRASES", "_STYLE_THEMES", "extract_allowed_keywords"]
  - path: "app/generation/identity_checker.py"
    contains: ["IdentityPreservationChecker", "IdentityCheckResult", "insightface", "buffalo_l", "preload", "check"]
  - path: "app/generation/face_cropper.py"
    contains: ["compute_crop", "composite_glowup", "match_color_stats", "create_feathered_mask", "face_ratio"]
  - path: "app/generation/color_normalizer.py"
    contains: ["normalize_output", "ImageEnhance", "ImageStat", "Brightness"]
  - path: "app/generation/cost_tracker.py"
    contains: ["CostTracker", "cost:24h", "circuit_breaker", "emergency_stop", "MAX_QUEUE_DEPTH", "TRIAL"]
  - path: "app/generation/adapters/falai.py"
    contains: ["FalAiAdapter", "fal_client", "flux-pulid", "flux-general", "instantid", "GenerationResult"]
  - path: "app/generation/adapters/mock.py"
    contains: ["MockGeneratorAdapter", "GenerationResult"]
  - path: "app/generation/modules/base.py"
    contains: ["TransformationModule", "TransformationOutput", "Protocol", "prompt_fragment", "negative_fragment"]
  - path: "app/generation/modules/registry.py"
    contains: ["register", "get_active_modules", "_MODULES"]
  - path: "app/generation/modules/styling.py"
    contains: ["StylingModule", "styling", "ALLOWED_KEYWORDS", "BLOCKED_KEYWORDS", "glowup_"]

key_links:
  - pattern: "from app.config import settings"
    in: ["app/generation/worker.py", "app/generation/worker_settings.py", "app/generation/adapters/falai.py", "app/generation/cost_tracker.py", "app/generation/prompt_builder.py"]
  - pattern: "from app.generation.ports import GlowUpGeneratorPort"
    in: ["app/generation/worker.py"]
  - pattern: "from app.generation.ports import GenerationOptions, GenerationResult"
    in: ["app/generation/adapters/falai.py", "app/generation/adapters/mock.py", "app/generation/worker.py"]
  - pattern: "from app.entitlement.ledger import CreditLedger"
    in: ["app/generation/worker.py"]
  - pattern: "from app.image_pipeline.nsfw_screener import NSFWScreenerPort"
    in: ["app/generation/worker.py"]
  - pattern: "from app.generation.identity_checker import IdentityPreservationChecker"
    in: ["app/generation/worker.py"]
  - pattern: "from app.generation.prompt_builder import PromptBuilder"
    in: ["app/generation/worker.py"]
  - pattern: "from app.generation.cost_tracker import CostTracker"
    in: ["app/generation/worker.py", "app/generation/worker_settings.py"]
  - pattern: "from app.generation.face_cropper import compute_crop, composite_glowup"
    in: ["app/generation/worker.py"]
  - pattern: "from app.generation.color_normalizer import normalize_output"
    in: ["app/generation/worker.py"]
  - pattern: "from app.generation.modules.registry import get_active_modules"
    in: ["app/generation/prompt_builder.py"]
  - pattern: "from prompts.keyword_allowlist import ALLOWED_KEYWORDS"
    in: ["app/generation/modules/styling.py"]
  - pattern: "from app.face_analysis.models import AnalysisResult, FaceShape"
    in: ["app/generation/prompt_builder.py"]
  - pattern: "from app.constants.tiers import"
    in: ["app/generation/worker.py"]
  - pattern: "process_generation_job"
    in: ["app/generation/worker.py", "app/generation/worker_settings.py"]
  - pattern: "watchdog_stuck_jobs"
    in: ["app/generation/worker.py", "app/generation/worker_settings.py"]

## Dev Notes

### Testing Approach

Zero automated tests per QA skill decision. All verification is via manual testing against local environment:
- Run ARQ worker locally: `arq app.generation.worker_settings.WorkerSettings`
- Use `ADAPTER__IMAGE_GENERATION_ADAPTER=mock` for local dev (no fal.ai calls)
- Enqueue test jobs via Redis CLI: `LPUSH arq:queue:generation:trial '{"job_id": "test-1"}'`
- Verify job lifecycle in Supabase Studio (`http://127.0.0.1:54323`): check glow_up_jobs rows
- Verify watchdog: insert a stuck job with old `updated_at`, wait 60s, verify it transitions to failed
- Verify credit release: check `credit_reservations.status` and `credit_ledger` entries after failure
- Verify NSFW screening on output: test with `ADAPTER__NSFW_ADAPTER=mock` (always passes)

### Conventions from Prior Stories

**Story 4-1 established:**
- `from app.config import settings` canonical config import
- `EntitlementService(supabase, redis_client)` constructor pattern
- `CreditLedger(supabase)` with RPC-only mutations (CS-1)
- `TierRecord` dataclass with all tier columns
- `UsageRepository.count_in_window()` for rolling-window checks
- `EntitlementResult` with error codes for API responses
- Constants from `app/constants/tiers.py`: `TRIAL`, `CREDIT_HOLDER`, `PREMIUM`, fixed tier UUIDs
- Redis async via `redis.asyncio` (`await redis.get()`, `await redis.incr()`)
- Concurrent guard pattern: `f"concurrent:{user_id}"` Redis key with TTL

**Story 3-1 established:**
- Port/adapter pattern with lazy imports inside feature module
- `_get_*_adapter()` factory functions based on config selection
- Dataclasses with `frozen=True` for immutable value objects
- `datetime.now(tz=timezone.utc).isoformat()` for timestamps
- Error format: `{"error": {"code": "...", "message": "...", "retry_eligible": true/false}}`
- Supabase `Client` is synchronous -- use `asyncio.get_running_loop().run_in_executor()` for CPU-bound sync ops
- NSFWScreenerPort at `app/image_pipeline/nsfw_screener.py` -- reuse for generated output screening
- RekognitionAdapter uses `asyncio.get_running_loop().run_in_executor()` for boto3 calls

**Story 3-2 established:**
- `asyncio.get_running_loop().run_in_executor()` for CPU-bound sync operations (replaced `get_event_loop()`)
- FaceShape StrEnum pattern for domain value objects
- MediaPipe model pre-loaded in lifespan before yield -- follow same pattern for insightface buffalo_l
- `FaceAnalysisService.analyze(image_storage_key)` returns `AnalysisResult`

**Story CS-1 established:**
- CreditLedger RPC-only (no fallback two-write paths). If RPC fails, operation fails.
- `UPDATE ... WHERE status = 'reserved' RETURNING *` for TOCTOU-safe release/commit
- Adapter startup guard: `APP_ENV != "development"` + mock adapter = CRITICAL + SystemExit

### Library Versions

- **arq:** 0.27.0 (verified 2026-03-17 via PyPI)
- **fal-client:** 0.13.1 (verified 2026-03-17 via PyPI)
- **insightface:** 0.7.3 (verified 2026-03-17 via PyPI)
- **onnxruntime:** 1.24.3 (verified 2026-03-17 via PyPI) -- required by insightface
- **numpy:** 2.4.3 (already pinned in requirements.txt)
- **Pillow:** 12.1.1 (already pinned in requirements.txt)
- **boto3:** 1.42.68 (already pinned in requirements.txt)
- **supabase-py:** 2.15.1 (pinned in requirements.txt)
- **redis-py:** 5.2.1 (pinned in requirements.txt)

### Local Dev Environment

```bash
# Start local Supabase (DB + Auth + Storage):
supabase start

# Start Redis:
docker compose up -d

# Run migrations (creates glow_up_jobs table):
python -m app.migrations.run

# Start the API (hot-reload):
./scripts/dev-start.sh

# Start the ARQ worker (separate terminal):
arq app.generation.worker_settings.WorkerSettings
```

Environment variables for this story:
- `SUPABASE_URL` -- local Supabase URL (from `supabase status`)
- `SUPABASE_SERVICE_ROLE_KEY` -- local service role key
- `REDIS_URL` -- `redis://localhost:6379/0` (default)
- `FAL_API_KEY` -- fal.ai key (required only when `ADAPTER__IMAGE_GENERATION_ADAPTER=falai`)
- `ADAPTER__IMAGE_GENERATION_ADAPTER` -- `"mock"` (default) or `"falai"` (real generation)
- `ADAPTER__NSFW_ADAPTER` -- `"mock"` (default) or `"rekognition"` (real NSFW screening)
- `GENERATION_TIMEOUT_SECONDS` -- `60` (default)
- `IMAGE_GEN_COST_CEILING_USD` -- `0.06` (default)
- `GENERATION_EMERGENCY_STOP` -- `false` (default)
- `MAX_QUEUE_DEPTH` -- `15000` (default)
- `MAX_GENERATIONS_PER_USER_PER_DAY` -- `50` (default)

### Worker Process Architecture

The ARQ worker runs as a separate process (`arq app.generation.worker_settings.WorkerSettings`), NOT inside the FastAPI app. It connects to the same Redis and Supabase instances. The worker process:
1. Pre-loads insightface buffalo_l model at startup (same as MediaPipe preload pattern)
2. Initializes GlowUpGeneratorPort adapter
3. Initializes CostTracker with Redis client
4. Resolves NSFWScreenerPort adapter
5. Polls Redis queues in priority order

### insightface buffalo_l Preload Pattern

```python
# In worker startup (ctx dict):
from insightface.app import FaceAnalysis
app = FaceAnalysis(name='buffalo_l', providers=['CPUExecutionProvider'])
app.prepare(ctx_id=0, det_size=(640, 640))
ctx['face_app'] = app
```

This is CPU-only. No GPU required. Model download happens on first run (~200MB). Pre-loading ensures no cold-start on first job.

### Prompt Template File Loading

Templates are plain text files in `prompts/` directory. Load at runtime:
```python
from pathlib import Path
_PROMPT_DIR = Path(__file__).resolve().parent.parent.parent / "prompts"

def _load_template(name: str) -> str:
    return (_PROMPT_DIR / name).read_text().strip()
```

This is consistent with the existing `prompts/keyword_allowlist.py` module being importable from the root.

### Supabase Signed URLs for Source Images

The worker needs to fetch source images from the `raw-selfies` private bucket. Use signed URLs:
```python
signed = supabase.storage.from_("raw-selfies").create_signed_url(
    storage_key, settings.SIGNED_URL_EXPIRY_SECONDS
)
# signed["signedURL"] is the URL to pass to fal.ai
```

fal.ai needs a publicly accessible URL. The signed URL has a 1-hour TTL (configurable).

### A/B Testing Data Collection

The `prompt_experiments` table records per-job metrics. The optimization job (ARQ cron, every 6 hours) reads this data to adjust traffic weights. For MVP, the mode selection is deterministic (based on keyword_count). The A/B framework is infrastructure -- the first experiment will be to test whether deterministic mode selection outperforms randomized selection.

## Wave Structure

Wave 1: [Task 1, Task 2, Task 3] -- independent, no shared files
  - Task 1: Migration file (SQL only, no Python deps)
  - Task 2: ports.py + models.py (type definitions, no business logic deps)
  - Task 3: modules/ directory (Protocol + registry + StylingModule, imports only from prompts/)

Wave 2: [Task 4, Task 5, Task 6, Task 7, Task 8, Task 9] -- independent, no shared files
  - Task 4: prompt_builder.py (imports from models.py, modules/registry.py, face_analysis/models.py)
  - Task 5: adapters/ (imports from ports.py)
  - Task 6: identity_checker.py (imports from models.py, standalone insightface usage)
  - Task 7: face_cropper.py (standalone Pillow logic)
  - Task 8: color_normalizer.py (standalone Pillow logic)
  - Task 9: cost_tracker.py (imports from config, standalone Redis logic)

Wave 3: [Task 10] -- depends on all Wave 1+2 outputs
  - Task 10: worker.py (orchestrator — imports all modules from Wave 1+2)

Wave 4: [Task 11] -- depends on Task 10
  - Task 11: worker_settings.py (imports process_generation_job from worker.py)

Wave 5: [Task 12] -- depends on all above (config + requirements update)
  - Task 12: config.py additions + requirements.txt (after all code is written, add missing config values and pin new packages)
