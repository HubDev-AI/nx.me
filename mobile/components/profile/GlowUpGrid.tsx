import { useCallback, useMemo } from "react";
import {
  View,
  Image,
  Text,
  FlatList,
  Pressable,
  useWindowDimensions,
  StyleSheet,
  ActivityIndicator,
} from "react-native";
import { Ionicons } from "@expo/vector-icons";

import {
  BG_CARD,
  CTA_PRIMARY,
  TEXT_PRIMARY,
  COLORS,
} from "../../constants/colors";
import { PROFILE_CONFIG } from "../../constants/config";
import type { GlowUpItem } from "./types";

interface GlowUpGridProps {
  items: GlowUpItem[];
  isLoadingMore: boolean;
  hasMore: boolean;
  onLoadMore: () => void;
  onItemPress?: (item: GlowUpItem) => void;
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
}: GlowUpGridProps) {
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
        <ActivityIndicator size="small" color={CTA_PRIMARY} />
      </View>
    );
  }, [isLoadingMore]);

  if (items.length === 0) {
    return (
      <View style={styles.emptyContainer}>
        <Ionicons
          name="images-outline"
          size={48}
          color={COLORS.neutral.dark[600]}
        />
        <Text style={styles.emptyText}>No glow-ups yet</Text>
        <Text style={styles.emptyHint}>
          Your before/after transformations will appear here
        </Text>
      </View>
    );
  }

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
      ListFooterComponent={renderFooter}
      showsVerticalScrollIndicator={false}
      scrollEnabled={false}
      nestedScrollEnabled={false}
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
    paddingBottom: 24,
  },
  row: {
    gap: PROFILE_CONFIG.GRID_GAP,
    marginBottom: PROFILE_CONFIG.GRID_GAP,
  },
  cell: {
    borderRadius: 4,
    overflow: "hidden",
    backgroundColor: BG_CARD,
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
    borderRadius: 4,
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
  emptyText: {
    fontSize: 16,
    fontWeight: "600",
    color: TEXT_PRIMARY,
    marginTop: 12,
  },
  emptyHint: {
    fontSize: 14,
    color: COLORS.neutral.dark[600],
    textAlign: "center",
    marginTop: 4,
  },
});
