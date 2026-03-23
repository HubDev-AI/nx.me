/**
 * TabBarContext -- provides scroll-driven show/hide of the tab bar
 * and a scroll-to-top callback for the floating pill button.
 *
 * The feed (or any scrollable screen) wires up the onScroll handler
 * and registers its scrollToTop ref. The tab layout reads the shared
 * translateY value to animate the bar off-screen.
 */
import {
  createContext,
  useContext,
  useCallback,
  useRef,
  type ReactNode,
} from "react";
import {
  useSharedValue,
  useAnimatedScrollHandler,
  withSpring,
  type SharedValue,
  type ScrollHandlerProcessed,
} from "react-native-reanimated";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

/** Context type for the scroll handler's internal state */
type ScrollCtx = { prevY: number; accumulatedDown: number };

interface TabBarContextValue {
  /** Animated translateY for the tab bar (0 = visible, 100 = hidden) */
  tabBarTranslateY: SharedValue<number>;
  /** Scroll handler to attach to Animated.FlatList / Animated.ScrollView */
  scrollHandler: ScrollHandlerProcessed<ScrollCtx>;
  /** Register a scroll-to-top callback from the active screen */
  registerScrollToTop: (cb: (() => void) | null) => void;
  /** Trigger scroll-to-top (called by the floating pill button) */
  scrollToTop: () => void;
}

const TabBarContext = createContext<TabBarContextValue | null>(null);

// ---------------------------------------------------------------------------
// Spring config
// ---------------------------------------------------------------------------

const SPRING_CONFIG = { damping: 20, stiffness: 150 };

/** Minimum downward scroll distance before we hide the tab bar */
const HIDE_THRESHOLD = 50;

// ---------------------------------------------------------------------------
// Provider
// ---------------------------------------------------------------------------

export function TabBarProvider({ children }: { children: ReactNode }) {
  const tabBarTranslateY = useSharedValue(0);
  const scrollToTopRef = useRef<(() => void) | null>(null);

  // ---- Animated scroll handler (runs on UI thread) ----
  const scrollHandler = useAnimatedScrollHandler({
    onScroll: (event, ctx: { prevY: number; accumulatedDown: number }) => {
      const y = event.contentOffset.y;

      // Ignore rubber-band / overscroll at the top
      if (y <= 0) {
        tabBarTranslateY.value = withSpring(0, SPRING_CONFIG);
        ctx.prevY = 0;
        ctx.accumulatedDown = 0;
        return;
      }

      const dy = y - (ctx.prevY ?? 0);

      if (dy > 0) {
        // Scrolling DOWN
        ctx.accumulatedDown = (ctx.accumulatedDown ?? 0) + dy;
        if (ctx.accumulatedDown > HIDE_THRESHOLD) {
          tabBarTranslateY.value = withSpring(100, SPRING_CONFIG);
        }
      } else if (dy < 0) {
        // Scrolling UP -- immediately show
        ctx.accumulatedDown = 0;
        tabBarTranslateY.value = withSpring(0, SPRING_CONFIG);
      }

      ctx.prevY = y;
    },
    onBeginDrag: (_event, ctx: { prevY: number; accumulatedDown: number }) => {
      // Reset accumulator on new gesture
      ctx.accumulatedDown = 0;
    },
  });

  // ---- JS-thread callbacks ----
  const registerScrollToTop = useCallback((cb: (() => void) | null) => {
    scrollToTopRef.current = cb;
  }, []);

  const scrollToTop = useCallback(() => {
    scrollToTopRef.current?.();
    // Also animate the tab bar back to visible
    tabBarTranslateY.value = withSpring(0, SPRING_CONFIG);
  }, [tabBarTranslateY]);

  return (
    <TabBarContext.Provider
      value={{ tabBarTranslateY, scrollHandler, registerScrollToTop, scrollToTop }}
    >
      {children}
    </TabBarContext.Provider>
  );
}

// ---------------------------------------------------------------------------
// Hook
// ---------------------------------------------------------------------------

export function useTabBar(): TabBarContextValue {
  const ctx = useContext(TabBarContext);
  if (!ctx) {
    throw new Error("useTabBar must be used within a TabBarProvider");
  }
  return ctx;
}
