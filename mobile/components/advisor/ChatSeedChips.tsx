/**
 * ChatSeedChips — up to 3 tappable chat-seed chips rendered above the
 * composer on the Ada chat empty-conversation state.
 *
 * Lifecycle:
 *   1. Mount → kick off `fetchChatSeeds()` with an AbortController.
 *   2. Skeleton: three muted-outline placeholder chips while loading.
 *   3. Success → clamp to `SEEDS_MAX` and render tappable chips.
 *   4. Timeout / error / empty response → render `null` (silent failure per
 *      the Unit 8 spec; composer is still usable).
 *
 * The chip tap callback surfaces `seed.text` (the full prompt) so the
 * parent can prefill the composer. Nothing auto-submits — the user must
 * press send. Backend contract: `GET /v1/advisor/chat-seeds` returns
 * `{seeds: [{label, text}, ...]}`.
 */
import { useEffect, useRef, useState } from "react";
import { Pressable, ScrollView, StyleSheet, Text, View } from "react-native";

import { MIN_TOUCH_TARGET } from "../../constants/config";
import { THEME } from "../../constants/theme";
import { FONTS } from "../../hooks/useFonts";
import type { ChatSeed } from "../../lib/advisor";
import { fetchChatSeeds } from "../../lib/advisor";

/**
 * Max chips rendered even if the server returns more. Mirrors the
 * backend's "exactly 3" contract; a server bug returning 5 still caps
 * here rather than overflowing the scroll row with stale items.
 */
export const SEEDS_MAX = 3;

/**
 * Hard cap on the skeleton. If `fetchChatSeeds` hasn't resolved by this
 * point we abort, hide the skeleton, and render nothing — subsequent
 * tab opens retry. Prevents an indefinite skeleton when the backend is
 * slow / degraded.
 */
export const LOADING_TIMEOUT_MS = 3_000;

/**
 * Horizontal pixel width of the skeleton placeholder chips. Wide enough
 * to read as "a chip is loading" without committing to a real label.
 */
const SKELETON_CHIP_WIDTH = 120;

export interface ChatSeedChipsProps {
  /**
   * Invoked with `seed.text` (the full prompt, not the shortened chip
   * label) when a chip is tapped. Parent is responsible for prefilling
   * the composer — this component does not auto-submit.
   */
  onChipPress: (text: string) => void;
}

type LoadState =
  /** Fetch still in flight or skeleton timer unresolved. */
  | { kind: "loading" }
  /** Fetch resolved with at least one seed (already clamped to SEEDS_MAX). */
  | { kind: "ready"; seeds: ChatSeed[] }
  /** Fetch failed, timed out, or returned an empty/malformed list. */
  | { kind: "empty" };

export function ChatSeedChips({ onChipPress }: ChatSeedChipsProps) {
  const [state, setState] = useState<LoadState>({ kind: "loading" });
  // Mounted ref shields against late state updates after unmount — the
  // AbortController already prevents the fetch from resolving, but the
  // skeleton-timeout branch resolves independently of the fetch and
  // would still race without this guard.
  const isMountedRef = useRef(true);

  useEffect(() => {
    isMountedRef.current = true;
    const controller = new AbortController();
    const timeoutId = setTimeout(() => {
      if (!isMountedRef.current) return;
      controller.abort();
      setState({ kind: "empty" });
    }, LOADING_TIMEOUT_MS);

    fetchChatSeeds({ signal: controller.signal })
      .then((response) => {
        if (!isMountedRef.current) return;
        clearTimeout(timeoutId);
        const seeds = Array.isArray(response?.seeds)
          ? response.seeds.slice(0, SEEDS_MAX)
          : [];
        if (seeds.length === 0) {
          setState({ kind: "empty" });
          return;
        }
        setState({ kind: "ready", seeds });
      })
      .catch(() => {
        if (!isMountedRef.current) return;
        clearTimeout(timeoutId);
        setState({ kind: "empty" });
      });

    return () => {
      isMountedRef.current = false;
      clearTimeout(timeoutId);
      controller.abort();
    };
  }, []);

  if (state.kind === "empty") {
    return null;
  }

  if (state.kind === "loading") {
    return (
      <ScrollView
        horizontal
        showsHorizontalScrollIndicator={false}
        contentContainerStyle={styles.row}
      >
        {Array.from({ length: SEEDS_MAX }).map((_, idx) => (
          <View
            key={`skeleton-${idx}`}
            style={[styles.chip, styles.chipSkeleton]}
          />
        ))}
      </ScrollView>
    );
  }

  return (
    <ScrollView
      horizontal
      showsHorizontalScrollIndicator={false}
      contentContainerStyle={styles.row}
    >
      {state.seeds.map((seed, idx) => (
        <Pressable
          key={`${idx}-${seed.label}`}
          onPress={() => onChipPress(seed.text)}
          style={({ pressed }) => [
            styles.chip,
            pressed && styles.chipPressed,
          ]}
          accessibilityLabel={seed.text}
          accessibilityRole="button"
          hitSlop={8}
        >
          <Text numberOfLines={1} style={styles.chipLabel}>
            {seed.label}
          </Text>
        </Pressable>
      ))}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  row: {
    paddingTop: THEME.spacing.lg,
    paddingHorizontal: THEME.spacing.xxl,
    gap: THEME.spacing.sm,
    alignItems: "center",
  },
  chip: {
    minHeight: MIN_TOUCH_TARGET,
    paddingHorizontal: THEME.spacing.lg,
    paddingVertical: THEME.spacing.sm,
    borderRadius: THEME.radius.pill,
    borderCurve: "continuous",
    borderWidth: 1,
    borderColor: THEME.colors.borderFocused,
    backgroundColor: "transparent",
    alignItems: "center",
    justifyContent: "center",
    minWidth: SKELETON_CHIP_WIDTH,
  },
  chipPressed: {
    opacity: 0.7,
  },
  chipSkeleton: {
    borderColor: THEME.colors.glassBorder,
    backgroundColor: THEME.colors.glass,
  },
  chipLabel: {
    fontFamily: FONTS.body,
    ...THEME.typography.body,
    color: THEME.colors.textPrimary,
  },
});
