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
import { useSubscriptionTier } from "./hooks/use-subscription-tier";

export interface Capabilities {
  /** Can view their own profile screen (full view with glowups + menu). */
  canViewOwnProfile: boolean;
  /** Can edit profile (display name, username, avatar). */
  canEditProfile: boolean;
  /** Can view real account details (email, plan, etc.). */
  canViewAccountDetails: boolean;
  /** Can permanently delete their account. */
  canDeleteAccount: boolean;
  /** Can sign out — only meaningful when the user is signed in. */
  canSignOut: boolean;
  /** Can sign in — only meaningful when the user is not signed in. */
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
  /**
   * Can publish a glowup to the social feed. Distinct from
   * `canShareGlowup` (native-share button, keyed to `share_enabled`)
   * and `canSeeFeed` (viewing the feed, keyed to `social_enabled`
   * alone): publishing creates server-side content attributed to an
   * account, so it requires a real signed-in user on top of the
   * social surface being enabled.
   */
  canPublishGlowup: boolean;
  /** Onboarding flow runs after login. */
  canSeeOnboarding: boolean;
  /** Subscription screen reachable — stub true until premium tiering ships. */
  canSubscribe: boolean;
  /** React to glowups in the feed (tied to social_enabled). */
  canReact: boolean;
  /** AI Makeup analysis — requires makeup_enabled flag + Pro tier + real user. */
  canUseMakeup: boolean;
  /**
   * Blocked-users screen reachable — needs social (to have the concept of
   * blocking someone). Without it the screen has nothing to show.
   */
  canViewBlockedUsers: boolean;
}

/**
 * Returns the derived capability set for the current (features, session).
 * Pure derivation — memoized on the stable inputs so consumers only re-render
 * when a flag or session mode actually changes.
 */
export function useCapabilities(): Capabilities {
  const { features } = useFeatures();
  const session = useSession();
  const tier = useSubscriptionTier();

  return useMemo<Capabilities>(
    () => ({
      canViewOwnProfile: session.isUser,
      canEditProfile: session.isUser,
      canViewAccountDetails: session.isUser,
      canDeleteAccount: session.isUser,
      canSignOut: session.isUser,
      canSignIn: !session.isUser,
      canSeeFeed: features.social_enabled,
      canUseAdvisor: features.advisor_enabled,
      canShareGlowup: features.share_enabled,
      canShareProfile: features.social_enabled,
      canPublishGlowup: features.social_enabled && session.isUser,
      canSeeOnboarding: features.onboarding_enabled,
      canSubscribe: true,
      canReact: features.social_enabled,
      canViewBlockedUsers: features.social_enabled,
      canUseMakeup: features.makeup_enabled && session.isUser && tier === "Pro",
    }),
    [
      features.social_enabled,
      features.advisor_enabled,
      features.share_enabled,
      features.onboarding_enabled,
      features.makeup_enabled,
      session.isUser,
      tier,
    ],
  );
}
