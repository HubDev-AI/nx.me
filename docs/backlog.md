# Backlog — Deferred Work

Items surfaced during audits/reviews that are real but intentionally not in any current fix or feature slice.

## Pre-App-Store submission (blockers)

- **Privacy Policy page** — static page in `card-web` (`/privacy`), real legal copy, linked from mobile `settings.tsx` under Privacy section. App Store Review rejects placeholders.
- **Terms of Service page** — static page in `card-web` (`/terms`), real legal copy, linked from mobile `settings.tsx` About section.
- **Help / Support surface** — pick one: static FAQ page, mailto link, Intercom/Zendesk widget. Link from mobile `settings.tsx`.
- **Push notifications end-to-end** — re-introduce stripped mobile push flow + backend `POST /v1/devices` + Expo push adapter + advisor nudge delivery. All-or-nothing; half-wired is worse than none.

## SEO / discovery (if organic traffic warrants)

- **Sitemap per-card-page entries** — today sitemap emits `/{username}`. When a user has multiple historical cards worth indexing, add per-hash entries with canonical pointing at latest.
- **Sitemap index file** — current `sitemap.ts` caps at 50k URLs per Google's limit. When user count exceeds 50k, split into multiple sitemap files + generate an index.
- **Privacy model for public cards** — today all users with a post are public by default. If product wants opt-in discoverability, add `is_public` / `privacy_public` column + UI toggle + filter the listing endpoint.

## Ops / infra

- **Priority-lane worker** — multi-queue ARQ worker if premium users ever queue behind trial users at volume. Requires multi-process deploy setup or arq extension. Rebuild with real queue-depth data.
