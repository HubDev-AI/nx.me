import { useEffect, useCallback, useState } from "react";
import {
  View,
  FlatList,
  RefreshControl,
  Text,
  ActivityIndicator,
  Pressable,
  Alert,
  StyleSheet,
  Platform,
} from "react-native";
import { Ionicons } from "@expo/vector-icons";

import {
  BG_PAGE,
  CTA_PRIMARY,
  TEXT_PRIMARY,
  TEXT_SECONDARY,
} from "../../constants/colors";
import { FEED_CONFIG } from "../../constants/config";
import { FeedCard } from "../../components/feed/FeedCard";
import { FeedSkeleton } from "../../components/feed/FeedSkeleton";
import { SortTabs } from "../../components/feed/SortTabs";
import { CommentsSheet } from "../../components/comments/CommentsSheet";
import { useFeed } from "../../components/feed/useFeed";
import type { FeedPost } from "../../components/feed/types";

/** Home / Feed tab — Story 5-4 */
export default function HomeScreen() {
  const {
    posts,
    isLoading,
    isRefreshing,
    isLoadingMore,
    hasMore: _hasMore,
    error,
    activeSort,
    reactedPostIds,
    loadFeed,
    loadMore,
    refresh,
    changeSort,
    reactToPost,
    incrementCommentCount,
  } = useFeed();

  // Comments sheet state
  const [commentsPostId, setCommentsPostId] = useState<string | null>(null);
  const isCommentsVisible = commentsPostId !== null;

  // Load feed on mount
  useEffect(() => {
    loadFeed();
  }, [loadFeed]);

  const handleCommentPress = useCallback((postId: string) => {
    setCommentsPostId(postId);
  }, []);

  const handleCloseComments = useCallback(() => {
    setCommentsPostId(null);
  }, []);

  const handleCommentPosted = useCallback((postId: string) => {
    incrementCommentCount(postId);
  }, [incrementCommentCount]);

  const handleReport = useCallback((_postId: string) => {
    Alert.alert(
      "Report Post",
      "Are you sure you want to report this post?",
      [
        { text: "Cancel", style: "cancel" },
        {
          text: "Report",
          style: "destructive",
          onPress: () => {
            // Report API call will be implemented in a future story
            Alert.alert("Reported", "Thank you for your feedback.");
          },
        },
      ],
    );
  }, []);

  const keyExtractor = useCallback(
    (item: FeedPost) => item.post_id,
    [],
  );

  const renderItem = useCallback(
    ({ item, index }: { item: FeedPost; index: number }) => (
      <FeedCard
        post={item}
        index={index}
        hasReacted={reactedPostIds.has(item.post_id)}
        onReact={reactToPost}
        onReport={handleReport}
        onCommentPress={handleCommentPress}
      />
    ),
    [reactedPostIds, reactToPost, handleReport, handleCommentPress],
  );

  const renderFooter = useCallback(() => {
    if (!isLoadingMore) return null;
    return (
      <View style={styles.footer}>
        <ActivityIndicator size="small" color={CTA_PRIMARY} />
      </View>
    );
  }, [isLoadingMore]);

  const renderEmpty = useCallback(() => {
    if (isLoading) return null;
    if (error) {
      return (
        <View style={styles.emptyContainer}>
          <Ionicons name="alert-circle-outline" size={48} color={TEXT_SECONDARY} />
          <Text style={styles.emptyTitle}>Something went wrong</Text>
          <Text style={styles.emptySubtitle}>{error}</Text>
          <Pressable
            onPress={loadFeed}
            style={styles.retryButton}
            accessibilityLabel="Retry loading feed"
            accessibilityRole="button"
          >
            <Ionicons name="refresh-outline" size={18} color="#FFFFFF" />
            <Text style={styles.retryText}>Try Again</Text>
          </Pressable>
        </View>
      );
    }
    return (
      <View style={styles.emptyContainer}>
        <Ionicons name="images-outline" size={48} color={TEXT_SECONDARY} />
        <Text style={styles.emptyTitle}>No posts yet</Text>
        <Text style={styles.emptySubtitle}>
          Be the first to share your glow-up
        </Text>
      </View>
    );
  }, [isLoading, error, loadFeed]);

  const renderHeader = useCallback(
    () => <SortTabs activeSort={activeSort} onSortChange={changeSort} />,
    [activeSort, changeSort],
  );

  // Loading state: show skeleton
  if (isLoading && posts.length === 0) {
    return (
      <View style={styles.container}>
        {renderHeader()}
        <FeedSkeleton />
      </View>
    );
  }

  return (
    <View style={styles.container}>
      <FlatList
        data={posts}
        keyExtractor={keyExtractor}
        renderItem={renderItem}
        ListHeaderComponent={renderHeader}
        ListFooterComponent={renderFooter}
        ListEmptyComponent={renderEmpty}
        onEndReached={loadMore}
        onEndReachedThreshold={0.5}
        refreshControl={
          <RefreshControl
            refreshing={isRefreshing}
            onRefresh={refresh}
            colors={[CTA_PRIMARY]}
            tintColor={CTA_PRIMARY}
            progressBackgroundColor={BG_PAGE}
          />
        }
        showsVerticalScrollIndicator={false}
        removeClippedSubviews={Platform.OS === "android"}
        maxToRenderPerBatch={FEED_CONFIG.MAX_TO_RENDER_PER_BATCH}
        updateCellsBatchingPeriod={FEED_CONFIG.UPDATE_CELLS_BATCHING_PERIOD_MS}
        windowSize={FEED_CONFIG.WINDOW_SIZE}
        contentContainerStyle={styles.listContent}
      />

      <CommentsSheet
        visible={isCommentsVisible}
        postId={commentsPostId ?? ""}
        onClose={handleCloseComments}
        onCommentPosted={handleCommentPosted}
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
    paddingBottom: 16,
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
  retryButton: {
    flexDirection: "row",
    alignItems: "center",
    gap: 6,
    marginTop: 16,
    paddingHorizontal: 20,
    paddingVertical: 10,
    borderRadius: 20,
    backgroundColor: CTA_PRIMARY,
    minHeight: 44,
  },
  retryText: {
    fontSize: 14,
    fontWeight: "600",
    color: "#FFFFFF",
  },
});
