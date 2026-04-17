import { useEffect, useCallback, useState, useRef } from "react";
import {
  ActivityIndicator,
  Alert,
  FlatList,
  Platform,
  RefreshControl,
  StyleSheet,
  View,
} from "react-native";
import Animated from "react-native-reanimated";

import { THEME } from "../../constants/theme";
import { TAB_BAR_HEIGHT } from "./_layout";
import { useTheme } from "../../lib/theme-context";
import { PageBackground } from "../../components/ui/PageBackground";
import { FEED_CONFIG } from "../../constants/config";
import { FeedCard } from "../../components/feed/FeedCard";
import { FeedSkeleton } from "../../components/feed/FeedSkeleton";
import { SortTabs } from "../../components/feed/SortTabs";
import { EmailVerifyBanner } from "../../components/feed/EmailVerifyBanner";
import { CommentsSheet } from "../../components/comments/CommentsSheet";
import { useFeed } from "../../components/feed/useFeed";
import type { FeedPost } from "../../components/feed/types";
import { blockUser } from "../../lib/block";
import { reportPost } from "../../lib/report";
import { hapticLight } from "../../lib/haptics";
import { showToast } from "../../lib/toast";
import { EmptyState } from "../../components/ui/EmptyState";
import { useTabBar } from "../../lib/tab-bar-context";

const AnimatedFlatList = Animated.createAnimatedComponent(FlatList<FeedPost>);

/** Home / Feed tab — Story 5-4 */
export default function HomeScreen() {
  const { theme } = useTheme();
  const {
    posts,
    isLoading,
    isRefreshing,
    isLoadingMore,
    error,
    activeSort,
    reactedPostIds,
    loadFeed,
    loadMore,
    refresh,
    changeSort,
    reactToPost,
    incrementCommentCount,
    removePostsByUser,
  } = useFeed();

  // Tab bar scroll integration
  const { scrollHandler, registerScrollToTop } = useTabBar();
  const flatListRef = useRef<FlatList<FeedPost>>(null);

  useEffect(() => {
    registerScrollToTop(() => {
      flatListRef.current?.scrollToOffset({ offset: 0, animated: true });
    });
    return () => registerScrollToTop(null);
  }, [registerScrollToTop]);

  // Comments sheet state
  const [commentsPostId, setCommentsPostId] = useState<string | null>(null);
  const isCommentsVisible = commentsPostId !== null;

  const handleCommentPress = useCallback((postId: string) => {
    setCommentsPostId(postId);
  }, []);

  const handleCloseComments = useCallback(() => {
    setCommentsPostId(null);
  }, []);

  const handleCommentPosted = useCallback((postId: string) => {
    incrementCommentCount(postId);
  }, [incrementCommentCount]);

  const handleReport = useCallback((postId: string) => {
    // Confirmation dialog — keep as Alert
    Alert.alert(
      "Report Post",
      "Are you sure you want to report this post as inappropriate?",
      [
        { text: "Cancel", style: "cancel" },
        {
          text: "Report",
          style: "destructive",
          onPress: async () => {
            try {
              await reportPost(postId);
              showToast({
                kind: "success",
                message: "Thanks for helping keep NXME safe. We'll review this post.",
              });
            } catch (err: unknown) {
              const status = (err as { status?: number }).status;
              if (status === 429) {
                showToast({
                  kind: "warning",
                  message: "You've reported a lot recently. Give it a little while.",
                });
              } else {
                showToast({
                  kind: "error",
                  message: "Couldn't submit that report. Try again.",
                });
              }
            }
          },
        },
      ],
    );
  }, []);

  const handleBlock = useCallback(
    (userId: string, displayName: string) => {
      // Confirmation dialog — keep as Alert
      Alert.alert(
        `Block ${displayName}?`,
        "They won't be able to see your posts or comment on them.",
        [
          { text: "Cancel", style: "cancel" },
          {
            text: "Block",
            style: "destructive",
            onPress: async () => {
              try {
                await blockUser(userId);
                removePostsByUser(userId);
              } catch {
                showToast({
                  kind: "error",
                  message: "Couldn't block that user. Try again.",
                });
              }
            },
          },
        ],
      );
    },
    [removePostsByUser],
  );

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
        onBlock={handleBlock}
        onCommentPress={handleCommentPress}
      />
    ),
    [reactedPostIds, reactToPost, handleReport, handleBlock, handleCommentPress],
  );

  const renderFooter = useCallback(() => {
    if (!isLoadingMore) return null;
    return (
      <View style={styles.footer}>
        <ActivityIndicator size="small" color={theme.accent} />
      </View>
    );
  }, [isLoadingMore, theme.accent]);

  // One source of truth for the feed's empty region: the FlatList's
  // ListEmptyComponent + contentContainerStyle flexGrow:1 (styles.listContent)
  // lets EmptyState (center={true}) stretch to the full available area
  // below the list header. Error branch renders the same primitive with
  // a Try Again action so the title lands at the same vertical spot
  // whether the list is empty-by-success or empty-by-failure.
  const renderEmpty = useCallback(() => {
    if (isLoading) return null;
    if (error) {
      return (
        <EmptyState
          icon="alert-circle-outline"
          title="Could not load posts"
          description={error.message}
          action={{
            label: "Try Again",
            onPress: loadFeed,
            accessibilityLabel: "Retry loading feed",
          }}
        />
      );
    }
    return (
      <EmptyState
        icon="images-outline"
        title="No posts yet"
        description="Be the first to share your glow-up"
      />
    );
  }, [isLoading, error, loadFeed]);

  const renderHeader = useCallback(
    () => (
      <>
        <EmailVerifyBanner />
        <SortTabs activeSort={activeSort} onSortChange={changeSort} />
      </>
    ),
    [activeSort, changeSort],
  );

  // Loading state: show skeleton
  if (isLoading && posts.length === 0) {
    return (
      <View style={styles.container}>
        <PageBackground overlayOpacity={0.88} />
        {renderHeader()}
        <FeedSkeleton />
      </View>
    );
  }

  return (
    <View style={styles.container}>
      <PageBackground overlayOpacity={0.88} />
      <AnimatedFlatList
        ref={flatListRef}
        data={posts}
        keyExtractor={keyExtractor}
        renderItem={renderItem}
        ListHeaderComponent={renderHeader}
        ListFooterComponent={renderFooter}
        ListEmptyComponent={renderEmpty}
        onEndReached={loadMore}
        onEndReachedThreshold={0.5}
        onScroll={scrollHandler}
        scrollEventThrottle={16}
        refreshControl={
          <RefreshControl
            refreshing={isRefreshing}
            onRefresh={() => { hapticLight(); refresh(); }}
            colors={[theme.accent]}
            tintColor={theme.accent}
            progressBackgroundColor={THEME.colors.bg}
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
    backgroundColor: THEME.colors.bg,
  },
  listContent: {
    flexGrow: 1,
    paddingBottom: TAB_BAR_HEIGHT,
  },
  footer: {
    paddingVertical: THEME.spacing.xl,
    alignItems: "center",
  },
});
