# Cross-Layer Audit — Fix Session Summary

Branch: `fix/cross-layer-audit`
Baseline: 0 lint / type / test failures; deep behavioural gaps discovered by 4 parallel discovery agents.
Final: same guards green (428 pytests, ruff, backend; tsc + expo lint, mobile; tsc + vitest, card-web).
Iterations used: 18 (of 50 budgeted).

## Commits (category-grouped)

### Backend correctness (6)
- **`8174b9d`** report real queue depth via ZCARD on `arq:queue` — LLEN on wrong key always returned 0, so queue_position and estimated_wait were lies
- **`52a5ded`** revert route generation jobs to tier-specific queue lane — discovered mid-loop that the worker only reads the default queue; would have stranded jobs forever
- **`42cbad1`** mark orphan job row FAILED on enqueue failure — mobile poller no longer hangs on jobs the worker never saw
- **`c5703c8`** return `share_hash` in `POST /v1/posts` response — unblocked all downstream share-URL work
- **`41f5c5f`** `persist_reaction` fails fast on missing `post_id` — no more ARQ retry loops on malformed payloads

### Mobile contract (4)
- **`70e34f3`** align `PublicCard` type with backend `CardResponse` (`recommendations` object shape, `display_name`, `share_hash`) — fixes `Objects are not valid as a React child` crash on card detail
- **`3127225`** surface cancel-subscription backend message as toast — DELETE `/v1/subscriptions` no longer ignored
- **`7dc43a5`** refresh-token endpoint comment was stale — backend does implement it
- **`29606fc`** `API_BASE_URL` fails fast when unset — no more silent fallback to prod from a broken dev env

### Card-web (4)
- **`96d5f3a`** render latest card at `/{username}` — profile shares no longer land on 404
- **`fa5a8f5`** add `openGraph.images` + fix revalidate tsc strict — Facebook/LinkedIn previews now render; pre-existing `TS2345` resolved
- **`227c9d8`** stop linking CTA buttons to bogus App Store `id=0` — falls back to the marketing URL until store listings go live
- **card-web `/{username}` page** added with canonical pointing at the hash-specific URL for SEO

### Mobile share flow (2)
- **`a64eca2`** feed-card share uses per-user card URL — recipients land on the poster's card, not the marketing root
- **`f443a72`** attach card-web link when sharing result composite — signed-in users get both PNG + clickable URL in the share sheet

### Mobile settings / tooling (3)
- **`9bc7b4a`** add Log Out action to settings screen — previously only reachable via the profile radial menu
- **`783b15d`** unblock `expo lint` — eslint@9.0.0 predates the `eslint/config` subpath export; bumped to `^9.1.0`
- **`f96dbd4`** document intentional exhaustive-deps exception in `useFeed.loadMore` — keeps lint at zero warnings now that it runs

## Discoveries we did NOT fix (out of scope for a fix loop)

| # | Area | Reason |
|---|------|--------|
| Priority-lane worker | backend | Dead architecture — needs multi-queue worker setup or arq extension. Hook left for future work. |
| `schedule_post_analysis_nudge` integration | backend | Registered worker function never enqueued by any endpoint — advisor nudge integration is incompletely wired. |
| `POST /v1/devices` push registration | backend | Mobile has commented TODO; backend route not implemented. Feature work. |
| Public card listing for sitemap | card-web / backend | Needs new backend endpoint (pagination + opt-in privacy). |
| `.well-known/apple-app-site-association` + `assetlinks.json` | deploy | Requires signed bundle IDs + dev team ID — operational, not code. |
| Mobile subscription.tsx typography migration | mobile | ~15 inline font-family / font-size mechanical rewrites — deferred to a dedicated polish PR. |
| Mobile settings: notifications prefs / help / privacy links | mobile | Depends on card-web `/privacy` + `/terms` pages and a notifications surface — neither exists yet. |
| Reconcile + retention cron race (03:00 vs 03:30) | backend | Low-probability window; deferred. |
| `PENDING` enum unused | backend | DB constraint allows the value; keeping alignment with the schema is safer than removal. |

## Guard status at end of loop

| Layer | Command | Result |
|-------|---------|--------|
| Backend | `ruff check app/ tests/` | All checks passed |
| Backend | `pytest tests/` | 428 passed |
| Mobile | `tsc --noEmit` | clean |
| Mobile | `expo lint` | 0 errors, 0 warnings |
| Card-web | `tsc --noEmit` | clean |
| Card-web | `vitest run` | 8 passed |

## Stop reason

No remaining findings can be landed as atomic fixes without a migration, backend feature, or marketing-surface scaffold — all of which are out of scope for `/autoresearch:fix`. Halting at iteration 18 rather than burning the budget on mechanical polish.
