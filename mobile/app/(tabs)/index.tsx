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
import { Ionicons } from "@expo/vector-icons";

import { THEME } from "../../constants/theme";
import { TAB_BAR_HEIGHT } from "./_layout";
import { useTheme } from "../../lib/theme-context";
import { PageBackground } from "../../components/ui/PageBackground";
import { QueryStateView } from "../../components/ui/QueryStateView";
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
import { Body, Heading } from "../../components/ui/Text";
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

  const renderEmpty = useCallback(() => {
    if (isLoading) return null;
    return (
      <View style={styles.emptyContainer}>
        <Ionicons name="images-outline" size={48} color={THEME.colors.textSecondary} />
        <Heading size="md" display={false} color="primary" style={styles.emptyTitle}>
          No posts yet
        </Heading>
        <Body color="secondary" style={styles.emptySubtitle}>
          Be the first to share your glow-up
        </Body>
      </View>
    );
  }, [isLoading]);

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
      <QueryStateView
        isLoading={false}
        isEmpty={false}
        error={posts.length === 0 && error ? error : null}
        onRetry={loadFeed}
      >
        <AnimatedFlatList
          ref={flatListRef as any}
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
      </QueryStateView>

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
  emptyContainer: {
    flex: 1,
    alignItems: "center",
    justifyContent: "center",
    paddingHorizontal: THEME.spacing.xxxl,
    paddingTop: 80,
    gap: THEME.spacing.sm,
  },
  emptyTitle: {
    marginTop: THEME.spacing.lg,
    textAlign: "center",
  },
  emptySubtitle: {
    textAlign: "center",
  },
  // retryButton and retryText removed — handled by QueryStateView
});
