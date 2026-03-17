import { useCallback } from "react";
import {
  View,
  Image,
  Text,
  FlatList,
  Pressable,
  ActivityIndicator,
  StyleSheet,
} from "react-native";
import { Ionicons } from "@expo/vector-icons";

import {
  BG_CARD,
  BG_ELEVATED,
  TEXT_PRIMARY,
  TEXT_SECONDARY,
  CTA_PRIMARY,
  COLORS,
} from "../../constants/colors";
import { MIN_TOUCH_TARGET } from "../../constants/config";
import type { ReactedPost } from "./types";

const IMAGE_SIZE = 56;

interface ReactionsTabProps {
  items: ReactedPost[];
  isLoadingMore: boolean;
  hasMore: boolean;
  onLoadMore: () => void;
  onItemPress?: (item: ReactedPost) => void;
}

/**
 * List of posts the user reacted to.
 * Each row shows before/after thumbnails, username, reaction count, and timestamp.
 */
export function ReactionsTab({
  items,
  isLoadingMore,
  hasMore,
  onLoadMore,
  onItemPress,
}: ReactionsTabProps) {
  const renderItem = useCallback(
    ({ item }: { item: ReactedPost }) => (
      <ReactionRow
        item={item}
        onPress={onItemPress ? () => onItemPress(item) : undefined}
      />
    ),
    [onItemPress],
  );

  const keyExtractor = useCallback(
    (item: ReactedPost) => item.post_id,
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

  if (items.length === 0 && !isLoadingMore) {
    return (
      <View style={styles.emptyContainer}>
        <Ionicons
          name="heart-outline"
          size={48}
          color={COLORS.neutral.dark[600]}
        />
        <Text style={styles.emptyText}>No reactions yet</Text>
        <Text style={styles.emptyHint}>
          Posts you react to will appear here
        </Text>
      </View>
    );
  }

  return (
    <FlatList
      data={items}
      renderItem={renderItem}
      keyExtractor={keyExtractor}
      onEndReached={handleEndReached}
      onEndReachedThreshold={0.5}
      ListFooterComponent={renderFooter}
      showsVerticalScrollIndicator={false}
      contentContainerStyle={styles.listContent}
      scrollEnabled={false}
      nestedScrollEnabled={false}
    />
  );
}

interface ReactionRowProps {
  item: ReactedPost;
  onPress?: () => void;
}

function ReactionRow({ item, onPress }: ReactionRowProps) {
  const timeAgo = formatTimeAgo(item.created_at);

  return (
    <Pressable
      onPress={onPress}
      style={({ pressed }) => [
        styles.row,
        pressed && styles.rowPressed,
      ]}
      accessibilityLabel={`Reacted to ${item.username}'s post, ${item.reaction_count} reactions, ${timeAgo}`}
      accessibilityRole="button"
    >
      {/* Before/After mini thumbnails */}
      <View style={styles.thumbnailPair}>
        <Image
          source={{ uri: item.before_image_url }}
          style={styles.thumbnailBefore}
          resizeMode="cover"
          accessibilityLabel="Before photo"
        />
        <Image
          source={{ uri: item.after_image_url }}
          style={styles.thumbnailAfter}
          resizeMode="cover"
          accessibilityLabel="After photo"
        />
      </View>

      {/* Info */}
      <View style={styles.infoContainer}>
        <Text style={styles.rowUsername} numberOfLines={1}>
          @{item.username}
        </Text>
        <View style={styles.rowMeta}>
          <Ionicons name="heart" size={12} color={CTA_PRIMARY} />
          <Text style={styles.rowReactionCount}>
            {item.reaction_count}
          </Text>
          <Text style={styles.rowTime}>{timeAgo}</Text>
        </View>
      </View>

      {/* Chevron */}
      <Ionicons
        name="chevron-forward"
        size={16}
        color={COLORS.neutral.dark[600]}
      />
    </Pressable>
  );
}

/** Format ISO date to relative time string */
function formatTimeAgo(isoDate: string): string {
  const now = Date.now();
  const then = new Date(isoDate).getTime();
  const diffSeconds = Math.floor((now - then) / 1000);

  if (diffSeconds < 60) return "just now";
  const diffMinutes = Math.floor(diffSeconds / 60);
  if (diffMinutes < 60) return `${diffMinutes}m`;
  const diffHours = Math.floor(diffMinutes / 60);
  if (diffHours < 24) return `${diffHours}h`;
  const diffDays = Math.floor(diffHours / 24);
  if (diffDays < 7) return `${diffDays}d`;
  const diffWeeks = Math.floor(diffDays / 7);
  if (diffWeeks < 4) return `${diffWeeks}w`;
  const diffMonths = Math.floor(diffDays / 30);
  return `${diffMonths}mo`;
}

const styles = StyleSheet.create({
  listContent: {
    paddingTop: 8,
    paddingBottom: 24,
  },
  row: {
    flexDirection: "row",
    alignItems: "center",
    backgroundColor: BG_CARD,
    marginHorizontal: 16,
    marginBottom: 8,
    borderRadius: 10,
    padding: 10,
    minHeight: MIN_TOUCH_TARGET,
    gap: 12,
  },
  rowPressed: {
    backgroundColor: BG_ELEVATED,
  },
  thumbnailPair: {
    flexDirection: "row",
    width: IMAGE_SIZE + 8,
    height: IMAGE_SIZE,
  },
  thumbnailBefore: {
    width: IMAGE_SIZE / 2 + 4,
    height: IMAGE_SIZE,
    borderTopLeftRadius: 6,
    borderBottomLeftRadius: 6,
  },
  thumbnailAfter: {
    width: IMAGE_SIZE / 2 + 4,
    height: IMAGE_SIZE,
    borderTopRightRadius: 6,
    borderBottomRightRadius: 6,
  },
  infoContainer: {
    flex: 1,
    gap: 4,
  },
  rowUsername: {
    fontSize: 14,
    fontWeight: "600",
    color: TEXT_PRIMARY,
  },
  rowMeta: {
    flexDirection: "row",
    alignItems: "center",
    gap: 4,
  },
  rowReactionCount: {
    fontSize: 12,
    fontWeight: "600",
    color: CTA_PRIMARY,
  },
  rowTime: {
    fontSize: 12,
    color: TEXT_SECONDARY,
    marginLeft: 4,
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
