# NXME Mobile App — UI Map

> **How to use:** Review each screen/element below. Add comments inline like:
> `- [x] NEEDS FIX: [your comment]` or `- [x] REDESIGN: [description]`
> Then I'll spawn agents to fix everything you mark.

---

## 1. Auth: Login — `/(auth)/login`
Header: None (full-screen hero)

### Hero Background
- [ ] Full-bleed portrait image from card-web collection
- [ ] No overlay gradient

### Brand
- [ ] "N X M E" tiny label top-left | Font: bodyMedium 11px | Tracking: 4

### Content (bottom-aligned)
- [ ] "Welcome back," title | Font: display 48px | Color: white + shadow
- [ ] "to your glow-up" accent line | Font: displayItalic 48px | Color: accent
- [ ] "Log in to your account" subtitle | Font: body 15px | Color: TEXT_PRIMARY

### Error Banner
- [ ] Alert icon + error text | Font: body 14px | Style: glass card

### Form
[X] REDESIGN: the google and apple login is the default, the email and password form should become visible after clicking on use email instead link or something
- [X] Email input | Font: body | Style: frosted glass (AUTH_INPUT_BG)
- [X] Password input + eye toggle | Font: body | Style: frosted glass

### CTA
- [ ] "Log in" GlowButton | Font: bodyMedium 18px | Style: accent solid + glow pulse

### Footer
- [X] Google login button | Style: glass outline - Google login should be the default login method, also the button is too transparent, it is not easily visible
- [X] Apple login button | Style: glass outline Apple should be also default login method
- [ ] "Don't have an account? Sign up" link | Font: body + bodySemiBold

---

## 2. Auth: Signup — `/(auth)/signup`
Header: None (full-screen hero)

### Hero Background
- [ ] Full-bleed portrait image

### Brand
- [ ] "N X M E" tiny label

### Content (bottom-aligned)
- [ ] "Create your account," title | Font: display 48px
- [ ] Accent subtitle | Font: displayItalic 48px | Color: accent
- [ ] Body subtitle | Font: body 15px

### Form (5 fields)  
[X] REDESIGN: the google and apple sign-up is the default, the email and password form should become visible after clicking on use email instead link or something
- [ ] Username input | Font: body | Style: frosted glass
- [ ] Display name input
- [ ] Email input
- [ ] Password input + eye toggle
- [ ] Confirm password input + eye toggle

### CTA
- [ ] "Create account" GlowButton

### Footer
- [X] Google / Apple social buttons Google/Apple login should be the default signup method, also the google button is too transparent, it is not easily visible
- [ ] "Already have an account? Log in" link

### Verification Sub-Screen
- [ ] Mail icon in glass circle (80x80)
- [ ] "Check your email" title | Font: display 24px
- [ ] "We sent a link to [email]" | Font: body
- [ ] "Open email app" button | solid
- [ ] "Resend email" text link
- [ ] "I've verified" text link

---

## 3. Onboarding — `/onboarding`
Header: None

### Background
- [ ] PageBackground overlay 0.88

### Header Section
- [ ] Sparkles icon in glass circle | Color: accent
- [ ] "Your Glow-Up Starts Here" title | Font: display 24px
- [ ] Trial count text | Font: body 16px

### Trial Badge
- [ ] Gift icon + "[N] free trials" | Font: bodySemiBold 15px | Style: glass pill

### Feature List (3 rows)
- [ ] "Upload Your Photo" | Icon: camera | Font: bodySemiBold + body | Style: glass
- [ ] "AI-Powered Styling" | Icon: sparkles | Style: glass
- [ ] "Your Identity, Preserved" | Icon: shield | Style: glass

### Push Notification Card
- [ ] Bell icon + "Stay in the Loop" | Font: bodySemiBold 18px
- [ ] "Enable Notifications" button | Style: solid
- [ ] "Not now" skip | Font: body 14px

### CTA
- [ ] "Analyze My Style" button | Style: solid
- [ ] "Upload a photo..." hint | Font: body 14px

---

## 4. Tab: Feed (Home) — `/(tabs)/index`
Header: BrandLabel (tappable→feed) + CreditBadge right

### Email Verify Banner
- [ ] Alert icon + "Verify your email" | Font: body 14px | Style: glass | Dismissible

### Sort Tabs
- [ ] "Latest" pill | Font: bodyMedium 14px | Style: glass pill | Active: accent glow
- [ ] "Trending" pill
- [ ] "Following" pill

### Feed Cards (each)
- [ ] Sparkle icon circle + Avatar (28px) + Display name | Font: bodySemiBold 14px
- [ ] "Before → After" label row | Font: bodyMedium 11px uppercase
- [ ] Before image (left half, 240px tall)
- [ ] After image (right half, 240px tall)
- [ ] 2px divider between images
- [ ] Caption text | Font: body | Max 3 lines
- [ ] Reaction button (heart + count) | Font: bodyMedium 14px | Animated spring
- [ ] Comment button (bubble + count) | Font: bodyMedium 14px
- [ ] Timestamp | Font: body caption | Right-aligned
- [ ] Double-tap → heart overlay (60px, fade in/out)
- [ ] Long-press → DropdownMenu (Share/Block/Report)

### Empty State
- [ ] Images icon 48px + "No posts yet" | Font: bodySemiBold
- [ ] "Be the first to share" | Font: body

### Error State
- [ ] Alert icon 48px + error text + "Try Again" button

### Loading State
- [ ] FeedSkeleton (glass shimmer cards)

---

## 5. Tab: Create — `/(tabs)/create`
Header: BrandLabel (tappable)

### Background
- [ ] PageBackground overlay 0.85

### Title
- [ ] "Create" | Font: display 32px
- [ ] "What would you like to do?" | Font: body 15px
- [ ] Divider line

### 2x2 Feature Grid
- [ ] "Glow Up" card (ACTIVE) | Icon: sparkles 32px | Font: bodySemiBold 15px + body 12px | Style: accent glow border | Press: → /upload
- [ ] "Style Check" card (INACTIVE) | "COMING SOON" badge | Style: muted
- [ ] "Skin Care" card (INACTIVE) | "COMING SOON" badge
- [ ] "Hair Style" card (INACTIVE) | "COMING SOON" badge

---

## 6. Tab: Profile — `/(tabs)/profile`
Header: BrandLabel + 3-dot menu (→ RadialMenu)

### Unauthenticated
- [ ] Person icon 64px + "Sign in" title | Font: display 24px
- [ ] "Track your glow-ups" | Font: body
- [ ] "Sign In" button | Style: accent solid

### Profile Header (collapsed)
- [ ] Avatar 40px + Display name | Font: display 20px
- [ ] @username | Font: body 13px | Color: textSecondary
- [ ] Stats pills (reactions, posts) | Style: glass
- [ ] Chevron toggle (rotate 0→180)

### Profile Header (expanded)
- [ ] Edit Profile button | Style: accent outline pill
- [ ] Share button

### Glow-Up Grid
- [ ] Grid cells (before/after side-by-side) | Style: glass | Press: → post detail
- [ ] Empty state: "No glow-ups yet" | Font: bodySemiBold

### RadialMenu (from 3-dot)
- [ ] "Edit Profile" | Icon: create-outline
- [ ] "Subscription" | Icon: diamond-outline
- [ ] "Settings" | Icon: settings-outline
- [ ] "Log Out" | Icon: log-out-outline | Style: destructive

### Modals
- [ ] EditProfileSheet: display name + bio inputs + Save/Cancel
- [ ] RadialMenu: circular context menu

---

## 7. Tab: Advisor — `/advisor/index`
Header: BrandLabel (standard tab header)

### Background
- [ ] PageBackground overlay 0.88

### Tab Bar (Chat / Nudges / Memories)
- [ ] "Chat" pill | Icon: chatbubble | Font: bodyMedium 14px | Style: glass pill | Active: accent bg + glow
- [ ] "Nudges" pill | Icon: sparkles
- [ ] "Memories" pill | Icon: bookmark

### Chat Tab (ChatView)
- [ ] Message list (FlatList, auto-scroll)
- [ ] Ada bubble (left) | Font: body 14px | Style: glass card
- [ ] User bubble (right) | Font: body 14px | Style: accent tint
- [ ] "Ada" sender label on assistant messages | Font: bodySemiBold
- [ ] Typing indicator (animated dots)
- [ ] Text input | Font: body | Style: glass pill | Placeholder: "Message Ada..."
- [ ] Send button (circle) | Icon: send 20px | Inactive: glass | Active: accent solid
- [ ] Empty: sparkles icon + "Start a conversation" | Font: bodySemiBold + body
- [ ] Error: alert icon + error text + "Try Again" button
- [ ] Loading: ChatSkeleton (glass bubbles)
- [ ] Paywall: PaywallModal on 402

### Nudges Tab (NudgeFeed)
- [ ] Nudge cards list
- [ ] Each card: icon + trigger text + content | Font: bodySemiBold + body | Style: glass
- [ ] Unread indicator (accent dot or different bg)
- [ ] Empty state message
- [ ] Loading: skeleton cards

### Memories Tab (MemoryList)
- [ ] SubTabs row (Goals / Notes) | Style: chip pair, pill, accent glow when active | Role: tablist
- [ ] Memory cards list (filtered by active subtab)
- [ ] Each card: type icon + content text + timestamp | Font: body | Style: glass
- [ ] Delete button (swipe left reveals trash)
- [ ] Per-tab composer: text input + "Add" button | Placeholder per tab (goal vs note)
- [ ] Per-tab drafts preserved across tab switch within session
- [ ] Per-tab empty state: "No goals yet / Tell Ada what you're working toward." or "No notes yet / Jot anything Ada should know about you."
- [ ] Loading (initial mount): skeleton cards
- [ ] Loading (tab switch refetch): small top-of-list ActivityIndicator, previous list stays visible

---

## 8. Post Detail — `/post/[postId]`
Header: None (custom floating header)

### Floating Header (over image)
- [ ] Close (X) button | Style: OVERLAY_LIGHT circle | Top-right
- [ ] Share button | Style: OVERLAY_LIGHT circle
- [ ] Menu (3-dot) button | Style: OVERLAY_LIGHT circle

### Before Image
- [ ] Full-width image
- [ ] "BEFORE" label | Font: bodySemiBold 10px | Style: OVERLAY_LIGHT badge

### Divider
- [ ] 2px gap | Color: bg

### After Image
- [ ] Full-width image
- [ ] "AFTER" label | Font: bodySemiBold 10px | Style: accent badge

### Footer
- [ ] Reaction button (heart + count) | Animated
- [ ] Comment button (bubble + count) | Opens CommentsSheet
- [ ] Timestamp | Right-aligned
- [ ] Caption text (if present) | Font: body 15px

### Modals
- [ ] CommentsSheet
- [ ] DropdownMenu (Block/Report/Delete)

---

## 9. Upload — `/upload`
Header: "Upload" navigation title

### Background
- [ ] PageBackground overlay 0.88

### Trial Badge
- [ ] Flash icon + "[N]/[M] trials" | Style: glass pill

### Photo Picker
- [ ] Preview image or placeholder
- [ ] Camera/gallery button overlay
- [ ] Clear photo button

### Error States
- [ ] Face validation error card | Icon: alert | Style: glass
- [ ] Generic error card | Icon: warning | Style: glass

### Loading State
- [ ] Spinner + "Uploading..." or "Generating..." | Font: bodySemiBold 18px
- [ ] Elapsed timer | Font: bodySemiBold 24px | Color: accent

### Bottom Bar (glass)
- [ ] Accent glow line (top)
- [ ] "Analyze" button (sparkles icon) | Style: accent solid | Disabled: glass outline
- [ ] "Cancel" button (during generation) | Style: glass outline

---

## 10. Result — `/result/[jobId]`
Header: "Your Glow-Up" title

### Background
- [ ] PageBackground overlay 0.88

### Before/After Reveal
- [ ] Before image slides in
- [ ] After image wipes with glow ring | Color: accent

### User Guidance
- [ ] Guidance text | Font: body | Color: textSecondary

### CTAs (staggered fade-in)
- [ ] "Share" button | Style: glass
- [ ] "This doesn't look like me" / "Refund requested" | Font: body | Style: text link
- [ ] "New Glow-Up" button | Style: accent outline

---

## 11. Settings — `/settings`
Header: "Settings" title

### Account Section
- [ ] "ACCOUNT" label | Font: bodySemiBold 11px uppercase
- [ ] Glass card with rows: Display Name, Username, Email

### Subscription Section
- [ ] "SUBSCRIPTION" label
- [ ] "Manage Subscription" row | Icon: diamond | → /subscription

### Privacy Section
- [ ] "PRIVACY" label
- [ ] "Blocked Users" row | Icon: shield | → /blocked-users

### About Section
- [ ] "ABOUT" label
- [ ] App Version row

### Danger Zone
- [ ] "DANGER ZONE" label | Color: destructive
- [ ] Warning text + "Delete Account" button | Style: destructive solid

---

## 12. Subscription — `/subscription`
Header: Back + "Subscription" title

### Current Plan Card
- [ ] Plan icon in accent circle
- [ ] Plan title | Font: display
- [ ] Plan subtitle | Font: body

### Stats Row
- [ ] Credit count (glow-ups remaining) | Large bold number
- [ ] Renewal date | Large bold

### Trial Timeline (FREE tier)
- [ ] Progress bar | 6px | Accent fill

### Premium Upsell (non-premium)
- [ ] "PREMIUM" badge + diamond icon
- [ ] "Go Pro" title | Font: display
- [ ] Price text | Color: accent
- [ ] "Subscribe Now" button | Style: accent solid

### Credit Packs (non-premium)
- [ ] "CREDIT PACKS" label
- [ ] Grid of pack cards: count + "Buy" button

---

## 13. Blocked Users — `/blocked-users`
Header: "Blocked Users" title

### Empty State
- [ ] Shield icon in glass circle
- [ ] "No blocked users" | Font: bodySemiBold
- [ ] "Users you block will appear here" | Font: body

### User List
- [ ] Each: Avatar + display name + @username + "Unblock" button
- [ ] "Unblock" | Style: accent outline | PressableScale

---

## 14. Public Card — `/card/[username]`
Header: "@username" title

### Before/After Reveal
- [ ] BeforeAfterReveal component with glow ring

### Stats Row
- [ ] Heart + count | Style: glass pill
- [ ] Bubble + count | Style: glass pill

### Recommendation Pills
- [ ] Horizontal pill badges | Style: glass outline

---

## 15. Floating Tab Bar
Position: absolute bottom, glass pill

- [ ] Home icon | Active: accent pill + glow
- [ ] Create icon
- [ ] Profile icon
- [ ] Advisor icon
- [ ] Style: TAB_BAR_BG + TAB_BAR_BORDER | Radius: 32px | Shadow: dark
- [ ] Scroll-to-top pill (appears on scroll) | Style: accent solid

---

## 16. Shared Components

### BrandLabel
- [ ] "N X M E" | Font: bodyMedium 11px | Tracking: 4 | Uppercase | Tappable → feed

### GlowButton
- [ ] Pill button with pulsing glow | Font: bodyMedium | Press scale 0.96

### GlassCard
- [ ] Glass bg + glassBorder + radius lg + shadow

### PageBackground
- [ ] Animated gradient background | Configurable overlay opacity

### PressableScale
- [ ] Animated press (default 0.96) + haptic feedback

### DropdownMenu
- [ ] Glass menu anchored to trigger | Items with icons

### CommentsSheet
- [ ] Bottom sheet: comment list + CommentInput
- [ ] Each comment: avatar + name + text + time
- [ ] Glass styling + X close button

### PaywallModal
- [ ] Bottom sheet: upgrade prompt
- [ ] Glass bg + X close button
- [ ] "Subscribe Now" CTA

### EditProfileSheet
- [ ] Bottom sheet: name + bio inputs + Save/Cancel

### RadialMenu
- [ ] Circular menu with spring physics

---

## Font Rules
| Token | Font | Usage |
|-------|------|-------|
| display | Instrument Serif | Page titles, hero text, plan names, display names |
| displayItalic | Instrument Serif Italic | Accent hero lines |
| body | Inter | Body text, descriptions, inputs |
| bodySemiBold | Inter SemiBold | Labels, section headers, emphasis |
| bodyMedium | Inter Medium | Buttons, tab labels, badges |
| bodyBold | Inter Bold | Strong emphasis (rare) |

---

## Color Tokens
| Token | Value | Usage |
|-------|-------|-------|
| bg | #0a0a0a | Page background |
| glass | rgba(17,17,17,0.85) | Card backgrounds |
| glassBorder | rgba(255,255,255,0.08) | Card borders |
| textPrimary | #e8e8e8 | Main text |
| textSecondary | #888888 | Secondary text |
| accent | dynamic (per session) | CTAs, highlights, glow |
| destructive | red | Delete, errors, warnings |
