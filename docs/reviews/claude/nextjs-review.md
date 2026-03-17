# Next.js Card Web Review
- Date: 2026-03-17
- Scope: card-web/**/*

---

## Findings

### Critical

**C-1: Wildcard `remotePatterns` in `next.config.mjs` — open redirect / SSRF surface**

`next/image` is configured with `hostname: '**'`, which allows any external host to be proxied through the Next.js image optimisation endpoint. An attacker can craft a URL that causes the Next.js server to fetch and transcode an arbitrary external resource (SSRF), and legitimate users can be served images from untrusted domains that appear to originate from the NXME card domain (phishing / brand abuse). The fix is to restrict `remotePatterns` to the specific hostnames used by Supabase Storage and the fal.ai CDN.

File: `/Users/vladimirtrifonov/src/ai/nxme.ai/card-web/next.config.mjs`

```js
// Current — dangerous
{ protocol: 'https', hostname: '**' }

// Replace with explicit patterns, e.g.:
{ protocol: 'https', hostname: '*.supabase.co' },
{ protocol: 'https', hostname: '*.fal.ai' },
{ protocol: 'https', hostname: 'fal.media' },
```

---

**C-2: `getCardData` fetch uses `NEXT_PUBLIC_API_URL` — server-side secret leakage risk**

`API_BASE_URL` is built from `process.env.NEXT_PUBLIC_API_URL`. The `NEXT_PUBLIC_` prefix causes Next.js to inline the value into the client-side JavaScript bundle. If this URL is an internal/private backend address it will be exposed to every browser that downloads the page. Backend API calls from Server Components should use a server-only env variable (no `NEXT_PUBLIC_` prefix). The current arrangement also means the constant is read at module evaluation time, so any misconfiguration only surfaces at runtime, not at build.

File: `/Users/vladimirtrifonov/src/ai/nxme.ai/card-web/src/config/constants.ts` line 27

---

### High

**H-1: `error.tsx` is not a route-segment error boundary — it will never be shown for the card route**

The file lives at `src/app/error.tsx` (root segment). The card page is at `src/app/[username]/page.tsx`. Next.js App Router requires an `error.tsx` co-located in the same segment (`src/app/[username]/error.tsx`) for it to catch errors thrown by that page. The root `error.tsx` only catches errors from the root segment. Without a segment-level boundary, a thrown error in `getCardData` (e.g., a 500 from the backend) will propagate to the root `not-found` or a generic Next.js error page, not to the custom UI with the "Try again" button.

Fix: add `src/app/[username]/error.tsx` (can re-use the same component body).

---

**H-2: `PageProps` uses synchronous `params` — breaks Next.js 15 async params contract**

`params` is typed as `{ username: string }` and accessed synchronously in both `generateMetadata` and `CardPage`. In Next.js 15 (and already in Next.js 14.2+ with the experimental async-params flag) `params` is a `Promise<{ username: string }>` that must be awaited. The code is currently safe only because the project targets Next.js 14.2.29, but this will become a runtime error on upgrade and Next.js 14.2 already emits a deprecation warning. Adding `Promise<…>` wrapping to the type and awaiting it now prevents a silent breakage on upgrade.

File: `/Users/vladimirtrifonov/src/ai/nxme.ai/card-web/src/app/[username]/page.tsx` line 18-19

---

**H-3: `CtaButton` CLA layout-shift — opacity-0 hides the primary conversion action until hydration**

The CTA button renders as `opacity-0 pointer-events-none` before the component mounts. On a slow connection, users see no download button for the entire hydration window. This directly harms Cumulative Layout Shift (CLS) and Time to Interactive (TTI) scores, and it means the primary monetisation action is invisible to users on slow 3G. The platform-detection logic requires the client, but the button's existence and styling do not. The recommended pattern is to render a server-side default href (App Store or a universal link) and only swap the click-handler on mount, keeping the button visible and tappable throughout.

File: `/Users/vladimirtrifonov/src/ai/nxme.ai/card-web/src/components/cta-button.tsx` line 95

---

**H-4: OG image fetches card data on every request with no caching hint**

`opengraph-image.tsx` calls `getCardData(params.username)` without any `next: { revalidate }` option on its internal fetch. The page itself sets `export const revalidate = 60`, but that export applies only to the page route, not to the `opengraph-image` route handler. Each social crawler or link-preview fetch triggers a cold backend request, which can be slow and costly under viral traffic. Add `export const revalidate = CARD_REVALIDATE_SECONDS` to `opengraph-image.tsx`.

File: `/Users/vladimirtrifonov/src/ai/nxme.ai/card-web/src/app/[username]/opengraph-image.tsx`

---

### Medium

**M-1: `tsconfig.json` missing `exactOptionalPropertyTypes`**

The project correctly enables `strict`, `noUncheckedIndexedAccess`, `noImplicitReturns`, `noFallthroughCasesInSwitch`, `noUnusedLocals`, and `noUnusedParameters`. The one missing strict setting from the project baseline (`.claude/rules/config-deviation.md`) is `exactOptionalPropertyTypes: true`, which distinguishes `{ prop?: string }` (property absent) from `{ prop: string | undefined }` (property present but undefined). Without it, TypeScript accepts silent undefined passing that can reach API calls or rendering code.

File: `/Users/vladimirtrifonov/src/ai/nxme.ai/card-web/tsconfig.json`

---

**M-2: ESLint configured at baseline only — `@typescript-eslint/strict` not extended**

`.eslintrc.json` extends `next/core-web-vitals` and `next/typescript` only. Per the project Node.js/TypeScript rules, `@typescript-eslint/strict` should also be included. The missing rules allow patterns like unsafe `any` casts, unconstrained generics, and non-null assertions to pass lint. `eslint-plugin-import` is also absent, so import order is not enforced.

File: `/Users/vladimirtrifonov/src/ai/nxme.ai/card-web/.eslintrc.json`

---

**M-3: `globals.css` removes all `:focus` outlines globally**

```css
*:focus { outline: none; }
```

This strips the native browser focus indicator from every element. While individual interactive components use `focus-visible:ring-*` classes, any element that lacks an explicit Tailwind focus style (including third-party components added in the future) will have no visible focus indicator, violating WCAG 2.1 SC 2.4.7 (Focus Visible). The safer fix is to remove the global rule and rely solely on component-level `focus-visible` styles, which already exist throughout the codebase.

File: `/Users/vladimirtrifonov/src/ai/nxme.ai/card-web/src/app/globals.css` line 34-36

---

**M-4: OG metadata in `[username]/page.tsx` points to `after_image_url` directly — dimensions not verified**

The `openGraph.images` array sets `width: OG_IMAGE_WIDTH` (1200) and `height: OG_IMAGE_HEIGHT` (630) for `card.after_image_url`. However, the actual after-image from fal.ai will be a portrait crop (likely 3:4 or 1:1), not 1200x630. Social crawlers use declared dimensions to decide how to layout the preview card; mismatched dimensions can cause the image to be rejected or shown as a thumbnail instead of `summary_large_image`. The `opengraph-image.tsx` (Satori composite) is the correct OG image source for this page and the static `openGraph` metadata block in `page.tsx` should reference the generated OG image URL, or omit the explicit image entirely and let Next.js wire the `opengraph-image.tsx` output automatically.

File: `/Users/vladimirtrifonov/src/ai/nxme.ai/card-web/src/app/[username]/page.tsx` lines 48-58

---

**M-5: No `sitemap.ts` or `robots.ts`**

The `public/` directory is empty and there is no `src/app/sitemap.ts` or `src/app/robots.ts`. Without a `robots.txt`, crawlers use their defaults (which may differ). Without a sitemap, card URLs are only discoverable through backlinks. For a shareable-card use case where SEO discoverability is a key goal, both should be present. The sitemap can be dynamic (fetching popular/public card usernames from the backend) or at minimum a static file listing the root.

---

**M-6: No `Content-Security-Policy` header**

There is no `next.config.mjs` `headers()` export and no middleware setting a `Content-Security-Policy`. The app loads external images from arbitrary CDN hostnames (currently unrestricted, see C-1), renders user-controlled text from the API (`display_name`, `suggestion`), and executes client-side JavaScript for deep-link handling. A CSP would mitigate XSS impact and is expected for a production public-facing web app.

---

**M-7: `APP_OPEN_TIMEOUT_MS` is a file-level magic number in `cta-button.tsx`**

```ts
const APP_OPEN_TIMEOUT_MS = 1500;
```

This is defined as a local `const` inside the component file rather than as a named export in `src/config/constants.ts`. Per project conventions, all business-meaningful literals must live in the constants/config layer. This particular value controls the user experience window before the store fallback fires — it is clearly business-meaningful.

File: `/Users/vladimirtrifonov/src/ai/nxme.ai/card-web/src/components/cta-button.tsx` line 14

---

**M-8: No font optimisation — Inter loaded as a CSS variable string, not via `next/font`**

`globals.css` sets `--font-inter: 'Inter', system-ui, sans-serif` as a plain CSS variable referencing a font name. There is no Google Fonts `<link>`, no `next/font/google` import, and no self-hosted font file in `public/`. This means Inter will not load at all — the browser falls back to `system-ui`. If Inter is intended to be the brand font, it must be loaded via `next/font/google` (which provides automatic size-adjust, font-display swap, and zero CLS), or the fallback stack is intentional and the variable should be removed.

File: `/Users/vladimirtrifonov/src/ai/nxme.ai/card-web/src/app/globals.css` line 11
File: `/Users/vladimirtrifonov/src/ai/nxme.ai/card-web/tailwind.config.ts` line 60

---

### Low

**L-1: `loading.tsx` uses a hardcoded `Array.from({ length: 5 })` — duplicates `RECOMMENDATIONS_DISPLAY_COUNT`**

The skeleton renders exactly 5 recommendation placeholders via `Array.from({ length: 5 })`. The real component uses `RECOMMENDATIONS_DISPLAY_COUNT` (also 5) from constants. If the constant changes, the skeleton will be out of sync. Import and use the constant.

File: `/Users/vladimirtrifonov/src/ai/nxme.ai/card-web/src/app/[username]/loading.tsx` line 31

---

**L-2: `CardNotFound` always links to `APP_STORE_URL` regardless of platform**

The not-found component imports and hardcodes `APP_STORE_URL` for its "Get NXME" link. Android users visiting a deleted card URL will be sent to the App Store, not the Play Store. The `CardNotFound` component is a Server Component; platform detection must happen client-side, so the simplest fix is to link to the universal marketing URL (`APP_BASE_URL`) or use the `CtaButton` component which already handles this.

File: `/Users/vladimirtrifonov/src/ai/nxme.ai/card-web/src/components/card-not-found.tsx` line 4

---

**L-3: `opengraph-image.tsx` uses apostrophe escape `&apos;` which is invalid in JSX**

```tsx
@{card.username}&apos;s Glow-Up
```

`&apos;` is a valid HTML5 entity but JSX is not HTML — React does not expand HTML entities in JSX text content. This will render literally as `@username&apos;s Glow-Up` in the generated OG image. Use the Unicode character directly (`'`) or the JavaScript escape (`{'\''}`). Note: the same pattern appears in the bottom strip (`{card.display_name}&apos;s transformation`).

File: `/Users/vladimirtrifonov/src/ai/nxme.ai/card-web/src/app/[username]/opengraph-image.tsx` lines 99, 195

---

**L-4: `revalidate` endpoint does not validate `username` format before calling `revalidatePath`**

Any string that passes `body.username.trim().length > 0` is accepted. A caller with the secret can pass `../../../../etc/passwd` or a very long string. `revalidatePath` itself is safe (it only purges the Next.js cache), but it is good hygiene to validate the username against the known format (alphanumeric + underscores, max 64 chars) before acting, and to return 400 for invalid shapes. This prevents unintentional cache-purge confusion and is a defence-in-depth measure.

File: `/Users/vladimirtrifonov/src/ai/nxme.ai/card-web/src/app/api/revalidate/route.ts` line 33

---

**L-5: No structured data (JSON-LD) on the card page**

The card page has strong SEO metadata but no `application/ld+json` structured data. A `Person` + `ImageObject` schema (or a custom `Article` schema) would enable rich results in Google Search (image carousels, structured snippets) and improve discoverability for the shareable card use case.

File: `/Users/vladimirtrifonov/src/ai/nxme.ai/card-web/src/app/[username]/page.tsx`

---

**L-6: `package.json` has no test script**

The `scripts` block has `dev`, `build`, `start`, `lint`, and `type-check` but no `test` entry. There are no test files anywhere under `card-web/src`. Even a minimal smoke test for `getCardData`'s `parseCardData` parser and the `detectPlatform` utility would catch regressions.

File: `/Users/vladimirtrifonov/src/ai/nxme.ai/card-web/package.json`

---

## Summary

The card-web app is well-structured for a Next.js 14 App Router project. ISR is correctly wired at both the page and fetch layers, the revalidation endpoint uses shared-secret auth, TypeScript strict mode is nearly fully configured, design tokens are centralised in constants and Tailwind config, and the server/client component split is appropriate throughout.

The two critical issues to fix before production launch are the wildcard `remotePatterns` (SSRF/phishing risk) and the `NEXT_PUBLIC_` prefix on the internal API URL. The high-priority items — missing segment-level error boundary for the card route, the CTA button layout-shift that hides the primary conversion action until hydration, the missing `revalidate` export on the OG image handler, and the params async-compat type issue — should be resolved in the current story cycle.

The medium items (font loading, OG image dimension mismatch, missing CSP, sitemap/robots, global focus outline removal) are production-readiness gaps that should be addressed before public launch. The low items are mostly polish and defensive hygiene.

| Severity | Count |
|----------|-------|
| Critical | 2 |
| High | 4 |
| Medium | 8 |
| Low | 6 |
| **Total** | **20** |
