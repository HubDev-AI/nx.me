# NXME Marketing

Home for all marketing strategy, context, and agent skills. Everything an
agent (or a human) needs to plan, write, and ship marketing for NXME lives
here or is linked from here.

## What's in this folder

| Path | Purpose |
|---|---|
| `product-marketing-context.md` | **Read first.** Foundational positioning doc. Every skill below reads this before working. Seeded from `docs/VISION.md` + `tools/tiktok-autoresearch/strategy.md`. |
| `skills/` | Curated subset of marketing agent skills (MIT, Corey Haines). 19 skills picked for NXME's current phase. |
| `strategy.md` | Current strategic plan (pre-launch warmup, solo, <$500/mo, 1–3 mo runway). |
| `LICENSE-marketingskills.md` | Attribution + MIT license for the copied skills. |

`.agents/product-marketing-context.md` is a symlink to the context doc above,
so skills that hard-code the `.agents/` path find it automatically.

---

## When to use which skill

NXME is mid pre-launch warmup: solo operator, <$500/mo, public launch 1–3
months out, TikTok is the established wedge (see
`tools/tiktok-autoresearch/`). The 19 skills in `./skills/` are triaged into
three tiers by what matters *now* vs *soon*.

### Tier 1 — use now (pre-launch warmup, next 30–60 days)

| Skill | Use it to |
|---|---|
| [product-marketing-context](skills/product-marketing-context/SKILL.md) | Maintain the positioning doc every other skill reads. Revisit weekly as we learn. |
| [marketing-psychology](skills/marketing-psychology/SKILL.md) | Build mental models for hooks, curiosity gaps, identity-relevance. Primary tool for improving TikTok hook scores in `tools/tiktok-autoresearch/`. |
| [social-content](skills/social-content/SKILL.md) | Plan and draft TikTok / IG Reels / YT Shorts content. Pairs with the autoresearch loop. |
| [content-strategy](skills/content-strategy/SKILL.md) | Own the editorial calendar across pillars (Education 40 / Transformation 30 / Trend 20 / BTS 10). |
| [copywriting](skills/copywriting/SKILL.md) | Landing page, App Store, email subject lines, TikTok captions. |
| [competitor-alternatives](skills/competitor-alternatives/SKILL.md) | Positioning vs Umax, LooksMax, YouCam, Lensa, Remini. Drafts alternative-to pages (huge SEO value pre-launch). |
| [aso-audit](skills/aso-audit/SKILL.md) | Prep App Store / Google Play listing *before* launch. Keyword research, screenshot plan, metadata. |
| [lead-magnets](skills/lead-magnets/SKILL.md) | Design waitlist magnet (free analysis at launch? face-shape guide PDF? glow-up starter kit?). |
| [free-tool-strategy](skills/free-tool-strategy/SKILL.md) | Evaluate if NXME itself, or a stripped free tool (e.g., browser-based face-shape quiz), can be top-of-funnel. |
| [marketing-ideas](skills/marketing-ideas/SKILL.md) | Divergent idea generator when we're stuck. Use once a month, not more. |
| [customer-research](skills/customer-research/SKILL.md) | Mine TikTok/Reddit comments for verbatim language. Fuel captions, landing copy, objection-handling. |
| [cold-email](skills/cold-email/SKILL.md) | Creator outreach (micro-influencer seeding), beauty press, TikTok-niche newsletter writers. |
| [community-marketing](skills/community-marketing/SKILL.md) | Reddit plays: r/femalefashionadvice, r/malefashionadvice, r/glowups, r/MUAontheCheap, r/SkincareAddiction. Discord for glow-up creators. |

### Tier 2 — use soon (launch window, peri-launch, 30–90 days out)

| Skill | When to reach for it |
|---|---|
| [launch-strategy](skills/launch-strategy/SKILL.md) | 4–6 weeks before public launch. Product Hunt prep, launch-day orchestration, creator go-live choreography. |
| [email-sequence](skills/email-sequence/SKILL.md) | Waitlist nurture (weekly teaser → launch day → post-launch conversion). |
| [referral-program](skills/referral-program/SKILL.md) | Invite mechanic for the K-factor viral loop (extra credits per invite, leaderboard, etc.). |
| [paid-ads](skills/paid-ads/SKILL.md) | Once $500/mo unlocks budget: small-scale TikTok/Meta creative tests post-launch. |
| [ad-creative](skills/ad-creative/SKILL.md) | Generating paid/boosted creative variations from winning organic TikToks. |

### Tier 3 — use only when you have traffic / revenue

These skills live in the marketingskills plugin but **were not copied here**
because they presume running campaigns or paying users. Pull them in when
you hit that phase:

ab-test-setup · analytics-tracking · churn-prevention · form-cro ·
onboarding-cro · page-cro · paywall-upgrade-cro · popup-cro ·
pricing-strategy · programmatic-seo · revops · sales-enablement ·
schema-markup · seo-audit · signup-flow-cro · site-architecture · ai-seo ·
copy-editing

Install source:
`~/.claude/plugins/marketplaces/marketingskills/skills/`.

---

## Recommended sequence (first 30 days)

1. **Week 1** — Read `product-marketing-context.md`. Validate and amend.
   Run `customer-research` against TikTok/Reddit to collect verbatim
   language. Update the context doc.
2. **Week 1–2** — Run `content-strategy` to lock the 30-day editorial
   calendar across the four pillars. Wire it into
   `tools/tiktok-autoresearch/strategy.md`.
3. **Week 2** — `competitor-alternatives` for Umax, LooksMax, Lensa. These
   become pre-launch SEO landing pages ("NXME vs Umax") and TikTok scripts.
4. **Week 2–3** — `lead-magnets` + `free-tool-strategy`: decide the
   waitlist magnet (face-shape quiz web tool is the strong candidate) and
   build it.
5. **Week 3** — `aso-audit` dry-run with mock listing; reserve the App
   Store/Play name; queue screenshots and metadata for launch.
6. **Week 3–4** — `community-marketing` + `cold-email`: seed 5–10
   micro-creators with early access, start Reddit rep-building (contribute,
   don't promote).
7. **Ongoing** — Autoresearch loop generates 50–100 hooks/week.
   `marketing-psychology` + `social-content` improve the scoring rubric.

---

## Conventions

- **Do not write strategy directly in `SKILL.md` files.** They are
  frameworks. Outputs go in `strategy.md`, campaign briefs, or per-asset
  docs under `./marketing/`.
- **Update `product-marketing-context.md` whenever we learn something.**
  All skills pick up the change automatically.
- **Canonical paths:** docs live in `./marketing/`, context has a
  `.agents/` symlink for skill autodiscovery.
- **Skill attribution:** see `LICENSE-marketingskills.md`. MIT. Please keep
  it in the repo.

---

## Related

- [docs/VISION.md](../docs/VISION.md) — product vision, viral loop, growth
  psychology, market context
- [tools/tiktok-autoresearch/](../tools/tiktok-autoresearch/) — autonomous
  content generation loop (Karpathy-style) for TikTok hooks, captions,
  trends, competitors, calendar
- [card-web/](../card-web/) — Next.js surface for the shareable before/after
  card; every generated card is a potential marketing asset
- [brand/](../brand/) — icons and identity assets
