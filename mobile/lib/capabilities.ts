/**
 * Capability layer — single source of truth for "feature X is available to
 * session Y" gating decisions in the mobile UI.
 *
 * Derives semantic booleans from (features × session) so screens never read
 * raw `features.X` for gating. Adding a new flag:
 *   1. Update `FeatureFlags` in `../constants/features.ts` + backend model.
 *   2. Add a capability here + matrix row in `capabilities.test.ts`.
 *   3. Consume via `useCapabilities()` — never `useFeatures().features.X`.
 *
 * Raw `useFeatures()` is still allowed inside this module, for loading-state
 * checks (splash on `isLoading`), and for session-bootstrap logic in
 * `AuthGuard` (mobile/app/_layout.tsx) that runs before `useAuth()` is ready.
 * Every other UI gating decision must route through `useCapabilities()`.
 */
import { useMemo } from "react";

import { useFeatures } from "./features-context";
import { useSession } from "./auth-context";

export interface Capabilities {
  /** Can view their own profile screen (full view with glowups + menu). */
  canViewOwnProfile: boolean;
  /**
   * Can edit profile (display name, username, avatar). Real users always
   * can; guests can while `auth_required` is false — in that mode the
   * guest row on the server is the real identity, and the owner-match
   * check on PATCH /v1/users/{username} accepts X-Guest-Token.
   */
  canEditProfile: boolean;
  /**
   * Can view real account details (email, plan, etc.) — only meaningful for
   * signed-in users. Guests have no account record server-side.
   */
  canViewAccountDetails: boolean;
  /**
   * Can permanently delete their account — only meaningful for signed-in
   * users. Guests have no server-side record to delete.
   */
  canDeleteAccount: boolean;
  /**
   * Can sign out — only meaningful when auth is enabled AND the user is
   * actually signed in. With auth off the concept doesn't apply.
   */
  canSignOut: boolean;
  /**
   * Can sign in — only meaningful when auth is enabled AND the user is
   * not already signed in. With auth off the concept doesn't apply.
   */
  canSignIn: boolean;
  /** Social feed tab visible + reachable. */
  canSeeFeed: boolean;
  /** Advisor tab + features available. */
  canUseAdvisor: boolean;
  /** Share glowup card flow available. */
  canShareGlowup: boolean;
  /**
   * Share-profile button visible (ProfileHeader). The public card-web
   * page only exists meaningfully when the social surface is on, so
   * this is keyed to `social_enabled` — distinct from `canShareGlowup`
   * which gates result-card sharing (tied to `share_enabled`).
   */
  canShareProfile: boolean;
  /** Onboarding flow runs after login. */
  canSeeOnboarding: boolean;
  /** Subscription screen reachable — stub true until premium tiering ships. */
  canSubscribe: boolean;
  /** React to glowups in the feed (tied to social_enabled). */
  canReact: boolean;
  /**
   * Blocked-users screen reachable — needs both auth (to have users at all)
   * and social (to have the concept of blocking someone). With either off,
   * the screen has nothing to show.
   */
  canViewBlockedUsers: boolean;
  /** Raw `auth_required` passthrough for flow-level gating (AuthGuard). */
  requiresAuth: boolean;
}

/**
 * Returns the derived capability set for the current (features, session).
 * Pure derivation — memoized on the stable inputs so consumers only re-render
 * when a flag or session mode actually changes.
 */
export function useCapabilities(): Capabilities {
  const { features } = useFeatures();
  const session = useSession();

  return useMemo<Capabilities>(
    () => ({
      canViewOwnProfile:
        session.isUser || (session.isGuest && !features.auth_required),
      canEditProfile:
        session.isUser || (session.isGuest && !features.auth_required),
      canViewAccountDetails: session.isUser,
      canDeleteAccount: session.isUser,
      canSignOut: features.auth_required && session.isUser,
      canSignIn: features.auth_required && !session.isUser,
      canSeeFeed: features.social_enabled,
      canUseAdvisor: features.advisor_enabled,
      canShareGlowup: features.share_enabled,
      canShareProfile: features.social_enabled,
      canSeeOnboarding: features.onboarding_enabled,
      canSubscribe: true,
      canReact: features.social_enabled,
      canViewBlockedUsers: features.auth_required && features.social_enabled,
      requiresAuth: features.auth_required,
    }),
    [
      features.auth_required,
      features.social_enabled,
      features.advisor_enabled,
      features.share_enabled,
      features.onboarding_enabled,
      session.isUser,
      session.isGuest,
    ],
  );
}
