# Cross-Layer Audit Findings — 2026-04-14

Four parallel discovery agents: mobile↔backend, backend↔worker, card-web share flow, mobile settings/UI.

## Priority Queue (fix order)

### P0 — Critical (user-visible crash / revenue / data loss)

| # | Area | File:Line | Issue | Suggested Fix |
|---|------|-----------|-------|---------------|
| 1 | Backend | app/api/glowup.py:468 | `enqueue_job("process_generation_job", ...)` omits `_queue_name=queue_lane` — tier priority lanes dead | Pass `_queue_name=queue_lane` |
| 2 | Mobile | mobile/app/card/[username].tsx:38-45 | `PublicCard.recommendations: string[]` but backend returns objects — crash | Fix type to `Array<{rank,category,suggestion,rationale}>` |
| 3 | Mobile share | mobile/components/result/ShareComposite.tsx:140 | Share.share sends only PNG `url` — no card-web URL | Add `message` with card-web link |
| 4 | Data contract | Backend `/v1/jobs/{id}` response | No `share_hash` returned — mobile can't build card-web URL | Add `share_hash` to JobStatusResponse |
| 5 | Card-web | card-web/src/app/[username]/glow-up/[hash]/page.tsx:43-55 | `generateMetadata` missing `openGraph.images` (only twitter has image) | Add openGraph.images array |
| 6 | Card-web | card-web/src/config/constants.ts:45-46 | `APP_STORE_URL = id000000000` placeholder | Replace or make env-driven |
| 7 | Mobile | mobile/components/profile/ProfileHeader.tsx:58 | Shares `nxme.ai/{username}` — card-web has no such route → 404 | Share full `/{username}/glow-up/{hash}` URL |

### P1 — High

| # | Area | File:Line | Issue | Fix |
|---|------|-----------|-------|-----|
| 8 | Mobile | mobile/app/card/[username].tsx:38-45 | `PublicCard` missing `display_name`, `share_hash` fields | Add to type |
| 9 | Mobile | mobile/app/subscription.tsx:194 | DELETE /v1/subscriptions typed as `<void>` but backend returns `CancelSubscriptionResponse` | Surface `message` in UI |
| 10 | Mobile | mobile/app/settings.tsx | No Logout button (only in profile radial menu) | Add Log Out action above Delete Account |
| 11 | Mobile | mobile/app/settings.tsx | No Help / Privacy Policy / Terms / Support links | Add About section with nav items |
| 12 | Mobile | mobile/app/settings.tsx | No notification preferences | Add Notifications nav item |
| 13 | Mobile | mobile/app/(tabs)/_layout.tsx:56 | `accessible={false}` on TabIcon blocks screen readers | Remove, let parent handle label |
| 14 | Backend | app/generation/worker.py | Credit reservation orphan if enqueue_job fails after job row created | Wrap enqueue in try, delete job row + release credits on failure |
| 15 | Backend | app/generation/worker.py:725-738 | Concurrent counter Lua in `finally` — SIGKILL leaves stale counter | Add TTL to counter key as safety net |
| 16 | Backend | app/generation/models.py:15 | `JobStatus.PENDING` unused dead enum | Remove or document |
| 17 | Deep link | No `apple-app-site-association` in card-web | iOS universal links dead | Add `card-web/public/.well-known/apple-app-site-association` |
| 18 | Deep link | No `.well-known/assetlinks.json` | Android app links dead | Add assetlinks.json |
| 19 | Mobile | mobile/constants/config.ts:67-73 | `AUTH_ENDPOINTS.REFRESH` stub — backend has no /v1/auth/refresh | Remove or implement backend |

### P2 — Medium

| # | Area | File:Line | Issue | Fix |
|---|------|-----------|-------|-----|
| 20 | Card-web | src/app/sitemap.ts:5 | Sitemap only has root — card pages unindexed | Iterate public usernames |
| 21 | Mobile share | mobile/components/feed/FeedCard.tsx | Feed share has no card URL — only domain | Include card-web path |
| 22 | Backend | app/advisor/nudge_scheduler.py:155-162 | Inline fallback for generate_nudge when no arq_pool — silent SLA violation in prod | Fail fast; keep only for tests via DI |
| 23 | Backend | app/advisor/nudge_scheduler.py:164,181 | Nudges enqueue no `_queue_name` | Add explicit queue |
| 24 | Backend | app/api/social.py:429 | `persist_reaction` accesses dict keys without Pydantic validation | Use TypedDict or Pydantic |
| 25 | Mobile | mobile/lib/notifications.ts:23 | POST `/v1/devices` commented — push tokens never registered server-side | Implement backend route OR remove stub |
| 26 | Backend | app/worker_settings.py:77-78 | `reconcile_reaction_counts` 03:00 + `run_retention` 03:30 race — retention may delete posts mid-reconcile | Move retention earlier or serialize |
| 27 | Mobile | mobile/constants/config.ts:13 | `API_BASE_URL` falls back to hardcoded `"https://api.nxme.ai"` — violates no-fallback rule | Fail fast if extra.apiBaseUrl missing |
| 28 | Mobile | mobile/app/subscription.tsx:276,320,337,... | Explicit `fontFamily:FONTS.display, fontSize:20` instead of semantic `<Heading>` | Typography migration |
| 29 | Mobile | mobile/app/blocked-users.tsx:237-299 | ScrollView+map for blocked users list — no windowing | FlatList |
| 30 | Mobile | mobile/app/subscription.tsx inline styles | Multi borderRadius without `borderCurve: "continuous"` iOS polish | Add borderCurve |

### P3 — Low (nits)

| # | Area | Issue |
|---|------|-------|
| 31 | Mobile | Dark/light theme toggle not in settings |
| 32 | Card-web | No view tracking on card pages |
| 33 | Mobile | Android share uses `message`, iOS uses `url` — inconsistent |
| 34 | Card-web | revalidate secret hardcoded for dev |
| 35 | Backend | Idempotency window unbounded |
| 36 | Mobile | Console.warn leftovers in _layout.tsx |
| 37 | Mobile | Subscription tierConfig hardcoded client-side |

## Iteration plan

Commits grouped by category:
- G1: Backend fixes (queue routing, credit orphan, PENDING cleanup, nudge queue)
- G2: Mobile type contract fixes (PublicCard, subscription response)
- G3: Share flow (share_hash return, URL construction, feed share)
- G4: Card-web metadata (OG images, APP_STORE_URL, AASA, assetlinks, sitemap)
- G5: Mobile settings (logout, help, notifications)
- G6: A11y + UI polish (TabIcon, borderCurve, typography)
- G7: Config strictness (API_BASE_URL no-fallback, REFRESH stub removal)

Guard: `make lint && make test && (cd mobile && npx tsc --noEmit)` after each commit.
