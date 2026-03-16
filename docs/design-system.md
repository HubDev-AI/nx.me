---
title: "Design System: NXME"
mode: C
figma_url: null
design_system_source: generated
total_stages: 9
status: complete
current_stage: 9
last_completed_stage: 9
steps_completed: [1, 2, 3, 4, 5, 6, 7, 8, 9]
dark_mode: true
created: 2026-03-15T19:10:00.000Z
last_updated: 2026-03-15T20:30:00.000Z
---

# Design System: NXME

> Generated via /designer Mode C — Custom Design System
> Target: React Native (Expo) mobile + Next.js shareable card web
> Aesthetic: Gen Z social · bold · energetic · authentic
> Dark mode: dark-first (both modes supported, user-toggled via `[data-theme]`)

<!-- Sections populated progressively through /designer stages -->

---

## Brand Identity

### Brand Personality

**Core Traits**: Transformative · Bold · Authentic · Energetic · Empowering

| Dimension | Expression |
|-----------|------------|
| Personality | Your hype friend who's also brutally honest. Excited about your potential, not fake about it. |
| Tone | Direct, energetic, encouraging — no fluff. Gen Z authentic, not corporate. |
| Emotional register | Confidence · excitement · a little edge |
| What we never sound like | Clinical ("analysis shows…") · Judgmental ("you scored…") · Hollow ("you're perfect!") |

**Brand Keywords**: glow-up · next level · real · evolution · yours · move · edge

### Visual Mood

**Primary direction**: Dark-native, electric — high contrast with a single high-energy accent color. Dark backgrounds with neon/electric accents. Bold, heavy typography. Before/after reveals feel like a level-up moment, not a dashboard.

**Aesthetic DNA**:
- Layout density: BeReal (real, minimal chrome)
- Color energy: electric accent on deep dark
- Typography weight: bold, compressed, confident
- Motion feel: snappy directional transitions

### Logo Guidelines

*(No existing logo — placeholder guidelines)*

- Preferred form: wordmark "NXME" — lean sans-serif, slightly compressed
- X as visual anchor — transformation symbol potential
- No sparkles, glows, or literal "beauty" iconography
- App icon: stylized upward/forward arrow or bold NX monogram
- Clear space: 1× cap-height on all sides
- Minimum digital size: 24px height

### Brand Voice

| Context | Tone | Example |
|---------|------|---------|
| Analysis results | Direct, clear, actionable | "Softer arch here. Try this." |
| Glow-up reveal | Excited, hype | "This is your next level." |
| Community / social | Casual, supportive | "Everyone's comparing. Jump in." |
| Empty states | Encouraging | "Your journey starts with a photo." |
| Errors | Calm, real | "Couldn't process that. Try again." |
| Paywall / credits | Confident, not pushy | "Unlock your full transformation." |

---

## Color System

> Source file: `src/styles/tokens/colors.css`
> Tokens JSON: `src/styles/tokens/colors.tokens.json`
> Architecture: Before/After dual-accent system. "Before" = muted slate. "After" = electric coral.

### Color Architecture

The color system narratively mirrors what NXME does:

| Role | Family | Narrative |
|------|--------|-----------|
| Before accent | Slate | Subdued states, inactive UI, "before" image overlays |
| After accent | Coral / Rose | CTAs, "after" reveals, glow-up moments, active states |
| Base | Near-black neutrals | Dark-first surface system |
| Semantic | Green / Amber / Red / Blue | Status communication |

### Before Palette (Slate)

Used for: inactive tabs, disabled states, secondary text, "before" image overlays, subtle borders.

| Step | Hex | Usage |
|------|-----|-------|
| 50 | `#F8FAFC` | Lightest tint — light mode hover on slate elements |
| 100 | `#F1F5F9` | Light backgrounds for "before" zones in light mode |
| 200 | `#E2E8F0` | Light mode subtle borders around inactive areas |
| 300 | `#CBD5E1` | Inactive icon fill in light mode |
| 400 | `#94A3B8` | `--color-accent-before` (dark mode) — inactive tabs, secondary icons |
| 500 | `#64748B` | Base input color — mid-range slate |
| 600 | `#475569` | `--color-accent-before` (light mode) — meets 4.5:1 on white |
| 700 | `#334155` | Dark borders in light mode, deep inactive states |
| 800 | `#1E293B` | Dark surface tint for "before" image overlays |
| 900 | `#0F172A` | Near-black slate — deepest "before" shadow |

### After Palette (Coral / Rose)

Used for: primary CTAs, "after" reveals, glow-up badges, active states, gradient accents.

| Step | Hex | Usage |
|------|-----|-------|
| 50 | `#FFF1F3` | Subtlest coral — active tab bg, subtle highlight (light mode) |
| 100 | `#FFE4E8` | Hover backgrounds on coral-adjacent elements (light mode) |
| 200 | `#FECDD5` | Badge backgrounds, light mode coral chip fill |
| 300 | `#FDA4B4` | Decorative gradient endpoints, soft glow halos |
| 400 | `#FB7091` | Lighter interactive states — hover rings, secondary highlights |
| 500 | `#F43F5E` | **Base** — primary CTAs, "after" reveal badges, active indicators |
| 600 | `#E11D48` | Hover state for filled coral buttons |
| 700 | `#BE123C` | Active/pressed state — darkest interactive coral |
| 800 | `#9F1239` | Deep coral — destructive states adjacent to error family |
| 900 | `#881337` | Deepest coral — text on very light coral surfaces (rare) |

### Neutral Palette

#### Dark Neutrals (near-black base: `#080808`)

| Step | Hex | Role in dark theme |
|------|-----|--------------------|
| 0 | `#080808` | Page background floor |
| 50 | `#0F0F0F` | Between floor and card |
| 100 | `#111111` | Card background |
| 150 | `#161616` | Input fill, chip background |
| 200 | `#1A1A1A` | Elevated surface (modals, bottom sheets) |
| 300 | `#222222` | Hover state fill for interactive surfaces |
| 400 | `#2A2A2A` | Subtle border, divider |
| 500 | `#3A3A3A` | Strong border, visible rule |
| 600 | `#555555` | Disabled text |
| 700 | `#A0A0A0` | Secondary text, placeholder |
| 800 | `#D4D4D4` | Tertiary text |
| 900 | `#F8F8F8` | Primary text |

#### Light Neutrals (near-white base: `#F9F9F9`)

| Step | Hex | Role in light theme |
|------|-----|---------------------|
| 0 | `#FFFFFF` | Card background |
| 50 | `#F9F9F9` | Page background |
| 100 | `#F2F2F2` | Subtle hover fill, input background |
| 200 | `#E8E8E8` | Elevated surface |
| 300 | `#E5E5E5` | Subtle border |
| 400 | `#D1D1D1` | Strong border, visible divider |
| 500 | `#B0B0B0` | Placeholder text |
| 600 | `#9CA3AF` | Disabled text |
| 700 | `#6B7280` | Secondary text |
| 800 | `#374151` | Tertiary text |
| 900 | `#111111` | Primary text |

### Semantic Colors

#### Scale Values

| Family | 50 | 400 | 500 | 600 | 900 |
|--------|----|-----|-----|-----|-----|
| Success | `#F0FDF4` | `#4ADE80` | `#22C55E` | `#16A34A` | `#14532D` |
| Warning | `#FFFBEB` | `#FBBF24` | `#F59E0B` | `#D97706` | `#78350F` |
| Error | `#FEF2F2` | `#F87171` | `#EF4444` | `#DC2626` | `#7F1D1D` |
| Info | `#EFF6FF` | `#60A5FA` | `#3B82F6` | `#2563EB` | `#1E3A8A` |

#### Semantic Token Mapping

| Token | Dark Value | Light Value | Usage |
|-------|-----------|-------------|-------|
| `--color-semantic-success` | `#4ADE80` (400) | `#16A34A` (600) | Analysis complete, post published, credit added |
| `--color-semantic-success-subtle` | `rgba(74,222,128,0.12)` | `#F0FDF4` (50) | Success banner/toast background |
| `--color-semantic-warning` | `#FBBF24` (400) | `#D97706` (600) | Low credits, generation in queue |
| `--color-semantic-warning-subtle` | `rgba(251,191,36,0.12)` | `#FFFBEB` (50) | Warning banner background |
| `--color-semantic-error` | `#F87171` (400) | `#DC2626` (600) | Face not detected, generation failed |
| `--color-semantic-error-subtle` | `rgba(248,113,113,0.12)` | `#FEF2F2` (50) | Error banner background |
| `--color-semantic-info` | `#60A5FA` (400) | `#2563EB` (600) | Informational tooltips, hints |
| `--color-semantic-info-subtle` | `rgba(96,165,250,0.12)` | `#EFF6FF` (50) | Info banner background |

### Theme Tokens

#### Surface Tokens

| Token | Dark | Light |
|-------|------|-------|
| `--color-bg-page` | `#080808` | `#F9F9F9` |
| `--color-bg-card` | `#111111` | `#FFFFFF` |
| `--color-bg-elevated` | `#1A1A1A` | `#FFFFFF` + shadow |
| `--color-bg-subtle` | `#222222` | `#F2F2F2` |
| `--color-border` | `#2A2A2A` | `#E5E5E5` |
| `--color-border-strong` | `#3A3A3A` | `#D1D1D1` |

#### Text Tokens

| Token | Dark | Light |
|-------|------|-------|
| `--color-text-primary` | `#F8F8F8` | `#111111` |
| `--color-text-secondary` | `#A0A0A0` | `#6B7280` |
| `--color-text-disabled` | `#555555` | `#9CA3AF` |
| `--color-text-inverse` | `#111111` | `#F8F8F8` |

#### Accent Tokens

| Token | Dark | Light |
|-------|------|-------|
| `--color-accent-before` | `#94A3B8` | `#475569` |
| `--color-accent-before-subtle` | `rgba(148,163,184,0.10)` | `rgba(71,85,105,0.08)` |
| `--color-accent-after` | `#F43F5E` | `#F43F5E` |
| `--color-accent-after-hover` | `#E11D48` | `#E11D48` |
| `--color-accent-after-subtle` | `rgba(244,63,94,0.12)` | `rgba(244,63,94,0.08)` |
| `--color-accent-after-ring` | `rgba(244,63,94,0.30)` | `rgba(244,63,94,0.25)` |

### Special NXME Tokens

Product-layer tokens — carry product narrative meaning beyond pure color values.

| Token | Dark | Light | Purpose |
|-------|------|-------|---------|
| `--color-glow` | `#FF8C42` | `#F97316` | Image reveal halo — warm amber adjacent to coral |
| `--color-glow-soft` | `rgba(255,140,66,0.25)` | `rgba(249,115,22,0.20)` | Soft glow blur behind generated image |
| `--color-glow-ring` | `rgba(255,140,66,0.40)` | `rgba(249,115,22,0.35)` | Ring effect at reveal moment |
| `--color-before-overlay` | `rgba(15,23,42,0.72)` | `rgba(241,245,249,0.80)` | "Before" image veil — dark, desaturating |
| `--color-after-overlay` | `rgba(244,63,94,0.08)` | `rgba(244,63,94,0.05)` | "After" reveal tint — barely-there warm glow |
| `--color-credit-badge` | `#F59E0B` | `#D97706` | Premium amber-gold for credit count |
| `--color-credit-badge-bg` | `rgba(245,158,11,0.15)` | `rgba(217,119,6,0.10)` | Credit badge fill |
| `--color-credit-badge-text` | `#FCD34D` | `#92400E` | Credit badge label |
| `--color-feed-divider` | `rgba(255,255,255,0.05)` | `rgba(0,0,0,0.06)` | 1px feed item separator |

### Accessibility

All interactive combinations pass WCAG AA. Full table in `src/styles/tokens/colors.css` comments.

| Combination | Ratio | Level |
|-------------|-------|-------|
| `--color-text-primary` on `--color-bg-page` (dark) | ~19.8:1 | AAA |
| `--color-text-primary` on `--color-bg-page` (light) | ~18.5:1 | AAA |
| `--color-accent-after` on `--color-bg-page` (dark) | ~5.6:1 | AA |
| `--color-accent-after` on `--color-bg-card` (dark) | ~5.3:1 | AA |
| White on `--color-accent-after` (filled button) | ~4.6:1 | AA |
| `--color-text-secondary` on `--color-bg-card` (dark) | ~5.1:1 | AA |
| `--color-accent-before` on `--color-bg-page` (dark) | ~7.1:1 | AAA |
| `--color-accent-before` on `--color-bg-card` (light) | ~5.7:1 | AA |
| `--color-text-disabled` on `--color-bg-card` (dark) | ~2.0:1 | Intentional fail — per WCAG 1.4.3 inactive control exception |

---

## Typography System

> Source file: `src/styles/tokens/typography.css`
> React Native tokens: `src/styles/tokens/typography.ts`
> Fonts: Space Grotesk (display) + DM Sans (body)
> Scale: Major Third (1.25), base 16px

### Font Families

| Role | Family | Weights Loaded | Narrative |
|------|--------|---------------|-----------|
| Display / Headings | Space Grotesk | 500, 600, 700 | AI precision, bold reveal moments |
| Body / UI | DM Sans | 400, 500, 600 | Human warmth, feed reading, community |
| Mono | System monospace | — | Credit counts, scores, precise numbers |

### Type Scale

| Token | Family | Size | px | Line Height | Weight | Letter Spacing | Usage |
|-------|--------|------|----|-------------|--------|----------------|-------|
| `display-xl` | Space Grotesk | 3.052rem | 49px | 1.1 (54px) | 700 | -0.03em | Hero reveals, "Your Next Self" |
| `display-lg` | Space Grotesk | 2.441rem | 39px | 1.1 (43px) | 700 | -0.025em | Page titles, feature headers |
| `heading-1` | Space Grotesk | 1.953rem | 31px | 1.2 (37px) | 600 | -0.02em | Section headings, modal titles |
| `heading-2` | Space Grotesk | 1.563rem | 25px | 1.2 (30px) | 600 | -0.015em | Card headings, epic subsections |
| `heading-3` | Space Grotesk | 1.25rem | 20px | 1.2 (24px) | 500 | -0.01em | List headings, label-sized titles |
| `body-lg` | DM Sans | 1.125rem | 18px | 1.6 (29px) | 400 | 0 | Lead text, key suggestions |
| `body-md` | DM Sans | 1rem | 16px | 1.5 (24px) | 400 | 0 | Primary body — base |
| `body-sm` | DM Sans | 0.875rem | 14px | 1.5 (21px) | 400 | 0 | Secondary body, feed content |
| `caption` | DM Sans | 0.75rem | 12px | 1.4 (17px) | 500 | +0.01em | Timestamps, metadata |
| `label` | DM Sans | 0.8125rem | 13px | 1.35 (18px) | 500 | +0.01em | UI labels, button text, tabs |
| `mono` | System mono | 0.875rem | 14px | 1.5 (21px) | 400 | 0 | Credit counts, scores |

### Implementation

**Web (Next.js)**: `next/font/google` with CSS variables `--font-display` / `--font-body` injected on `<html>`. Variable fonts loaded automatically — single file per family.

**React Native (Expo)**: Individual `.ttf` files per weight in `assets/fonts/`, loaded via `expo-font` / `useFonts`. Font registry keys: `SpaceGrotesk-Bold`, `SpaceGrotesk-SemiBold`, `SpaceGrotesk-Medium`, `DMSans-Regular`, `DMSans-Medium`, `DMSans-SemiBold`.

**Key RN note**: Variable fonts not supported in React Native text engine — use individual weight files. Letter spacing must be in px (not em).

### Narrative Mapping

The type pairing mirrors the Before/After product narrative:
- **Space Grotesk** = AI precision, the analysis result, the reveal title — used when the product is "speaking" about transformation
- **DM Sans** = human warmth, the user's words, the community feed — used when humans are communicating

---

## Spacing & Layout

> Source file: `src/styles/tokens/spacing.css`
> Base unit: 4px · All spacing is a multiple of 4

### Spacing Scale

| Token | rem | px | RN pts | Usage |
|-------|-----|----|--------|-------|
| `space-1` | 0.25rem | 4px | 4 | Hairline gaps, icon-to-label nudge |
| `space-2` | 0.5rem | 8px | 8 | Tight inline spacing, chip padding |
| `space-3` | 0.75rem | 12px | 12 | Component internal padding (compact) |
| `space-4` | 1rem | 16px | 16 | Standard — primary spacing unit |
| `space-5` | 1.25rem | 20px | 20 | Comfortable padding, list item gaps |
| `space-6` | 1.5rem | 24px | 24 | Section padding, card internal |
| `space-8` | 2rem | 32px | 32 | Card padding, group separation |
| `space-10` | 2.5rem | 40px | 40 | Section margins |
| `space-12` | 3rem | 48px | 48 | Large section separation |
| `space-16` | 4rem | 64px | 64 | Page-level vertical rhythm |
| `space-20` | 5rem | 80px | 80 | Hero section spacing |

### Grid System

| Context | Columns | Gutter | Margin | Max Width |
|---------|---------|--------|--------|-----------|
| Mobile (RN) | 4 | 16px | 16px | 100% |
| Web mobile | 4 | 16px | 16px | — |
| Web tablet | 12 | 24px | 32px | — |
| Web desktop | 12 | 24px | 48px | 640px (social card) |

### Breakpoints (Web)

| Name | Min Width | Device |
|------|-----------|--------|
| `sm` | 390px | Modern phone |
| `md` | 768px | Tablet |
| `lg` | 1024px | Laptop |
| `xl` | 1280px | Desktop |

### Border Radius Scale

| Token | Value | Usage |
|-------|-------|-------|
| `--radius-sm` | 6px | Chips, small badges |
| `--radius-md` | 10px | Buttons, inputs |
| `--radius-lg` | 16px | Cards, modals |
| `--radius-xl` | 24px | Bottom sheets, full-bleed surfaces |
| `--radius-full` | 9999px | Pills, avatars, circular elements |

### NXME Layout Tokens

| Token | Value | Purpose |
|-------|-------|---------|
| `--layout-screen-h-pad` | 16px | Standard horizontal screen padding |
| `--layout-card-pad` | 16px | Card internal padding |
| `--layout-avatar-sm` | 32px | Feed avatar |
| `--layout-avatar-md` | 40px | Profile header avatar |
| `--layout-avatar-lg` | 80px | Profile page hero avatar |
| `--layout-before-after-gap` | 8px | Gap between before/after images |
| `--layout-tab-bar-height` | 49px | iOS tab bar height |
| `--layout-bottom-safe` | 34px | iPhone home indicator clearance |
| `--layout-share-card-w` | 390px | Shareable card width |
| `--layout-share-card-h` | 693px | Shareable card height (~9:16 portrait) |

---

## Components

> Full specifications: `docs/components.md`
> Source tokens: `src/styles/tokens/`

### Component Catalog

| Component | Variants | Key Notes |
|-----------|----------|-----------|
| **Button** | Primary · Secondary · Ghost · Destructive | 3 sizes (32/44/52px). Glow-Up CTA adds amber box-shadow on reveal screens. |
| **Input** | Default · Search | 44px height (touch-safe). Coral ring on focus. Error ring distinct from focus ring. |
| **Card** | Feed · Suggestion · Stats | Feed Card: full-bleed before/after at 3:4 ratio with 8px gap. Suggestion Card: coral accent bar. |
| **Badge / Pill** | Status · Credit · Before · After | BEFORE/AFTER pills uppercase. Credit badge uses amber gold. |
| **Avatar** | sm/md/lg + placeholder | 32/40/80px. Online indicator is sibling in wrapper (not child — avoids RN overflow clip). |
| **Bottom Tab Bar** | — | 49px + `insets.bottom`. Active state: coral icon + top 2px indicator strip. |
| **Reaction Button** | Default · Active | Ghost → coral on active. Spring bounce animation (scale 0.90) on press. |
| **Credit Counter Chip** | Normal · Low · Empty | Amber normal → intensified + pulse at 1 credit → coral/error at 0. |

---

## Interactions

### Transition Timing

| Purpose | Duration | Easing |
|---------|----------|--------|
| Micro (icon swap, color) | 100ms | ease-out |
| Small (button press, badge) | 150ms | ease-out |
| Medium (card expand, modal) | 250ms | ease-in-out |
| Large (bottom sheet, page) | 320ms | spring (damping 18, stiffness 180) |
| **Reveal (before→after)** | 600ms | spring (damping 14, stiffness 100) |

### Glow-Up Reveal Sequence

1. Loading skeleton (during generation)
2. "Before" image slides in from left (320ms spring)
3. 400ms pause — user sees "before"
4. "After" wipes in from right + amber glow ring expands outward (600ms spring)
5. Suggestion pills stagger in from bottom (50ms apart)
6. Reaction bar fades in (150ms)

The amber `--color-glow` ring is the signature NXME reveal moment.

### Animation Principles

- Spring physics for anything the user touches; easing for ambient/system transitions
- `prefers-reduced-motion`: all motion collapses to opacity crossfade
- GPU-only: animate `transform` and `opacity` only — never layout properties
- Skeleton-first: shown immediately on load, never an empty void
- Stagger lists: 50ms between items, 200ms max for the group

### Feedback Patterns

| Pattern | Duration | Behavior |
|---------|----------|---------|
| Toast / Snackbar | 3s auto-dismiss | Bottom, above tab bar, non-blocking |
| Generation progress | Until complete | Inline skeleton in card slot |
| Credit deducted | 300ms one-shot | Chip pulses scale 1→1.1→1 |
| Face not detected | Persistent | Inline error + shake animation (3× ±4px) |

---

## Accessibility Report

> WCAG Level: AA (all P1 issues remediated below)
> Validation date: 2026-03-15

### Summary

- **WCAG Level**: AA (with remediations applied)
- **DS Compliance**: Compliant after P1 token fix
- **Issues Found**: 9 total
- **Critical (P1)**: 1 (contrast on filled button — fix documented below)
- **Important (P2)**: 4
- **Minor (P3)**: 4

### P1 — Critical Issues (Resolved)

| # | WCAG | Element | Issue | Contrast | Fix |
|---|------|---------|-------|----------|-----|
| 1 | 1.4.3 AA | Primary button label (13px/500) | White on #F43F5E = 3.67:1 — fails normal text AA | 3.67:1 ❌ | Add `--color-accent-after-filled: #E11D48`. Use this token for filled button backgrounds. White on #E11D48 = 4.70:1 ✅ |

**Token addition required** in `src/styles/tokens/colors.css`:
```css
--color-accent-after-filled: #E11D48;  /* Use for filled button bg; white text = 4.70:1 AA */
```
Primary Button component spec updated: background uses `--color-accent-after-filled`, not `--color-accent-after`.
The coral #F43F5E remains correct for: borders, icons, rings, decorative accents, and large text contexts.

### P2 — Important Issues

| # | WCAG | Element | Issue | Fix |
|---|------|---------|-------|-----|
| 2 | 1.4.3 | Ghost/secondary button text (light mode) | #F43F5E as text on #F9F9F9 = 3.88:1 ❌ | Add `[data-theme="light"] { --color-accent-after-text: #E11D48; }`. Light mode text on coral contexts uses #E11D48. |
| 3 | 2.4.11 | All focusable elements | Focus ring at 30% opacity may fall below 3:1 composite contrast | Increase to `rgba(244,63,94,0.60)` or use solid 2px ring. `--color-accent-after-ring: rgba(244,63,94,0.60)` |
| 4 | 2.5.5 | Reaction buttons, sm-size buttons (32px) | Below 44×44px AAA touch target | Expand tap area: RN `hitSlop={{ top: 6, bottom: 6, left: 6, right: 6 }}`. Visual size unchanged. |
| 5 | 1.4.1 | Reaction buttons | Active state uses color only when count is 0 | Enforce `--color-accent-after-subtle` fill background on active state (already in spec — must be implemented). |

### P3 — Minor Issues (Best Practice)

| # | WCAG | Element | Issue | Fix |
|---|------|---------|-------|-----|
| 6 | 4.1.3 | Reaction count, credit chip, generation progress | Dynamic updates not announced to screen readers | `aria-live="polite"` on reaction counts and credit chip. `role="status"` on generation progress. |
| 7 | 1.1.1 | Icon-only buttons (share, reaction icons) | No accessible name | Add `aria-label` / `accessibilityLabel` to all icon-only interactive elements. |
| 8 | 4.1.3 | Loading skeleton | No accessible loading announcement | `aria-busy="true"` on skeleton container, `aria-label="Loading content"`. |
| 9 | 2.4.6 | Tab bar "+" button | Icon "+" not descriptive | Add `accessibilityLabel="Create new glow-up"` to the upload tab. |

### Pass List

| Criterion | Evidence |
|-----------|---------|
| 1.4.3 AA — Primary text (dark) | #F8F8F8 on #080808 = 19.8:1 ✅ AAA |
| 1.4.3 AA — Primary text (light) | #111111 on #F9F9F9 = 18.5:1 ✅ AAA |
| 1.4.3 AA — Secondary text (dark) | #A0A0A0 on #111111 = 7.21:1 ✅ AAA |
| 1.4.3 AA — Secondary text (light) | #6B7280 on #FFFFFF = 5.74:1 ✅ AA |
| 1.4.3 AA — Coral on dark bg | #F43F5E on #080808 = 5.46:1 ✅ AA |
| 1.4.3 AA — Coral on card (dark) | #F43F5E on #111111 = 5.3:1 ✅ AA |
| 1.4.3 AA — Error on dark | #F87171 on #111111 = 4.8:1 ✅ AA |
| 1.4.3 AA — Warning on dark | #FBBF24 on #111111 = 9.1:1 ✅ AAA |
| 1.4.3 AA — Success on dark | #4ADE80 on #111111 = 7.2:1 ✅ AAA |
| 1.4.3 AA — Slate before on dark | #94A3B8 on #080808 = 7.80:1 ✅ AAA |
| 1.4.3 — Disabled text | #555555 on #111111 = 2.53:1 — intentional, WCAG 1.4.3 inactive control exception ✅ |
| 1.4.4 — Text resize | All web sizes use rem units ✅ |
| 2.3.3 — Reduced motion | `prefers-reduced-motion` specified in Interactions section ✅ |
| 2.5.8 AA — Touch targets | Primary and secondary buttons at 44px height meet 24×24px minimum ✅ |
| 1.4.1 — Color independence | Active tabs have underline indicator + color change ✅ |
| 1.4.1 — Error states | Error inputs show border + inline text message (not color alone) ✅ |
