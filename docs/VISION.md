# NXME — Product Vision

AI-powered appearance improvement social platform.

**Tagline:** "See the best version of yourself."

## What NXME Is

NXME is an **AI glow-up social platform** — not a beauty filter app, not a face rating app. Users upload a selfie, get AI-generated improvement suggestions with a realistic before/after simulation, and share their transformation with a community that reacts and provides feedback.

The key differentiator: NXME shows **what would actually improve your look** and visualizes it, rather than applying generic filters or giving a meaningless score.

## What NXME Is Not

- Not a beauty score/rating app (no "you are a 7/10")
- Not a Snapchat-style beauty filter (no skin smoothing, eye enlarging)
- Not an AI portrait generator (not Remini/Lensa)
- Not a dating profile optimizer (dating is a future feature, not the core)

## Core Concept

```
Upload selfie
  -> AI analyzes face (shape, symmetry, features)
  -> AI generates improvement suggestions
  -> AI generates realistic glow-up image (before/after)
  -> User posts transformation to feed
  -> Community reacts (comments, votes)
  -> User shares externally -> new users join
```

Every analysis result becomes shareable content. The app is a **content engine**, not a utility tool.

---

## Market Context

- AI beauty/styling apps: ~$1.2B (2024) -> projected $7.8B by 2033 (~36-41% CAGR)
- Virtual try-on market: projected $48B by 2030
- 350M+ people use dating apps (adjacent demand for looking better)
- Glow-up/transformation content is among the most viral categories on TikTok

### Competitive Landscape

| Category | Examples | Gap |
|----------|----------|-----|
| Face rating | Umax, LooksMax AI, FaceScore | Only give scores + generic advice, no visual simulation |
| Makeup AR | YouCam Makeup | Filters only, no real improvement suggestions |
| Hairstyle apps | HairApp, HairX AI | Single feature, no holistic approach |
| Virtual try-on | Google Doppl, FitRoom | Clothes only, no face/style analysis |
| AI portraits | Remini, Artisse AI | Generate photos, don't suggest improvements |

**The gap:** No single app combines face analysis + body/style analysis + realistic improvement simulation + social sharing in one product.

---

## Core Features (Current Implementation)

### 1. Glow-Up Analyzer (MVP core)
- Upload selfie -> AI analyzes face shape, symmetry, eyes, eyebrows, proportions
- Generates top improvement suggestions (hairstyle, eyebrow shape, clothing style, etc.)
- Generates realistic before/after image using identity-preserving AI generation
- Identity constraint: face structure never changes, only style elements (hair, eyebrows, lighting, clothing)

### 2. Social Feed
- Every glow-up result becomes a post (original + AI glow-up + suggestions)
- Feed shows trending glow-ups, biggest transformations, new posts
- Comments, reactions (like, fire), voting

### 3. Shareable Glow-Up Card
- Auto-generated shareable image: "Before | After" with AI suggestions
- Optimized for TikTok, Instagram, Reddit sharing
- Includes subtle NXME branding for organic acquisition

### 4. AI Advisor (Ada)
- Personal style and self-improvement advisor (she/her persona)
- Context-aware conversations with memory system
- Nudge system for proactive engagement (post-analysis, milestone-based)

---

## AI Pipeline

```
Selfie
  -> Face detection (MediaPipe FaceMesh — 468 3D landmarks)
  -> Feature extraction (proportions, symmetry, angles, ratios)
  -> Face shape classification (oval, round, square, heart, oblong)
  -> NSFW screening (AWS Rekognition)
  -> Recommendation engine (rule-based + LLM for natural language suggestions)
  -> Image generation (fal.ai Flux PuLID — identity-preserving, ~$0.035/image)
  -> ArcFace identity verification (post-generation check)
  -> Before/After result
```

### Key Technical Decisions
- **Primary model:** Flux PuLID (`fal-ai/flux-pulid`, id_weight=0.85) — preserves identity while editing style
- **Fallbacks:** Flux Dev img2img + IP-Adapter -> InstantID (SDXL) — only on model failure
- **Identity preservation:** 3 layers — model conditioning (id_weight) -> ArcFace post-check -> prompt guidance
- **No beauty filters:** Never smooth skin, remove freckles, or retouch. Styling changes only.
- **Keyword allowlist:** Blocks skin-modification terms ("clear skin", "reduced blemishes", etc.)

---

## Growth Strategy

### Viral Loop
```
User uploads selfie
  -> AI generates glow-up
  -> Before/After post created
  -> User shares to TikTok/Instagram/Reddit
  -> Friends see it, try the app
  -> They create their own glow-ups
  -> Cycle repeats
```

### Psychological Drivers
1. **Curiosity** — "How good could I look?"
2. **Social validation** — "Do people think this looks better?"
3. **Comparison** — Before/After is inherently engaging
4. **Self-improvement** — Aspirational, not judgmental

### Key Growth Metric
- K-factor (viral coefficient) = invites x conversion. Target: K > 1 for organic exponential growth.

### Content Format Priorities
1. **Glow-Up** — before/after transformation (highest virality)
2. **Style Battle** — "Which look is better? A vs B" (community voting)
3. **Progress Timeline** — day 1 / day 30 / day 90 (retention)

---

## Monetization

**Freemium model (credit-based):**

| Tier | What you get |
|------|-------------|
| Trial | 2 free analyses |
| Credit Holder | Buy credit packs ($) for more generations |
| Premium | Subscription with higher limits |

Credit packs via Stripe (10/25/50 credits). Price per generation: ~$0.035 cost.

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Mobile | React Native (Expo) |
| Backend | Python, FastAPI |
| Database | PostgreSQL (Supabase) |
| Queue | Redis + ARQ |
| AI Generation | fal.ai (Flux PuLID) |
| Face Analysis | MediaPipe FaceMesh |
| Identity Check | ArcFace (insightface) |
| NSFW Screening | AWS Rekognition |
| LLM (Advisor) | Claude (Anthropic) |
| Payments | Stripe |
| Storage | Supabase Storage |
| Card Web | Next.js (shareable card pages) |

---

## Future Features (Not Yet Built)

### Phase: Advanced AI
- **Hairstyle simulator** — virtual haircut preview based on face shape
- **AI Makeup Mapping** — exact guideline overlays on face (eyebrow start/arch/end, contour placement, blush zones, eyeliner angle). Functions as a smart makeup mirror. Especially valuable for daily makeup users.
- **Outfit analyzer** — snap outfit photo, AI says what fits and what doesn't based on body type
- **Body type analysis** — detect body proportions, recommend clothing cuts and colors

### Phase: Virtual Try-On
- Try different hairstyles, glasses, clothing on your photo
- Style simulation without changing identity

### Phase: Social Expansion
- **Glow-Up Battle** — community votes on "Which look is better?"
- **Glow-Up Timeline** — track visual progress over months (day 1 / 30 / 90)
- **Trending feed** — most improved, best transformations
- **"Future You" mode** — AI generates how you'd look with a different overall style (classy, street, business, etc.)

### Phase: Smart Mirror (AR)
- Real-time camera mode with AI overlay
- Live eyebrow guidelines, contour placement
- "Before leaving the house" daily style check

### Phase: Dating Profile Optimizer
- Upload 3-5 photos, AI picks best one
- Generate improved dating profile photos
- Community votes on best profile photo

### Phase: Commerce
- Affiliate links to clothing/cosmetics from AI recommendations
- Brand partnerships
- Personalized product suggestions based on analysis

---

## Product Principles

1. **Content engine, not utility** — every result must be a post. "AI tool" apps die; "AI content" apps grow.
2. **Improvement, not judgment** — show "how you could look better", never "you are a 6/10". No beauty scores.
3. **Identity preservation** — the glow-up must look like the same person. If identity drifts, trust is destroyed.
4. **Subtle changes only** — hair, eyebrows, lighting, style. Never change face structure or bone structure.
5. **Social from day one** — growth requires sharing. Every feature should create shareable content.
6. **Not a beauty filter** — NXME is positioned as self-improvement, not photo editing.
