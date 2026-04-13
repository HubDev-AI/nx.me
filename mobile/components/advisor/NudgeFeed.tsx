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
import { Ionicons } from "@expo/vector-icons";

import { THEME } from "../../constants/theme";
import { useTheme } from "../../lib/theme-context";
import { Body, Heading } from "../ui/Text";
import { Button } from "../ui/Button";
import { ADVISOR_CONFIG } from "../../constants/config";
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
    // Optimistic update — set read_at to current time
    const now = new Date().toISOString();
    setNudges((prev) =>
      prev.map((n) => (n.id === nudgeId ? { ...n, read_at: now } : n)),
    );
    try {
      await markNudgeRead(nudgeId);
    } catch {
      // Revert on failure
      setNudges((prev) =>
        prev.map((n) => (n.id === nudgeId ? { ...n, read_at: null } : n)),
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
        <Heading size="md" display={false} color="primary" style={styles.errorTitle}>
          Could not load nudges
        </Heading>
        <Body color="secondary" style={styles.errorSubtitle}>
          {error}
        </Body>
        <Button
          title="Try Again"
          onPress={loadNudges}
          variant="primary"
          size="md"
          accentColor={theme.accent}
          leftIcon={
            <Ionicons name="refresh-outline" size={18} color={THEME.colors.bg} />
          }
          accessibilityLabel="Retry loading nudges"
          style={styles.retryButton}
        />
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
            <Heading size="md" display={false} color="primary" style={styles.emptyTitle}>
              No nudges yet
            </Heading>
            <Body color="secondary" style={styles.emptySubtitle}>
              Ada will send you tips and check-ins as she gets to know you
            </Body>
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
  emptyContainer: {
    flex: 1,
    alignItems: "center",
    justifyContent: "center",
    paddingHorizontal: THEME.spacing.xxxl,
    paddingTop: THEME.spacing.xxxl * 2.5,
    gap: THEME.spacing.sm,
  },
  emptyTitle: {
    marginTop: THEME.spacing.md,
    textAlign: "center",
  },
  emptySubtitle: {
    textAlign: "center",
  },
  errorContainer: {
    flex: 1,
    alignItems: "center",
    justifyContent: "center",
    paddingHorizontal: THEME.spacing.xxxl,
    gap: THEME.spacing.sm,
    backgroundColor: "transparent",
  },
  errorTitle: {
    marginTop: THEME.spacing.md,
    textAlign: "center",
  },
  errorSubtitle: {
    textAlign: "center",
  },
  retryButton: {
    marginTop: THEME.spacing.lg,
  },
});
