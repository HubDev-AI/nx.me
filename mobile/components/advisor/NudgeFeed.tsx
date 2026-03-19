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

import {
  BG_PAGE,
  BG_CARD,
  CTA_PRIMARY,
  TEXT_PRIMARY,
  TEXT_SECONDARY,
} from "../../constants/colors";
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
    padding: 16,
    gap: 12,
  },
  card: {
    flexDirection: "row",
    backgroundColor: BG_CARD,
    borderRadius: 14,
    padding: 14,
    gap: 12,
  },
  icon: {
    width: 36,
    height: 36,
    borderRadius: 18,
    backgroundColor: "rgba(255,255,255,0.05)",
  },
  lines: {
    flex: 1,
    gap: 8,
  },
  line: {
    height: 12,
    borderRadius: 6,
    backgroundColor: "rgba(255,255,255,0.05)",
  },
});

const Separator = () => <View style={styles.separator} />;

export function NudgeFeed() {
  const [nudges, setNudges] = useState<Nudge[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [isLoadingMore, setIsLoadingMore] = useState(false);
  const [hasMore, setHasMore] = useState(false);
  const [error, setError] = useState<string | null>(null);


  const retryCountRef = useRef(0);

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
        setTimeout(() => {
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
        <ActivityIndicator size="small" color={CTA_PRIMARY} />
      </View>
    );
  }, [isLoadingMore]);

  // -------------------------------------------------------------------------
  // States
  // -------------------------------------------------------------------------
  if (isLoading) {
    return <NudgeSkeleton />;
  }

  if (error && nudges.length === 0) {
    return (
      <View style={styles.errorContainer}>
        <Ionicons name="alert-circle-outline" size={48} color={TEXT_SECONDARY} />
        <Text style={styles.errorTitle}>Could not load nudges</Text>
        <Text style={styles.errorSubtitle}>{error}</Text>
        <Pressable
          onPress={loadNudges}
          style={styles.retryButton}
          accessibilityLabel="Retry loading nudges"
          accessibilityRole="button"
        >
          <Ionicons name="refresh-outline" size={18} color="#FFFFFF" />
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
            <Ionicons name="sparkles-outline" size={48} color={TEXT_SECONDARY} />
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
            colors={[CTA_PRIMARY]}
            tintColor={CTA_PRIMARY}
            progressBackgroundColor={BG_PAGE}
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
    backgroundColor: BG_PAGE,
  },
  listContent: {
    flexGrow: 1,
    padding: 16,
  },
  separator: {
    height: 10,
  },
  footer: {
    paddingVertical: 20,
    alignItems: "center",
  },
  emptyContainer: {
    flex: 1,
    alignItems: "center",
    justifyContent: "center",
    paddingHorizontal: 32,
    paddingTop: 80,
    gap: 8,
  },
  emptyTitle: {
    fontSize: 18,
    fontWeight: "700",
    color: TEXT_PRIMARY,
    marginTop: 12,
  },
  emptySubtitle: {
    fontSize: 14,
    color: TEXT_SECONDARY,
    textAlign: "center",
    lineHeight: 20,
  },
  errorContainer: {
    flex: 1,
    alignItems: "center",
    justifyContent: "center",
    paddingHorizontal: 32,
    gap: 8,
    backgroundColor: BG_PAGE,
  },
  errorTitle: {
    fontSize: 18,
    fontWeight: "700",
    color: TEXT_PRIMARY,
    marginTop: 12,
  },
  errorSubtitle: {
    fontSize: 14,
    color: TEXT_SECONDARY,
    textAlign: "center",
    lineHeight: 20,
  },
  retryButton: {
    flexDirection: "row",
    alignItems: "center",
    gap: 6,
    marginTop: 16,
    paddingHorizontal: 20,
    paddingVertical: 10,
    borderRadius: 20,
    backgroundColor: CTA_PRIMARY,
    minHeight: MIN_TOUCH_TARGET,
  },
  retryButtonText: {
    fontSize: 14,
    fontWeight: "600",
    color: "#FFFFFF",
  },
});
