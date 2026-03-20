/**
 * NudgeFeed — scrollable list of Ada's nudge cards with read state management.
 *
 * Available to all tiers. Supports pull-to-refresh and pagination.
 * Tapping an unread nudge fires POST /advisor/nudges/{id}/read.
 */
import { useState, useEffect, useCallback, useRef } from "react";
import {
  View,
  FlatList,
  RefreshControl,
  Text,
  Pressable,
  ActivityIndicator,
  StyleSheet,
  Platform,
} from "react-native";
import { Ionicons } from "@expo/vector-icons";

import { THEME } from "../../constants/theme";
import { useTheme } from "../../lib/theme-context";
import { FONTS } from "../../hooks/useFonts";
import { ADVISOR_CONFIG, MIN_TOUCH_TARGET } from "../../constants/config";
import { fetchNudges, markNudgeRead } from "../../lib/advisor";
import type { Nudge } from "../../lib/advisor";
import { NudgeCard } from "./NudgeCard";

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
    backgroundColor: THEME.colors.surface,
    borderRadius: THEME.radius.lg - 2,
    padding: THEME.spacing.lg - 2,
    gap: THEME.spacing.md,
  },
  icon: {
    width: 36,
    height: 36,
    borderRadius: 18,
    backgroundColor: THEME.colors.surfaceElevated,
  },
  lines: {
    flex: 1,
    gap: THEME.spacing.sm,
  },
  line: {
    height: 12,
    borderRadius: THEME.radius.sm - 2,
    backgroundColor: THEME.colors.surfaceElevated,
  },
});

const Separator = () => <View style={styles.separator} />;

export function NudgeFeed() {
  const { theme } = useTheme();
  const [nudges, setNudges] = useState<Nudge[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [isLoadingMore, setIsLoadingMore] = useState(false);
  const [hasMore, setHasMore] = useState(false);
  const [error, setError] = useState<string | null>(null);


  const retryCountRef = useRef(0);
  const retryTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // -------------------------------------------------------------------------
  // Load nudges
  // -------------------------------------------------------------------------
  const loadNudges = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const response = await fetchNudges();
      setNudges(response.nudges);
      setHasMore(response.has_more);
    } catch (err) {
      const message =
        err instanceof Error ? err.message : "Failed to load nudges";
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
    try {
      const response = await fetchNudges();
      setNudges(response.nudges);
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
    if (!hasMore || isLoadingMore || nudges.length === 0) return;
    setIsLoadingMore(true);
    try {
      const lastNudge = nudges[nudges.length - 1]!;
      const response = await fetchNudges(lastNudge.id);
      setNudges((prev) => [...prev, ...response.nudges]);
      setHasMore(response.has_more);
      retryCountRef.current = 0;
    } catch {
      retryCountRef.current += 1;
      if (retryCountRef.current < 3) {
        const delay = retryCountRef.current === 1 ? 2000 : 3000;
        setIsLoadingMore(false);
        retryTimeoutRef.current = setTimeout(() => {
          loadMore();
        }, delay);
        return;
      }
      // Reset so next user-initiated scroll starts a fresh retry round
      retryCountRef.current = 0;
    } finally {
      setIsLoadingMore(false);
    }
  }, [hasMore, isLoadingMore, nudges]);

  // -------------------------------------------------------------------------
  // Mark nudge as read
  // -------------------------------------------------------------------------
  const handleMarkRead = useCallback(async (nudgeId: string) => {
    // Optimistic update
    setNudges((prev) =>
      prev.map((n) => (n.id === nudgeId ? { ...n, is_read: true } : n)),
    );
    try {
      await markNudgeRead(nudgeId);
    } catch {
      // Revert on failure
      setNudges((prev) =>
        prev.map((n) => (n.id === nudgeId ? { ...n, is_read: false } : n)),
      );
    }
  }, []);

  // -------------------------------------------------------------------------
  // Render helpers
  // -------------------------------------------------------------------------
  const keyExtractor = useCallback((item: Nudge) => item.id, []);

  const renderItem = useCallback(
    ({ item }: { item: Nudge }) => (
      <NudgeCard nudge={item} onMarkRead={handleMarkRead} />
    ),
    [handleMarkRead],
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

  if (error && nudges.length === 0) {
    return (
      <View style={styles.errorContainer}>
        <Ionicons name="alert-circle-outline" size={48} color={THEME.colors.textSecondary} />
        <Text style={styles.errorTitle}>Could not load nudges</Text>
        <Text style={styles.errorSubtitle}>{error}</Text>
        <Pressable
          onPress={loadNudges}
          style={[styles.retryButton, { backgroundColor: theme.accent }]}
          accessibilityLabel="Retry loading nudges"
          accessibilityRole="button"
        >
          <Ionicons name="refresh-outline" size={18} color={THEME.colors.bg} />
          <Text style={styles.retryButtonText}>Try Again</Text>
        </Pressable>
      </View>
    );
  }

  return (
    <View style={styles.container}>
      <FlatList
        data={nudges}
        keyExtractor={keyExtractor}
        renderItem={renderItem}
        ListFooterComponent={renderFooter}
        ListEmptyComponent={
          <View style={styles.emptyContainer}>
            <Ionicons name="sparkles-outline" size={48} color={THEME.colors.textSecondary} />
            <Text style={styles.emptyTitle}>No nudges yet</Text>
            <Text style={styles.emptySubtitle}>
              Ada will send you tips and check-ins as she gets to know you
            </Text>
          </View>
        }
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
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: THEME.colors.bg,
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
  emptyContainer: {
    flex: 1,
    alignItems: "center",
    justifyContent: "center",
    paddingHorizontal: THEME.spacing.xxxl,
    paddingTop: THEME.spacing.xxxl * 2.5,
    gap: THEME.spacing.sm,
  },
  emptyTitle: {
    fontFamily: FONTS.display,
    fontSize: 18,
    color: THEME.colors.textPrimary,
    letterSpacing: THEME.typography.heading.letterSpacing,
    marginTop: THEME.spacing.md,
  },
  emptySubtitle: {
    fontFamily: FONTS.displayItalic,
    ...THEME.typography.caption,
    color: THEME.colors.textSecondary,
    textAlign: "center",
  },
  errorContainer: {
    flex: 1,
    alignItems: "center",
    justifyContent: "center",
    paddingHorizontal: THEME.spacing.xxxl,
    gap: THEME.spacing.sm,
    backgroundColor: THEME.colors.bg,
  },
  errorTitle: {
    fontFamily: FONTS.display,
    fontSize: 18,
    color: THEME.colors.textPrimary,
    letterSpacing: THEME.typography.heading.letterSpacing,
    marginTop: THEME.spacing.md,
  },
  errorSubtitle: {
    fontFamily: FONTS.body,
    ...THEME.typography.caption,
    color: THEME.colors.textSecondary,
    textAlign: "center",
  },
  retryButton: {
    flexDirection: "row",
    alignItems: "center",
    gap: THEME.spacing.sm,
    marginTop: THEME.spacing.lg,
    paddingHorizontal: THEME.spacing.xl,
    paddingVertical: THEME.spacing.md - 2,
    borderRadius: THEME.radius.pill,
    minHeight: MIN_TOUCH_TARGET,
  },
  retryButtonText: {
    fontFamily: FONTS.bodySemiBold,
    fontSize: 14,
    color: THEME.colors.bg,
  },
});
