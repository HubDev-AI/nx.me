/**
 * Last-active-tab fallback resolver.
 *
 * When a detail screen (e.g. `/card/[username]`) is pushed on top of the
 * `(tabs)` group, `router.back()` pops it cleanly and lands on whichever
 * tab was active. But when the screen is opened via universal-link
 * deep-linking, there is no back-stack to pop — `router.canGoBack()`
 * returns false and a naive `router.replace("/(tabs)")` always lands on
 * the tab group's initialRouteName (feed), regardless of which tab the
 * user was viewing before leaving the app.
 *
 * This resolver reads the root navigation state, finds the `(tabs)`
 * route, and returns the path of whichever tab is currently selected in
 * the tab navigator's own state. That way any number of tabs can share
 * the same detail screen without each needing a `from=foo` hint in its
 * push call — the detail screen just asks "which tab is active?" on
 * fallback.
 */
import { useCallback } from "react";
import { useRootNavigationState, useRouter, type Href } from "expo-router";

const TABS_GROUP_SEGMENT = "(tabs)";
const TABS_ROOT_PATH = "/(tabs)" as const;
const FEED_TAB_ROUTE_NAME = "index";

// eslint-disable-next-line @typescript-eslint/no-explicit-any
type NavState = any;

function findActiveTabPath(rootState: NavState | undefined): Href {
  const tabsRoute = rootState?.routes?.find(
    (r: { name?: string }) => r.name === TABS_GROUP_SEGMENT,
  );
  const tabState = tabsRoute?.state;
  if (
    !tabState ||
    typeof tabState.index !== "number" ||
    !Array.isArray(tabState.routes)
  ) {
    return TABS_ROOT_PATH;
  }
  const activeName: string | undefined = tabState.routes[tabState.index]?.name;
  if (!activeName || activeName === FEED_TAB_ROUTE_NAME) {
    return TABS_ROOT_PATH;
  }
  return `${TABS_ROOT_PATH}/${activeName}` as Href;
}

/**
 * Returns a stable back-navigation callback for any detail screen
 * rendered above the `(tabs)` group. Pops the native stack when
 * possible (preserves tab state automatically) and falls back to the
 * tab that was active when the detail screen was opened — even on a
 * cold-start deep link, as long as the tab navigator has been mounted.
 */
export function useBackToActiveTab(): () => void {
  const router = useRouter();
  const rootState = useRootNavigationState();

  return useCallback(() => {
    if (router.canGoBack()) {
      router.back();
      return;
    }
    router.replace(findActiveTabPath(rootState));
  }, [router, rootState]);
}
