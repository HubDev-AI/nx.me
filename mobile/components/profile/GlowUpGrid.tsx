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

import { THEME } from "../../constants/theme";
import { PROFILE_CONFIG } from "../../constants/config";
import { useTheme } from "../../lib/theme-context";
import { TAB_BAR_HEIGHT } from "../../app/(tabs)/_layout";
import { EmptyState } from "../ui/EmptyState";
import type { GlowUpItem } from "./types";

interface GlowUpGridProps {
  items: GlowUpItem[];
  isLoadingMore: boolean;
  hasMore: boolean;
  onLoadMore: () => void;
  onItemPress?: (item: GlowUpItem) => void;
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

  const renderItem = useCallback(
    ({ item }: { item: GlowUpItem }) => (
      <GlowUpCell
        item={item}
        size={itemSize}
        onPress={onItemPress ? () => onItemPress(item) : undefined}
      />
    ),
    [itemSize, onItemPress],
  );

  const keyExtractor = useCallback(
    (item: GlowUpItem) => item.analysis_id,
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
}

const GlowUpCell = React.memo(function GlowUpCell({ item, size, onPress }: GlowUpCellProps) {
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
    paddingTop: THEME.spacing.sm,
    paddingBottom: TAB_BAR_HEIGHT,
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
  footer: {
    paddingVertical: THEME.spacing.lg,
    alignItems: "center",
  },
  container: {
    flex: 1,
  },
});
