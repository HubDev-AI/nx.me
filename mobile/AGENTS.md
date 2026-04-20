# AGENTS.md — `mobile/` (React Native + Expo)

TypeScript, Expo Router, native dev build.
Root CLAUDE.md covers project-wide rules — this file is for mobile-specific context only.

## Layout

- `app/` — Expo Router file-based routes (`(auth)/`, `(tabs)/`, `onboarding/`, etc.)
- `components/` — reusable UI primitives (shared location — do not duplicate)
- `lib/` — API client (`apiFetch`), auth context, offline queue, utilities
- `hooks/` — shared React hooks (single source; feature code imports from here)
- `constants/` — design tokens, enums, route names
- `assets/` — fonts, images
- `android/`, `ios/` — native code (ejected build, required for Google Sign-In / TikTok SDK)

## Commands (from `mobile/`)

- `npx expo run:ios` / `npx expo run:android` — **native dev build** (required after native-dep changes)
- `npx expo start` — JS-only reload (faster, after native build exists)
- `npx expo lint` — ESLint via Expo config
- `npm test` — Jest (`jest-expo` preset); tests match `**/*.test.ts(x)`; setup file `jest.setup.ts`
- `npm run test:watch` — Jest watch mode

## TypeScript

`tsconfig.json` extends `expo/tsconfig.base`. Strict mode on, plus:
- `noUncheckedIndexedAccess: true` — array/object access returns `T | undefined`
- `noImplicitReturns`, `noFallthroughCasesInSwitch`, `noUnusedLocals`, `noUnusedParameters`
- Path alias: `@/*` → `./*`

## Env

`mobile/.env` + `mobile/.env.example`. `API_BASE_URL` must be your machine's LAN IP (e.g. `http://192.168.x.x:8000`) — `localhost` does not work from a physical device or simulator hitting the host.

## UI / UX rules

- **All pagination is infinite scroll** — no load-more buttons, no tap-to-retry UI.
- **Action buttons (cancel, retry, submit) stay visible when disabled** — disable visually, never hide. Users need to see the next action is there.
- **No design tokens in line** — import from `constants/` or the design-token module.

## BottomTabBar / SafeArea

Floating pill tab bars: set `safeAreaInsets={{ top:0, right:0, bottom:0, left:0 }}` on the `Tabs`/`Navigator` component **and** zero insets in the custom `tabBar` wrapper. The navigator-level prop is the primary fix — overriding only the wrapper fails because `BottomTabView.renderTabBar` reads insets from `SafeAreaInsetsContext` before passing them to the wrapper callback.

## Before recommending an AI model or prompt

Test on fal.ai playground (or equivalent) first. Caveat any unreviewed recommendation with "needs playground testing." Over-constrained prompts with many "do not …" instructions often produce near-zero change — prefer positive instructions plus post-generation checks.
