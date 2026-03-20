import { useCallback, useMemo } from "react";
import {
  View,
  Image,
  Text,
  FlatList,
  Pressable,
  RefreshControl,
  useWindowDimensions,
  StyleSheet,
  ActivityIndicator,
} from "react-native";
import { Ionicons } from "@expo/vector-icons";

import {
  TEXT_PRIMARY,
  COLORS,
} from "../../constants/colors";
import { PROFILE_CONFIG } from "../../constants/config";
import { FONTS } from "../../hooks/useFonts";
import { useTheme } from "../../lib/theme-context";
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
    const padding = 16;
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

  const renderEmpty = useCallback(() => {
    if (items.length > 0) return null;
    return (
      <View style={styles.emptyContainer}>
        <View style={[styles.emptyIconCircle, { backgroundColor: theme.accent + "1A" }]}>
          <Ionicons name="sparkles" size={28} color={theme.accent} />
        </View>
        <Text style={styles.emptyText}>Your glow-ups will appear here</Text>
        <Text style={styles.emptyHint}>
          Create your first transformation to get started
        </Text>
      </View>
    );
  }, [items.length]);

  return (
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
  );
}

interface GlowUpCellProps {
  item: GlowUpItem;
  size: number;
  onPress?: () => void;
}

function GlowUpCell({ item, size, onPress }: GlowUpCellProps) {
  return (
    <Pressable
      onPress={onPress}
      style={({ pressed }) => [
        styles.cell,
        { width: size, height: size },
        pressed && styles.cellPressed,
      ]}
      accessibilityLabel={`Glow-up transformation from ${new Date(item.created_at).toLocaleDateString()}`}
      accessibilityRole="image"
    >
      {/* Show after image as thumbnail */}
      {item.after_image_url ? (
        <Image
          source={{ uri: item.after_image_url }}
          style={styles.thumbnail}
          resizeMode="cover"
        />
      ) : null}

      {/* Before image overlay (small, bottom-left) */}
      {item.before_image_url ? (
        <View style={styles.beforeOverlay}>
          <Image
            source={{ uri: item.before_image_url }}
            style={styles.beforeThumbnail}
            resizeMode="cover"
          />
        </View>
      ) : null}
    </Pressable>
  );
}

const styles = StyleSheet.create({
  gridContent: {
    paddingTop: 8,
    paddingBottom: 80,
  },
  row: {
    gap: PROFILE_CONFIG.GRID_GAP,
    marginBottom: PROFILE_CONFIG.GRID_GAP,
  },
  cell: {
    borderRadius: 12,
    overflow: "hidden",
    backgroundColor: "#111111",
  },
  cellPressed: {
    opacity: 0.8,
  },
  thumbnail: {
    width: "100%",
    height: "100%",
  },
  beforeOverlay: {
    position: "absolute",
    bottom: 4,
    left: 4,
    width: 28,
    height: 28,
    borderRadius: 6,
    overflow: "hidden",
    borderWidth: 1,
    borderColor: "rgba(255,255,255,0.3)",
  },
  beforeThumbnail: {
    width: "100%",
    height: "100%",
  },
  footer: {
    paddingVertical: 16,
    alignItems: "center",
  },
  emptyContainer: {
    alignItems: "center",
    justifyContent: "center",
    paddingVertical: 48,
    paddingHorizontal: 32,
  },
  emptyIconCircle: {
    width: 56,
    height: 56,
    borderRadius: 28,
    alignItems: "center",
    justifyContent: "center",
    marginBottom: 4,
  },
  emptyText: {
    fontFamily: FONTS.display,
    fontSize: 20,
    color: "#e8e8e8",
    marginTop: 12,
    textAlign: "center",
  },
  emptyHint: {
    fontFamily: FONTS.body,
    fontSize: 14,
    color: "#888888",
    textAlign: "center",
    marginTop: 4,
  },
});
