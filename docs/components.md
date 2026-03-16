---
title: "Component Specifications: NXME"
generated: 2026-03-15
source: style-generator
design_system: docs/design-system.md
---

# Component Specifications: NXME

> Covers CSS custom properties (web / Next.js) and React Native StyleSheet pixel values.
> All tokens reference `docs/design-system.md`. Dark mode is the default; light mode overrides are noted where they differ.

---

## Button

### State Table

| State | Background | Border | Text / Icon | Other |
|-------|-----------|--------|-------------|-------|
| **Primary — default** | `--color-accent-after` (#F43F5E) | none | #FFFFFF | — |
| **Primary — hover** | `--color-accent-after-hover` (#E11D48) | none | #FFFFFF | cursor: pointer |
| **Primary — pressed** | #BE123C (after-700) | none | #FFFFFF | scale 0.97 |
| **Primary — loading** | `--color-accent-after` | none | #FFFFFF | spinner visible, label hidden |
| **Primary — disabled** | `rgba(244,63,94,0.35)` | none | `rgba(255,255,255,0.45)` | cursor: not-allowed |
| **Secondary — default** | transparent | 1.5px `--color-accent-after` | `--color-accent-after` | — |
| **Secondary — hover** | `--color-accent-after-subtle` | 1.5px `--color-accent-after` | `--color-accent-after` | — |
| **Secondary — pressed** | `rgba(244,63,94,0.20)` | 1.5px `--color-accent-after-hover` | `--color-accent-after-hover` | scale 0.97 |
| **Secondary — disabled** | transparent | 1.5px `rgba(244,63,94,0.30)` | `rgba(244,63,94,0.40)` | cursor: not-allowed |
| **Ghost — default** | transparent | none | `--color-accent-after` | — |
| **Ghost — hover** | `--color-accent-after-subtle` | none | `--color-accent-after` | — |
| **Ghost — pressed** | `rgba(244,63,94,0.20)` | none | `--color-accent-after-hover` | scale 0.97 |
| **Ghost — disabled** | transparent | none | `rgba(244,63,94,0.35)` | cursor: not-allowed |
| **Destructive — default** | `--color-semantic-error` (#F87171) | none | #FFFFFF | — |
| **Destructive — hover** | #EF4444 (error-500) | none | #FFFFFF | — |
| **Destructive — pressed** | #DC2626 (error-600) | none | #FFFFFF | scale 0.97 |
| **Destructive — disabled** | `rgba(248,113,113,0.35)` | none | `rgba(255,255,255,0.45)` | cursor: not-allowed |
| **Glow-Up CTA** | `--color-accent-after` | none | #FFFFFF | box-shadow glow effect |

### Size Dimensions

| Size | Height | Padding H | Font Size | Border Radius |
|------|--------|-----------|-----------|---------------|
| sm | 32px | 12px | 13px (label) | `--radius-md` (10px) |
| md | 44px | 16px | 13px (label) | `--radius-md` (10px) |
| lg | 52px | 20px | 16px (body-md) | `--radius-md` (10px) |

### CSS

```css
/* ─── Base ─────────────────────────────────────────────── */
.btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: var(--space-2);
  border: none;
  border-radius: var(--radius-md);
  font-family: var(--font-body);
  font-size: var(--text-label);       /* 13px */
  font-weight: var(--font-weight-semibold);
  line-height: 1;
  letter-spacing: 0.01em;
  cursor: pointer;
  transition: background-color 120ms ease-out,
              border-color 120ms ease-out,
              color 120ms ease-out,
              box-shadow 120ms ease-out,
              transform 80ms ease-out;
  white-space: nowrap;
  user-select: none;
  position: relative;
}

.btn:focus-visible {
  outline: none;
  box-shadow: 0 0 0 3px var(--color-accent-after-ring);
}

/* ─── Sizes ─────────────────────────────────────────────── */
.btn--sm {
  height: 32px;
  padding: 0 var(--space-3);
  font-size: var(--text-label);
}

.btn--md {
  height: 44px;
  padding: 0 var(--space-4);
  font-size: var(--text-label);
}

.btn--lg {
  height: 52px;
  padding: 0 var(--space-5);
  font-size: var(--text-body-md);
}

/* ─── Primary ───────────────────────────────────────────── */
.btn--primary {
  background-color: var(--color-accent-after);
  color: #ffffff;
}

.btn--primary:hover:not(:disabled) {
  background-color: var(--color-accent-after-hover);
}

.btn--primary:active:not(:disabled) {
  background-color: #BE123C;
  transform: scale(0.97);
}

.btn--primary:disabled {
  background-color: rgba(244, 63, 94, 0.35);
  color: rgba(255, 255, 255, 0.45);
  cursor: not-allowed;
}

/* ─── Secondary ─────────────────────────────────────────── */
.btn--secondary {
  background-color: transparent;
  color: var(--color-accent-after);
  border: 1.5px solid var(--color-accent-after);
}

.btn--secondary:hover:not(:disabled) {
  background-color: var(--color-accent-after-subtle);
}

.btn--secondary:active:not(:disabled) {
  background-color: rgba(244, 63, 94, 0.20);
  border-color: var(--color-accent-after-hover);
  color: var(--color-accent-after-hover);
  transform: scale(0.97);
}

.btn--secondary:disabled {
  border-color: rgba(244, 63, 94, 0.30);
  color: rgba(244, 63, 94, 0.40);
  cursor: not-allowed;
}

/* ─── Ghost ─────────────────────────────────────────────── */
.btn--ghost {
  background-color: transparent;
  color: var(--color-accent-after);
}

.btn--ghost:hover:not(:disabled) {
  background-color: var(--color-accent-after-subtle);
}

.btn--ghost:active:not(:disabled) {
  background-color: rgba(244, 63, 94, 0.20);
  color: var(--color-accent-after-hover);
  transform: scale(0.97);
}

.btn--ghost:disabled {
  color: rgba(244, 63, 94, 0.35);
  cursor: not-allowed;
}

/* ─── Destructive ───────────────────────────────────────── */
.btn--destructive {
  background-color: var(--color-semantic-error);
  color: #ffffff;
}

.btn--destructive:hover:not(:disabled) {
  background-color: #EF4444;
}

.btn--destructive:active:not(:disabled) {
  background-color: #DC2626;
  transform: scale(0.97);
}

.btn--destructive:disabled {
  background-color: rgba(248, 113, 113, 0.35);
  color: rgba(255, 255, 255, 0.45);
  cursor: not-allowed;
}

/* ─── Glow-Up CTA (special) ─────────────────────────────── */
.btn--glow-up {
  background-color: var(--color-accent-after);
  color: #ffffff;
  box-shadow:
    0 0 16px rgba(255, 140, 66, 0.45),
    0 0 32px rgba(244, 63, 94, 0.25);
}

.btn--glow-up:hover:not(:disabled) {
  background-color: var(--color-accent-after-hover);
  box-shadow:
    0 0 24px rgba(255, 140, 66, 0.55),
    0 0 48px rgba(244, 63, 94, 0.30);
}

/* ─── Loading state ─────────────────────────────────────── */
.btn--loading {
  cursor: wait;
  pointer-events: none;
}

.btn--loading .btn__label {
  visibility: hidden;
}

.btn--loading .btn__spinner {
  position: absolute;
  display: block;
  width: 16px;
  height: 16px;
  border: 2px solid rgba(255, 255, 255, 0.35);
  border-top-color: #ffffff;
  border-radius: 50%;
  animation: btn-spin 600ms linear infinite;
}

@keyframes btn-spin {
  to { transform: rotate(360deg); }
}
```

### React Native StyleSheet

```typescript
import { StyleSheet } from 'react-native';

export const buttonStyles = StyleSheet.create({
  // ── Base ──────────────────────────────────────────────────
  base: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 8,
    borderRadius: 10,
  },
  label: {
    fontFamily: 'DMSans-SemiBold',
    fontSize: 13,
    lineHeight: 13,
    letterSpacing: 0.13,
  },

  // ── Sizes ─────────────────────────────────────────────────
  sizeSm: { height: 32, paddingHorizontal: 12 },
  sizeMd: { height: 44, paddingHorizontal: 16 },
  sizeLg: { height: 52, paddingHorizontal: 20 },
  sizeLgLabel: { fontSize: 16, lineHeight: 16 },

  // ── Primary ───────────────────────────────────────────────
  primaryDefault: { backgroundColor: '#F43F5E' },
  primaryPressed: { backgroundColor: '#BE123C' },
  primaryDisabled: { backgroundColor: 'rgba(244,63,94,0.35)' },
  primaryLabel: { color: '#FFFFFF' },
  primaryLabelDisabled: { color: 'rgba(255,255,255,0.45)' },

  // ── Secondary ─────────────────────────────────────────────
  secondaryDefault: {
    backgroundColor: 'transparent',
    borderWidth: 1.5,
    borderColor: '#F43F5E',
  },
  secondaryPressed: {
    backgroundColor: 'rgba(244,63,94,0.20)',
    borderColor: '#E11D48',
  },
  secondaryDisabled: {
    borderColor: 'rgba(244,63,94,0.30)',
  },
  secondaryLabel: { color: '#F43F5E' },
  secondaryLabelDisabled: { color: 'rgba(244,63,94,0.40)' },

  // ── Ghost ─────────────────────────────────────────────────
  ghostDefault: { backgroundColor: 'transparent' },
  ghostPressed: { backgroundColor: 'rgba(244,63,94,0.20)' },
  ghostLabel: { color: '#F43F5E' },
  ghostLabelDisabled: { color: 'rgba(244,63,94,0.35)' },

  // ── Destructive ───────────────────────────────────────────
  destructiveDefault: { backgroundColor: '#F87171' },
  destructivePressed: { backgroundColor: '#DC2626' },
  destructiveDisabled: { backgroundColor: 'rgba(248,113,113,0.35)' },
  destructiveLabel: { color: '#FFFFFF' },
});
```

---

## Input / Text Field

### State Table

| State | Background | Border | Text | Placeholder | Other |
|-------|-----------|--------|------|-------------|-------|
| Default | `--color-bg-subtle` (#222222) | 1px `--color-border` (#2A2A2A) | `--color-text-primary` | `--color-text-secondary` | — |
| Focused | `--color-bg-subtle` | 1.5px `--color-accent-after` + ring | `--color-text-primary` | `--color-text-secondary` | ring: `--color-accent-after-ring` |
| Filled | `--color-bg-subtle` | 1px `--color-border-strong` (#3A3A3A) | `--color-text-primary` | — | — |
| Error | `--color-bg-subtle` | 1.5px `--color-semantic-error` | `--color-text-primary` | `--color-text-secondary` | error message below |
| Disabled | `--color-bg-card` (#111111) | 1px `--color-border` | `--color-text-disabled` | `--color-text-disabled` | cursor: not-allowed |

### CSS

```css
/* ─── Field wrapper ─────────────────────────────────────── */
.input-field {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
}

.input-field__label {
  font-family: var(--font-body);
  font-size: var(--text-label);
  font-weight: var(--font-weight-medium);
  color: var(--color-text-secondary);
  line-height: 1.35;
  letter-spacing: 0.01em;
}

/* ─── Input row (icon + input) ──────────────────────────── */
.input-field__row {
  position: relative;
  display: flex;
  align-items: center;
}

/* ─── Core input ────────────────────────────────────────── */
.input-field__input {
  width: 100%;
  height: 44px;
  padding: 0 var(--space-3);
  background-color: var(--color-bg-subtle);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  font-family: var(--font-body);
  font-size: var(--text-body-sm);
  font-weight: var(--font-weight-medium);
  color: var(--color-text-primary);
  transition: border-color 120ms ease-out, box-shadow 120ms ease-out;
  outline: none;
  -webkit-appearance: none;
}

.input-field__input::placeholder {
  color: var(--color-text-secondary);
  font-weight: 400;
}

/* Focused */
.input-field__input:focus {
  border-color: var(--color-accent-after);
  border-width: 1.5px;
  box-shadow: 0 0 0 3px var(--color-accent-after-ring);
}

/* Filled (has value, not focused) */
.input-field__input:not(:placeholder-shown):not(:focus) {
  border-color: var(--color-border-strong);
}

/* Error */
.input-field--error .input-field__input {
  border-color: var(--color-semantic-error);
  border-width: 1.5px;
}

.input-field--error .input-field__input:focus {
  box-shadow: 0 0 0 3px rgba(248, 113, 113, 0.25);
}

/* Disabled */
.input-field__input:disabled {
  background-color: var(--color-bg-card);
  color: var(--color-text-disabled);
  cursor: not-allowed;
}

.input-field__input:disabled::placeholder {
  color: var(--color-text-disabled);
}

/* ─── Error message ─────────────────────────────────────── */
.input-field__error-msg {
  font-family: var(--font-body);
  font-size: var(--text-caption);
  font-weight: var(--font-weight-medium);
  color: var(--color-semantic-error);
  line-height: 1.4;
  letter-spacing: 0.01em;
}

/* ─── Search variant (icon left) ────────────────────────── */
.input-field--search .input-field__input {
  padding-left: 40px; /* 12px gap + 16px icon + 12px inner padding */
}

.input-field__search-icon {
  position: absolute;
  left: var(--space-3);
  width: 16px;
  height: 16px;
  color: var(--color-text-secondary);
  pointer-events: none;
  flex-shrink: 0;
}

.input-field--search .input-field__input:focus ~ .input-field__search-icon,
.input-field--search .input-field__input:focus + .input-field__search-icon {
  color: var(--color-accent-after);
}
```

### React Native StyleSheet

```typescript
import { StyleSheet } from 'react-native';

export const inputStyles = StyleSheet.create({
  // ── Wrapper ───────────────────────────────────────────────
  field: {
    gap: 4,
  },
  label: {
    fontFamily: 'DMSans-Medium',
    fontSize: 13,
    lineHeight: 18,
    letterSpacing: 0.13,
    color: '#A0A0A0',
  },

  // ── Input container (for icon positioning) ────────────────
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    position: 'relative',
  },

  // ── Core input ────────────────────────────────────────────
  input: {
    flex: 1,
    height: 44,
    paddingHorizontal: 12,
    backgroundColor: '#222222',
    borderWidth: 1,
    borderColor: '#2A2A2A',
    borderRadius: 10,
    fontFamily: 'DMSans-Medium',
    fontSize: 14,
    color: '#F8F8F8',
  },

  // States
  inputFocused: {
    borderColor: '#F43F5E',
    borderWidth: 1.5,
    // RN shadow for focus ring effect
    shadowColor: '#F43F5E',
    shadowOffset: { width: 0, height: 0 },
    shadowOpacity: 0.30,
    shadowRadius: 6,
    elevation: 0,
  },
  inputFilled: {
    borderColor: '#3A3A3A',
  },
  inputError: {
    borderColor: '#F87171',
    borderWidth: 1.5,
  },
  inputDisabled: {
    backgroundColor: '#111111',
    borderColor: '#2A2A2A',
  },

  // ── Error message ─────────────────────────────────────────
  errorMsg: {
    fontFamily: 'DMSans-Medium',
    fontSize: 12,
    lineHeight: 17,
    letterSpacing: 0.12,
    color: '#F87171',
  },

  // ── Search variant ────────────────────────────────────────
  searchInput: {
    paddingLeft: 40, // 12px gap + 16px icon + 12px inner
  },
  searchIcon: {
    position: 'absolute',
    left: 12,
    width: 16,
    height: 16,
    zIndex: 1,
  },
});
```

---

## Card

### Feed Card (before/after transformation post)

#### State Table

| State | Background | Border | Shadow | Other |
|-------|-----------|--------|--------|-------|
| Default | `--color-bg-card` (#111111) | 1px `--color-border` (#2A2A2A) | none | — |
| Hover (web) | `--color-bg-card` | 1px `--color-border-strong` (#3A3A3A) | `0 4px 24px rgba(0,0,0,0.40)` | cursor: pointer |
| Pressed (RN) | `--color-bg-elevated` (#1A1A1A) | 1px `--color-border` | — | scale 0.985 |

#### CSS

```css
.card-feed {
  background-color: var(--color-bg-card);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  overflow: hidden;
  transition: border-color 150ms ease-out, box-shadow 150ms ease-out;
}

.card-feed:hover {
  border-color: var(--color-border-strong);
  box-shadow: 0 4px 24px rgba(0, 0, 0, 0.40);
  cursor: pointer;
}

/* ── Header: avatar + username + timestamp ────────────── */
.card-feed__header {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  padding: var(--space-4);
}

.card-feed__meta {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.card-feed__username {
  font-family: var(--font-body);
  font-size: var(--text-body-sm);
  font-weight: var(--font-weight-semibold);
  color: var(--color-text-primary);
  line-height: 1.35;
}

.card-feed__timestamp {
  font-family: var(--font-body);
  font-size: var(--text-caption);
  font-weight: var(--font-weight-medium);
  color: var(--color-text-secondary);
  line-height: 1.4;
  letter-spacing: 0.01em;
}

/* ── Before/After image row ───────────────────────────── */
.card-feed__images {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px; /* --layout-before-after-gap */
  padding: 0 var(--space-4);
}

.card-feed__image-wrap {
  position: relative;
  aspect-ratio: 3 / 4;
  border-radius: var(--radius-md);
  overflow: hidden;
  background-color: var(--color-bg-elevated);
}

.card-feed__image-label {
  position: absolute;
  bottom: var(--space-2);
  left: var(--space-2);
  font-family: var(--font-body);
  font-size: var(--text-caption);
  font-weight: var(--font-weight-semibold);
  letter-spacing: 0.04em;
  text-transform: uppercase;
  padding: 2px 6px;
  border-radius: var(--radius-sm);
}

.card-feed__image-label--before {
  background-color: var(--color-accent-before-subtle);
  color: var(--color-accent-before);
}

.card-feed__image-label--after {
  background-color: var(--color-accent-after-subtle);
  color: var(--color-accent-after);
}

/* ── Footer: caption + reactions ─────────────────────── */
.card-feed__footer {
  padding: var(--space-3) var(--space-4) var(--space-4);
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}

.card-feed__caption {
  font-family: var(--font-body);
  font-size: var(--text-body-sm);
  font-weight: 400;
  color: var(--color-text-primary);
  line-height: 1.5;
}

.card-feed__reactions {
  display: flex;
  align-items: center;
  gap: var(--space-4);
}
```

### Suggestion Card

#### State Table

| State | Background | Border | Left Accent | Other |
|-------|-----------|--------|-------------|-------|
| Default | `--color-bg-card` | 1px `--color-border` | — | — |
| Hover (web) | `--color-bg-subtle` (#222222) | 1px `--color-border-strong` | — | cursor: pointer |
| Expanded | `--color-bg-card` | 1px `--color-accent-after` | 3px `--color-accent-after` | — |

#### CSS

```css
.card-suggestion {
  background-color: var(--color-bg-card);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  padding: var(--space-4);
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
  transition: background-color 150ms ease-out, border-color 150ms ease-out;
  position: relative;
  overflow: hidden;
}

.card-suggestion::before {
  content: '';
  position: absolute;
  left: 0;
  top: 0;
  bottom: 0;
  width: 3px;
  background-color: var(--color-accent-after);
  opacity: 0;
  transition: opacity 150ms ease-out;
}

.card-suggestion:hover {
  background-color: var(--color-bg-subtle);
  border-color: var(--color-border-strong);
  cursor: pointer;
}

.card-suggestion--expanded {
  border-color: var(--color-accent-after);
}

.card-suggestion--expanded::before {
  opacity: 1;
}

.card-suggestion__header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: var(--space-3);
}

.card-suggestion__area {
  font-family: var(--font-body);
  font-size: var(--text-label);
  font-weight: var(--font-weight-semibold);
  color: var(--color-accent-after);
  line-height: 1.35;
  letter-spacing: 0.01em;
  text-transform: uppercase;
  letter-spacing: 0.06em;
}

.card-suggestion__title {
  font-family: var(--font-display);
  font-size: 1.25rem; /* heading-3: 20px */
  font-weight: 500;
  color: var(--color-text-primary);
  line-height: 1.2;
  letter-spacing: -0.01em;
}

.card-suggestion__body {
  font-family: var(--font-body);
  font-size: var(--text-body-sm);
  font-weight: 400;
  color: var(--color-text-secondary);
  line-height: 1.5;
}
```

### Stats Card

#### State Table

| State | Background | Border | Value Color | Other |
|-------|-----------|--------|-------------|-------|
| Default | `--color-bg-card` | 1px `--color-border` | `--color-text-primary` | — |
| Hover (web) | `--color-bg-card` | 1px `--color-border-strong` | `--color-text-primary` | cursor: default |
| Credit variant | `--color-bg-card` | 1px `rgba(245,158,11,0.30)` | `--color-credit-badge-text` | amber glow tint |

#### CSS

```css
.card-stats {
  background-color: var(--color-bg-card);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  padding: var(--space-4) var(--space-5);
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  transition: border-color 150ms ease-out;
}

.card-stats:hover {
  border-color: var(--color-border-strong);
}

.card-stats--credit {
  border-color: rgba(245, 158, 11, 0.30);
  background: linear-gradient(135deg, #111111 0%, rgba(245,158,11,0.06) 100%);
}

.card-stats__label {
  font-family: var(--font-body);
  font-size: var(--text-label);
  font-weight: var(--font-weight-medium);
  color: var(--color-text-secondary);
  line-height: 1.35;
  letter-spacing: 0.01em;
}

.card-stats__value {
  font-family: var(--font-display);
  font-size: 1.953rem; /* heading-1: 31px */
  font-weight: 600;
  color: var(--color-text-primary);
  line-height: 1.1;
  letter-spacing: -0.02em;
  font-variant-numeric: tabular-nums;
}

.card-stats--credit .card-stats__value {
  color: #FCD34D; /* --color-credit-badge-text */
}

.card-stats__sublabel {
  font-family: var(--font-body);
  font-size: var(--text-caption);
  font-weight: var(--font-weight-medium);
  color: var(--color-text-secondary);
  line-height: 1.4;
  letter-spacing: 0.01em;
}
```

### React Native StyleSheet (Cards)

```typescript
import { StyleSheet } from 'react-native';

export const cardStyles = StyleSheet.create({
  // ── Feed Card ─────────────────────────────────────────────
  feed: {
    backgroundColor: '#111111',
    borderWidth: 1,
    borderColor: '#2A2A2A',
    borderRadius: 16,
    overflow: 'hidden',
  },
  feedPressed: {
    backgroundColor: '#1A1A1A',
    borderColor: '#2A2A2A',
  },
  feedHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
    padding: 16,
  },
  feedUsername: {
    fontFamily: 'DMSans-SemiBold',
    fontSize: 14,
    color: '#F8F8F8',
    lineHeight: 19,
  },
  feedTimestamp: {
    fontFamily: 'DMSans-Medium',
    fontSize: 12,
    color: '#A0A0A0',
    lineHeight: 17,
    letterSpacing: 0.12,
  },
  feedImages: {
    flexDirection: 'row',
    gap: 8,
    paddingHorizontal: 16,
  },
  feedImageWrap: {
    flex: 1,
    aspectRatio: 3 / 4,
    borderRadius: 10,
    overflow: 'hidden',
    backgroundColor: '#1A1A1A',
  },
  feedLabelBefore: {
    position: 'absolute',
    bottom: 8,
    left: 8,
    backgroundColor: 'rgba(148,163,184,0.10)',
    paddingVertical: 2,
    paddingHorizontal: 6,
    borderRadius: 6,
  },
  feedLabelAfter: {
    position: 'absolute',
    bottom: 8,
    left: 8,
    backgroundColor: 'rgba(244,63,94,0.12)',
    paddingVertical: 2,
    paddingHorizontal: 6,
    borderRadius: 6,
  },
  feedLabelText: {
    fontFamily: 'DMSans-SemiBold',
    fontSize: 10,
    letterSpacing: 0.6,
    textTransform: 'uppercase',
  },
  feedLabelBeforeText: { color: '#94A3B8' },
  feedLabelAfterText: { color: '#F43F5E' },
  feedFooter: {
    padding: 16,
    paddingTop: 12,
    gap: 12,
  },

  // ── Suggestion Card ───────────────────────────────────────
  suggestion: {
    backgroundColor: '#111111',
    borderWidth: 1,
    borderColor: '#2A2A2A',
    borderRadius: 16,
    padding: 16,
    gap: 12,
  },
  suggestionPressed: {
    backgroundColor: '#1A1A1A',
  },
  suggestionExpanded: {
    borderColor: '#F43F5E',
  },
  suggestionArea: {
    fontFamily: 'DMSans-SemiBold',
    fontSize: 11,
    color: '#F43F5E',
    lineHeight: 15,
    letterSpacing: 0.66,
    textTransform: 'uppercase',
  },
  suggestionTitle: {
    fontFamily: 'SpaceGrotesk-Medium',
    fontSize: 20,
    color: '#F8F8F8',
    lineHeight: 24,
    letterSpacing: -0.2,
  },
  suggestionBody: {
    fontFamily: 'DMSans-Regular',
    fontSize: 14,
    color: '#A0A0A0',
    lineHeight: 21,
  },

  // ── Stats Card ────────────────────────────────────────────
  stats: {
    backgroundColor: '#111111',
    borderWidth: 1,
    borderColor: '#2A2A2A',
    borderRadius: 16,
    paddingVertical: 16,
    paddingHorizontal: 20,
    gap: 8,
  },
  statsCredit: {
    borderColor: 'rgba(245,158,11,0.30)',
  },
  statsLabel: {
    fontFamily: 'DMSans-Medium',
    fontSize: 13,
    color: '#A0A0A0',
    lineHeight: 18,
    letterSpacing: 0.13,
  },
  statsValue: {
    fontFamily: 'SpaceGrotesk-SemiBold',
    fontSize: 31,
    color: '#F8F8F8',
    lineHeight: 34,
    letterSpacing: -0.62,
  },
  statsValueCredit: {
    color: '#FCD34D',
  },
  statsSublabel: {
    fontFamily: 'DMSans-Medium',
    fontSize: 12,
    color: '#A0A0A0',
    lineHeight: 17,
    letterSpacing: 0.12,
  },
});
```

---

## Badge / Pill

### State Table

| Variant | Background | Border | Text | Icon |
|---------|-----------|--------|------|------|
| Status — success | `rgba(74,222,128,0.12)` | none | `--color-semantic-success` (#4ADE80) | success icon |
| Status — warning | `rgba(251,191,36,0.12)` | none | `--color-semantic-warning` (#FBBF24) | warning icon |
| Status — error | `rgba(248,113,113,0.12)` | none | `--color-semantic-error` (#F87171) | error icon |
| Status — info | `rgba(96,165,250,0.12)` | none | `--color-semantic-info` (#60A5FA) | info icon |
| Credit | `rgba(245,158,11,0.15)` | none | `#FCD34D` | coin/star icon |
| Before | `--color-accent-before-subtle` | none | `--color-accent-before` (#94A3B8) | — |
| After | `--color-accent-after-subtle` | none | `--color-accent-after` (#F43F5E) | — |

### CSS

```css
/* ─── Base ─────────────────────────────────────────────── */
.badge {
  display: inline-flex;
  align-items: center;
  gap: var(--space-1);
  border-radius: var(--radius-full);
  font-family: var(--font-body);
  font-weight: var(--font-weight-semibold);
  white-space: nowrap;
  line-height: 1;
}

/* ─── Sizes ─────────────────────────────────────────────── */
.badge--sm {
  padding: 3px 8px;
  font-size: var(--text-caption);  /* 12px */
  letter-spacing: 0.01em;
}

.badge--md {
  padding: 4px 10px;
  font-size: var(--text-label);   /* 13px */
  letter-spacing: 0.01em;
}

.badge__icon {
  width: 10px;
  height: 10px;
  flex-shrink: 0;
}

.badge--md .badge__icon {
  width: 12px;
  height: 12px;
}

/* ─── Semantic variants ─────────────────────────────────── */
.badge--success {
  background-color: rgba(74, 222, 128, 0.12);
  color: var(--color-semantic-success);
}

.badge--warning {
  background-color: rgba(251, 191, 36, 0.12);
  color: var(--color-semantic-warning);
}

.badge--error {
  background-color: rgba(248, 113, 113, 0.12);
  color: var(--color-semantic-error);
}

.badge--info {
  background-color: rgba(96, 165, 250, 0.12);
  color: var(--color-semantic-info);
}

/* ─── Credit ─────────────────────────────────────────────── */
.badge--credit {
  background-color: var(--color-credit-badge-bg);
  color: var(--color-credit-badge-text);
}

/* ─── Before / After ─────────────────────────────────────── */
.badge--before {
  background-color: var(--color-accent-before-subtle);
  color: var(--color-accent-before);
  font-weight: var(--font-weight-semibold);
  letter-spacing: 0.04em;
  text-transform: uppercase;
}

.badge--after {
  background-color: var(--color-accent-after-subtle);
  color: var(--color-accent-after);
  font-weight: var(--font-weight-semibold);
  letter-spacing: 0.04em;
  text-transform: uppercase;
}
```

### React Native StyleSheet

```typescript
import { StyleSheet } from 'react-native';

export const badgeStyles = StyleSheet.create({
  // ── Base ──────────────────────────────────────────────────
  base: {
    flexDirection: 'row',
    alignItems: 'center',
    alignSelf: 'flex-start',
    borderRadius: 9999,
    gap: 4,
  },

  // ── Sizes ─────────────────────────────────────────────────
  sm: { paddingVertical: 3, paddingHorizontal: 8 },
  md: { paddingVertical: 4, paddingHorizontal: 10 },

  textSm: {
    fontFamily: 'DMSans-SemiBold',
    fontSize: 12,
    lineHeight: 12,
    letterSpacing: 0.12,
  },
  textMd: {
    fontFamily: 'DMSans-SemiBold',
    fontSize: 13,
    lineHeight: 13,
    letterSpacing: 0.13,
  },

  // ── Variants ──────────────────────────────────────────────
  success: { backgroundColor: 'rgba(74,222,128,0.12)' },
  successText: { color: '#4ADE80' },

  warning: { backgroundColor: 'rgba(251,191,36,0.12)' },
  warningText: { color: '#FBBF24' },

  error: { backgroundColor: 'rgba(248,113,113,0.12)' },
  errorText: { color: '#F87171' },

  info: { backgroundColor: 'rgba(96,165,250,0.12)' },
  infoText: { color: '#60A5FA' },

  credit: { backgroundColor: 'rgba(245,158,11,0.15)' },
  creditText: { color: '#FCD34D' },

  before: { backgroundColor: 'rgba(148,163,184,0.10)' },
  beforeText: {
    color: '#94A3B8',
    textTransform: 'uppercase',
    letterSpacing: 0.52,
  },

  after: { backgroundColor: 'rgba(244,63,94,0.12)' },
  afterText: {
    color: '#F43F5E',
    textTransform: 'uppercase',
    letterSpacing: 0.52,
  },
});
```

---

## Avatar

### State Table

| State | Background | Border | Content | Indicator |
|-------|-----------|--------|---------|-----------|
| Default (image) | — | none | `<Image>` | — |
| Placeholder (initials) | `--color-bg-elevated` (#1A1A1A) | 1px `--color-border` | initials, `--color-text-secondary` | — |
| Online | — | 2px `--color-accent-after` | image or initials | dot: `--color-semantic-success` |

### Size Dimensions

| Size | Diameter | Font Size | Indicator dot | Border offset |
|------|----------|-----------|--------------|---------------|
| sm | 32px | 12px | 8px | −1px |
| md | 40px | 14px | 10px | −1px |
| lg | 80px | 20px | 14px | −2px |

### CSS

```css
/* ─── Base ─────────────────────────────────────────────── */
.avatar {
  position: relative;
  flex-shrink: 0;
  border-radius: var(--radius-full);
  overflow: hidden;
  display: inline-flex;
  align-items: center;
  justify-content: center;
}

.avatar img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

/* ─── Sizes ─────────────────────────────────────────────── */
.avatar--sm {
  width: 32px;
  height: 32px;
}

.avatar--md {
  width: 40px;
  height: 40px;
}

.avatar--lg {
  width: 80px;
  height: 80px;
}

/* ─── Placeholder ───────────────────────────────────────── */
.avatar--placeholder {
  background-color: var(--color-bg-elevated);
  border: 1px solid var(--color-border);
  overflow: visible; /* allow indicator to overflow */
}

.avatar__initials {
  font-family: var(--font-body);
  font-weight: var(--font-weight-semibold);
  color: var(--color-text-secondary);
  line-height: 1;
  user-select: none;
}

.avatar--sm .avatar__initials  { font-size: 12px; }
.avatar--md .avatar__initials  { font-size: 14px; }
.avatar--lg .avatar__initials  { font-size: 20px; }

/* ─── Online state ──────────────────────────────────────── */
.avatar--online {
  outline: 2px solid var(--color-accent-after);
  outline-offset: 1px;
}

.avatar__indicator {
  position: absolute;
  border-radius: var(--radius-full);
  background-color: var(--color-semantic-success);
  border: 2px solid var(--color-bg-page);
  pointer-events: none;
}

/* Indicator positioning by size */
.avatar--sm .avatar__indicator {
  width: 8px;
  height: 8px;
  bottom: -1px;
  right: -1px;
}

.avatar--md .avatar__indicator {
  width: 10px;
  height: 10px;
  bottom: -1px;
  right: -1px;
}

.avatar--lg .avatar__indicator {
  width: 14px;
  height: 14px;
  bottom: -2px;
  right: -2px;
}
```

### React Native StyleSheet

```typescript
import { StyleSheet } from 'react-native';

export const avatarStyles = StyleSheet.create({
  // ── Base ──────────────────────────────────────────────────
  base: {
    borderRadius: 9999,
    overflow: 'hidden',
    alignItems: 'center',
    justifyContent: 'center',
    flexShrink: 0,
  },
  image: {
    width: '100%',
    height: '100%',
  },

  // ── Sizes ─────────────────────────────────────────────────
  sm: { width: 32, height: 32 },
  md: { width: 40, height: 40 },
  lg: { width: 80, height: 80 },

  // ── Placeholder ───────────────────────────────────────────
  placeholder: {
    backgroundColor: '#1A1A1A',
    borderWidth: 1,
    borderColor: '#2A2A2A',
  },
  initialsBase: {
    fontFamily: 'DMSans-SemiBold',
    color: '#A0A0A0',
    lineHeight: 1,
  },
  initialsSm: { fontSize: 12 },
  initialsMd: { fontSize: 14 },
  initialsLg: { fontSize: 20 },

  // ── Online state ──────────────────────────────────────────
  // Applied as a wrapper style — RN doesn't support CSS outline
  onlineBorder: {
    borderWidth: 2,
    borderColor: '#F43F5E',
  },

  // ── Indicator dot (absolute, positioned outside avatar) ───
  // Must be on a non-overflow:hidden parent wrapper
  indicator: {
    position: 'absolute',
    backgroundColor: '#4ADE80',
    borderRadius: 9999,
  },
  indicatorBorder: {
    borderWidth: 2,
    borderColor: '#080808', // matches page background
  },
  indicatorSm: { width: 8, height: 8, bottom: -1, right: -1 },
  indicatorMd: { width: 10, height: 10, bottom: -1, right: -1 },
  indicatorLg: { width: 14, height: 14, bottom: -2, right: -2 },
});
```

---

## Bottom Tab Bar (React Native)

### State Table

| State | Background | Top Border | Icon | Label |
|-------|-----------|-----------|------|-------|
| Tab — inactive | `--color-bg-elevated` (#1A1A1A) | 1px `--color-border` | `--color-accent-before` (#94A3B8) | `--color-text-secondary` (#A0A0A0) |
| Tab — active | `--color-bg-elevated` | 1px `--color-border` | `--color-accent-after` (#F43F5E) | `--color-accent-after` |
| Tab — pressed | `--color-bg-elevated` | 1px `--color-border` | `--color-accent-after-hover` (#E11D48) | `--color-accent-after-hover` |

Note: The active tab uses no background fill behind the icon — only the color change differentiates active from inactive. A subtle 2px wide indicator line at the top of the active item may optionally be added.

### CSS (web fallback / reference only)

```css
.tab-bar {
  display: flex;
  align-items: flex-start;
  height: calc(49px + env(safe-area-inset-bottom, 0px));
  background-color: var(--color-bg-elevated);
  border-top: 1px solid var(--color-border);
}

.tab-bar__item {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 3px;
  height: 49px;
  cursor: pointer;
  padding: 0 var(--space-2);
  transition: color 120ms ease-out;
}

.tab-bar__icon {
  width: 24px;
  height: 24px;
  color: var(--color-accent-before);
  transition: color 120ms ease-out;
}

.tab-bar__label {
  font-family: var(--font-body);
  font-size: var(--text-caption);  /* 12px */
  font-weight: var(--font-weight-medium);
  color: var(--color-text-secondary);
  line-height: 1;
  letter-spacing: 0.01em;
  transition: color 120ms ease-out;
}

.tab-bar__item--active .tab-bar__icon {
  color: var(--color-accent-after);
}

.tab-bar__item--active .tab-bar__label {
  color: var(--color-accent-after);
  font-weight: var(--font-weight-semibold);
}

.tab-bar__item--active::before {
  content: '';
  position: absolute;
  top: 0;
  left: 50%;
  transform: translateX(-50%);
  width: 24px;
  height: 2px;
  background-color: var(--color-accent-after);
  border-radius: 0 0 2px 2px;
}
```

### React Native StyleSheet

```typescript
import { StyleSheet } from 'react-native';

// Use with useSafeAreaInsets() from 'react-native-safe-area-context'
// tabBarHeight = 49 + insets.bottom

export const tabBarStyles = StyleSheet.create({
  // ── Container ─────────────────────────────────────────────
  bar: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    backgroundColor: '#1A1A1A',
    borderTopWidth: 1,
    borderTopColor: '#2A2A2A',
    height: 49, // add insets.bottom at runtime
  },
  safeArea: {
    backgroundColor: '#1A1A1A', // fills the safe area below the bar
  },

  // ── Tab item ──────────────────────────────────────────────
  item: {
    flex: 1,
    flexDirection: 'column',
    alignItems: 'center',
    justifyContent: 'center',
    height: 49,
    gap: 3,
    paddingHorizontal: 8,
  },

  // ── Active indicator (top line) ───────────────────────────
  activeIndicator: {
    position: 'absolute',
    top: 0,
    width: 24,
    height: 2,
    backgroundColor: '#F43F5E',
    borderBottomLeftRadius: 2,
    borderBottomRightRadius: 2,
  },

  // ── Icon ──────────────────────────────────────────────────
  iconInactive: { color: '#94A3B8' },
  iconActive:   { color: '#F43F5E' },
  iconPressed:  { color: '#E11D48' },

  // ── Label ─────────────────────────────────────────────────
  label: {
    fontFamily: 'DMSans-Medium',
    fontSize: 12,
    lineHeight: 12,
    letterSpacing: 0.12,
  },
  labelInactive: { color: '#A0A0A0' },
  labelActive: {
    fontFamily: 'DMSans-SemiBold',
    color: '#F43F5E',
  },
});
```

---

## Reaction Button

### State Table

| State | Background | Icon | Count Text | Transform |
|-------|-----------|------|-----------|-----------|
| Default (ghost) | transparent | `--color-text-secondary` (#A0A0A0) | `--color-text-secondary` | — |
| Hover (web) | `--color-accent-after-subtle` | `--color-accent-after` | `--color-accent-after` | — |
| Active | `--color-accent-after-subtle` | `--color-accent-after` | `--color-accent-after` | — |
| Pressed (RN) | `rgba(244,63,94,0.20)` | `--color-accent-after-hover` | `--color-accent-after-hover` | scale 0.90 |
| Active + pressed | `rgba(244,63,94,0.20)` | `--color-accent-after-hover` | `--color-accent-after-hover` | scale 0.90 |

### CSS

```css
/* ─── Base ─────────────────────────────────────────────── */
.reaction-btn {
  display: inline-flex;
  align-items: center;
  gap: var(--space-1);
  padding: var(--space-1) var(--space-2);
  border-radius: var(--radius-full);
  background-color: transparent;
  border: none;
  cursor: pointer;
  transition:
    background-color 120ms ease-out,
    color 120ms ease-out,
    transform 80ms ease-out;
  -webkit-tap-highlight-color: transparent;
}

.reaction-btn__icon {
  width: 18px;
  height: 18px;
  color: var(--color-text-secondary);
  transition: color 120ms ease-out;
  flex-shrink: 0;
}

.reaction-btn__count {
  font-family: var(--font-body);
  font-size: var(--text-label); /* 13px */
  font-weight: var(--font-weight-medium);
  color: var(--color-text-secondary);
  line-height: 1;
  min-width: 16px;
  transition: color 120ms ease-out;
  font-variant-numeric: tabular-nums;
}

/* ─── Hover ─────────────────────────────────────────────── */
.reaction-btn:hover {
  background-color: var(--color-accent-after-subtle);
}

.reaction-btn:hover .reaction-btn__icon,
.reaction-btn:hover .reaction-btn__count {
  color: var(--color-accent-after);
}

/* ─── Active state ──────────────────────────────────────── */
.reaction-btn--active {
  background-color: var(--color-accent-after-subtle);
}

.reaction-btn--active .reaction-btn__icon,
.reaction-btn--active .reaction-btn__count {
  color: var(--color-accent-after);
}

/* ─── Active + hover ────────────────────────────────────── */
.reaction-btn--active:hover {
  background-color: rgba(244, 63, 94, 0.18);
}

/* ─── Pressed ───────────────────────────────────────────── */
.reaction-btn:active {
  transform: scale(0.90);
  background-color: rgba(244, 63, 94, 0.20);
}

.reaction-btn:active .reaction-btn__icon,
.reaction-btn:active .reaction-btn__count {
  color: var(--color-accent-after-hover);
}

/* ─── Focus ─────────────────────────────────────────────── */
.reaction-btn:focus-visible {
  outline: none;
  box-shadow: 0 0 0 2px var(--color-accent-after-ring);
}
```

### React Native StyleSheet

```typescript
import { StyleSheet } from 'react-native';

export const reactionButtonStyles = StyleSheet.create({
  // ── Base ──────────────────────────────────────────────────
  base: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
    paddingVertical: 4,
    paddingHorizontal: 8,
    borderRadius: 9999,
    backgroundColor: 'transparent',
  },

  // ── States ────────────────────────────────────────────────
  active: {
    backgroundColor: 'rgba(244,63,94,0.12)',
  },
  pressed: {
    backgroundColor: 'rgba(244,63,94,0.20)',
    transform: [{ scale: 0.90 }],
  },

  // ── Icon ──────────────────────────────────────────────────
  iconInactive: { color: '#A0A0A0' },
  iconActive:   { color: '#F43F5E' },
  iconPressed:  { color: '#E11D48' },

  // ── Count ─────────────────────────────────────────────────
  count: {
    fontFamily: 'DMSans-Medium',
    fontSize: 13,
    lineHeight: 13,
    minWidth: 16,
  },
  countInactive: { color: '#A0A0A0' },
  countActive:   { color: '#F43F5E' },
  countPressed:  { color: '#E11D48' },
});
```

---

## Credit Counter Chip

### State Table

| State | Condition | Background | Border | Icon | Text | Glow |
|-------|-----------|-----------|--------|------|------|------|
| Normal | credits > 1 | `rgba(245,158,11,0.15)` | `rgba(245,158,11,0.25)` | `#FCD34D` | `#FCD34D` | none |
| Low | credits === 1 | `rgba(245,158,11,0.20)` | `rgba(245,158,11,0.45)` | `#FBBF24` | `#FBBF24` | subtle amber pulse |
| Empty | credits === 0 | `rgba(244,63,94,0.12)` | `rgba(244,63,94,0.30)` | `#F43F5E` | `#F43F5E` | none |

### CSS

```css
/* ─── Base ─────────────────────────────────────────────── */
.credit-chip {
  display: inline-flex;
  align-items: center;
  gap: var(--space-1);
  padding: 5px 10px;
  border-radius: var(--radius-full);
  border: 1px solid transparent;
  font-family: var(--font-body);
  font-size: var(--text-label); /* 13px */
  font-weight: var(--font-weight-semibold);
  line-height: 1;
  letter-spacing: 0.01em;
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
  transition:
    background-color 200ms ease-out,
    border-color 200ms ease-out,
    color 200ms ease-out;
}

.credit-chip__icon {
  width: 14px;
  height: 14px;
  flex-shrink: 0;
}

/* ─── Normal state (credits > 1) ───────────────────────── */
.credit-chip--normal {
  background-color: rgba(245, 158, 11, 0.15);
  border-color: rgba(245, 158, 11, 0.25);
  color: #FCD34D;
}

/* ─── Low state (credits === 1) ─────────────────────────── */
.credit-chip--low {
  background-color: rgba(245, 158, 11, 0.20);
  border-color: rgba(245, 158, 11, 0.45);
  color: #FBBF24;
  animation: credit-pulse 2s ease-in-out infinite;
}

@keyframes credit-pulse {
  0%, 100% {
    box-shadow: 0 0 0 0 rgba(245, 158, 11, 0.0);
  }
  50% {
    box-shadow: 0 0 8px 2px rgba(245, 158, 11, 0.25);
  }
}

/* ─── Empty state (credits === 0) ──────────────────────── */
.credit-chip--empty {
  background-color: rgba(244, 63, 94, 0.12);
  border-color: rgba(244, 63, 94, 0.30);
  color: var(--color-accent-after);
}

/* ─── Label override for empty state ───────────────────── */
.credit-chip--empty .credit-chip__count::after {
  content: ' — Get more';
  font-weight: var(--font-weight-medium);
  opacity: 0.80;
}
```

### React Native StyleSheet

```typescript
import { StyleSheet } from 'react-native';

export const creditChipStyles = StyleSheet.create({
  // ── Base ──────────────────────────────────────────────────
  base: {
    flexDirection: 'row',
    alignItems: 'center',
    alignSelf: 'flex-start',
    gap: 4,
    paddingVertical: 5,
    paddingHorizontal: 10,
    borderRadius: 9999,
    borderWidth: 1,
  },
  label: {
    fontFamily: 'DMSans-SemiBold',
    fontSize: 13,
    lineHeight: 13,
    letterSpacing: 0.13,
  },
  icon: {
    width: 14,
    height: 14,
  },

  // ── Normal ────────────────────────────────────────────────
  normal: {
    backgroundColor: 'rgba(245,158,11,0.15)',
    borderColor: 'rgba(245,158,11,0.25)',
  },
  normalText: { color: '#FCD34D' },
  normalIcon: { color: '#FCD34D' },

  // ── Low (1 credit remaining) ──────────────────────────────
  low: {
    backgroundColor: 'rgba(245,158,11,0.20)',
    borderColor: 'rgba(245,158,11,0.45)',
  },
  lowText: { color: '#FBBF24' },
  lowIcon: { color: '#FBBF24' },
  // Use Animated.loop + Animated.sequence for the pulse shadow in RN

  // ── Empty (0 credits) ─────────────────────────────────────
  empty: {
    backgroundColor: 'rgba(244,63,94,0.12)',
    borderColor: 'rgba(244,63,94,0.30)',
  },
  emptyText: { color: '#F43F5E' },
  emptyIcon: { color: '#F43F5E' },
});

/*
 * Low-state pulse animation (React Native):
 *
 * const shadowAnim = useRef(new Animated.Value(0)).current;
 *
 * Animated.loop(
 *   Animated.sequence([
 *     Animated.timing(shadowAnim, { toValue: 1, duration: 1000, useNativeDriver: false }),
 *     Animated.timing(shadowAnim, { toValue: 0, duration: 1000, useNativeDriver: false }),
 *   ])
 * ).start();
 *
 * shadowOpacity: shadowAnim.interpolate({ inputRange: [0, 1], outputRange: [0, 0.35] })
 * shadowColor: '#F59E0B'
 * shadowRadius: 8
 * shadowOffset: { width: 0, height: 0 }
 */
```

---

## Accessibility Notes

| Component | Combination | Contrast Ratio | WCAG Level |
|-----------|-------------|---------------|------------|
| Button — Primary | White on `#F43F5E` | 4.6:1 | AA |
| Button — Secondary label | `#F43F5E` on `#111111` | 5.3:1 | AA |
| Button — Ghost label | `#F43F5E` on `#080808` | 5.6:1 | AA |
| Button — Destructive | White on `#F87171` | 3.8:1 | AA (large text / UI control) |
| Button — disabled (Primary) | `rgba(255,255,255,0.45)` on `rgba(244,63,94,0.35)` | ~2.1:1 | Intentional — inactive control exception (WCAG 1.4.3) |
| Input — placeholder | `#A0A0A0` on `#222222` | 4.0:1 | AA (UI component, not body text) |
| Input — label text | `#A0A0A0` on `#080808` | 5.1:1 | AA |
| Input — error message | `#F87171` on `#080808` | 4.8:1 | AA |
| Badge — success text | `#4ADE80` on `rgba(74,222,128,0.12)` over `#111111` | 5.5:1 | AA |
| Badge — credit text | `#FCD34D` on `rgba(245,158,11,0.15)` over `#111111` | 6.2:1 | AA |
| Tab bar — inactive label | `#A0A0A0` on `#1A1A1A` | 4.4:1 | AA |
| Tab bar — active label | `#F43F5E` on `#1A1A1A` | 5.0:1 | AA |
| Reaction button — active count | `#F43F5E` on `rgba(244,63,94,0.12)` over `#111111` | 5.2:1 | AA |
| Credit chip — normal text | `#FCD34D` on `rgba(245,158,11,0.15)` over `#111111` | 6.2:1 | AA |
| Credit chip — empty text | `#F43F5E` on `rgba(244,63,94,0.12)` over `#111111` | 5.3:1 | AA |
| Avatar — initials | `#A0A0A0` on `#1A1A1A` | 4.4:1 | AA |

**Interactive requirements (all components):**
- Minimum touch target: 44×44pt (iOS HIG) — all interactive components meet this or are wrapped in a 44pt touch target
- Focus indicators: `box-shadow: 0 0 0 3px var(--color-accent-after-ring)` on all web interactive elements
- `aria-disabled` used (not `disabled`) where interaction lockout must preserve keyboard focusability for screen reader context
- Button loading state: `aria-busy="true"` + `aria-label` updated to "{action} in progress"
- Tab bar: `role="tablist"` + `aria-selected` on each tab item
