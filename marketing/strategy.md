# NXME Pre-Launch Marketing Strategy — 90-day warmup

*Version: 1.0 · Date: 2026-04-16*

This is the active strategic plan for NXME's pre-launch warmup. It answers
*"what are we doing, why, and how will we know it's working?"* and stays
short enough to re-read weekly. Tactical playbooks live in
`./marketing/skills/` and are invoked by this plan.

---

## Phase & constraints

| Dimension | Value | Source of truth |
|---|---|---|
| Phase | **Pre-launch warmup** | Product not in App Store yet |
| Runway | **1–3 months** to public launch | |
| Team | **Solo operator** | |
| Budget | **<$500/mo** (≈$1,500 over 90 days) | |
| On-camera capacity | **None — faceless / screen-rec only** | |
| Product readiness | MVP complete. Beta-ready target: Day 60 (Jun 15). Risk D in §8 owns slippage. | |

Positioning and audience baseline lives in
[`product-marketing-context.md`](./product-marketing-context.md). Read that
first; this doc builds on it.

---

## 1 · Positioning wedge

**Anti-LooksMax, engineer-authored.** NXME is the science-backed glow-up
brand from the team that measures 468 facial landmarks and classifies face
shape with ML — not the vibes crowd that rates your jaw on a 10-point scale
and calls it a day.

This wedge pairs naturally with faceless content: the brand voice is
**technical + warm**, not **personality + charisma**, so we ship without a
founder face. It captures demand leaking from LooksMax discourse users are
tired of without alienating the broader glow-up audience.

### Verbatim-backed messaging angles

Research pass (2026-04-16) documented ~120 verbatim quotes from App Store
reviews, the looksmaxxing forum, and TikTok comment snippets. Full
synthesis in [`./research/README.md`](./research/README.md). Each angle
below is a direct answer to a ranked category pain.

| # | Angle | Pain answered (freq rank) | Candidate line |
|---|---|---|---|
| 1 | No dark patterns | Pricing deception (#1 — 22 quotes, 9 apps) | *"See your result free. No trial ambush."* |
| 2 | Determinism | AI inconsistency (#2) | *"Same photo. Same answer. Every time."* |
| 3 | Identity preservation | Identity drift / whitewashing (#3) | *"Your face, upgraded — not replaced."* |
| 4 | Explainability | Missing reasoning (#4 — Qoves's praise pattern) | *"We show our work. 468 landmarks, all labeled."* |
| 5 | Privacy | FaceApp-shaped fear (#5) | *"Your selfie never trains a model."* |
| 6 | Face-shape answer | Confusion (#6 — TikTok-specific) | *"Not another face-shape guess."* |
| 7 | Aspirational floor | Self-doubt (#7) | Softer mainstream variant; harder angle only inside LooksMax-critique context |
| 8 | Believable result | Fake/plastic output (#8) | *"The person in the after photo is still you."* |

Use phrases: *science-backed*, *468 landmarks*, *measurements*, *show my
work*, *without changing my face*, *detailed*, *structure*, *depth*, *your
best look*, *identity-preserving*.

Avoid: *score*, *rating*, *beautify*, *filter*, *Chad/Stacy*, *halo/fail*,
*free trial* (poisoned by competitors — prefer *free result*), *AI
portraits*, *AI avatars*, *magic*.

Full language inventory in
[`./product-marketing-context.md`](./product-marketing-context.md).

---

## 2 · Channels

Prioritized. Every tier below is a real commitment, not a wish.

1. **TikTok — primary.** 2 posts/day, 7 days/week. Fed by the existing
   autoresearch loop in `tools/tiktok-autoresearch/`. Every asset we make
   starts here.
2. **Instagram Reels + YouTube Shorts — free cross-post.** Same asset,
   reposted same day. No native content creation. Buffer or Later
   scheduled. Target: 30 seconds of extra work per asset.
3. **Reddit — weekly presence.** r/glowups, r/MakeupAddiction,
   r/femalefashionadvice, r/malefashionadvice, r/SkincareAddiction. **Contribute for 3 weeks before mentioning NXME once.** When we do post,
   lead with data ("I built an AI that analyzes 468 facial landmarks — here's
   what it says are the most common face shape misclassifications"). Never
   promote in a comment; always earn it with the post itself.

**Deprioritized this phase:** Twitter/X, LinkedIn, Pinterest, Facebook. Not
a priority fit. Revisit post-launch if a specific thesis emerges.

---

## 3 · Content formats (faceless-native)

Four formats, rotated. Each one is filmable in ≤30 minutes by a solo
operator with no one on camera.

| Format | Description | Pillar |
|---|---|---|
| **Screen-rec walkthroughs** | NXME analyzing a stock / consented face, text overlay of what it sees | Education |
| **Face-shape explainers** | MediaPipe landmark visualizations + motion-graphics overlays + voiceover | Education |
| **LooksMax reactions** | Stitch / duet TikTok face-rating content; caption-overlay debunks | Trend |
| **Transformation reels** | User-submitted (with consent) before/afters with text narration | Transformation |

**Content pillar rebalance** (vs. the original
`tools/tiktok-autoresearch/strategy.md` split of 40/30/20/10):

| Pillar | Old | New | Why the change |
|---|---|---|---|
| Education | 40% | **55%** | Faceless-native, strongest wedge carrier |
| Transformation | 30% | **20%** | Gated on real users — ramps post-beta |
| Trend (stitch/duet) | 20% | **25%** | High algorithmic lift with zero on-camera time |
| Behind-the-scenes / BIP | 10% | **0%** | Dropped this phase |

Source tooling: CapCut Pro for editing, ElevenLabs for voiceover, stock
footage from Pexels or a single paid Envato month near launch.

---

## 4 · Funnel

TikTok bio → single linktree → single landing page.

The landing page is one page and does three things:
1. Explains NXME in one sentence + before/after hero animation.
2. Waitlist email capture above the fold.
3. Sample analysis gallery below the fold — 4–6 curated example results (founder's own face + consented volunteers; *no* stock photos — consent + realness is the proof).

One CTA per post: *"join waitlist — see yours first."* No competing asks.
Instagram and YouTube bios follow the same pattern.

Post-launch, the landing page swaps the waitlist CTA for an App Store link;
same page, same metric.

---

## 5 · Autoresearch loop — adjustments

`tools/tiktok-autoresearch/` is already built and is our content-volume
engine. Three changes for this phase:

1. **Add scoring dimension `faceless-feasibility` (2 pts)** to every rubric
   in `strategy.md`. Kill hooks that require a founder on camera before
   they burn iteration budget.
2. **Rewrite the hooks prompt** to bias toward text-first, stat-first, and
   question-first formats. Drop "POV" and "me when" archetypes.
3. **Retire the build-in-public content type.** It's out of scope this
   phase.

Update `tools/tiktok-autoresearch/strategy.md` to reflect the new pillar
split (55 / 20 / 25 / 0) before running the next batch.

---

## 6 · Metrics + weekly cadence

**North-star:** waitlist size at Day 90.

**Leading indicators, measured weekly:**
- Median views per post (outlier-robust — ignore the one banger)
- TikTok net-new followers
- Bio-link click-through rate (Linktree or equivalent, % of profile visits)
- Waitlist conversions / bio-link click (%)
- Top 3 hook archetypes driving reach (feed back into autoresearch)

**Sunday 1-hour weekly review:**
1. Pull the five leading indicators.
2. Identify this week's top post + lowest post. What drove each.
3. Update `tools/tiktok-autoresearch/strategy.md` with any learned
   constraint.
4. Queue next week's content outline (not scripts — outline only; the
   autoresearch loop writes the scripts).
5. Log it in `marketing/weekly-review.md` (append-only — reuse format once
   created).

---

## 7 · Budget — $1,500 over 90 days

| Line item | Monthly | 90-day | Rationale |
|---|---|---|---|
| TikTok post boosts | $200 | $600 | Only boost confirmed organic winners. $20–50 per boost, max 4/mo. No cold ads. |
| Tool stack | $150 | $450 | CapCut Pro, ElevenLabs, Envato (1 month near launch), scheduler |
| Reddit + community | $100 | $300 | Mostly covered by free tiers; flex for tools we don't anticipate |
| Experiments buffer | $50 | $150 | Unallocated; release monthly or forfeit |
| **Total** | **$500** | **$1,500** | |

Budget triggers: if median post views double in any 14-day window,
reallocate $100/mo from buffer → boosts. If they flatline for 30 days,
trigger the contingency in section 8.

---

## 8 · Risks + contingencies

| Risk | Likelihood | Trigger | Contingency |
|---|---|---|---|
| **A. TikTok algorithm kills reach** | Medium | Median views down >50% for 14 days across pillars | Double Reddit cadence; pause boosts; start weekly long-form YouTube |
| **B. Faceless content plateaus** | Medium | Median views flat for 30 days despite autoresearch iteration | Hire a $200–500/mo creator-face at week 6; keep founder-faceless |
| **C. Waitlist conversion <5% of bio clicks** | High (default) | Week 4 review | Run `page-cro` skill against the landing page; iterate copy and hero image |
| **D. Beta not ready by Day 60** | Medium | Product status at D60 milestone | Extend warmup by 30 days, spin up Option B (free face-shape tool) as bridge to keep email capture alive |
| **E. Negative brand association from LooksMax subculture** | Low–medium | Reddit / TikTok comment volume of hostile framing | Reframe: lean harder into "glow-up" positioning, de-emphasize "anti-LooksMax" language, add explicit inclusivity lines to bio and landing page |

Read this list at every weekly review. Any trigger hit → escalate to a
separate working doc before the next review.

---

## 9 · 90-day plan

### Weeks 1–2 · Foundation (Apr 16 – Apr 29)
- Validate and amend `product-marketing-context.md` with verbatim TikTok /
  Reddit comment mining (`customer-research` skill).
- Update `tools/tiktok-autoresearch/strategy.md` with new pillar split,
  faceless-feasibility score, and retired content types.
- Ship the waitlist landing page (one page, the three things in §4).
- Publish first 14 posts — bias toward Education pillar to establish voice.
- First Sunday review: baseline metrics recorded.

### Weeks 3–4 · Volume ramp (Apr 30 – May 13)
- Sustain 2 posts/day. Cross-post to IG Reels + YT Shorts same day.
- Start Reddit presence: contribute to top subreddits, no NXME mention yet.
- End-of-week-4 review: if waitlist conversion <5%, trigger contingency C.

### Weeks 5–8 · Double-down (May 14 – Jun 10)
- Identify top 3 hook archetypes and top 2 content formats. Autoresearch
  loop biases toward them.
- Boost the two top-performing organic posts of the month ($20–50 each). "Top-performing" = highest view count in the first 48 hours post-upload, gated by an engagement rate ≥5% (likes + comments + saves ÷ views).
- Reddit: first NXME-associated post after 3 weeks of contribution. Must
  lead with data, never a promo.
- If the product hits beta in this window, open up transformation pillar
  content with consenting beta users.

### Weeks 9–12 · Launch prep (Jun 11 – Jul 8)
- Invoke the `launch-strategy` skill for Product Hunt prep, launch-day
  orchestration, press list, and email-sequence design.
- `aso-audit` skill: finalize App Store / Play listing keywords and
  screenshots.
- Build the waitlist email sequence (`email-sequence` skill): pre-launch
  teaser → launch day → post-launch conversion.
- Final review on Day 90: decide launch date.

---

## 10 · Out of scope (explicitly)

These are good ideas we are **not** doing this phase:
- Free browser face-shape tool (Option B — revisit at Day 60 if needed)
- Creator seeding program (Option C — revisit post-launch)
- Paid acquisition beyond post-boosts
- Twitter / X build-in-public
- LinkedIn / Pinterest / Facebook
- Press outreach before Week 9
- SEO long-tail landing pages (no build capacity as solo operator)

If one of these starts pulling attention, check it against this list and
the risk triggers before shifting scope.

---

## Appendix · Skill → step mapping

Every section above maps to one or more skills in `./marketing/skills/`.
Full catalog in `./marketing/README.md`; condensed here:

| Section | Skill to invoke |
|---|---|
| 1 Positioning | `product-marketing-context`, `competitor-alternatives` |
| 2 Channels | `social-content`, `community-marketing` |
| 3 Content formats | `content-strategy`, `social-content`, `marketing-psychology` |
| 4 Funnel | `copywriting`, `lead-magnets` |
| 5 Autoresearch updates | `marketing-psychology`, `marketing-ideas` |
| 6 Metrics | *(no skill — manual weekly review)* |
| 7 Budget | *(no skill — manual tracking)* |
| 8 Risks | `page-cro` (contingency C only) |
| 9 Week 9–12 launch | `launch-strategy`, `aso-audit`, `email-sequence` |
| Ongoing | `customer-research` (language mining) |
