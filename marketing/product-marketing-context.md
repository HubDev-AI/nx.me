# Product Marketing Context — NXME

*Last updated: 2026-04-16*

> Foundational marketing context. Every skill in `./marketing/skills/` reads
> this first so we don't repeat product, audience, and positioning
> information. Source of truth seeded from `docs/VISION.md` and
> `tools/tiktok-autoresearch/strategy.md`.

## Product Overview

**One-liner:** See the best version of yourself — AI glow-up social platform that shows you what would actually look better, not a filter, not a score.

**What it does:** Upload a selfie. We analyze your face with 468 landmarks and ML face-shape classification. You get personalized style recommendations (hair, eyebrows, grooming, makeup, accessories) plus a realistic AI-generated before/after that preserves your identity. Every result is a shareable social card.

**Product category:** AI glow-up / personal style analyzer. Positioned against (a) face-rating apps (Umax, LooksMax AI), (b) beauty filters (YouCam, Snapchat), (c) AI portrait generators (Lensa, Remini), (d) single-feature styling apps (HairApp, HairX).

**Product type:** Consumer mobile app — iOS and Android (React Native / Expo). Shareable card web surface (Next.js). Social content engine, not a utility.

**Business model:** Freemium + credit packs.
- Trial: 2 free analyses
- Credit packs: 10 / 25 / 50 credits via Stripe (~$0.035 AI cost per generation)
- Premium subscription: higher limits

---

## Target Audience

**Age:** 16–35
**Gender:** All (female-skew ~65/35; male glow-up is a growing niche)
**Geography:** United States primary, English-speaking markets
**Platforms they live on:** TikTok, Instagram, YouTube Shorts, Reddit (r/femalefashionadvice, r/malefashionadvice, r/glowups, r/looksmaxxing)

**Primary use case:** "I want to glow up but I don't know what would actually look good on me, and I don't trust apps that rate my face or filter me into a different person."

**Jobs to be done:**
1. Show me how to actually look better — not rate me, not retouch me.
2. Make before/after content I can post (shareable transformation, not a selfie).
3. Help me understand my face scientifically (bone structure, shape, proportions).

**Psychographic profile:** Curious about their appearance. Want to look their best but don't know where to start. Love before/after content. Respond to "find your personal style" messaging. Suspicious of beauty scores. Consume glow-up TikTok daily.

---

## Personas

Consumer B2C — no formal buyer personas. Two user archetypes:

| Archetype | Cares about | Frustration | What we promise |
|---|---|---|---|
| Glow-up curious (16–22, ~70% of audience) | Figuring out their "look", TikTok-worthy transformations | Random advice from creators, wasted money on haircuts that didn't suit them | Science-backed recs + see the result before you commit |
| Style optimizer (23–35, ~30% of audience) | Putting their best face forward (dating, career, confidence), daily style | Mirror fatigue, decision paralysis, fake-looking filters | Identity-preserving AI that looks like them, just styled better |

**Anti-persona:** Anyone looking for photo retouching / beautification; anyone who already has their style locked; dating-app-specific optimization (that's a future feature, not the core today).

---

## Problems & Pain Points

**Core problem:** "I want to glow up but I don't know what would look good on me."

**Why alternatives fall short:**
- Face-rating apps (Umax, LooksMax, FaceScore) give a score and generic tips. No visualization. Users describe them as "demoralizing" or "manosphere brain rot."
- Beauty filters (Snap, YouCam) make everyone look the same. Doesn't translate to real life.
- Hair-only apps (HairApp, HairX) don't analyze face shape holistically.
- AI portrait apps (Lensa, Remini, Artisse) don't suggest — they just generate something pretty. Often identity drifts.
- TikTok face-shape creators — inaccurate, opinion-based, not data-driven.

**What it costs them:**
- Wasted money on wrong haircuts, makeup, and clothes
- Decision paralysis → nothing changes
- Comparison anxiety from TikTok glow-up content
- Feeling "my face isn't working for me" with no path forward

**Emotional tension:** shame around "not looking good enough," fear of trying new styles and failing in public, suspicion that AI apps make you look weird or fake.

---

## Competitive Landscape

**Direct (same problem, similar solution):**
- **Umax / LooksMax AI / FaceScore** — score-first, no visualization, no actionable recs. We show the result.
- **Face-shape TikTok creators** — manual, inconsistent, opinion-based. We use 468-landmark ML.

**Secondary (same problem, different approach):**
- **YouCam / Perfect Corp** — AR virtual try-on for makeup. No analysis, no face-shape logic, no shareable output.
- **HairApp / HairX AI** — single feature (hair). No holistic face/style integration.

**Indirect (different problem, competes for attention):**
- **Lensa / Remini / Artisse AI** — AI portraits. Don't analyze or suggest; they generate pretty pictures. Identity often drifts.
- **FaceApp** — age/gender/hair swaps. Fun but shallow. No styling logic.

**How each falls short:** Every one of them produces either (a) an unhelpful score, (b) a generic filter, or (c) a "pretty" image that doesn't look like the user. None give *actionable, identity-preserving, shareable* recommendations.

---

## Differentiation

**Key differentiators:**
1. **468-landmark face analysis** + ML face-shape classification — not vibes, not self-reported.
2. **Identity-preserving generation** — Flux PuLID (id_weight=0.85) + ArcFace post-check. Output looks unmistakably like the user.
3. **Never a beauty filter** — keyword allowlist blocks skin-smoothing, freckle removal, retouching. Styling changes only (hair, eyebrows, lighting, accessories).
4. **Shareable card auto-generated** — every analysis produces a TikTok/IG-ready before/after card. Viral loop baked into the product.
5. **AI Advisor (Ada)** — personalized ongoing style guidance with memory, not a one-shot analysis.

**Why that's better:** Users get real recommendations they can actually use, visualized on their actual face, formatted for sharing — in one flow. Competitors give you one of those, never all four.

**Why customers choose us:**
- Umax user: "finally, something that shows me what to do, not just a number"
- Filter user: "the person in the after photo is still me"
- Lensa user: "it tells me what changed and why it works for my face shape"

---

## Objections

| Objection | Response |
|---|---|
| "This is just another beauty filter." | We analyze bone structure with 468 landmarks. We never retouch skin, remove freckles, or smooth features. Show a side-by-side where identity is unmistakable. |
| "AI apps just make you look weird." | Identity preservation is our #1 rule. ArcFace verifies every output is you. |
| "Why upload my face to another app?" | Your selfie is used only for your analysis. We do not train on user faces. |
| "I don't want to be told I need to change." | NXME is aspirational, not judgmental. We never give you a score. We show you *your* best style options and you choose. |
| "AI-generated content is slop." | The AI proposes, you judge. Every generation ships with the analytical reasoning (face shape + why each rec) so it's not a black box. |

---

## Switching Dynamics — JTBD Four Forces

**Push (frustrations driving them away from the status quo):**
- Wasted money on a bad haircut.
- Got a "looksmax score" that tanked their mood.
- Took a TikTok face-shape quiz that contradicted itself.
- Tired of beauty filters that only work on camera.

**Pull (what attracts them to NXME):**
- See the glow-up before committing IRL.
- Science-backed, not random AI slop.
- Shareable before/after card — makes it social, not clinical.
- "Find my best style" framing, not "rate my face."

**Habit (what keeps them stuck):**
- Doomscrolling beauty TikTok without acting.
- Taking random face-shape quizzes.
- Asking friends "does this look good?"

**Anxiety (what worries them about switching):**
- "What if the AI makes me look weird/worse?"
- "Is my selfie private?"
- "Will my friends see I used this?"
- "Is this pseudoscience like the other face-rating apps?"

---

## Customer Language

**How they describe the problem (verbatim, collected from TikTok/Reddit — to be validated with user research):**
- "I don't know what hairstyle works for my face shape"
- "what would I look like with ___"
- "how do I glow up"
- "is my face shape heart or oval"
- "i need a makeover but don't know where to start"
- "why does everyone else's hair look good and mine doesn't"

**How they describe us (pre-launch — target phrasing):**
- "it's like a glow-up advisor that actually shows you the result"
- "it tells you what to change and why"
- "not a rating app, a suggestion app"

**Words to use:** glow-up, bone structure, face shape, your best look, see yourself, personal style, transformation, before/after, styling, natural, identity-preserving, recommendations.

**Words to avoid:** beauty score, attractive, ugly, rating, 7/10, 9/10, Chad/Stacy, halo/fail (LooksMax discourse), beautify, perfect, flawless, filter, retouch, smooth skin, enhance.

**Glossary:**
| Term | Meaning |
|---|---|
| Glow-up | Intentional self-improvement transformation |
| Face shape | ML-classified bone structure (oval, round, square, heart, oblong) |
| Before/After | Shareable image pair: original vs AI-suggested styled version |
| Landmark | One of 468 MediaPipe facial points used for measurement |
| Identity preservation | Output looks unmistakably like the same person (ArcFace-verified) |
| Ada | Our AI style advisor persona, female, context-aware memory |

---

## Brand Voice

**Tone:** Confident but not arrogant. Playful, energetic. Curiosity-driven (lead with questions, not answers). Inclusive ("all face shapes are beautiful; we help you find YOUR best style"). Never clinical or medical.

**Style:** Direct. TikTok-native. Short sentences. Not corporate. No jargon unless we own the word (face shape, landmarks, glow-up).

**Personality (5 adjectives):** scientific · empowering · authentic · fun · aspirational.

---

## Proof Points

**Technical metrics (usable pre-launch):**
- 468 facial landmarks analyzed per selfie (MediaPipe FaceMesh)
- Identity retention verified with ArcFace on every generation
- Flux PuLID id_weight=0.85 — industry-leading identity preservation
- Never retouches skin (keyword allowlist enforced server-side)

**Future proof (to collect during warmup):**
- Creator testimonials (first 10–25 seeded users)
- Glow-up gallery (before/after compilation reel)
- Press mentions (Product Hunt, TechCrunch, beauty-tech press if we earn it)
- Waitlist size at launch

**Value themes:**
| Theme | Proof |
|---|---|
| Real recommendations, not just a score | 468 landmarks + face-shape ML |
| Look like yourself, just better | Flux PuLID + ArcFace identity check |
| Share-worthy by default | Auto-generated before/after card |

---

## Goals

**Primary business goal (pre-launch, next 90 days):** Build an engaged audience we can convert to users on launch day. Concretely: waitlist sign-ups + TikTok/IG follower base.

**Conversion action (pre-launch):** Join waitlist. Secondary: follow on TikTok/Instagram.

**Key growth metric:** K-factor (invites × conversion) — product is designed for K > 1 via the shareable card viral loop.

**Current metrics:** Pre-launch warmup. No public users. Content generation automated via `tools/tiktok-autoresearch/`. Waitlist infrastructure TBD.

---

## References

- `docs/VISION.md` — product vision, viral loop, growth strategy
- `tools/tiktok-autoresearch/strategy.md` — TikTok content pillars, tone, scoring
- `app/features/README.md` — feature flag / capability layer
- `mobile/AGENTS.md` — mobile UI conventions
