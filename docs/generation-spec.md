---
status: complete
created: 2026-03-16
last_updated: 2026-03-16
---

# NXME Glow-Up Generation Specification

Single source of truth for AI generation behavior. Story 4-2 (Generation Queue & ARQ Worker) reads this document. The story-creator agent inlines relevant sections.

---

## 1. What NXME Does

NXME takes a user's selfie, analyzes their face shape and features, then generates a "glow-up" — the same person with better styling.

**What changes:** hair, grooming, clothing, lighting, composition.
**What stays:** the face, bone structure, skin (freckles, moles, texture, pores, tone), eye shape, natural asymmetries.

NXME is NOT a beauty filter. It does NOT smooth skin, remove freckles, or retouch. The improvement is purely stylistic.

---

## 2. Generation Pipeline

```
User selfie (in raw-selfies bucket)
    |
[1] Adaptive crop (if face < threshold of image area)
    |
[2] Build prompt (mode + face analysis → keywords)
    |
[3] Compute adaptive parameters (face size, symmetry, keyword count)
    |
[4] Call primary model (Flux PuLID)
    |
[5] NSFW screen output (Rekognition)
    |
[6] ArcFace identity check
    |  ↳ If fail → retry once with conservative params
    |  ↳ If still fail → IDENTITY_PRESERVATION_FAILED, release credit
    |
[7] Optional: minimal color/exposure normalization (non-destructive, no skin touch)
    |
[8] Write to generated-images bucket
    |
[9] Commit credit, job → COMPLETED
```

---

## 3. Model Selection

### Primary: Flux PuLID

**Endpoint:** `fal-ai/flux-pulid`

| Parameter | Default | Retry | Range | Purpose |
|-----------|---------|-------|-------|---------|
| `id_weight` | 0.85 | 0.95 | 0.75-0.95 | Identity preservation (independent from prompt) |
| `guidance_scale` | 4.0 | 3.5 | 2.0-6.0 | Prompt adherence |
| `num_inference_steps` | 30 | 30 | 20-50 | Quality/speed |
| `image_size` | `square_hd` | — | — | 1024x1024 |
| `max_sequence_length` | `512` | — | 128/256/512 | Prompt token capacity |
| `negative_prompt` | Section 5.2 | — | — | Anti-beauty-filter |

**Cost:** ~$0.035/image. **Speed:** ~10-15s.

### Fallback 1: Flux Dev img2img + IP-Adapter

**Endpoint:** `fal-ai/flux-general/image-to-image`
**When:** PuLID circuit breaker open.

| Parameter | Value | Purpose |
|-----------|-------|---------|
| `strength` | 0.55 (retry: 0.40) | Change magnitude |
| `guidance_scale` | 4.5 | Prompt adherence |
| `num_inference_steps` | 35 | |
| `ip_adapters` | FaceID, scale=0.6 | Face conditioning |

**Cost:** ~$0.026/image.

### Fallback 2: InstantID (SDXL)

**Endpoint:** `fal-ai/instantid`
**When:** Both Flux models down.

| Parameter | Value | Purpose |
|-----------|-------|---------|
| `controlnet_conditioning_scale` | 0.80 | Identity |
| `guidance_scale` | 5.0 | |
| `num_inference_steps` | 30 | |
| `model_type` | `SDXL-v2-plus` | |

**Cost:** ~$0.02/image.

---

## 4. Prompt System

### 4.1 Three prompt modes

Not every glow-up should look like a magazine shoot. The mode is selected based on the source image context and user preferences (future: user chooses; MVP: auto-detect from image).

**Mode: everyday** (default)
```
This same person with better styling: {keywords}. Natural daylight
photography, relaxed and approachable. Keep all natural skin exactly as
it is — every freckle, mole, pore, and skin detail stays. Improve only
hair, grooming, and clothing. Looks like their best casual day, not a
photoshoot.
```

**Mode: polished**
```
This same person styled for a professional headshot: {keywords}. Clean
portrait photography with flattering lighting. All natural skin features
preserved — freckles, moles, pores, texture unchanged. Only styling,
grooming, and lighting are improved. Confident and camera-ready.
```

**Mode: editorial**
```
This same person in a high-end editorial photoshoot: {keywords}. Magazine
quality, dramatic lighting, fashion-forward. Natural skin fully preserved
— freckles, moles, texture, pores all visible. The styling is elevated,
the skin is untouched.
```

### 4.2 Mode selection logic (MVP)

```python
def select_mode(face_ratio: float, keyword_count: int) -> str:
    """Auto-select prompt mode based on input characteristics."""
    if keyword_count <= 2:
        return "everyday"     # Few changes → keep it natural
    if keyword_count <= 4:
        return "polished"     # Moderate changes → professional look
    return "editorial"        # Many changes → editorial treatment
```

Future: user selects mode via the mobile UI ("casual / professional / editorial").

### 4.3 Prompt builder

```python
def build_prompt(
    face_shape: FaceShape,
    symmetry_score: float,
    recommendations: list[Suggestion],
) -> tuple[str, str, dict]:
    """Returns (prompt, negative_prompt, adaptive_params)."""
    keywords = extract_allowed_keywords(recommendations, max_count=6)
    lighting = select_lighting_keyword(symmetry_score)
    keywords.append(lighting)

    mode = select_mode(face_ratio=..., keyword_count=len(keywords))
    template = load_template(f"prompts/glowup_{mode}.txt")
    prompt = template.replace("{keywords}", ", ".join(keywords))

    negative = load_template("prompts/glowup_negative.txt")

    params = compute_adaptive_params(
        face_ratio=...,
        symmetry_score=symmetry_score,
        keyword_count=len(keywords),
    )

    return prompt, negative, params
```

### 4.4 Prompt diversity layer

Runs inside `build_prompt()` to prevent repetitive outputs across users.

#### Identity phrase rotation

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

Templates become: `"{identity_phrase} with better styling: {keywords}..."`

#### Style theme injection

When `keyword_count <= 4`, inject ONE random style theme to increase visual diversity:

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

Appended to keyword list (does not count toward `MAX_PROMPT_KEYWORDS`). These are styling atmosphere terms — no skin or beauty language.

#### Anti-repetition

The prompt builder tracks recent keyword sets in Redis (`prompt:recent:{user_id}`, list of last 5 keyword hashes, TTL 24h). If the same keyword set was used in the last 3 generations for this user:

1. Shuffle keyword order (models weight earlier tokens differently)
2. Swap one keyword with its synonym from the allowlist (e.g., "layered cut" ↔ "textured crop")
3. Inject a different style theme than the last one used

This only matters for users who generate multiple glow-ups — first-time users always get fresh prompts.

#### Borderline wow boost

When the first candidate scores wow_score 0.45–0.60 AND ArcFace score > 0.85 (identity has room to spare):

```python
if 0.45 <= wow_score <= 0.60 and arcface_score > 0.85:
    # Small creative push — identity has margin
    boosted_params = {
        "id_weight": params["id_weight"] - 0.03,
        "guidance_scale": params["guidance_scale"] + 0.2,
    }
    # Add 1 safe extension keyword
    extra = random.choice(list(SAFE_EXTENSION_KEYWORDS))
    boosted_keywords = keywords + [extra]
    # Generate second candidate with boosted params
```

This is a lighter version of the weak-transformation second candidate (Section 6.5) — it fires at a higher wow threshold (0.45-0.60 vs < 0.50) but only when identity margin exists.

### 4.5 InstantID fallback prompts

Positive:
```
same person, style makeover, {keywords}, portrait photography, natural
lighting, sharp focus, natural skin with visible pores and freckles
```

Negative: same as Section 5.2.

---

## 5. Negative Prompt & Skin Preservation

### 5.1 Skin preservation strategy

Three reinforcement layers:
1. **Prompt:** explicit "keep freckles, moles, pores, texture"
2. **Negative prompt:** blocks 20+ beauty-filter terms
3. **No post-processing model:** no face-enhancement step. PuLID output is final (except optional non-destructive color normalization).

### 5.2 Negative prompt (shared across all models)

```
smooth skin, airbrushed skin, beauty filter, skin retouch, porcelain
skin, plastic skin, doll-like, mannequin, freckle removal, mole removal,
skin smoothing, beauty enhancement, face tune, filtered skin, flawless
skin, perfect skin, glass skin, blemish removal, wrinkle removal, pore
removal, skin resurfacing, dermabrasion effect, distorted face,
asymmetric eyes, extra fingers, deformed hands, blurry, low resolution,
cartoon, anime, painting, illustration, 3d render, oversaturated,
watermark, text, different person, altered bone structure
```

---

## 6. Adaptive Generation Parameters

Static parameters produce inconsistent results across different input types. The system adapts based on three signals.

### 6.1 Signals

| Signal | Source | Range | Meaning |
|--------|--------|-------|---------|
| `face_ratio` | face bbox area / image area | 0.0-1.0 | How much of the image is face |
| `symmetry_score` | FaceAnalysisService | 0.0-1.0 | Facial symmetry |
| `keyword_count` | allowlist extraction | 1-6 | How many styling changes requested |

### 6.2 Parameter ranges (hard limits)

Never push both id_weight high AND guidance high simultaneously — this over-constrains the model and produces near-identical outputs.

| Parameter | Min | Max | Danger zone |
|-----------|-----|-----|-------------|
| `id_weight` | 0.80 | 0.93 | >0.93 = near-identical output; <0.80 = identity risk |
| `guidance_scale` | 3.5 | 4.8 | >4.8 = artifacts; <3.5 = ignores prompt |

**Tradeoff rule:** `id_weight + guidance_scale` should sum to roughly 4.85 ± 0.3. If one goes up, the other goes down.

### 6.3 Adaptive rules (PuLID)

```python
def compute_adaptive_params(
    face_ratio: float,
    symmetry_score: float,
    keyword_count: int,
) -> dict:
    """Adjust generation parameters based on input characteristics."""

    # Base values
    id_weight = 0.86
    guidance = 4.0

    # --- Keyword scaling ---
    # More keywords = more change requested = give the model room
    if keyword_count >= 5:
        id_weight = 0.82
        guidance = 4.5
    elif keyword_count == 3 or keyword_count == 4:
        id_weight = 0.85
        guidance = 4.0
    elif keyword_count <= 2:
        # Few keywords can still produce visible change — don't over-lock
        id_weight = 0.87
        guidance = 3.8

    # --- Symmetry adjustment ---
    # Low symmetry faces are harder for the model — tighten identity
    if symmetry_score < 0.75:
        id_weight = min(id_weight + 0.04, 0.93)
        guidance = max(guidance - 0.2, 3.5)

    # --- Face size adjustment ---
    if face_ratio < 0.15:
        id_weight = min(id_weight + 0.02, 0.93)

    # --- Clamp to safe ranges ---
    id_weight = max(0.80, min(0.93, round(id_weight, 2)))
    guidance = max(3.5, min(4.8, round(guidance, 1)))

    return {
        "id_weight": id_weight,
        "guidance_scale": guidance,
        "num_inference_steps": 30,
    }
```

### 6.4 Adaptive rules (Flux Dev fallback)

Same signals, adjusts `strength` instead of `id_weight`:
- keyword_count >= 5 → `strength = 0.58`
- keyword_count 3-4 → `strength = 0.52`
- keyword_count <= 2 → `strength = 0.45`
- Low symmetry → `strength -= 0.05`
- Clamped to [0.40, 0.60]

### 6.5 Candidate scoring and selection

After generation passes ArcFace, the system scores the result and decides whether to accept it or generate a second candidate.

#### Wow score formula

```python
def compute_wow_score(
    arcface_score: float,
    keyword_count: int,
    id_weight_used: float,
    threshold: float = 0.80,
) -> float:
    """Score a candidate's visual impact. Higher = better glow-up.

    Sweet spot: arcface 0.82-0.88 (visible change, clearly same person).
    Too similar (>0.93) = boring. Too different (<threshold) = rejected.
    """
    # Identity band reward: peaks at 0.85, drops off toward edges
    # 0.80 → 0.6, 0.85 → 1.0, 0.90 → 0.6, 0.95 → 0.1
    sweet_spot = 0.85
    identity_score = max(0, 1.0 - abs(arcface_score - sweet_spot) * 6.0)

    # More keywords = more styling intent = reward
    styling_intent = min(keyword_count / 6.0, 1.0)

    # Lower id_weight used = model had more freedom = reward (if identity held)
    freedom_score = 1.0 - ((id_weight_used - 0.80) / 0.13)  # 0.80→1.0, 0.93→0.0
    freedom_score = max(0, min(1.0, freedom_score))

    # Composite: identity band matters most
    return (
        identity_score * 0.50
        + styling_intent * 0.25
        + freedom_score * 0.25
    )
```

**Score interpretation:**
| Score | Meaning | Action |
|-------|---------|--------|
| ≥ 0.70 | Strong glow-up | Accept immediately |
| 0.50 - 0.70 | Decent glow-up | Accept (normal) |
| 0.30 - 0.50 | Weak glow-up | Generate second candidate |
| < 0.30 | Near-identical or too different | Generate second candidate |

#### Anti-meh detection and second candidate

```python
def should_generate_second_candidate(
    wow_score: float,
    arcface_score: float,
    keyword_count: int,
) -> bool:
    """Determine if a second candidate should be generated."""
    if wow_score < 0.50:
        return True
    # Specific case: high identity + many keywords = under-transformed
    if arcface_score > 0.93 and keyword_count >= 3:
        return True
    return False
```

**When second candidate is generated:**
1. Original candidate is kept (it passed ArcFace — it's valid)
2. Generate ONE additional candidate with boosted parameters:
   - `id_weight -= 0.04` (more room for change)
   - `guidance_scale += 0.3` (stronger prompt adherence)
   - Add one keyword from the safe extension set (Section 8.3)
3. Score both candidates with `compute_wow_score()`
4. Select the HIGHER wow_score candidate, provided it passes ArcFace threshold
5. If the second candidate fails ArcFace, use the first (safe fallback)

#### Selection logic

```python
def select_best_candidate(
    candidates: list[dict],  # [{image_url, arcface_score, wow_score, params}]
    threshold: float,
) -> dict:
    """Select the best candidate from available options."""
    # Filter: must pass identity threshold
    valid = [c for c in candidates if c["arcface_score"] >= threshold]
    if not valid:
        return None  # All failed identity — IDENTITY_PRESERVATION_FAILED

    # Sort by wow_score descending
    valid.sort(key=lambda c: c["wow_score"], reverse=True)
    return valid[0]
```

#### Pipeline integration point

```
[4] ArcFace identity check
    |
[4a] Compute wow_score for candidate
    |
[4b] If should_generate_second_candidate():
    |     Generate second candidate (boosted params)
    |     ArcFace check second candidate
    |     Compute wow_score for second candidate
    |     select_best_candidate([first, second])
    |
[4c] Log: selected_wow_score, candidate_count, arcface_score
    |
[5] NSFW screen the SELECTED candidate (not both)
    |
[6] Write selected to generated-images bucket
```

**Safety:** Identity threshold is ALWAYS enforced. A higher wow_score NEVER overrides a failed ArcFace check.

#### Job result includes scoring data

```python
{
    "image_url": "...",
    "arcface_score": 0.86,
    "wow_score": 0.72,
    "candidate_count": 1,  # or 2 if second was generated
    "selected_candidate": 1,  # which one was picked
}
```

This data feeds into the prompt A/B testing system (Section 14) — wow_score is a key metric for prompt variant evaluation.

**Cost impact:** Second candidate fires ~10-15% of the time. Adds ~$0.035 to those jobs. Weighted average: ~$0.044. Under ceiling.

### 6.6 Retry keyword pruning (first-attempt optimization)

To reduce retry rate below 15%:

```python
def prepare_keywords_for_generation(keywords: list[str]) -> list[str]:
    """Optimize keyword list for best first-attempt success."""
    # If > 5 keywords, drop the least impactful one (lighting keywords are least likely to cause drift)
    if len(keywords) > 5:
        # Priority order: hair > grooming > eyebrows > facial_hair > clothing > lighting
        # Drop from the end (lowest priority)
        keywords = keywords[:5]

    # Put most important keywords first (model weights earlier tokens more)
    # Hair changes are the most visible glow-up element
    hair_first = [k for k in keywords if k in HAIR_KEYWORDS]
    rest = [k for k in keywords if k not in HAIR_KEYWORDS]
    return hair_first + rest
```

---

## 7. Face Crop Strategy

### 7.1 When to crop

| Face ratio | Action | Reason |
|-----------|--------|--------|
| > 0.40 | No crop | Face fills frame, model focuses on it naturally |
| 0.15 - 0.40 | Crop to head+shoulders | Model needs guidance to focus on face |
| < 0.15 | Crop to head only | Face is tiny, need maximum zoom |

### 7.2 Crop implementation

```python
def compute_crop(image_size: tuple, face_bbox: tuple, face_confidence: float) -> tuple | None:
    """Return crop box or None if no crop needed."""
    img_w, img_h = image_size
    fx, fy, fw, fh = face_bbox
    face_area = fw * fh
    img_area = img_w * img_h
    face_ratio = face_area / img_area

    # Skip crop if face is large enough
    if face_ratio > 0.40:
        return None

    # Skip crop if face detection confidence is low (might be wrong bbox)
    if face_confidence < 0.85:
        return None

    # Compute padded crop around face center
    cx, cy = fx + fw / 2, fy + fh / 2
    pad = 2.0 if face_ratio > 0.15 else 1.5  # Less padding for tiny faces

    crop_size = max(fw, fh) * pad
    crop_size = min(crop_size, min(img_w, img_h))  # Don't exceed image

    x1 = max(0, int(cx - crop_size / 2))
    y1 = max(0, int(cy - crop_size / 2))
    x2 = min(img_w, int(cx + crop_size / 2))
    y2 = min(img_h, int(cy + crop_size / 2))

    return (x1, y1, x2, y2)
```

### 7.3 Post-generation composite

After generation + identity check, if the image was cropped:

```python
def composite_glowup(original_img, generated_img, crop_box, face_bbox):
    """Blend generated glow-up back into original frame."""
    x1, y1, x2, y2 = crop_box
    crop_w, crop_h = x2 - x1, y2 - y1

    # 1. Resize generated to match crop dimensions
    result = generated_img.resize((crop_w, crop_h), Image.LANCZOS)

    # 2. Color-match BEFORE compositing (prevents tonal seams)
    result = match_color_stats(result, original_img.crop(crop_box))

    # 3. Dynamic feather radius based on face size
    face_size = max(face_bbox[2], face_bbox[3])
    feather_px = max(15, int(face_size * 0.08))  # 8% of face size, min 15px

    # 4. Create feathered mask (gradient at edges)
    mask = create_feathered_mask(crop_w, crop_h, feather_px)

    # 5. Composite
    canvas = original_img.copy()
    canvas.paste(result, (x1, y1), mask)
    return canvas

def match_color_stats(generated, original_crop):
    """Match mean brightness and color temperature of generated to original."""
    import numpy as np
    gen_arr = np.array(generated, dtype=float)
    orig_arr = np.array(original_crop, dtype=float)

    for c in range(3):  # R, G, B
        gen_mean = gen_arr[:,:,c].mean()
        orig_mean = orig_arr[:,:,c].mean()
        if gen_mean > 0:
            gen_arr[:,:,c] *= (orig_mean / gen_mean)

    gen_arr = np.clip(gen_arr, 0, 255).astype(np.uint8)
    return Image.fromarray(gen_arr)
```

This preserves the original background while showing the glow-up, with color-matched blending to avoid visible seams.

---

## 8. Keyword Allowlist

### 8.1 Allowed keywords (styling only)

**Hair (18):** textured crop, side part, slicked back, pompadour, layered cut, curtain bangs, tapered fade, undercut, shorter sides, longer top, voluminous blowout, soft waves, defined curls, straightened, well-groomed hair, polished hairstyle, neat hairline, healthy shine

**Hair — extended (12):** bob cut, pixie cut, buzz cut, french crop, middle part, messy bun, high ponytail, braided style, beach waves, afro texture, twisted locs, silk press

**Eyebrows (8):** refined eyebrow arch, groomed eyebrows, natural brow shape, defined brows, trimmed brows, filled brows, soft brow arch, structured brows

**Facial hair (7):** clean shaven, neat stubble, trimmed beard, defined beard line, groomed mustache, shaped goatee, well-maintained facial hair

**Clothing (10):** fitted blazer, crisp white shirt, leather jacket, turtleneck, denim jacket, linen shirt, tailored suit, casual streetwear, athleisure, smart casual

**Accessories (8):** statement necklace, minimal earrings, rectangular glasses, round glasses, aviator sunglasses, watch, scarf, headband

**Lighting (8):** improved lighting, soft natural lighting, golden hour glow, studio lighting, even skin lighting, warm tones, cool tones, balanced exposure

**Grooming (3):** well-rested appearance, brighter eyes, healthy complexion

**Total: 74 keywords**

### 8.2 Blocked terms (never allowed)

clear skin, even complexion, reduced blemishes, moisturized skin, skin glow, smooth skin, poreless, dewy skin, glass skin, skin resurfacing, anti-aging, wrinkle reduction, pore minimizing, skin brightening, complexion evening

These trigger beauty-filter behavior in diffusion models.

### 8.3 Safe extension keywords (weak-transformation boost only)

When Section 6.5 detects a weak transformation, ONE keyword from this set is added. These amplify styling intensity without touching skin:

elevated style, refined look, fashion-forward, magazine cover ready, red carpet styling, freshly styled, sharp dressed, well-coordinated outfit, professional grooming, editorial quality

These are NOT in the primary allowlist. Used only when the output is too conservative (~10-15% of jobs).

---

## 9. Identity Preservation

### 9.1 Three layers

| Layer | Mechanism | What it catches |
|-------|-----------|-----------------|
| 1. Model conditioning | `id_weight=0.85` (PuLID) / IP-Adapter / ControlNet | Face consistency during generation |
| 2. ArcFace post-check | Cosine similarity ≥ 0.80 | Identity drift the model missed |
| 3. Prompt design | "same person" + skin preservation instructions | Guides model away from face modification |

### 9.2 ArcFace implementation

- **Model:** `insightface` buffalo_l, CPU, pre-loaded at worker startup
- **Ephemeral:** embeddings discarded after comparison (ADR-1)
- **Threshold:** `IDENTITY_SIMILARITY_THRESHOLD` (default 0.80, per-tier)

### 9.3 Retry strategy

```
Attempt 1:
  id_weight = adaptive (0.80-0.90)
  guidance_scale = adaptive (3.5-4.5)
  All extracted keywords (up to 6)
  → ArcFace check → if pass: done

Attempt 2 (conservative):
  id_weight = min(attempt1 + 0.10, 0.95)
  guidance_scale = attempt1 - 0.5
  Top 3 keywords only (drop least-confident)
  Downgrade mode: editorial → polished, polished → everyday
  → ArcFace check → if pass: done
  → if fail: IDENTITY_PRESERVATION_FAILED, release credit
```

### 9.4 Retry cost optimization

Target: keep retry rate below 15% to maintain ~$0.040 average cost.

Strategies to reduce retries:
- Adaptive `id_weight` based on input signals (Section 6) — prevents over-generation
- More keywords = slightly lower `id_weight` — gives the model room
- Low symmetry = higher `id_weight` — protects harder faces
- Face crop before generation — model focuses on face, not background

---

## 10. Post-Processing (Minimal, Non-Destructive)

### 10.1 What's allowed

After PuLID generation and ArcFace check, ONE optional step:

**Color/exposure normalization** using Pillow (no AI model):
```python
from PIL import ImageEnhance, ImageStat

def normalize_output(source_img, generated_img):
    """Match generated image's brightness/color to source. No skin touch."""
    # Match average brightness
    src_brightness = ImageStat.Stat(source_img).mean[0]
    gen_brightness = ImageStat.Stat(generated_img).mean[0]
    if abs(src_brightness - gen_brightness) > 20:  # Only if significantly different
        factor = src_brightness / max(gen_brightness, 1)
        factor = max(0.8, min(1.2, factor))  # Clamp to ±20%
        generated_img = ImageEnhance.Brightness(generated_img).enhance(factor)

    return generated_img
```

### 10.2 What's NOT allowed

- Any AI-based face enhancement, retouching, or upscaling model
- Skin smoothing, blemish removal, frequency separation
- Sharpening beyond Pillow's basic `ImageEnhance.Sharpness`
- Any model that takes "face" as input category

---

## 11. Face Analysis → Prompt Mapping

| Face Shape | Symmetry | Mode | Keywords | Lighting |
|------------|----------|------|----------|----------|
| Oval, 0.87 | High | polished | layered cut, soft brow arch, fitted blazer, polished hairstyle | studio lighting |
| Round, 0.78 | Lower | everyday | pompadour, defined brows, trimmed beard, shorter sides | soft natural lighting |
| Square, 0.82 | Mid | polished | soft waves, groomed eyebrows, neat stubble, leather jacket | warm tones |
| Heart, 0.90 | High | editorial | curtain bangs, natural brow shape, denim jacket, beach waves, minimal earrings | golden hour glow |
| Oblong, 0.76 | Lower | everyday | layered cut, headband, turtleneck | even skin lighting |

---

## 12. Config Values

```python
# Generation models
FAL_MODEL_PRIMARY: str = "fal-ai/flux-pulid"
FAL_MODEL_FALLBACK_1: str = "fal-ai/flux-general/image-to-image"
FAL_MODEL_FALLBACK_2: str = "fal-ai/instantid"

# PuLID defaults (overridden by adaptive logic)
FAL_PULID_ID_WEIGHT: float = 0.85
FAL_PULID_GUIDANCE_SCALE: float = 4.0
FAL_PULID_INFERENCE_STEPS: int = 30

# Flux Dev defaults
FAL_FLUX_STRENGTH: float = 0.55
FAL_FLUX_GUIDANCE_SCALE: float = 4.5
FAL_FLUX_INFERENCE_STEPS: int = 35
FAL_FLUX_IP_ADAPTER_SCALE: float = 0.6

# InstantID defaults
FAL_INSTANTID_CONTROLNET_SCALE: float = 0.80
FAL_INSTANTID_GUIDANCE_SCALE: float = 5.0
FAL_INSTANTID_INFERENCE_STEPS: int = 30

# Generation behavior
GENERATION_OUTPUT_RESOLUTION: int = 1024
IDENTITY_MAX_RETRIES: int = 1
MAX_PROMPT_KEYWORDS: int = 6
FACE_CROP_MIN_CONFIDENCE: float = 0.85
IMAGE_GEN_COST_CEILING_USD: float = 0.06
CREDIT_COST_ALERT_USD: float = 0.05
```

---

## 13. Files

| File | Purpose |
|------|---------|
| `prompts/glowup_everyday.txt` | Default casual glow-up template |
| `prompts/glowup_polished.txt` | Professional headshot template |
| `prompts/glowup_editorial.txt` | Magazine editorial template |
| `prompts/glowup_instantid_positive.txt` | InstantID fallback positive |
| `prompts/glowup_negative.txt` | Shared negative prompt |
| `prompts/keyword_allowlist.py` | 74 allowed styling keywords |
| `docs/generation-spec.md` | This document |

---

## 14. Prompt A/B Testing System

### 14.1 Why

Prompt quality directly impacts identity preservation, styling visibility, and retry rate. Static prompts can't adapt to what actually works. The system tracks which prompt variants perform best and shifts traffic toward winners.

### 14.2 Schema

```sql
CREATE TABLE prompt_experiments (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    job_id          UUID NOT NULL REFERENCES glow_up_jobs(id),
    prompt_mode     TEXT NOT NULL,        -- 'everyday', 'polished', 'editorial'
    prompt_template TEXT NOT NULL,        -- full prompt text used
    keyword_count   INT NOT NULL,
    arcface_score   FLOAT,               -- NULL if identity check not reached
    retry_count     INT NOT NULL DEFAULT 0,
    generation_ms   INT,                 -- inference time in ms
    estimated_cost  DECIMAL(6,4),
    model_used      TEXT NOT NULL,        -- 'flux-pulid', 'flux-general', 'instantid'
    outcome         TEXT NOT NULL,        -- 'success', 'identity_failed', 'nsfw_blocked', 'error'
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_prompt_exp_mode ON prompt_experiments (prompt_mode, created_at DESC);
```

### 14.3 Traffic allocation

```python
# Default: top performer gets 70%, rest split 30% equally
PROMPT_TRAFFIC = {
    "everyday":  0.40,   # Default mode gets most traffic initially
    "polished":  0.35,
    "editorial": 0.25,
}

# After 500+ generations, shift to performance-weighted:
# weight = success_rate * avg_arcface_score / avg_cost
# Top mode gets 70%, second gets 20%, third gets 10%
```

### 14.4 Evaluation metrics

```python
@dataclass
class PromptScore:
    mode: str
    success_rate: float      # % of generations that passed ArcFace
    avg_arcface_score: float # Average identity similarity
    retry_rate: float        # % that needed retry
    avg_cost: float          # Average cost including retries
    sample_count: int        # Number of generations

    @property
    def composite_score(self) -> float:
        """Higher is better. Weighs identity + success heavily."""
        return (
            self.success_rate * 0.40
            + self.avg_arcface_score * 0.30
            + (1 - self.retry_rate) * 0.20
            + (1 - min(self.avg_cost / 0.06, 1.0)) * 0.10
        )
```

### 14.5 Optimization job

ARQ scheduled task, runs every 6 hours:

```python
async def optimize_prompt_traffic(ctx):
    """Analyze last 48h of prompt experiments. Update traffic weights."""
    scores = await compute_prompt_scores(hours=48, min_samples=50)

    if all(s.sample_count >= 50 for s in scores):
        # Enough data — shift to performance-weighted
        ranked = sorted(scores, key=lambda s: s.composite_score, reverse=True)
        PROMPT_TRAFFIC[ranked[0].mode] = 0.70
        PROMPT_TRAFFIC[ranked[1].mode] = 0.20
        PROMPT_TRAFFIC[ranked[2].mode] = 0.10

        # Safety: if any mode has retry_rate > 30%, disable it
        for s in scores:
            if s.retry_rate > 0.30:
                PROMPT_TRAFFIC[s.mode] = 0.0
                # Redistribute to others
                redistribute_traffic(PROMPT_TRAFFIC)

    await save_traffic_weights(PROMPT_TRAFFIC)  # Redis hash
```

### 14.6 Safety guardrails

- Experimental prompts are limited to 30% of traffic (even if a new variant is added)
- Any mode with retry_rate > 30% is auto-disabled
- Cost ceiling still applies globally — experiments don't get a cost exemption
- Minimum 50 samples before a mode influences traffic allocation

---

## 15. User Feedback Learning Loop

### 15.1 Feedback signals

Users express quality preferences through existing app actions — no new UI needed:

| Action | Signal | Weight | Source |
|--------|--------|--------|--------|
| Share to social feed | Strong positive | +1.0 | `POST /posts` (creates a post from this generation) |
| Save / download | Positive | +0.7 | `POST /jobs/{id}/save` |
| No action (30min+) | Neutral | 0.0 | Absence of any action after viewing result |
| Regenerate | Negative | -0.5 | `POST /jobs/{id}/regenerate` (same selfie, new generation) |
| "Doesn't look like me" | Strong negative | -1.0 | `POST /jobs/{id}/identity-complaint` (AC-U8 refund flow) |

### 15.2 User score computation

```python
def compute_user_score(job_id: UUID) -> float | None:
    """Compute user score from feedback signals. Returns None if no signal yet."""
    actions = get_job_actions(job_id)  # From usage_events or a dedicated table

    if "identity_complaint" in actions:
        return -1.0
    if "regenerate" in actions:
        return -0.5
    if "share" in actions:
        return 1.0
    if "save" in actions:
        return 0.7

    # Check if enough time passed for "no action" signal
    job = get_job(job_id)
    if job.completed_at and (now() - job.completed_at) > timedelta(minutes=30):
        return 0.0

    return None  # Too early to score
```

### 15.3 Final score

```python
def compute_final_score(wow_score: float, user_score: float | None) -> float:
    """Combine technical quality with user preference."""
    if user_score is None:
        return wow_score  # No feedback yet — use technical score only

    return 0.7 * wow_score + 0.3 * user_score
```

`final_score` replaces `wow_score` in the prompt A/B system (Section 14) once user feedback is available. Before feedback, `wow_score` is used alone.

### 15.4 Schema extension

```sql
-- Extend prompt_experiments (Section 14.2) with feedback columns
ALTER TABLE prompt_experiments ADD COLUMN user_score FLOAT;
ALTER TABLE prompt_experiments ADD COLUMN final_score FLOAT;
ALTER TABLE prompt_experiments ADD COLUMN feedback_actions TEXT[];  -- ['share', 'save', etc.]
ALTER TABLE prompt_experiments ADD COLUMN feedback_at TIMESTAMPTZ;
```

A background job (ARQ, every 10 minutes) scans recent completed jobs and computes `user_score` from observed actions:

```python
async def update_feedback_scores(ctx):
    """Backfill user_score for completed jobs with sufficient time elapsed."""
    pending = await db.fetch("""
        SELECT pe.id, pe.job_id, gj.completed_at
        FROM prompt_experiments pe
        JOIN glow_up_jobs gj ON pe.job_id = gj.id
        WHERE pe.user_score IS NULL
        AND gj.status = 'completed'
        AND gj.completed_at < NOW() - INTERVAL '30 minutes'
    """)
    for row in pending:
        score = compute_user_score(row["job_id"])
        if score is not None:
            final = 0.7 * row.get("wow_score", 0.5) + 0.3 * score
            await db.execute("""
                UPDATE prompt_experiments
                SET user_score = $1, final_score = $2, feedback_at = NOW()
                WHERE id = $3
            """, score, final, row["id"])
```

### 15.5 Integration with prompt A/B system

Section 14.4's `PromptScore.composite_score` is extended to use `final_score` when available:

```python
@property
def composite_score(self) -> float:
    # Use final_score (includes user feedback) when available, else wow_score
    scores = [e.final_score if e.final_score is not None else e.wow_score
              for e in self.experiments]
    avg_quality = sum(scores) / len(scores) if scores else 0.5

    return (
        self.success_rate * 0.35
        + avg_quality * 0.35       # Was 0.30 for arcface alone
        + (1 - self.retry_rate) * 0.20
        + (1 - min(self.avg_cost / 0.06, 1.0)) * 0.10
    )
```

Over time, this makes the prompt optimization job favor combinations that users actually like (share/save), not just combinations that score well technically.

### 15.6 Safety constraints

- `final_score` NEVER overrides ArcFace threshold — identity is a hard gate
- A high `user_score` on a technically questionable output does NOT make it acceptable
- If a prompt mode consistently gets identity complaints (`user_score = -1.0` rate > 5%), it is auto-disabled regardless of other scores
- The 70/30 weighting ensures technical quality (wow_score) always dominates

---

### 15.7 Novelty scoring

Prevents the optimization loop from converging on a single "safe" output style.

#### Signals

```python
def compute_novelty_score(
    keywords: list[str],
    style_theme: str,
    identity_phrase: str,
    user_id: str,
    redis: Redis,
) -> float:
    """Score how different this generation is from recent outputs. 0-1, higher = more novel."""

    keyword_hash = hashlib.md5(",".join(sorted(keywords)).encode()).hexdigest()[:8]

    # 1. Keyword combination uniqueness (global last 50)
    global_recent = await redis.lrange("novelty:global:keywords", 0, 49)
    keyword_repeats = global_recent.count(keyword_hash)
    keyword_novelty = max(0, 1.0 - keyword_repeats * 0.25)  # 0 repeats=1.0, 4+=0.0

    # 2. Per-user repetition (last 10)
    user_recent = await redis.lrange(f"novelty:user:{user_id}:keywords", 0, 9)
    user_repeats = user_recent.count(keyword_hash)
    user_novelty = 1.0 if user_repeats == 0 else 0.3  # Binary: new for this user or not

    # 3. Style theme frequency (global last 100)
    theme_counts = await redis.hgetall("novelty:global:themes")
    total_themes = sum(int(v) for v in theme_counts.values()) or 1
    this_theme_pct = int(theme_counts.get(style_theme, 0)) / total_themes
    theme_novelty = max(0, 1.0 - this_theme_pct * 2.5)  # 40%+ usage → 0.0

    return round(
        keyword_novelty * 0.45
        + user_novelty * 0.35
        + theme_novelty * 0.20,
        3,
    )
```

#### Tracking (Redis, lightweight)

```python
# After each generation commit:
async def track_novelty(keywords, style_theme, user_id, redis):
    keyword_hash = hashlib.md5(",".join(sorted(keywords)).encode()).hexdigest()[:8]

    # Global keyword history (capped at 200, TTL 24h)
    await redis.lpush("novelty:global:keywords", keyword_hash)
    await redis.ltrim("novelty:global:keywords", 0, 199)
    await redis.expire("novelty:global:keywords", 86400)

    # Per-user keyword history (capped at 20, TTL 7d)
    key = f"novelty:user:{user_id}:keywords"
    await redis.lpush(key, keyword_hash)
    await redis.ltrim(key, 0, 19)
    await redis.expire(key, 604800)

    # Style theme counter (TTL 24h, reset daily)
    await redis.hincrby("novelty:global:themes", style_theme, 1)
    await redis.expire("novelty:global:themes", 86400)
```

#### Updated final_score

```python
def compute_final_score(
    wow_score: float,
    user_score: float | None,
    novelty_score: float,
) -> float:
    if user_score is None:
        # No feedback yet — novelty gets user_score's share
        return 0.65 * wow_score + 0.35 * novelty_score

    return (
        0.60 * wow_score
        + 0.25 * user_score
        + 0.15 * novelty_score
    )
```

Novelty is always the smallest weight. It breaks ties and nudges diversity but never overrides quality or safety.

#### Selection impact

When `select_best_candidate()` (Section 6.5) compares two candidates with similar wow_scores (within 0.05), novelty_score is the tiebreaker. The more novel candidate wins.

#### Safety

- Novelty scoring only reads the allowlist keywords and style themes already selected — it never introduces new terms
- A high novelty_score on a failed-ArcFace candidate is irrelevant — identity threshold is checked first
- If a novel keyword combination causes retry_rate > 30%, the A/B system (Section 14.5) disables it automatically
- Novelty cannot push `id_weight` below 0.80 or `guidance_scale` above 4.8 — the hard limits in Section 6.2 are unchanged

---

### 15.8 Exploration pressure

Prevents the optimization loop from collapsing to a single "best" pattern.

#### Exploration ratio

Every generation request rolls a random number:
- **80%**: use optimized distribution (A/B system weights from Section 14)
- **20%**: use exploration — randomized mode, shuffled keywords, random style theme

This ratio is fixed. It is NOT configurable down to 0% — exploration always exists.

#### Exploration behavior

When a request is tagged `exploration=True`:
1. Mode: random selection (equal weight across everyday/polished/editorial)
2. Keywords: shuffle order, swap 1 keyword with a random synonym from allowlist
3. Style theme: random from `_STYLE_THEMES`, ignoring frequency weighting
4. Parameters: stay within safe ranges (Section 6.2) — exploration does NOT relax id_weight below 0.80

#### Anti-collapse enforcement

Checked by the A/B optimization job (Section 14.5) every 6 hours:

```python
async def enforce_distribution_limits(ctx):
    """Ensure no single pattern dominates."""
    stats = await get_recent_distribution(hours=24)

    violations = []
    for combo, pct in stats["keyword_combos"].items():
        if pct > 0.25:
            violations.append(f"keyword combo '{combo}' at {pct:.0%} (max 25%)")

    for theme, pct in stats["style_themes"].items():
        if pct > 0.35:
            violations.append(f"theme '{theme}' at {pct:.0%} (max 35%)")

    for mode, pct in stats["prompt_modes"].items():
        if pct > 0.70:
            violations.append(f"mode '{mode}' at {pct:.0%} (max 70%)")

    if violations:
        # Temporarily boost exploration to 40% until next check
        await redis.set("exploration_rate_override", "0.40", ex=21600)
        logger.warning("Distribution collapse detected: %s", violations)
```

When an override is active, the exploration rate doubles from 20% to 40% for 6 hours, then drops back.

#### Exploration → production promotion

If an exploration output scores `final_score > 0.65` over 20+ samples, the A/B optimization job (Section 14.5) automatically increases that pattern's weight in the optimized distribution. No manual intervention needed.

---

## 16. Transformation Module Architecture

### 16.1 Why modules

The current glow-up is "styling" — hair, grooming, clothing, lighting. Future transformations could include teeth, eyes, body posture, skin treatment visualization, makeup, accessories, etc. Each needs its own keywords, prompt fragments, scoring, and possibly different model parameters — but they all share the same identity check, credit system, queue, and storage.

Without modular design, adding a new transformation type means touching: the prompt builder, keyword allowlist, recommendation engine, adaptive parameter logic, wow scoring, A/B testing, and the worker — spaghetti.

### 16.2 TransformationModule protocol

```python
# app/generation/modules/base.py

from typing import Protocol
from dataclasses import dataclass


@dataclass(frozen=True)
class TransformationOutput:
    """What a module contributes to the generation prompt."""
    prompt_fragment: str       # Appended to the base prompt
    negative_fragment: str     # Appended to the negative prompt
    keywords_used: list[str]   # For tracking / A/B
    wow_weight: float          # How much this module contributes to wow_score (0-1)


class TransformationModule(Protocol):
    """A pluggable transformation type."""

    @property
    def slug(self) -> str:
        """Unique identifier: 'styling', 'teeth', 'eyes', etc."""
        ...

    @property
    def display_name(self) -> str:
        """User-facing name."""
        ...

    def is_applicable(self, analysis_result) -> bool:
        """Whether this module should run for this face analysis."""
        ...

    def build_output(self, analysis_result, mode: str) -> TransformationOutput:
        """Generate prompt fragments from face analysis data."""
        ...

    def get_allowed_keywords(self) -> frozenset[str]:
        """Keywords this module can inject into prompts."""
        ...

    def get_blocked_keywords(self) -> frozenset[str]:
        """Keywords this module explicitly blocks."""
        ...

    def adjust_params(self, base_params: dict) -> dict:
        """Module-specific parameter adjustments (e.g., teeth needs higher guidance)."""
        ...
```

### 16.3 Module registry

```python
# app/generation/modules/registry.py

_MODULES: dict[str, TransformationModule] = {}


def register(module: TransformationModule) -> None:
    _MODULES[module.slug] = module


def get_active_modules(analysis_result, enabled_slugs: list[str]) -> list[TransformationModule]:
    """Return modules that are both enabled and applicable to this face."""
    return [
        m for slug, m in _MODULES.items()
        if slug in enabled_slugs and m.is_applicable(analysis_result)
    ]
```

Modules register themselves at import time. Enabling/disabling a module is a config change (`ENABLED_TRANSFORMATION_MODULES`), not a code change.

### 16.4 Styling module (current glow-up = first module)

```python
# app/generation/modules/styling.py

class StylingModule:
    slug = "styling"
    display_name = "Style Glow-Up"

    def is_applicable(self, analysis_result) -> bool:
        return True  # Always applicable

    def build_output(self, analysis_result, mode: str) -> TransformationOutput:
        keywords = extract_allowed_keywords(analysis_result.recommendations, max_count=6)
        lighting = select_lighting_keyword(analysis_result.symmetry_score)
        keywords.append(lighting)

        template = load_template(f"prompts/glowup_{mode}.txt")
        prompt = template.replace("{keywords}", ", ".join(keywords))
        negative = load_template("prompts/glowup_negative.txt")

        return TransformationOutput(
            prompt_fragment=prompt,
            negative_fragment=negative,
            keywords_used=keywords,
            wow_weight=1.0,
        )

    def get_allowed_keywords(self) -> frozenset[str]:
        from prompts.keyword_allowlist import ALLOWED_KEYWORDS
        return ALLOWED_KEYWORDS

    def get_blocked_keywords(self) -> frozenset[str]:
        from prompts.keyword_allowlist import BLOCKED_KEYWORDS
        return BLOCKED_KEYWORDS

    def adjust_params(self, base_params: dict) -> dict:
        return base_params  # Styling uses the default adaptive params
```

### 16.5 Future module example: teeth

```python
# app/generation/modules/teeth.py (NOT built yet — shows the pattern)

class TeethModule:
    slug = "teeth"
    display_name = "Smile Enhancement"

    _TEETH_KEYWORDS = frozenset({"bright smile", "aligned teeth", "natural white teeth"})
    _TEETH_BLOCKED = frozenset({"veneers", "perfect teeth", "bleached teeth"})

    def is_applicable(self, analysis_result) -> bool:
        # Only applicable if the face analysis detected an open-mouth smile
        return getattr(analysis_result, "smile_detected", False)

    def build_output(self, analysis_result, mode: str) -> TransformationOutput:
        return TransformationOutput(
            prompt_fragment="with a natural, bright smile showing clean teeth",
            negative_fragment="fake teeth, veneers, over-whitened teeth, dental work",
            keywords_used=["bright smile", "natural white teeth"],
            wow_weight=0.3,  # Teeth is a minor enhancement, not the main event
        )

    def get_allowed_keywords(self) -> frozenset[str]:
        return self._TEETH_KEYWORDS

    def get_blocked_keywords(self) -> frozenset[str]:
        return self._TEETH_BLOCKED

    def adjust_params(self, base_params: dict) -> dict:
        # Teeth changes need tighter identity to avoid mouth distortion
        params = dict(base_params)
        params["id_weight"] = min(params.get("id_weight", 0.85) + 0.03, 0.93)
        return params
```

### 16.6 How the pipeline uses modules

The prompt builder (Section 4.3) changes from building a single prompt to composing module outputs:

```python
def build_prompt(
    analysis_result,
    enabled_modules: list[str],  # e.g., ["styling"] or ["styling", "teeth"]
    mode: str,
) -> tuple[str, str, dict]:
    """Compose prompt from active transformation modules."""

    modules = get_active_modules(analysis_result, enabled_modules)
    if not modules:
        raise ValueError("No applicable transformation modules")

    # Collect outputs from all modules
    outputs = [m.build_output(analysis_result, mode) for m in modules]

    # Compose prompt: identity phrase + module fragments joined
    identity = random.choice(_IDENTITY_PHRASES)
    prompt_parts = [identity] + [o.prompt_fragment for o in outputs]
    prompt = ". ".join(prompt_parts)

    # Compose negative: union of all module negatives
    negative = ", ".join(set(
        kw for o in outputs
        for kw in o.negative_fragment.split(", ")
    ))

    # Merge allowed/blocked keywords
    all_allowed = frozenset().union(*(m.get_allowed_keywords() for m in modules))
    all_blocked = frozenset().union(*(m.get_blocked_keywords() for m in modules))

    # Adaptive params: start with base, let each module adjust
    params = compute_adaptive_params(...)
    for m in modules:
        params = m.adjust_params(params)

    # Wow weight: weighted sum for multi-module scoring
    total_wow_weight = sum(o.wow_weight for o in outputs)

    return prompt, negative, params
```

### 16.7 Config

```python
# app/config.py

# Which transformation modules are active (feature flags)
ENABLED_TRANSFORMATION_MODULES: list[str] = ["styling"]
# Future: ["styling", "teeth", "eyes", "makeup"]
```

Adding a new module means:
1. Create `app/generation/modules/{slug}.py` implementing `TransformationModule`
2. Register it in the module registry
3. Add its slug to `ENABLED_TRANSFORMATION_MODULES`
4. Add its prompt template file(s) to `prompts/`

No changes to: pipeline, queue, identity check, credit system, storage, API, or worker.

### 16.8 File structure

```
app/generation/
    __init__.py
    modules/
        __init__.py          # Registers all modules
        base.py              # TransformationModule protocol + TransformationOutput
        registry.py          # Module registry
        styling.py           # Current glow-up (MVP)
        # teeth.py           # Future
        # eyes.py            # Future
        # makeup.py          # Future
        # body.py            # Future
prompts/
    glowup_everyday.txt      # Styling module templates
    glowup_polished.txt
    glowup_editorial.txt
    glowup_negative.txt
    keyword_allowlist.py     # Styling module keywords
    # teeth_keywords.py      # Future: teeth module keywords
    # eyes_keywords.py       # Future
```

---

## 17. What This Document Does NOT Cover

- ARQ worker setup, queue lanes, priority (Story 4-2 ACs + architecture Section 2.5)
- Credit ledger reserve/release/commit (Story 4-1, already built)
- fal.ai circuit breaker logic (corrections.md item 4)
- Worker scaling, cost tracking Redis counters (corrections.md items 1-9)
- The GlowUpGeneratorPort interface (architecture Section 2.4)
