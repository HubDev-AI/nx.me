---
status: complete
created: 2026-03-13T12:33:47.000Z
feature: nxme
pausedStep: null
---

# Brief: NXME

## Problem

People face a daily, personal struggle with appearance uncertainty — standing in front of a mirror every morning wondering whether their eyebrows are shaped correctly for their face, which clothes suit their body type, or how a different hairstyle might look. The advice they get is generic (TikTok tutorials, fashion rules-of-thumb) and not calibrated to their specific facial geometry or body proportions. Existing apps address only fragments of this problem: YouCam Makeup does AR filters, LooksMax AI gives face ratings, HairApp covers hairstyles — but none combine face analysis, personalized improvement suggestions, realistic visual simulation, and a social feedback layer in a single product. The result is a fragmented, frustrating experience for the millions of people who care deeply about their appearance and seek actionable, personalized guidance.

## Vision

NXME will be the first social platform where AI analysis and community feedback converge around one compelling idea: discovering your "next self." A user uploads a selfie, receives AI-powered improvement suggestions grounded in their facial geometry and proportions, sees a realistic before-and-after glow-up simulation that preserves their identity, and shares that transformation as social content that invites reactions, comments, and discussion. Over time, NXME evolves into a self-improvement network — a place people return to daily to track their style evolution, explore "Future You" looks, and engage with a community obsessed with personal growth. The core positioning is not an attractiveness rater but a **visual guide to personal improvement**: a product that shows what small, achievable changes can do.

## Users

- **Primary — Self-Improvement Enthusiast (16–35)**: Active on TikTok and Instagram, interested in beauty, fashion, dating, and self-improvement. Uploads selfies regularly, follows glow-up content, and wants personalized feedback they can act on. Pain: generic advice that doesn't account for their specific face or body type.
- **Secondary — Content Creator**: Uses before/after transformations as social content. Wants shareable AI-generated results that drive engagement. Pain: creating compelling transformation content is time-consuming without tools.
- **Secondary — Dating App User**: Wants to optimize their profile photos and understand which looks make the best impression. Pain: uncertain which photo or style presents them best.

## Success Metrics

- **MVP (Month 1–2)**: 10,000 registered users; 1,000 daily active users
- **Phase 2 (Month 3–4)**: 100,000 users with active social feed engagement
- **Phase 3 (Month 6)**: 1,000,000 users driven by viral share loop
- **Revenue**: Freemium; subscription target $5–10/month; comparable benchmark: Umax ~$500K/month from subscriptions
- **Viral K-factor**: Target K > 1 (each user brings ≥1 new user via share links / before-after cards)

## Scope

### In Scope (MVP)
- Selfie upload with face validation (single person, clearly visible face)
- AI face analysis: face shape classification, symmetry score, key features (eyes, eyebrows, hairline, proportions)
- Glow-up suggestions: Top 5 personalized improvements per user
- Before/after simulation: AI-generated image showing subtle improvements while preserving identity
- Post creation: publish glow-up result to in-app feed
- Social feed: trending transformations, newest posts, biggest improvements (fully free — no gate)
- Reactions and comments on posts (fully free — no gate)
- Shareable glow-up card: `nxme.ai/{username}` — standalone page with before/after + suggestions (fully free — no gate)
- User profile with transformation history
- Credits system: users purchase analysis packs or subscribe for unlimited access
- Free trial: 1–2 included analyses at signup

### In Scope (Post-MVP / Roadmap)
- Outfit analyzer: AI judgment on whether clothing suits the user's body type and proportions
- Future You mode: style evolution previews with different hairstyle, color, clothing styles
- AI Makeup Mapping: exact overlay guides on the face (eyebrow arch, contour placement, eyeliner angle)
- Glow-Up Timeline: month 1 / month 3 / month 6 progress tracking
- Glow-Up Battle: A vs B community voting between two looks
- Hairstyle and glasses virtual try-on
- **Style Categories**: after base glow-up, user explores 5 AI styles — Natural, Clean aesthetic, Korean, Professional, Casual. "1 selfie → 5 versions" multiplies shareable posts.
- Creator economy: style pack creators, premium style packs

### Out of Scope
- Face rating / attractiveness scoring (explicitly NOT a face rater — this is a positioning choice)
- Full 3D digital twin / avatar (technically complex, not needed for MVP value proposition)
- Real-time AR camera mode (Phase 3 — requires on-device model optimization)
- Direct e-commerce / affiliate clothing links (Phase 4 — requires brand partnerships)
- Clothing virtual try-on (Phase 3 — requires body detection and garment simulation)

## Constraints

- **Identity preservation**: AI may only modify hair, eyebrows, style, and lighting. It must NEVER alter bone structure, nose, jaw, or face shape. "Different person" results destroy trust and kill sharing. (Technical — LOCKED)
- **Glow-Up type = improvement simulator, not beauty filter**: NXME is type 3 of 3 glow-up app categories. Type 1 (beauty filter/skin blur/eye enlargement) looks fake and dies fast. Type 2 (AI portrait generator like Remini) is a photo product, not improvement guidance. Type 3 — showing what would *actually* improve your look with realistic, achievable changes — is the approach that builds trust and drives sharing. (Positioning — LOCKED)
- **Mobile-first**: App must work well on iOS and Android; face detection must be fast enough for a responsive UX. (Platform constraint)
- **AI generation cost**: Target ≤ $0.05 per glow-up image to keep unit economics viable at scale. (Business constraint)
- **Realism over perfection**: AI results will not be photorealistic at launch; the product must frame this as "style guidance" not "photo manipulation." (Trust/positioning constraint)
- **Social from day one**: The product must have a social feed and sharing from the first release — adding social features later to an analysis tool rarely works. (Growth constraint, LOCKED)
- **Not a rating app**: The app must never show an "attractiveness score" or rank users by looks. This is both a brand and ethical constraint. (LOCKED)

## Design Decisions

- **DD-1**: App name = **NXME**, domain = `nxme.ai`, meaning "Next Me" [LOCKED — domain acquired]
- **DD-2**: Social-first architecture from day one — every analysis result becomes a shareable post [LOCKED — core growth strategy]
- **DD-3**: Not a face rating app — positioned as "visual guide to personal improvement," tagline "See your next self" [LOCKED — brand/positioning]
- **DD-4**: Credits + subscription monetization — social layer (feed, reactions, comments, shareable cards) is fully free; face analysis + glow-up simulation requires credits (pay-per-use) or a subscription (unlimited); free trial includes 1–2 analyses to demonstrate value [LOCKED — business model]
- **DD-5**: Image generation approach — image-to-image diffusion (not text-to-image from scratch) to preserve identity [LOCKED — technical approach, validates realism requirement]
- **DD-6**: Mobile framework (React Native vs native iOS/Android) [DISCRETION — to be decided in Architecture]
- **DD-7**: Specific diffusion model and hosting (Stable Diffusion + ControlNet self-hosted vs API like Replicate/fal.ai) [DEFERRED — cost/quality tradeoff requires prototyping]
- **DD-8**: Backend framework and cloud provider [DISCRETION — Python/FastAPI/PostgreSQL + AWS/GCP suggested in conversation]
- **DD-9**: Authentication provider [DEFERRED]
- **DD-10**: Moderation strategy for social feed (NSFW, harmful content) [DEFERRED — requires legal/policy review]

## Additional Context

### Competitive Landscape (from conversation research)

| App | What it does | Gap |
|-----|-------------|-----|
| Umax | Face analysis + advice, ~$500K/month | No social layer, no visual simulation |
| LooksMax AI | Face rating + beauty score | Rating-only, no improvements shown |
| YouCam Makeup | AR makeup filters | Filters only, no analysis or suggestions |
| Remini | AI photo enhancement, 100M MAU | Enhancement only, no style guidance |
| HiFace | Face shape + hairstyle recs | No simulation, no social |
| HairApp | Hairstyle try-on | Hair only |
| Google Doppl | Virtual clothing try-on | Clothes only, no face analysis |
| Photofeeler | Photo rating by humans, 770K/month visits | Rating only, no AI transformation |

**The gap**: No app combines comprehensive face analysis + personalized improvement suggestions + realistic AI transformation simulation + social content layer in one product.

### AI Architecture (from conversation, for Architecture phase)

**Pipeline:**
```
Selfie → Face Detection → Landmark Extraction → Feature Analysis → Recommendation Engine → Image-to-Image Diffusion → Glow-Up Result
```

**Layers:**
1. **Face Detection**: MediaPipe Face Detection (mobile-optimized, real-time, free)
2. **Landmark Detection**: MediaPipe FaceMesh (468 3D landmarks — eyes, nose, jawline, eyebrow arc, lips)
3. **Feature Extraction**: Calculate face proportions, symmetry, angles, ratios from landmarks
4. **Face Classification**: oval / round / square / heart / oblong using distance ratios and jaw/forehead widths
5. **Face Identity Embedding**: ArcFace or FaceNet (preserve identity vector through generation)
6. **Recommendation Engine**: Rule-based system mapping face_shape → style recommendations (e.g., `if face_shape == round → recommend shorter sides haircut`)
7. **Image Generation**: image-to-image diffusion (Stable Diffusion + ControlNet); prompt example: `"same person, better hairstyle, clean skin, natural lighting, professional portrait"`

**Cost**: ~$0.01–$0.05 per generated image on cloud GPU.

**Biggest technical risk**: AI results looking fake or identity-changing ("uncanny valley"). Mitigation: subtle edits only (hair, eyebrows, color, style), limited transformation scope.

### Growth Mechanics (from conversation)

**Viral loop:**
```
Upload selfie → AI glow-up → Before/After → Post to feed → Comments/votes → Share → New users
```

**Shareable assets that drive acquisition:**
- Glow-up card: `nxme.ai/{username}` — standalone page with before/after + AI suggestions
- Glow-Up Battle: post two looks, community votes A vs B
- Progress timeline: Day 1 / Month 1 / Month 3 / Month 6 improvement cards

**Psychological drivers**: Self-improvement desire, curiosity ("how good could I look?"), social validation, before/after comparison engagement.

**Content distribution**: TikTok, Instagram Reels, Snapchat — "AI gave me a glow-up" content format is proven viral in this niche.

### Monetization Model

```
Free tier:     Full social layer — browse feed, react, comment, view/share glow-up cards
Free trial:    1–2 face analyses included at signup (to demonstrate value)
Credits:       Pay-per-use pack — e.g., 5 analyses for $4, 20 analyses for $12
Subscription:  Unlimited analyses + advanced transformations + premium styles ($5–10/month)
```

Gating principle: the social experience has zero cost — users can engage, discover, and share freely. The value gate is the personal analysis itself (face analysis + AI image generation). This separates the viral/social flywheel (free, frictionless) from the monetizable core action (generating your own glow-up).

Rationale for credits alongside subscription: a credit pack lowers the purchase commitment barrier for users who don't want a recurring subscription. Subscription is the preferred monetization path (higher LTV), but credits capture one-time buyers and converts some to subscribers.

### Product Roadmap (from conversation)

| Phase | Features | Goal |
|-------|----------|------|
| Phase 1 — MVP (Month 1–2) | Selfie upload, face analysis, glow-up suggestions, before/after image, post + feed + reactions, share card | 10k users |
| Phase 2 — Social (Month 3–4) | Profile history, glow-up timeline, battles, trending feed | 100k users |
| Phase 3 — Advanced AI (Month 5–6) | Hairstyle/makeup simulation, makeup mapping overlay, real-time AR | 1M users |
| Phase 4 — Commerce (Month 7+) | Outfit analysis, virtual try-on, affiliate clothing links | Revenue scale |
