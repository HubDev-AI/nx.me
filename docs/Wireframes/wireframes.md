# NXME Wireframes

> Mobile wireframes: 390×844px (iPhone 14 reference)
> Grid: 4-column, 16px margins, 16px gutters
> Tokens: colors from `src/styles/tokens/colors.css`, spacing from `src/styles/tokens/spacing.css`

---

## Screen 1: Social Feed

```
┌─────────────────────────────┐  390px wide
│ NXME              [+] [👤]  │  ← Header: logo (display-lg, Space Grotesk), icon buttons
├─────────────────────────────┤
│ [Trending] [New] [Following]│  ← Tabs: label (DM Sans 13px). Active = coral underline + text
├─────────────────────────────┤  ← --color-border separator
│                             │
│  ┌──────────────────────┐   │  ← Feed Card (--color-bg-card, radius-lg)
│  │ [av] @username  2d   │   │    avatar-sm (32px), caption text
│  │ ┌──────┐  ┌────────┐ │   │
│  │ │BEFORE│  │ AFTER  │ │   │    Before/After 3:4 ratio, 8px gap
│  │ │      │  │   🔥   │ │   │    --color-before-overlay on left
│  │ └──────┘  └────────┘ │   │    amber glow ring on right image
│  │ ─────────────────── │   │    --color-feed-divider
│  │ Softer brow arch ↑  │   │    body-sm (14px, DM Sans)
│  │ Shorter sides ↑     │   │
│  │ Better lighting ↑   │   │
│  │                     │   │
│  │ [🔥 42] [💬 8] [↗]  │   │    Reaction buttons (ghost → coral on active)
│  └──────────────────────┘   │
│                             │
│  ┌──────────────────────┐   │  ← Next feed card (same structure)
│  │ [av] @another  5h    │   │
│  │ ┌──────┐  ┌────────┐ │   │
│  │ │      │  │        │ │   │
│  └──────────────────────┘   │
│                             │
├─────────────────────────────┤
│  [🏠]  [🔍]  [+]  [🔔]  [👤]│  ← Tab bar: 49px + safe area
│  ████                       │    active tab: coral icon + 2px top strip
└─────────────────────────────┘

Interaction notes:
- Pull-to-refresh: spinner in coral
- Infinite scroll: skeleton card loads at bottom
- [+] tab: opens Upload & Analyze (modal sheet)
- Long-press on post: context menu (share, report)
```

---

## Screen 2: Glow-Up Reveal (Hero Screen)

```
┌─────────────────────────────┐
│ ←  Your Glow-Up        [↗]  │  ← Nav: back arrow, share icon (coral)
├─────────────────────────────┤
│                             │
│  ┌──────────┐ ┌──────────┐  │  ← Before/After side-by-side
│  │  BEFORE  │ │  AFTER   │  │    3:4 aspect ratio each, 8px gap
│  │          │ │          │  │    BEFORE: --color-before-overlay veil
│  │  [photo] │ │[glow img]│  │    AFTER:  amber glow ring (--color-glow)
│  │          │ │   🔥     │  │           pulse animation on arrive
│  └──────────┘ └──────────┘  │
│                             │
│  ┌──────────────────────┐   │  ← Result card (--color-bg-card)
│  │ Your Next Self       │   │    heading-2 (Space Grotesk 25px)
│  │ ─────────────────── │   │
│  │ ① Softer brow arch   │   │    body-md (16px, DM Sans)
│  │ ② Shorter sides cut  │   │    suggestions stagger in (50ms each)
│  │ ③ Better lighting    │   │
│  │ ④ Defined jawline    │   │
│  │ ⑤ Clean styling      │   │
│  └──────────────────────┘   │
│                             │
│  [🔥 React]    [💬 Comment] │  ← Reaction + comment ghost buttons
│                             │
│  ┌──────────────────────┐   │  ← Primary CTA (coral, Glow-Up button)
│  │   Post to Feed  →    │   │    box-shadow: --color-glow for warm halo
│  └──────────────────────┘   │
│  ┌──────────────────────┐   │  ← Secondary CTA (ghost)
│  │   Share My Card      │   │
│  └──────────────────────┘   │
│                             │
├─────────────────────────────┤
│  [🏠]  [🔍]  [+]  [🔔]  [👤]│
└─────────────────────────────┘

Interaction notes:
- Reveal animation sequence (see Interactions section):
  before slides in → 400ms pause → after wipes from right + glow ring expands
  → suggestion pills stagger up → CTAs fade in
- Tap before/after image: full-screen lightbox with zoom
- [↗] share: native share sheet with card preview
```

---

## Screen 3: Upload & Analyze

```
┌─────────────────────────────┐
│            ×                │  ← Dismiss (presented as bottom sheet)
├─────────────────────────────┤
│                             │
│     Glow Up                 │  ← heading-1 (Space Grotesk 31px)
│     See your next self      │  ← body-md (DM Sans, --color-text-secondary)
│                             │
│  ┌──────────────────────┐   │  ← Upload zone (dashed border --color-border-strong)
│  │                      │   │    tap area: full zone, --color-bg-subtle fill
│  │    [📷 48px icon]    │   │    icon: --color-accent-before (slate)
│  │                      │   │
│  │  Tap to upload       │   │    body-md
│  │  or take a selfie    │   │    --color-text-secondary
│  │                      │   │
│  └──────────────────────┘   │
│                             │
│  ─────────── or ──────────  │  ← caption, --color-text-disabled
│                             │
│  [📷 Camera]  [🖼 Library]  │  ← Secondary buttons (outline, md height 44px)
│                             │
│  ┌──────────────────────┐   │  ← Validation hints (--color-bg-subtle, radius-md)
│  │ ✓ Face clearly visible│  │    caption (12px, DM Sans Medium)
│  │ ✓ Good lighting      │   │    ✓ = success green, ✗ = error red
│  │ ✓ Single person only │   │
│  └──────────────────────┘   │
│                             │
│  ⬤ 2 free analyses left    │  ← Credit chip (amber, --color-credit-badge)
│                             │
│  ┌──────────────────────┐   │  ← Primary CTA (coral, disabled until photo)
│  │  Analyze My Glow-Up  │   │    disabled: 40% opacity, no press
│  └──────────────────────┘   │
└─────────────────────────────┘

States:
- Empty: upload zone dashed, CTA disabled (40% opacity)
- Photo selected: upload zone shows thumbnail, CTA enabled (full coral)
- Validating: loading spinner in upload zone, CTA loading state
- Face error: upload zone shows error border, inline message "No face detected"
- Analyzing: CTA shows "Analyzing..." + spinner, progress indeterminate
```

---

## Screen 4: User Profile

```
┌─────────────────────────────┐
│ ←  @username         [⋯]   │  ← Nav: back, username, overflow menu
├─────────────────────────────┤
│                             │
│         [avatar 80px]       │  ← Circle avatar, --layout-avatar-lg
│          @username          │  ← heading-3 (Space Grotesk 20px)
│     12 posts · 348 reacts   │  ← caption (12px, --color-text-secondary)
│                             │
│  [Edit Profile]  [↗ Share]  │  ← Secondary buttons (outline, sm height 32px)
│                             │
│  ┌────┐ ┌────┐ ┌────┐       │  ← Stats row (--color-bg-card chips)
│  │ 12 │ │348 │ │ 5  │       │    label: "posts", "reactions", "streak"
│  │post│ │rxns│ │days│       │    number: heading-3 coral, label: caption slate
│  └────┘ └────┘ └────┘       │
│                             │
├─────────────────────────────┤
│  [All Glow-Ups] [Reactions] │  ← Tabs, same pattern as feed
├─────────────────────────────┤
│                             │
│  ┌──────┐ ┌──────┐ ┌──────┐│  ← 3-column grid, 2px gap (--layout-feed-item-gap)
│  │ B/A  │ │ B/A  │ │ B/A  ││    each cell: square, before/after split diagonally
│  └──────┘ └──────┘ └──────┘│    coral badge in corner: reaction count
│  ┌──────┐ ┌──────┐ ┌──────┐│
│  │ B/A  │ │ B/A  │ │ B/A  ││
│  └──────┘ └──────┘ └──────┘│
│  ┌──────┐ ┌──────┐ ┌──────┐│
│  │ B/A  │ │ B/A  │ │ B/A  ││
│  └──────┘ └──────┘ └──────┘│
│                             │
├─────────────────────────────┤
│  [🏠]  [🔍]  [+]  [🔔]  [👤]│
└─────────────────────────────┘

Grid cell detail:
  ┌──────────┐
  │ ▓▓ │ ░░ │  ← left half = before (--color-before-overlay), right = after
  │ ▓▓ │ 🔥░│
  │    │    │
  │         🔥5│  ← reaction count badge (coral pill, bottom-right)
  └──────────┘
```

---

## Screen 5: Shareable Card (Web — nxme.ai/@username)

```
┌─────────────────────────────────────────┐  390px (mobile web) / max 640px desktop
│  NXME                    Login  Sign up │  ← minimal nav, web
├─────────────────────────────────────────┤
│                                         │
│   ┌─────────────────────────────────┐   │
│   │                                 │   │  ← Card container (--color-bg-card)
│   │     @username's Glow-Up        │   │    heading-2 (25px, Space Grotesk)
│   │                                 │   │
│   │  ┌──────────┐  ┌─────────────┐  │   │
│   │  │  BEFORE  │  │   AFTER  🔥 │  │   │  ← Before/After, 3:4 ratio
│   │  │  [photo] │  │  [glow img] │  │   │    8px gap, amber glow ring on after
│   │  └──────────┘  └─────────────┘  │   │
│   │                                 │   │
│   │  Top improvements               │   │    heading-3 (20px)
│   │  ─────────────────────────────  │   │
│   │  ① Softer brow arch             │   │    body-md (16px, DM Sans)
│   │  ② Shorter sides haircut        │   │
│   │  ③ Better lighting              │   │
│   │  ④ Defined jawline              │   │
│   │  ⑤ Clean styling                │   │
│   │                                 │   │
│   │  🔥 42 reactions  💬 8 comments │   │    caption, --color-text-secondary
│   │                                 │   │
│   └─────────────────────────────────┘   │
│                                         │
│   ┌─────────────────────────────────┐   │  ← Acquisition CTA (coral, full-width)
│   │      Get Your Free Glow-Up  →  │   │    body-lg (18px, DM Sans SemiBold)
│   └─────────────────────────────────┘   │
│                                         │
│   nxme.ai  ·  Privacy  ·  Terms        │  ← footer, caption
└─────────────────────────────────────────┘

Notes:
- OG image: card crops to 1200×630 with before/after + username for link previews
- Fully public, no login required to view
- "Get Your Free Glow-Up" → app store / sign-up (acquisition funnel entry point)
- Animate the reveal on page load (same sequence as in-app) to hook new visitors
```

---

## Screen 6: Credits / Paywall

```
┌─────────────────────────────┐
│ ←  Unlock More Glow-Ups     │  ← Nav header
├─────────────────────────────┤
│                             │
│  ⬤ 0 analyses remaining    │  ← Credit chip (coral empty state)
│  You've used all your       │
│  free analyses              │  ← body-sm, --color-text-secondary
│                             │
│  ┌──────────────────────┐   │  ← Subscription card (--color-bg-card)
│  │  ⭐ BEST VALUE        │   │    coral border (--color-accent-after)
│  │                      │   │    badge: "BEST VALUE" in coral pill
│  │  Unlimited           │   │    heading-2 (Space Grotesk 25px)
│  │  $7.99 / month       │   │    --color-text-secondary, body-sm
│  │                      │   │
│  │  · Unlimited analyses│   │    checkmarks in success green
│  │  · All AI styles     │   │
│  │  · Priority queue    │   │
│  │  · Cancel anytime    │   │
│  │                      │   │
│  │  ┌──────────────────┐│   │
│  │  │  Subscribe Now → ││   │  ← Primary CTA (coral, Glow-Up button style)
│  │  └──────────────────┘│   │
│  └──────────────────────┘   │
│                             │
│  ─────── or buy a pack ──── │  ← caption, --color-text-disabled
│                             │
│  ┌───────────┐ ┌──────────┐ │  ← Credit packs (--color-bg-card, radius-lg)
│  │  5 uses   │ │ 20 uses  │ │
│  │  $3.99    │ │ $11.99   │ │    heading-3 (20px) for price
│  │  ─────    │ │ ─────    │ │
│  │  [Buy]    │ │  [Buy]   │ │    secondary outline button
│  └───────────┘ └──────────┘ │
│                             │
│  Restore Purchase           │  ← ghost text button, --color-text-secondary
│                             │
│  🔒 Secure · Managed by     │
│     App Store               │  ← caption, --color-text-disabled
│                             │
├─────────────────────────────┤
│  [🏠]  [🔍]  [+]  [🔔]  [👤]│
└─────────────────────────────┘

States:
- Entry from empty credit chip: credit chip shown as coral (empty)
- Entry from profile/settings: neutral header, no urgency chip
- Purchase in progress: button shows loading state
- Success: dismiss sheet + credit chip updates with animation
```
