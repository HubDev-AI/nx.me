/**
 * NudgeFeed — scrollable list of Ada's nudge cards with read state management.
 *
 * Available to all tiers. Supports pull-to-refresh and pagination.
 * Tapping an unread nudge fires POST /advisor/nudges/{id}/read.
 */
import { useCallback, useEffect, useRef, useState } from "react";
import {
  ActivityIndicator,
  FlatList,
  Platform,
  RefreshControl,
  StyleSheet,
  View,
} from "react-native";
import { useRouter } from "expo-router";

import {
  ADVISOR_CONFIG,
  NUDGE_CTA_ERROR_TOAST,
  NUDGE_CTA_STALE_TOAST,
  PAGINATION_CONFIG,
} from "../../constants/config";
import { THEME } from "../../constants/theme";
import { ApiError } from "../../lib/api";
import { fetchNudges, markNudgeRead, requestNudgeNextStep } from "../../lib/advisor";
import type { Nudge } from "../../lib/advisor";
import { useTheme } from "../../lib/theme-context";
import { showToast } from "../../lib/toast";
import { AdvisorEmptyOverlay } from "./AdvisorEmptyOverlay";
import { NudgeCard } from "./NudgeCard";
import { NudgeDetailSheet } from "./NudgeDetailSheet";

/** HTTP status code surfaced when a nudge has been deleted server-side. */
const HTTP_STALE_NUDGE = 404;

/** Expo Router pathname for the Ada advisor screen. */
const ADVISOR_ROUTE = "/advisor" as const;

/** Skeleton for loading state */
function NudgeSkeleton() {
  return (
    <View style={skeletonStyles.container}>
      {[1, 2, 3, 4].map((i) => (
        <View key={i} style={skeletonStyles.card}>
          <View style={skeletonStyles.icon} />
          <View style={skeletonStyles.lines}>
            <View style={[skeletonStyles.line, { width: "60%" }]} />
            <View style={[skeletonStyles.line, { width: "90%" }]} />
            <View style={[skeletonStyles.line, { width: "30%" }]} />
          </View>
        </View>
      ))}
    </View>
  );
}

const skeletonStyles = StyleSheet.create({
  container: {
    padding: THEME.spacing.lg,
    gap: THEME.spacing.md,
  },
  card: {
    flexDirection: "row",
    backgroundColor: THEME.colors.glass,
    borderRadius: THEME.radius.lg,
    borderWidth: 1,
    borderColor: THEME.colors.glassBorder,
    padding: THEME.spacing.lg,
    gap: THEME.spacing.md,
  },
  icon: {
    width: 36,
    height: 36,
    borderRadius: 18,
    backgroundColor: THEME.colors.glass,
  },
  lines: {
    flex: 1,
    gap: THEME.spacing.sm,
  },
  line: {
    height: 12,
    borderRadius: THEME.radius.sm,
    backgroundColor: THEME.colors.surface,
  },
});

const Separator = () => <View style={styles.separator} />;

export function NudgeFeed() {
  const { theme } = useTheme();
  const router = useRouter();
  const [nudges, setNudges] = useState<Nudge[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [isLoadingMore, setIsLoadingMore] = useState(false);
  const [hasMore, setHasMore] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // Selected nudge drives the detail sheet. Card bodies truncate at
  // three lines; tapping opens the full copy in a sheet.
  const [selectedNudge, setSelectedNudge] = useState<Nudge | null>(null);


  const retryCountRef = useRef(0);
  const retryTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const nextCursorRef = useRef<string | null>(null);

  // -------------------------------------------------------------------------
  // Load nudges
  // -------------------------------------------------------------------------
  const loadNudges = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const response = await fetchNudges();
      setNudges(response.nudges);
      nextCursorRef.current = response.next_cursor;
      setHasMore(response.has_more);
    } catch (err) {
      const message =
        err instanceof Error ? err.message : "We couldn't load your nudges.";
      setError(message);
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    loadNudges();
    return () => {
      if (retryTimeoutRef.current) {
        clearTimeout(retryTimeoutRef.current);
        retryTimeoutRef.current = null;
      }
    };
  }, [loadNudges]);

  // -------------------------------------------------------------------------
  // Refresh
  // -------------------------------------------------------------------------
  const handleRefresh = useCallback(async () => {
    setIsRefreshing(true);
    // Cancel any pending retry so a late retry cannot append a
    // post-cursor page into the freshly-refreshed list.
    if (retryTimeoutRef.current) {
      clearTimeout(retryTimeoutRef.current);
      retryTimeoutRef.current = null;
    }
    retryCountRef.current = 0;
    try {
      const response = await fetchNudges();
      setNudges(response.nudges);
      nextCursorRef.current = response.next_cursor;
      setHasMore(response.has_more);
    } catch {
      // Silently ignore refresh errors — existing data stays
    } finally {
      setIsRefreshing(false);
    }
  }, []);

  // -------------------------------------------------------------------------
  // Pagination
  // -------------------------------------------------------------------------
  const loadMore = useCallback(async () => {
    if (!hasMore || isLoadingMore || !nextCursorRef.current) return;
    setIsLoadingMore(true);
    try {
      const response = await fetchNudges(nextCursorRef.current);
      setNudges((prev) => [...prev, ...response.nudges]);
      nextCursorRef.current = response.next_cursor;
      setHasMore(response.has_more);
      retryCountRef.current = 0;
    } catch {
      retryCountRef.current += 1;
      if (retryCountRef.current < PAGINATION_CONFIG.MAX_RETRIES) {
        const attemptIndex = Math.min(
          retryCountRef.current - 1,
          PAGINATION_CONFIG.RETRY_DELAYS_MS.length - 1,
        );
        const delay = PAGINATION_CONFIG.RETRY_DELAYS_MS[attemptIndex]!;
        setIsLoadingMore(false);
        // Clear any previously scheduled retry so rapid scrolls don't stack timers.
        if (retryTimeoutRef.current) {
          clearTimeout(retryTimeoutRef.current);
        }
        retryTimeoutRef.current = setTimeout(() => {
          retryTimeoutRef.current = null;
          loadMore();
        }, delay);
        return;
      }
      // All retries exhausted — surface the error; next scroll starts fresh.
      retryCountRef.current = 0;
      showToast({
        kind: "error",
        message: "Couldn't load more nudges. Pull to refresh.",
      });
    } finally {
      setIsLoadingMore(false);
    }
  }, [hasMore, isLoadingMore]);

  // -------------------------------------------------------------------------
  // Card tap → open detail sheet + mark unread nudges as read.
  // -------------------------------------------------------------------------
  const handleCardPress = useCallback(async (nudge: Nudge) => {
    setSelectedNudge(nudge);

    if (nudge.read_at !== null) return;

    // Optimistic mark-read; revert on failure so the unread dot comes back.
    const now = new Date().toISOString();
    setNudges((prev) =>
      prev.map((n) => (n.id === nudge.id ? { ...n, read_at: now } : n)),
    );
    try {
      await markNudgeRead(nudge.id);
    } catch {
      setNudges((prev) =>
        prev.map((n) => (n.id === nudge.id ? { ...n, read_at: null } : n)),
      );
    }
  }, []);

  const handleCloseSheet = useCallback(() => setSelectedNudge(null), []);

  // -------------------------------------------------------------------------
  // CTA press → seed the chat composer via Expo Router search params.
  //
  // Happy path: navigate to the advisor screen with `seedText` param.
  // ChatView.handleSeedText (Unit 7) consumes the param one-shot and
  // forwards it to AdvisorComposer.initialText. We intentionally `push`
  // even when already on /advisor so `useLocalSearchParams` picks up
  // the new seed; the advisor screen effect force-selects the chat tab
  // whenever a seed param arrives.
  //
  // 404 path: the nudge was deleted server-side between the list fetch
  // and the tap. Toast + refresh so the stale card drops out of the
  // feed without the user having to pull-to-refresh manually.
  // -------------------------------------------------------------------------
  const handleCtaPress = useCallback(
    async (nudge: Nudge) => {
      try {
        const response = await requestNudgeNextStep(nudge.id);
        router.push({
          pathname: ADVISOR_ROUTE,
          params: { seedText: response.seed_text },
        });
      } catch (err) {
        if (err instanceof ApiError && err.status === HTTP_STALE_NUDGE) {
          showToast({ kind: "warning", message: NUDGE_CTA_STALE_TOAST });
          // Refresh so the stale card disappears from the list.
          void handleRefresh();
          return;
        }
        showToast({ kind: "error", message: NUDGE_CTA_ERROR_TOAST });
      }
    },
    [handleRefresh, router],
  );

  // -------------------------------------------------------------------------
  // Render helpers
  // -------------------------------------------------------------------------
  const keyExtractor = useCallback((item: Nudge) => item.id, []);

  const renderItem = useCallback(
    ({ item, index }: { item: Nudge; index: number }) => (
      <NudgeCard
        nudge={item}
        index={index}
        onPress={handleCardPress}
        onCtaPress={handleCtaPress}
      />
    ),
    [handleCardPress, handleCtaPress],
  );

  const renderFooter = useCallback(() => {
    if (!isLoadingMore) return null;
    return (
      <View style={styles.footer}>
        <ActivityIndicator size="small" color={theme.accent} />
      </View>
    );
  }, [isLoadingMore, theme.accent]);

  // -------------------------------------------------------------------------
  // States
  // -------------------------------------------------------------------------
  if (isLoading) {
    return <NudgeSkeleton />;
  }

  return (
    <View style={styles.container}>
      <FlatList
        data={nudges}
        keyExtractor={keyExtractor}
        renderItem={renderItem}
        ListFooterComponent={renderFooter}
        onEndReached={loadMore}
        onEndReachedThreshold={0.5}
        refreshControl={
          <RefreshControl
            refreshing={isRefreshing}
            onRefresh={handleRefresh}
            colors={[theme.accent]}
            tintColor={theme.accent}
            progressBackgroundColor={THEME.colors.bg}
          />
        }
        showsVerticalScrollIndicator={false}
        removeClippedSubviews={Platform.OS === "android"}
        maxToRenderPerBatch={ADVISOR_CONFIG.MAX_TO_RENDER_PER_BATCH}
        updateCellsBatchingPeriod={ADVISOR_CONFIG.UPDATE_CELLS_BATCHING_PERIOD_MS}
        windowSize={ADVISOR_CONFIG.WINDOW_SIZE}
        contentContainerStyle={styles.listContent}
        ItemSeparatorComponent={Separator}
      />

      {/* Error overlay — centered with Try Again button. */}
      {error && nudges.length === 0 && (
        <AdvisorEmptyOverlay
          icon="alert-circle-outline"
          title="Could not load nudges"
          description={error}
          action={{
            label: "Try Again",
            onPress: loadNudges,
            accessibilityLabel: "Retry loading nudges",
          }}
        />
      )}

      {/* Fixed-center empty state — matches position across advisor tabs. */}
      {!error && nudges.length === 0 && (
        <AdvisorEmptyOverlay
          icon="sparkles-outline"
          title="No nudges yet"
          description="Ada will send you tips and check-ins as she gets to know you"
        />
      )}

      <NudgeDetailSheet
        nudge={selectedNudge}
        onClose={handleCloseSheet}
        onCtaPress={handleCtaPress}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: "transparent",
  },
  listContent: {
    flexGrow: 1,
    padding: THEME.spacing.lg,
  },
  separator: {
    height: THEME.spacing.md - 2,
  },
  footer: {
    paddingVertical: THEME.spacing.xl,
    alignItems: "center",
  },
});
