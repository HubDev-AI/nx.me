# 2026-03-17 Review Sweep

Static review of the current branch across architecture, simplicity, performance, data/migrations, deployment, frontend/UI, TypeScript, Python, and docs/spec.

Skills used: `architecture-strategist`, `code-simplicity-reviewer`, `performance-oracle`, `data-migration-expert`, `deployment-verification-agent`, `web-design-guidelines`, `kieran-typescript-reviewer`, `kieran-python-reviewer`, `spec-flow-analyzer`.

## Architecture Review

- P1: The profile feature has no stable boundary between mobile and API. Mobile hardcodes a pseudo-user `"me"` and expects `/users/{username}/reactions`, `reaction_count`, and `streak_days`, but the backend only exposes `/profile`, `/history`, and `PATCH`, and returns `total_reactions` / `member_since` instead. This is not just a frontend bug; it is a broken cross-layer contract. Refs: `mobile/app/(tabs)/profile.tsx:74`, `mobile/constants/config.ts:172`, `mobile/components/profile/types.ts:5`, `mobile/components/profile/useProfile.ts:61`, `app/api/users.py:34`, `app/api/users.py:110`, `app/api/users.py:153`, `app/api/users.py:292`.
- P1: The generation worker violates the documented storage boundary. The architecture says the generated image is written to NXME storage first and that fal.ai URLs are never used for downstream processing, but the worker downloads `gen_result.image_url` directly for NSFW and identity checks before uploading to `generated-images`. Refs: `docs/architecture.md:160`, `app/generation/worker.py:171`, `app/generation/worker.py:249`.
- P2: The API layer is owning storage-copy orchestration that the architecture assigns to service boundaries. `create_post` directly downloads private bucket objects, uploads them to the public bucket, and builds CDN URLs inside the router, which increases coupling between HTTP handling, storage, and publication semantics. Refs: `docs/architecture.md:81`, `docs/architecture.md:104`, `app/api/posts.py:112`, `app/api/posts.py:145`.

## Simplicity Review

- P2: `app/advisor/nudge_scheduler.py` is carrying four responsibilities at once: trigger policy, prompt templates, eligibility scans, and queue dispatch. The repeated "scan rows -> compute in Python -> per-user query -> enqueue" shape makes the file harder to reason about and harder to optimize later. Refs: `app/advisor/nudge_scheduler.py:54`, `app/advisor/nudge_scheduler.py:210`.
- P2: The profile feature duplicates an imaginary contract in three places on the mobile side: endpoint constants, TS types, and hook logic. Because there is no shared source of truth, the code drifted away from the implemented API without any single file looking obviously wrong in isolation. Refs: `mobile/constants/config.ts:172`, `mobile/components/profile/types.ts:5`, `mobile/components/profile/useProfile.ts:61`.
- P3: The codebase still carries both old and new `glow_up_jobs` image-column names, which increases cognitive overhead across migrations, docs, and runtime code. Refs: `app/migrations/0001_initial.sql:81`, `app/migrations/0006_glow_up_jobs.sql:12`, `docs/architecture.md:450`, `docs/stories/4-3-generation-api.md:88`.

## Performance Review

- P1: `get_user_history()` is an N+1 query path. For each analysis it separately fetches the original image, latest completed job, and generated image, then signs URLs one row at a time. Profile/history latency will degrade sharply for users with long histories. Refs: `app/api/users.py:202`, `app/api/users.py:231`, `app/api/users.py:245`.
- P1: Feed ranking is still heavily Python-side. Trending always pulls up to 500 posts, filters images after the fetch, computes scores in Python, and sorts in memory; biggest-improvements can over-fetch by `limit + cursor_reactions`, which explodes for hot posts. Refs: `app/api/social.py:167`, `app/api/social.py:185`, `app/api/social.py:218`, `app/api/social.py:232`, `app/api/social.py:270`.
- P1: The advisor eligibility cron does full-table scans and then issues per-user follow-up queries. Weekly, milestone, and re-engagement logic all scale with table size rather than with the actually eligible user set. Refs: `app/advisor/nudge_scheduler.py:242`, `app/advisor/nudge_scheduler.py:254`, `app/advisor/nudge_scheduler.py:292`, `app/advisor/nudge_scheduler.py:347`, `app/advisor/nudge_scheduler.py:375`.
- P2: Reaction persistence recalculates the entire reaction count on every insert, and the nightly reconciliation loops per post and re-counts again. That is acceptable at tiny scale but expensive under bursty engagement. Refs: `app/api/social.py:436`, `app/api/social.py:469`.
- P2: `get_user_profile()` reads every non-deleted post row just to compute `post_count` and total reactions in Python instead of using aggregate queries. Refs: `app/api/users.py:122`.

## Data / Migration Review

- P1: Rollback support is unreliable because the runner only recognizes the exact marker `-- DOWN:`. `0005_username_reserved_until.sql` uses `-- === DOWN ===`, and `0006_glow_up_jobs.sql` uses `-- DOWN`, so `python -m app.migrations.run --down ...` will not parse their revert sections. Refs: `app/migrations/run.py:26`, `app/migrations/run.py:95`, `app/migrations/run.py:123`, `app/migrations/0005_username_reserved_until.sql:15`, `app/migrations/0006_glow_up_jobs.sql:81`.
- P2: `glow_up_jobs` now has schema drift rather than a clean rename. `0001` creates `before_image_id` / `after_image_id`, while `0006` adds `original_image_id` / `generated_image_id` and leaves the legacy columns in place. That preserves compatibility in the short term but leaves two competing representations in the canonical table. Refs: `app/migrations/0001_initial.sql:81`, `app/migrations/0006_glow_up_jobs.sql:12`.
- P2: The migration/doc contract is explicitly inconsistent with the planning contract. The plan says the applied schema must match the architecture exactly, while the story doc already instructs implementers to ignore the architecture and trust the migration instead. Refs: `docs/plan.md:32`, `docs/architecture.md:438`, `docs/stories/4-3-generation-api.md:47`, `docs/stories/4-3-generation-api.md:88`.

## Deployment Review

- P1: Local/dev startup instructions still point operators to the wrong worker entrypoint. If someone follows the checked-in script/docs, they start `app.worker.WorkerSettings` instead of the actual unified worker in `app.worker_settings.WorkerSettings`, which risks missing `default` queue jobs and cron tasks. Refs: `scripts/dev-start.sh:25`, `docs/local-dev.md:18`, `docs/local-dev.md:113`, `app/worker_settings.py:6`, `app/worker_settings.py:54`.
- P1: The rollback path for deploys involving `0005` or `0006` is not trustworthy because the migration runner cannot parse their down sections. That raises release risk for any production rollout that needs a quick schema revert. Refs: `app/migrations/run.py:123`, `app/migrations/0005_username_reserved_until.sql:15`, `app/migrations/0006_glow_up_jobs.sql:81`.
- P2: Automated verification is effectively absent for deploy confidence. The spec requires meaningful CI coverage gates, but the current test run is `12 skipped`, so production changes rely on static review and manual testing. Refs: `docs/spec.md:85`, `docs/spec.md:247`. Verification run: `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest -q` -> `12 skipped in 0.03s`.

## Frontend / UI Review

- P1: The share-card CTA does not do what the product flow promises on mobile. On iOS and Android it always points to the App Store / Play Store instead of attempting to open the installed app first, despite the plan explicitly requiring app-open when installed. Refs: `card-web/src/components/cta-button.tsx:21`, `card-web/src/components/cta-button.tsx:35`, `docs/plan.md:440`.
- P1: Even if the app is opened from a card link, the native card detail route is still a placeholder that shows only `Card details loading...` with no before/after content, no recommendations, and no conversion context. Refs: `mobile/app/card/[username].tsx:13`.
- P2: Comment UI is designed to show avatar and display name, but the backend never returns those fields, so the shipped experience degrades to generic placeholders for every server-backed comment. Refs: `mobile/components/comments/CommentItem.tsx:44`, `mobile/components/comments/types.ts:12`, `app/api/posts.py:50`, `app/api/posts.py:262`, `app/api/posts.py:307`.

## TypeScript Review

- P1: Social auth is wired to the wrong backend contract. The mobile login/signup screens send `{ provider, code, redirect_uri }` from an authorization-code flow, but the backend request model accepts `{ provider, id_token, nonce? }` and calls `sign_in_with_id_token`. This will fail at runtime. Refs: `mobile/app/(auth)/login.tsx:155`, `mobile/app/(auth)/signup.tsx:227`, `app/api/auth.py:339`, `app/api/auth.py:399`.
- P1: The mobile profile types and endpoints do not match the implemented API. `UserProfile` expects `user_id`, `reaction_count`, `streak_days`, and `created_at`; the hook also calls `/users/{username}/reactions`; none of that exists in the backend. Refs: `mobile/components/profile/types.ts:5`, `mobile/constants/config.ts:172`, `mobile/components/profile/useProfile.ts:80`, `app/api/users.py:34`, `app/api/users.py:110`.
- P2: The comments TypeScript types claim parity with the backend, but both `CommentsResponse` and `CreateCommentResponse` require `post_id`, `is_deleted`, `display_name`, and `avatar_url` that the backend does not send. Refs: `mobile/components/comments/types.ts:2`, `app/api/posts.py:50`, `app/api/posts.py:262`, `app/api/posts.py:307`.
- P3: `card-web` trusts backend JSON with a direct cast instead of runtime validation, so silent contract drift will surface as render-time failures deeper in the tree. Refs: `card-web/src/lib/api.ts:50`.

## Python Review

- P1: `create_post()` logs and suppresses public-bucket copy failures, then still writes `before_image_url` / `after_image_url` into `posts` and returns success. That can publish broken URLs while the API reports a successful post creation. Refs: `app/api/posts.py:129`, `app/api/posts.py:142`, `app/api/posts.py:150`.
- P1: `create_comment()` increments `posts.comment_count` using read-modify-write logic from a stale value. Concurrent comments can overwrite each other and undercount. Refs: `app/api/posts.py:233`, `app/api/posts.py:255`.
- P2: `PATCH /users/{username}` only updates `display_name`, while the mobile payload and plan both assume avatar updates are part of the same endpoint. Refs: `mobile/components/profile/types.ts:46`, `docs/plan.md:457`, `app/api/users.py:59`, `app/api/users.py:314`.

## Docs / Spec Review

- P1: The auth contract is contradictory across spec, plan, client, and backend. The plan says Authorization Code + PKCE; the backend story and route code are written around `id_token`; the mobile client implements code flow. There is no single authoritative login contract at the moment. Refs: `docs/spec.md:185`, `docs/plan.md:88`, `docs/stories/2-2-auth-social-login-logout-deletion.md:15`, `docs/stories/2-2-auth-social-login-logout-deletion.md:67`, `app/api/auth.py:339`, `mobile/app/(auth)/login.tsx:165`.
- P1: The profile story/plan promises capabilities that the backend does not expose: `reaction_count`, `streak_days`, avatar update support, and a reactions endpoint. The mobile implementation followed the plan, not the backend. Refs: `docs/plan.md:454`, `docs/plan.md:457`, `docs/plan.md:470`, `app/api/users.py:34`, `app/api/users.py:292`.
- P2: The architecture still documents the old `glow_up_jobs` column names and the old TOCTOU-safe storage-first flow, while the current code and story doc have moved on. The architecture is no longer a reliable source of truth for this area. Refs: `docs/architecture.md:160`, `docs/architecture.md:450`, `docs/stories/4-3-generation-api.md:47`, `app/generation/worker.py:171`.

## Verification

- Static review only.
- `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest -q` completed successfully, but all `12` tests were skipped.
