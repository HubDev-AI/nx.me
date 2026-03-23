/**
 * CommentsSheet — bottom sheet displaying comments for a feed post.
 *
 * Opens via Modal with slide-in animation from bottom. Swipe-down to dismiss.
 * Guest users see an auth prompt when tapping the comment input.
 * Registered users post with optimistic UI; rollback on API failure with error toast.
 */
import { useEffect, useCallback, useRef } from "react";
import {
  View,
  Text,
  FlatList,
  Modal,
  Pressable,
  Animated,
  KeyboardAvoidingView,
  Platform,
  PanResponder,
  Dimensions,
  StyleSheet,
  AccessibilityInfo,
} from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { useRouter } from "expo-router";

import { THEME } from "../../constants/theme";
import { FONTS } from "../../hooks/useFonts";
import { COMMENTS_CONFIG, MIN_TOUCH_TARGET } from "../../constants/config";
import { useComments } from "./useComments";
import { CommentItem } from "./CommentItem";
import { CommentInput } from "./CommentInput";
import { CommentSkeleton } from "./CommentSkeleton";
import type { Comment } from "./types";

const { height: SCREEN_HEIGHT } = Dimensions.get("window");

interface CommentsSheetProps {
  visible: boolean;
  postId: string;
  onClose: () => void;
  /** Called when a comment is posted so the parent can increment comment_count. */
  onCommentPosted?: (postId: string) => void;
}

export function CommentsSheet({
  visible,
  postId,
  onClose,
  onCommentPosted,
}: CommentsSheetProps) {
  const router = useRouter();
  const {
    comments,
    isLoading,
    isLoadingMore,
    hasMore,
    error,
    isAuthenticated,
    isPosting,
    postError,
    loadComments,
    loadMore,
    postComment,
    reset,
  } = useComments();

  // ---------------------------------------------------------------------------
  // Focus management refs
  // ---------------------------------------------------------------------------
  const closeButtonRef = useRef<React.ElementRef<typeof Pressable>>(null);

  // ---------------------------------------------------------------------------
  // Animation refs
  // ---------------------------------------------------------------------------
  const backdropOpacity = useRef(new Animated.Value(0)).current;
  const sheetTranslateY = useRef(new Animated.Value(SCREEN_HEIGHT)).current;
  const panY = useRef(new Animated.Value(0)).current;

  // ---------------------------------------------------------------------------
  // Swipe-down to dismiss via PanResponder
  // ---------------------------------------------------------------------------
  const panResponder = useRef(
    PanResponder.create({
      onStartShouldSetPanResponder: () => false,
      onMoveShouldSetPanResponder: (_, gestureState) =>
        gestureState.dy > 10,
      onPanResponderMove: (_, gestureState) => {
        if (gestureState.dy > 0) {
          panY.setValue(gestureState.dy);
        }
      },
      onPanResponderRelease: (_, gestureState) => {
        if (gestureState.dy > COMMENTS_CONFIG.SWIPE_DISMISS_THRESHOLD) {
          handleClose();
        } else {
          Animated.spring(panY, {
            toValue: 0,
            useNativeDriver: true,
            tension: 40,
            friction: 7,
          }).start();
        }
      },
    }),
  ).current;

  // ---------------------------------------------------------------------------
  // Open / close animations
  // ---------------------------------------------------------------------------
  const animateIn = useCallback(() => {
    sheetTranslateY.setValue(SCREEN_HEIGHT);
    backdropOpacity.setValue(0);
    panY.setValue(0);

    Animated.parallel([
      Animated.timing(backdropOpacity, {
        toValue: COMMENTS_CONFIG.SCRIM_OPACITY,
        duration: COMMENTS_CONFIG.ENTER_DURATION_MS,
        useNativeDriver: true,
      }),
      Animated.timing(sheetTranslateY, {
        toValue: 0,
        duration: COMMENTS_CONFIG.ENTER_DURATION_MS,
        useNativeDriver: true,
      }),
    ]).start();
  }, [backdropOpacity, sheetTranslateY, panY]);

  const animateOut = useCallback(
    (callback: () => void) => {
      Animated.parallel([
        Animated.timing(backdropOpacity, {
          toValue: 0,
          duration: COMMENTS_CONFIG.EXIT_DURATION_MS,
          useNativeDriver: true,
        }),
        Animated.timing(sheetTranslateY, {
          toValue: SCREEN_HEIGHT,
          duration: COMMENTS_CONFIG.EXIT_DURATION_MS,
          useNativeDriver: true,
        }),
      ]).start(callback);
    },
    [backdropOpacity, sheetTranslateY],
  );

  // ---------------------------------------------------------------------------
  // Open: animate in + fetch comments + accessibility announcement
  // ---------------------------------------------------------------------------
  useEffect(() => {
    if (visible && postId) {
      animateIn();
      loadComments(postId);
      AccessibilityInfo.announceForAccessibility("Dialog opened");
      closeButtonRef.current?.focus();
    }
  }, [visible, postId, animateIn, loadComments]);

  // ---------------------------------------------------------------------------
  // Close handler
  // ---------------------------------------------------------------------------
  const handleClose = useCallback(() => {
    animateOut(() => {
      reset();
      onClose();
    });
  }, [animateOut, reset, onClose]);

  // ---------------------------------------------------------------------------
  // Post comment
  // ---------------------------------------------------------------------------
  const handleSubmit = useCallback(
    (content: string) => {
      postComment(postId, content);
      onCommentPosted?.(postId);
    },
    [postId, postComment, onCommentPosted],
  );

  // ---------------------------------------------------------------------------
  // Auth prompt — navigate to login
  // ---------------------------------------------------------------------------
  const handleAuthPrompt = useCallback(() => {
    handleClose();
    router.push("/(auth)/signup");
  }, [handleClose, router]);

  // ---------------------------------------------------------------------------
  // Load more on end reached
  // ---------------------------------------------------------------------------
  const handleEndReached = useCallback(() => {
    if (hasMore && !isLoadingMore) {
      loadMore(postId);
    }
  }, [hasMore, isLoadingMore, loadMore, postId]);

  // ---------------------------------------------------------------------------
  // Render helpers
  // ---------------------------------------------------------------------------
  const renderItem = useCallback(
    ({ item, index }: { item: Comment; index: number }) => (
      <CommentItem comment={item} index={index} />
    ),
    [],
  );

  const keyExtractor = useCallback(
    (item: Comment) => item.comment_id,
    [],
  );

  const renderEmpty = useCallback(() => {
    if (isLoading) return null;
    if (error) {
      return (
        <View style={styles.emptyState}>
          <Ionicons name="alert-circle" size={28} color={THEME.colors.destructive} />
          <Text style={styles.errorText}>{error}</Text>
          <Pressable
            onPress={() => loadComments(postId)}
            style={styles.retryButton}
            accessibilityLabel="Retry loading comments"
            accessibilityRole="button"
          >
            <Text style={styles.retryText}>Retry</Text>
          </Pressable>
        </View>
      );
    }
    return (
      <View style={styles.emptyState}>
        <Ionicons
          name="chatbubble-outline"
          size={28}
          color={THEME.colors.textDisabled}
        />
        <Text style={styles.emptyText}>No comments yet</Text>
        <Text style={styles.emptyHint}>Be the first to comment</Text>
      </View>
    );
  }, [isLoading, error, loadComments, postId]);

  return (
    <Modal
      visible={visible}
      transparent
      animationType="none"
      onRequestClose={handleClose}
      statusBarTranslucent
    >
      {/* Scrim backdrop */}
      <Animated.View
        style={[styles.backdrop, { opacity: backdropOpacity }]}
      >
        <Pressable
          style={StyleSheet.absoluteFill}
          onPress={handleClose}
          accessibilityLabel="Close comments"
          accessibilityRole="button"
        />
      </Animated.View>

      {/* Sheet */}
      <KeyboardAvoidingView
        style={styles.keyboardAvoid}
        behavior={Platform.OS === "ios" ? "padding" : undefined}
        keyboardVerticalOffset={0}
      >
        {/* Dismiss area above the sheet — KeyboardAvoidingView sits over the
            backdrop Animated.View in the z-order, so taps in this region would
            be swallowed without this extra Pressable. */}
        <Pressable
          style={styles.dismissArea}
          onPress={handleClose}
          accessibilityLabel="Close comments"
          accessibilityRole="button"
        />
        <Animated.View
          style={[
            styles.sheet,
            {
              transform: [
                { translateY: Animated.add(sheetTranslateY, panY) },
              ],
            },
          ]}
          {...panResponder.panHandlers}
        >
          {/* Drag handle */}
          <View style={styles.handleBar} />

          {/* Header */}
          <View style={styles.header}>
            <Text style={styles.headerTitle}>Comments</Text>
            <Pressable
              ref={closeButtonRef}
              onPress={handleClose}
              hitSlop={12}
              accessibilityLabel="Close comments"
              accessibilityRole="button"
              style={styles.closeButton}
            >
              <Ionicons name="close" size={24} color={THEME.colors.textSecondary} />
            </Pressable>
          </View>

          {/* Post error toast */}
          {postError ? (
            <View style={styles.errorBanner} accessibilityRole="alert">
              <Ionicons name="alert-circle" size={16} color={THEME.colors.destructive} />
              <Text style={styles.errorBannerText}>{postError}</Text>
            </View>
          ) : null}

          {/* Comment list */}
          {isLoading ? (
            <CommentSkeleton />
          ) : (
            <FlatList
              data={comments}
              renderItem={renderItem}
              keyExtractor={keyExtractor}
              onEndReached={handleEndReached}
              onEndReachedThreshold={0.3}
              ListEmptyComponent={renderEmpty}
              showsVerticalScrollIndicator={false}
              keyboardShouldPersistTaps="handled"
              contentContainerStyle={
                comments.length === 0 ? styles.emptyListContent : undefined
              }
            />
          )}

          {/* Comment input */}
          <CommentInput
            isAuthenticated={isAuthenticated}
            isPosting={isPosting}
            onSubmit={handleSubmit}
            onAuthPrompt={handleAuthPrompt}
          />
        </Animated.View>
      </KeyboardAvoidingView>
    </Modal>
  );
}

const styles = StyleSheet.create({
  backdrop: {
    ...StyleSheet.absoluteFillObject,
    backgroundColor: "#000000",
  },
  keyboardAvoid: {
    flex: 1,
    justifyContent: "flex-end",
  },
  dismissArea: {
    flex: 1,
  },
  sheet: {
    maxHeight: SCREEN_HEIGHT * 0.75,
    backgroundColor: THEME.colors.glass,
    borderTopLeftRadius: THEME.radius.xl,
    borderTopRightRadius: THEME.radius.xl,
    borderTopWidth: 0.5,
    borderTopColor: THEME.colors.glassBorder,
    paddingTop: THEME.spacing.sm,
    paddingBottom: THEME.spacing.lg,
  },
  handleBar: {
    width: 36,
    height: 4,
    borderRadius: 2,
    backgroundColor: THEME.colors.borderFocused,
    alignSelf: "center",
    marginBottom: THEME.spacing.sm,
  },
  header: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    paddingHorizontal: THEME.spacing.lg,
    marginBottom: THEME.spacing.xs,
  },
  headerTitle: {
    fontFamily: FONTS.display,
    color: THEME.colors.textPrimary,
    fontSize: 18,
    letterSpacing: THEME.typography.heading.letterSpacing,
  },
  closeButton: {
    width: MIN_TOUCH_TARGET,
    height: MIN_TOUCH_TARGET,
    alignItems: "center",
    justifyContent: "center",
  },
  errorBanner: {
    flexDirection: "row",
    alignItems: "center",
    gap: THEME.spacing.sm,
    marginHorizontal: THEME.spacing.lg,
    marginBottom: THEME.spacing.sm,
    backgroundColor: "rgba(239, 68, 68, 0.1)",
    borderRadius: THEME.radius.sm,
    padding: THEME.spacing.md,
  },
  errorBannerText: {
    fontFamily: FONTS.bodyMedium,
    color: THEME.colors.destructive,
    fontSize: 13,
    flex: 1,
  },
  emptyState: {
    alignItems: "center",
    justifyContent: "center",
    paddingVertical: THEME.spacing.xxxl + THEME.spacing.sm,
    gap: THEME.spacing.sm,
  },
  emptyText: {
    fontFamily: FONTS.display,
    color: THEME.colors.textPrimary,
    fontSize: 18,
    letterSpacing: THEME.typography.heading.letterSpacing,
  },
  emptyHint: {
    fontFamily: FONTS.displayItalic,
    color: THEME.colors.textSecondary,
    ...THEME.typography.caption,
  },
  errorText: {
    fontFamily: FONTS.body,
    color: THEME.colors.destructive,
    fontSize: 14,
    textAlign: "center",
  },
  retryButton: {
    paddingHorizontal: THEME.spacing.lg,
    paddingVertical: THEME.spacing.sm,
    backgroundColor: THEME.colors.surfaceElevated,
    borderRadius: THEME.radius.sm,
    minHeight: MIN_TOUCH_TARGET,
    justifyContent: "center",
    marginTop: THEME.spacing.xs,
  },
  retryText: {
    fontFamily: FONTS.bodySemiBold,
    color: THEME.colors.textPrimary,
    fontSize: 14,
  },
  emptyListContent: {
    flexGrow: 1,
  },
});
