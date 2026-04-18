import React, { useCallback, useMemo } from "react";
import {
  View,
  Image,
  FlatList,
  Pressable,
  RefreshControl,
  useWindowDimensions,
  StyleSheet,
  ActivityIndicator,
} from "react-native";
import Animated, {
  useSharedValue,
  useAnimatedStyle,
  withSpring,
} from "react-native-reanimated";

import { Ionicons } from "@expo/vector-icons";

import { THEME } from "../../constants/theme";
import {
  PROFILE_CONFIG,
  PROFILE_PENDING_CELL_MAX_VISIBLE,
} from "../../constants/config";
import { useTheme } from "../../lib/theme-context";
import { TAB_BAR_HEIGHT } from "../../app/(tabs)/_layout";
import { EmptyState } from "../ui/EmptyState";
import type { JobResult } from "../../lib/analysis";
import { PendingGlowUpCell } from "./PendingGlowUpCell";
import type { GlowUpItem } from "./types";

// Published-state globe indicator tuning. Sized + positioned to mirror the
// saved check-mark badge (top-right corner on saved cells), but on the
// opposite (top-left) corner so a saved + published cell shows both badges
// without overlap. The circular pill keeps the icon readable on any
// thumbnail tone — white-on-dark glass.
const PUBLISHED_INDICATOR_SIZE = 22;
const PUBLISHED_INDICATOR_ICON_SIZE = 14;
const PUBLISHED_INDICATOR_BG = "rgba(0,0,0,0.55)";
const PUBLISHED_INDICATOR_BORDER = "rgba(255,255,255,0.8)";
// testID — referenced in RN tests to locate the globe indicator.
const PUBLISHED_INDICATOR_TEST_ID = "glowup-cell-published-indicator";

interface GlowUpGridProps {
  items: GlowUpItem[];
  isLoadingMore: boolean;
  hasMore: boolean;
  onLoadMore: () => void;
  onItemPress?: (item: GlowUpItem) => void;
  /**
   * Long-press handler — only called for items that should be
   * dismissable (the parent decides which ones based on status).
   */
  onItemLongPress?: (item: GlowUpItem) => void;
  /**
   * Callback fired by PendingGlowUpCell when its poll observes a
   * fresh job state. Parent should reconcile the item's status +
   * URLs into local state so the cell flips to thumbnail / errored
   * variant on the next render.
   */
  onJobResolved?: (jobId: string, result: JobResult) => void;
  ListHeaderComponent?: React.ComponentType | React.ReactElement | null;
  refreshing?: boolean;
  onRefresh?: () => void;
}

/**
 * 3-column grid of before/after thumbnails.
 * Each cell shows the after image with a coral reaction count badge.
 * On press, could navigate to detail (future enhancement).
 */
export function GlowUpGrid({
  items,
  isLoadingMore,
  hasMore,
  onLoadMore,
  onItemPress,
  onItemLongPress,
  onJobResolved,
  ListHeaderComponent,
  refreshing = false,
  onRefresh,
}: GlowUpGridProps) {
  const { theme } = useTheme();
  const { width: screenWidth } = useWindowDimensions();

  const { itemSize, containerPadding } = useMemo(() => {
    const padding = THEME.spacing.lg;
    const totalGap =
      PROFILE_CONFIG.GRID_GAP * (PROFILE_CONFIG.GRID_COLUMNS - 1);
    const availableWidth = screenWidth - padding * 2;
    const size = Math.floor(
      (availableWidth - totalGap) / PROFILE_CONFIG.GRID_COLUMNS,
    );
    return { itemSize: size, containerPadding: padding };
  }, [screenWidth]);

  // Compute the set of job_ids allowed to poll concurrently. First N
  // non-terminal items by display order get a polling slot; over-cap
  // pending cells render shimmer but skip the network request. Errored
  // cells (failed/cancelled) are terminal — they don't need polling
  // and don't count against the cap.
  const pollingJobIds = useMemo(() => {
    const ids = new Set<string>();
    for (const item of items) {
      if (ids.size >= PROFILE_PENDING_CELL_MAX_VISIBLE) break;
      if (
        item.job_id &&
        item.status !== "completed" &&
        item.status !== "failed" &&
        item.status !== "cancelled"
      ) {
        ids.add(item.job_id);
      }
    }
    return ids;
  }, [items]);

  const handleJobResolved = useCallback(
    (jobId: string, result: JobResult) => {
      onJobResolved?.(jobId, result);
    },
    [onJobResolved],
  );

  const renderItem = useCallback(
    ({ item }: { item: GlowUpItem }) => {
      const isCompleted = item.status === "completed";
      if (!isCompleted) {
        return (
          <PendingGlowUpCell
            item={item}
            size={itemSize}
            onPress={onItemPress ? () => onItemPress(item) : undefined}
            onLongPress={
              onItemLongPress ? () => onItemLongPress(item) : undefined
            }
            shouldPoll={
              item.job_id ? pollingJobIds.has(item.job_id) : false
            }
            onJobResolved={handleJobResolved}
          />
        );
      }
      return (
        <GlowUpCell
          item={item}
          size={itemSize}
          onPress={onItemPress ? () => onItemPress(item) : undefined}
          onLongPress={
            onItemLongPress ? () => onItemLongPress(item) : undefined
          }
        />
      );
    },
    [
      itemSize,
      onItemPress,
      onItemLongPress,
      pollingJobIds,
      handleJobResolved,
    ],
  );

  // Prefer job_id when available so the optimistic-pending-row insert
  // (U6) and the server's /history rehydrate row collapse to a single
  // FlatList item — React reconciles them in place rather than rendering
  // both. Legacy rows without a job_id fall back to analysis_id.
  const keyExtractor = useCallback(
    (item: GlowUpItem) => item.job_id ?? item.analysis_id,
    [],
  );

  const handleEndReached = useCallback(() => {
    if (hasMore && !isLoadingMore) {
      onLoadMore();
    }
  }, [hasMore, isLoadingMore, onLoadMore]);

  const renderFooter = useCallback(() => {
    if (!isLoadingMore) return null;
    return (
      <View style={styles.footer}>
        <ActivityIndicator size="small" color={theme.accent} />
      </View>
    );
  }, [isLoadingMore, theme.accent]);

  // Empty-state goes through ListEmptyComponent with contentContainerStyle
  // flexGrow:1 so the EmptyState primitive (flex:1 centering when
  // `center`) stretches across the region BELOW the ProfileHeader
  // (ListHeaderComponent). This matches the Feed tab's pattern and
  // keeps the title at the same vertical rhythm as the advisor tabs
  // without needing any per-screen padding bias.
  const renderEmpty = useCallback(
    () => (
      <EmptyState
        icon="sparkles-outline"
        title="Your glow-ups will appear here"
        description="Create your first transformation to get started"
      />
    ),
    [],
  );

  return (
    <View style={styles.container}>
      <FlatList
        data={items}
        renderItem={renderItem}
        keyExtractor={keyExtractor}
        numColumns={PROFILE_CONFIG.GRID_COLUMNS}
        columnWrapperStyle={[
          styles.row,
          { paddingHorizontal: containerPadding },
        ]}
        contentContainerStyle={styles.gridContent}
        onEndReached={handleEndReached}
        onEndReachedThreshold={0.5}
        ListHeaderComponent={ListHeaderComponent}
        ListHeaderComponentStyle={styles.headerGap}
        ListFooterComponent={renderFooter}
        ListEmptyComponent={renderEmpty}
        showsVerticalScrollIndicator={false}
        scrollEnabled={true}
        refreshControl={
          onRefresh !== undefined ? (
            <RefreshControl
              refreshing={refreshing}
              onRefresh={onRefresh}
              tintColor={theme.accent}
              colors={[theme.accent]}
            />
          ) : undefined
        }
      />
    </View>
  );
}

interface GlowUpCellProps {
  item: GlowUpItem;
  size: number;
  onPress?: () => void;
  onLongPress?: () => void;
}

const GlowUpCell = React.memo(function GlowUpCell({
  item,
  size,
  onPress,
  onLongPress,
}: GlowUpCellProps) {
  const scale = useSharedValue(1);
  const pressStyle = useAnimatedStyle(() => ({
    transform: [{ scale: scale.value }],
  }));

  const handlePressIn = useCallback(() => {
    scale.value = withSpring(0.97, THEME.animation.press);
  }, [scale]);
  const handlePressOut = useCallback(() => {
    scale.value = withSpring(1, THEME.animation.press);
  }, [scale]);

  return (
    <Animated.View style={[{ width: size, height: size }, pressStyle]}>
      <Pressable
        onPress={onPress}
        onLongPress={onLongPress}
        onPressIn={handlePressIn}
        onPressOut={handlePressOut}
        style={[styles.cell, { width: size, height: size }]}
        accessibilityLabel={`Glow-up transformation from ${new Date(item.created_at).toLocaleDateString()}`}
        accessibilityRole="image"
      >
        {/* Show after image as thumbnail */}
        {item.after_image_url ? (
          <Image
            source={{ uri: item.after_image_url }}
            style={styles.thumbnail}
            resizeMode="cover"
            accessibilityLabel={`After photo from ${new Date(item.created_at).toLocaleDateString()}`}
          />
        ) : null}

        {/* Before image overlay (small, bottom-left) */}
        {item.before_image_url ? (
          <View style={styles.beforeOverlay}>
            <Image
              source={{ uri: item.before_image_url }}
              style={styles.beforeThumbnail}
              resizeMode="cover"
              accessibilityLabel={`Before photo from ${new Date(item.created_at).toLocaleDateString()}`}
            />
          </View>
        ) : null}

        {/* Saved badge — surfaces which transformations the user has
            already kept so the profile grid answers "did I save this?"
            at a glance without tapping through to the result screen. */}
        {item.saved_at ? (
          <View
            style={styles.savedBadge}
            accessibilityLabel="Saved"
            accessible
          >
            <Ionicons
              name="checkmark"
              size={14}
              color={THEME.colors.white}
            />
          </View>
        ) : null}

        {/* Published indicator — surfaces which transformations have a
            live public post so the profile grid answers "did I publish
            this?" at a glance. Positioned in the opposite corner of the
            saved check-mark so the two badges never overlap on a
            saved+published cell. */}
        {item.post_id ? (
          <View
            style={styles.publishedBadge}
            accessibilityLabel="Published"
            accessible
            testID={PUBLISHED_INDICATOR_TEST_ID}
          >
            <Ionicons
              name="globe-outline"
              size={PUBLISHED_INDICATOR_ICON_SIZE}
              color={THEME.colors.white}
            />
          </View>
        ) : null}
      </Pressable>
    </Animated.View>
  );
});

const styles = StyleSheet.create({
  gridContent: {
    // flexGrow:1 lets ListEmptyComponent (EmptyState with default
    // center={true}) stretch across the space BELOW ProfileHeader
    // so the empty-state title lands at the vertical centre of that
    // region — matches the advisor tabs via the shared EmptyState
    // primitive instead of a per-screen padding hack.
    flexGrow: 1,
    // Gap between the tab nav header and ProfileHeader — the screen
    // body no longer adds its own safe-area padding (that lives on
    // the nav header), so this padding is the sole breathing room
    // above the collapsed card.
    paddingTop: THEME.spacing.lg,
    paddingBottom: TAB_BAR_HEIGHT,
  },
  // Breathing room BELOW the ProfileHeader (ListHeaderComponent) and
  // ABOVE the first grid row. Without this the card visually touches
  // the photo grid and the two surfaces read as a single block.
  headerGap: {
    paddingBottom: THEME.spacing.md,
  },
  row: {
    gap: PROFILE_CONFIG.GRID_GAP,
    marginBottom: PROFILE_CONFIG.GRID_GAP,
  },
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
  beforeOverlay: {
    position: "absolute",
    bottom: THEME.spacing.xs,
    left: THEME.spacing.xs,
    width: 28,
    height: 28,
    borderRadius: THEME.radius.sm - 2,
    overflow: "hidden",
    borderWidth: 1,
    borderColor: THEME.colors.borderFocused,
  },
  beforeThumbnail: {
    width: "100%",
    height: "100%",
  },
  // Saved check-mark badge — top-right corner of a saved cell. Uses a
  // dark-glass pill so the mark reads on both light and dark thumbnails.
  savedBadge: {
    position: "absolute",
    top: THEME.spacing.xs,
    right: THEME.spacing.xs,
    width: 22,
    height: 22,
    borderRadius: 11,
    backgroundColor: "rgba(0,0,0,0.55)",
    borderWidth: 1,
    borderColor: "rgba(255,255,255,0.8)",
    alignItems: "center",
    justifyContent: "center",
  },
  // Published globe badge — top-left corner of a cell whose glow-up has
  // a live public post. Matches the saved pill's size/finish so a cell
  // with both indicators reads as two balanced dots in the top corners.
  publishedBadge: {
    position: "absolute",
    top: THEME.spacing.xs,
    left: THEME.spacing.xs,
    width: PUBLISHED_INDICATOR_SIZE,
    height: PUBLISHED_INDICATOR_SIZE,
    borderRadius: PUBLISHED_INDICATOR_SIZE / 2,
    backgroundColor: PUBLISHED_INDICATOR_BG,
    borderWidth: 1,
    borderColor: PUBLISHED_INDICATOR_BORDER,
    alignItems: "center",
    justifyContent: "center",
  },
  footer: {
    paddingVertical: THEME.spacing.lg,
    alignItems: "center",
  },
  container: {
    flex: 1,
  },
});
