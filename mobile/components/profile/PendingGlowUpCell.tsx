/**
 * PendingGlowUpCell — variant of GlowUpCell for non-completed history rows.
 *
 * Two visual states:
 *   - Shimmer (queued/processing/finalizing): pulsing tile signaling work
 *     in progress. Reuses SHIMMER_DURATION_MS so cadence matches the
 *     feed skeleton — shimmer drift is visual noise.
 *   - Errored (failed/cancelled): muted before-image with a corner icon.
 *     Tap navigates to /result/[jobId] terminal-failure branch; long-press
 *     opens the dismiss action sheet (handled by the parent).
 *
 * Polling: the cell owns a useAppQuery against `['job', jobId]`. The
 * shared queryKey collapses with the result-screen poller so observing
 * the same job from both surfaces costs one network request per poll.
 * Polling stops on terminal status. `shouldPoll=false` (set by the grid
 * when the cell is over the cap) renders the visual but skips the query.
 *
 * On status terminal, the cell calls `onJobResolved` so the parent
 * updates its local state — the cell itself is stateless beyond the
 * poll observer.
 */
import React, { useCallback, useEffect } from "react";
import {
  ActivityIndicator,
  Image,
  Pressable,
  StyleSheet,
  View,
} from "react-native";
import Animated, {
  Easing,
  useAnimatedStyle,
  useReducedMotion,
  useSharedValue,
  withRepeat,
  withSequence,
  withSpring,
  withTiming,
} from "react-native-reanimated";
import { Ionicons } from "@expo/vector-icons";

import {
  PROFILE_PENDING_CELL_POLL_INTERVAL_MS,
} from "../../constants/config";
import { THEME } from "../../constants/theme";
import { SHIMMER_DURATION_MS } from "../feed/FeedSkeleton";
import { getJobStatus, type JobResult } from "../../lib/analysis";
import { useAppQuery } from "../../lib/hooks/use-app-query";
import { useRefundToast } from "../../lib/hooks/use-refund-toast";
import { parseApiError, shouldRetry } from "../../lib/errors";
import type { GlowUpItem } from "./types";

const TERMINAL_STATUSES = new Set<string>(["completed", "failed", "cancelled"]);
const ERRORED_STATUSES = new Set<string>(["failed", "cancelled"]);

// Shimmer opacity bounds — same as FeedSkeleton's pulse.
const SHIMMER_OPACITY_MIN = 0.3;
const SHIMMER_OPACITY_MAX = 0.7;

// Press-feedback scale tuning — matches GlowUpCell.
const PRESS_SCALE = 0.97;

interface PendingGlowUpCellProps {
  item: GlowUpItem;
  size: number;
  onPress?: () => void;
  onLongPress?: () => void;
  /**
   * Whether this cell is allowed to poll. False when the cell is over
   * the visible-pending cap; the visual still renders but no network
   * request fires.
   */
  shouldPoll: boolean;
  /**
   * Called when the poller observes a terminal status (or fresh poll
   * data the parent should reconcile into its local list). The parent
   * is responsible for updating the items array; the cell does not
   * own state beyond the query observer.
   */
  onJobResolved: (jobId: string, result: JobResult) => void;
}

export const PendingGlowUpCell = React.memo(function PendingGlowUpCell({
  item,
  size,
  onPress,
  onLongPress,
  shouldPoll,
  onJobResolved,
}: PendingGlowUpCellProps) {
  const jobId = item.job_id;
  const isErrored = ERRORED_STATUSES.has(item.status);
  const reducedMotion = useReducedMotion();

  // Press-feedback scale, mirroring GlowUpCell so a long stack of
  // pending + completed cells behaves identically to the user's hand.
  const scale = useSharedValue(1);
  const pressStyle = useAnimatedStyle(() => ({
    transform: [{ scale: scale.value }],
  }));
  const handlePressIn = useCallback(() => {
    scale.value = withSpring(PRESS_SCALE, THEME.animation.press);
  }, [scale]);
  const handlePressOut = useCallback(() => {
    scale.value = withSpring(1, THEME.animation.press);
  }, [scale]);

  // Shimmer animation. Skipped for errored cells (terminal — no progress
  // signal needed) and for users who turned reduced-motion on.
  const shimmer = useSharedValue(SHIMMER_OPACITY_MAX);
  useEffect(() => {
    if (isErrored || reducedMotion) {
      shimmer.value = SHIMMER_OPACITY_MAX;
      return;
    }
    shimmer.value = withRepeat(
      withSequence(
        withTiming(SHIMMER_OPACITY_MIN, {
          duration: SHIMMER_DURATION_MS,
          easing: Easing.inOut(Easing.quad),
        }),
        withTiming(SHIMMER_OPACITY_MAX, {
          duration: SHIMMER_DURATION_MS,
          easing: Easing.inOut(Easing.quad),
        }),
      ),
      -1,
      false,
    );
  }, [isErrored, reducedMotion, shimmer]);
  const shimmerStyle = useAnimatedStyle(() => ({
    opacity: shimmer.value,
  }));

  // Polling. Errored cells never poll (terminal). Cells over the cap
  // don't poll. Otherwise: 2s cadence, stop on terminal.
  const enabled = shouldPoll && !isErrored && !!jobId;
  const jobQuery = useAppQuery<JobResult>({
    queryKey: ["job", jobId],
    queryFn: () => getJobStatus(jobId as string),
    enabled,
    refetchInterval: (query) => {
      const err = query.state.error;
      if (err) {
        const appError = parseApiError(err);
        return shouldRetry(appError)
          ? PROFILE_PENDING_CELL_POLL_INTERVAL_MS
          : false;
      }
      const data = query.state.data;
      if (!data) return PROFILE_PENDING_CELL_POLL_INTERVAL_MS;
      if (TERMINAL_STATUSES.has(data.status)) return false;
      return PROFILE_PENDING_CELL_POLL_INTERVAL_MS;
    },
  });

  // Lift the latest response back to the parent. We notify on every
  // poll (not only terminal) so a status flip from queued → processing
  // → finalizing reflects in the parent's state if anything else cares.
  // Parent's reconciler is idempotent so an over-notify is cheap.
  useEffect(() => {
    if (!jobId || !jobQuery.data) return;
    onJobResolved(jobId, jobQuery.data);
  }, [jobId, jobQuery.data, onJobResolved]);

  // Pending-cell observer for the refund toast. Module-level dedup
  // ensures the user sees the banner once per device — the result
  // screen has the same hook so observing the same job from both
  // surfaces fires exactly one toast.
  useRefundToast(jobQuery.data);

  const accessibilityLabel = isErrored
    ? `${item.status === "cancelled" ? "Cancelled" : "Failed"} glow-up from ${new Date(item.created_at).toLocaleDateString()} — tap to view details`
    : `Glow-up in progress from ${new Date(item.created_at).toLocaleDateString()}`;

  return (
    <Animated.View style={[{ width: size, height: size }, pressStyle]}>
      <Pressable
        onPress={onPress}
        onLongPress={onLongPress}
        onPressIn={handlePressIn}
        onPressOut={handlePressOut}
        style={[styles.cell, { width: size, height: size }]}
        accessibilityLabel={accessibilityLabel}
        accessibilityRole="button"
      >
        {item.before_image_url ? (
          <Image
            source={{ uri: item.before_image_url }}
            style={[
              styles.thumbnail,
              isErrored ? styles.erroredThumbnail : null,
            ]}
            resizeMode="cover"
          />
        ) : (
          <View style={[styles.thumbnail, styles.placeholderThumbnail]} />
        )}

        {/* Shimmer veil for non-terminal states. Sits above the
            before-image so the user sees the source they uploaded
            with a subtle pulse over it — communicates "we have your
            photo and we're working on it". */}
        {!isErrored ? (
          <Animated.View
            pointerEvents="none"
            style={[styles.shimmerOverlay, shimmerStyle]}
          />
        ) : (
          <View pointerEvents="none" style={styles.erroredOverlay} />
        )}

        {/* Center spinner only when actually polling. Over-cap cells
            still render shimmer but no spinner so the user doesn't
            think every cell is hammering the server. */}
        {!isErrored && enabled ? (
          <View pointerEvents="none" style={styles.centerBadge}>
            <ActivityIndicator
              size="small"
              color={THEME.colors.textPrimary}
            />
          </View>
        ) : null}

        {/* Errored corner icon — failed = destructive red, cancelled =
            muted secondary. Same icon language as result-screen
            terminal-failure branch. */}
        {isErrored ? (
          <View pointerEvents="none" style={styles.cornerIcon}>
            <Ionicons
              name={
                item.status === "cancelled"
                  ? "close-circle-outline"
                  : "alert-circle-outline"
              }
              size={18}
              color={
                item.status === "cancelled"
                  ? THEME.colors.textSecondary
                  : THEME.colors.destructive
              }
            />
          </View>
        ) : null}
      </Pressable>
    </Animated.View>
  );
});

const styles = StyleSheet.create({
  cell: {
    borderRadius: THEME.radius.md,
    overflow: "hidden",
    backgroundColor: THEME.colors.glass,
    borderWidth: 1,
    borderColor: THEME.colors.glassBorder,
  },
  thumbnail: {
    width: "100%",
    height: "100%",
  },
  placeholderThumbnail: {
    backgroundColor: THEME.colors.surfaceElevated,
  },
  erroredThumbnail: {
    // Dim the source image so the failure read is unmistakable.
    opacity: 0.4,
  },
  shimmerOverlay: {
    ...StyleSheet.absoluteFillObject,
    backgroundColor: "rgba(255,255,255,0.08)",
  },
  erroredOverlay: {
    ...StyleSheet.absoluteFillObject,
    backgroundColor: "rgba(0,0,0,0.35)",
  },
  centerBadge: {
    ...StyleSheet.absoluteFillObject,
    alignItems: "center",
    justifyContent: "center",
  },
  cornerIcon: {
    position: "absolute",
    top: THEME.spacing.xs,
    right: THEME.spacing.xs,
    backgroundColor: "rgba(0,0,0,0.55)",
    borderRadius: THEME.radius.pill,
    paddingHorizontal: 4,
    paddingVertical: 2,
  },
});
