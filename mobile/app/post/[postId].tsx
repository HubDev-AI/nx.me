/**
 * Post detail — full-screen before/after view with larger images.
 * Reuses ReactionButton and CommentsSheet components.
 */
import { useState, useCallback } from "react";
import { View, Text, Image, ScrollView, StyleSheet, Pressable, Share, Alert, ActivityIndicator, Platform } from "react-native";
import { useLocalSearchParams, Stack, useRouter } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Ionicons } from "@expo/vector-icons";
import Animated, {
  useSharedValue,
  useAnimatedStyle,
  withSpring,
} from "react-native-reanimated";

import { THEME } from "../../constants/theme";
import { OVERLAY_LIGHT, OVERLAY_MEDIUM } from "../../constants/colors";
import { FEED_ENDPOINTS, UNIVERSAL_LINK_ORIGIN } from "../../constants/config";
import { FONTS } from "../../hooks/useFonts";
import { useTheme } from "../../lib/theme-context";
import { apiFetch, ApiError } from "../../lib/api";
import { hapticLight, hapticError } from "../../lib/haptics";
import { blockUser } from "../../lib/block";
import { reportPost } from "../../lib/report";
import { ReactionButton } from "../../components/feed/ReactionButton";
import { CommentsSheet } from "../../components/comments/CommentsSheet";
import { DropdownMenu } from "../../components/ui/DropdownMenu";
import type { ReactionResponse } from "../../components/feed/types";

export default function PostDetailScreen() {
  const {
    postId,
    beforeImage,
    afterImage,
    caption,
    displayName,
    username,
    userId,
    reactionCount: initialReactionCount,
    commentCount: initialCommentCount,
    timeAgo,
    hasReacted: initialHasReacted,
  } = useLocalSearchParams<{
    postId: string;
    beforeImage: string;
    afterImage: string;
    caption?: string;
    displayName?: string;
    username?: string;
    avatarUrl?: string;
    userId?: string;
    reactionCount?: string;
    commentCount?: string;
    timeAgo?: string;
    hasReacted?: string;
  }>();

  const insets = useSafeAreaInsets();
  const router = useRouter();
  const { theme } = useTheme();

  const [reactionCount, setReactionCount] = useState(Number(initialReactionCount) || 0);
  const [commentCount, setCommentCount] = useState(Number(initialCommentCount) || 0);
  const [hasReacted, setHasReacted] = useState(initialHasReacted === "true");
  const [commentsVisible, setCommentsVisible] = useState(false);
  const [menuVisible, setMenuVisible] = useState(false);
  const [isDeleting, setIsDeleting] = useState(false);

  // Press scale animations
  const backScale = useSharedValue(1);
  const shareScale = useSharedValue(1);
  const menuScale = useSharedValue(1);
  const commentBtnScale = useSharedValue(1);
  const backPressStyle = useAnimatedStyle(() => ({
    transform: [{ scale: backScale.value }],
  }));
  const sharePressStyle = useAnimatedStyle(() => ({
    transform: [{ scale: shareScale.value }],
  }));
  const menuPressStyle = useAnimatedStyle(() => ({
    transform: [{ scale: menuScale.value }],
  }));
  const commentBtnPressStyle = useAnimatedStyle(() => ({
    transform: [{ scale: commentBtnScale.value }],
  }));

  const handleReact = useCallback(async () => {
    if (hasReacted || !postId) return;

    // Optimistic update
    setHasReacted(true);
    setReactionCount((c) => c + 1);

    try {
      const response = await apiFetch<ReactionResponse>(
        FEED_ENDPOINTS.REACT(postId),
        { method: "POST" },
      );
      // Reconcile with server count
      setReactionCount(response.reaction_count);
    } catch {
      // Rollback on failure
      setHasReacted(false);
      setReactionCount((c) => Math.max(0, c - 1));
    }
  }, [hasReacted, postId]);

  const handleCommentPosted = useCallback(() => {
    setCommentCount((c) => c + 1);
  }, []);

  const handleShare = useCallback(async () => {
    hapticLight();
    const shareMessage = caption
      ? `${caption} — Check it out on NXME ${UNIVERSAL_LINK_ORIGIN}`
      : `Check out this glow-up on NXME ${UNIVERSAL_LINK_ORIGIN}`;
    try {
      if (Platform.OS === "web") {
        if (typeof navigator !== "undefined" && navigator.share) {
          await navigator.share({ url: UNIVERSAL_LINK_ORIGIN, text: shareMessage });
        } else if (typeof navigator !== "undefined" && navigator.clipboard) {
          await navigator.clipboard.writeText(UNIVERSAL_LINK_ORIGIN);
          Alert.alert("Link copied", "Share link copied to clipboard");
        }
      } else if (Platform.OS === "ios") {
        await Share.share({ message: shareMessage, url: UNIVERSAL_LINK_ORIGIN });
      } else {
        await Share.share({ message: shareMessage });
      }
    } catch {
      // User cancelled share sheet — not an error
    }
  }, [caption]);



  const handleDeletePost = useCallback(() => {
    if (!postId || isDeleting) return;

    Alert.alert(
      "Delete Post",
      "This will permanently remove this post. This action cannot be undone.",
      [
        { text: "Cancel", style: "cancel" },
        {
          text: "Delete",
          style: "destructive",
          onPress: async () => {
            setIsDeleting(true);
            try {
              await apiFetch<void>(FEED_ENDPOINTS.DELETE_POST(postId), {
                method: "DELETE",
              });
              hapticLight();
              router.back();
            } catch (err) {
              hapticError();
              const msg =
                err instanceof ApiError && err.status === 403
                  ? "You can only delete your own posts."
                  : "Failed to delete post. Please try again.";
              Alert.alert("Error", msg);
            } finally {
              setIsDeleting(false);
            }
          },
        },
      ],
    );
  }, [postId, isDeleting, router]);

  const handleBlockUser = useCallback(() => {
    if (!userId) return;
    const name = displayName || "this user";

    Alert.alert(
      "Block User",
      `Are you sure you want to block ${name}? You won't see their posts anymore.`,
      [
        { text: "Cancel", style: "cancel" },
        {
          text: "Block",
          style: "destructive",
          onPress: async () => {
            try {
              await blockUser(userId);
              hapticLight();
              Alert.alert("Blocked", `${name} has been blocked.`);
              router.back();
            } catch {
              hapticError();
              Alert.alert("Error", "Failed to block user. Please try again.");
            }
          },
        },
      ],
    );
  }, [userId, displayName, router]);

  const handleReportPost = useCallback(() => {
    if (!postId) return;

    Alert.alert(
      "Report Post",
      "Are you sure you want to report this post? Our team will review it.",
      [
        { text: "Cancel", style: "cancel" },
        {
          text: "Report",
          style: "destructive",
          onPress: async () => {
            try {
              await reportPost(postId);
              hapticLight();
              Alert.alert("Reported", "Thank you. Our team will review this post.");
            } catch {
              hapticError();
              Alert.alert("Error", "Failed to report post. Please try again.");
            }
          },
        },
      ],
    );
  }, [postId]);

  const toggleMenu = useCallback(() => {
    setMenuVisible((prev) => !prev);
  }, []);

  const closeMenu = useCallback(() => {
    setMenuVisible(false);
  }, []);

  const menuItems = [
    ...(userId
      ? [
          {
            label: "Block User",
            icon: "ban-outline" as const,
            onPress: handleBlockUser,
          },
        ]
      : []),
    {
      label: "Report Post",
      icon: "flag-outline" as const,
      onPress: handleReportPost,
      destructive: true,
    },
    {
      label: isDeleting ? "Deleting..." : "Delete Post",
      icon: "trash-outline" as const,
      onPress: handleDeletePost,
      destructive: true,
    },
  ];

  return (
    <>
      <Stack.Screen options={{ headerShown: false }} />
      <View style={styles.container}>
        <ScrollView
          style={styles.scrollView}
          contentContainerStyle={{ paddingBottom: insets.bottom + 16 }}
          showsVerticalScrollIndicator={false}
        >
          {/* Before image — full width */}
          <View>
            <View style={styles.beforeLabelWrap}>
              <View style={styles.beforeLabel}>
                <Text style={styles.labelText}>BEFORE</Text>
              </View>
            </View>
            <Image
              source={{ uri: beforeImage }}
              style={styles.fullImage}
              resizeMode="cover"
              accessibilityLabel={`Before photo by ${displayName ?? "user"}`}
            />
          </View>

          {/* 2px gap between images */}
          <View style={styles.imageGap} />

          {/* After image — full width */}
          <View>
            <View style={styles.afterLabelWrap}>
              <View style={[styles.afterLabel, { backgroundColor: theme.accent }]}>
                <Text style={styles.labelText}>AFTER</Text>
              </View>
            </View>
            <Image
              source={{ uri: afterImage }}
              style={styles.fullImage}
              resizeMode="cover"
              accessibilityLabel={`After photo by ${displayName ?? "user"}`}
            />
          </View>

          {/* Footer: actions row */}
          <View style={styles.footer}>
            <View style={styles.actionsRow}>
              <View style={styles.actionsLeft}>
                <ReactionButton
                  reactionCount={reactionCount}
                  hasReacted={hasReacted}
                  onReact={handleReact}
                />

                <Animated.View style={commentBtnPressStyle}>
                  <Pressable
                    onPress={() => setCommentsVisible(true)}
                    onPressIn={() => { commentBtnScale.value = withSpring(0.96, THEME.animation.press); }}
                    onPressOut={() => { commentBtnScale.value = withSpring(1, THEME.animation.press); }}
                    style={styles.commentButton}
                    accessibilityLabel={`${commentCount} comments, tap to view`}
                    accessibilityRole="button"
                  >
                    <Ionicons name="chatbubble-outline" size={18} color={THEME.colors.textSecondary} />
                    <Text style={styles.commentCountText}>{commentCount}</Text>
                  </Pressable>
                </Animated.View>
              </View>

              <Text style={styles.timeAgo}>{timeAgo || ""}</Text>
            </View>

            {/* Caption */}
            {caption ? (
              <Text style={styles.caption}>{caption}</Text>
            ) : null}
          </View>
        </ScrollView>
      </View>

      {/* Floating header row — close left, share + menu right */}
      <View style={[styles.headerRow, { paddingTop: insets.top + 12 }]}>
        <Animated.View style={backPressStyle}>
          <Pressable
            onPress={() => router.back()}
            onPressIn={() => { backScale.value = withSpring(0.92, THEME.animation.press); }}
            onPressOut={() => { backScale.value = withSpring(1, THEME.animation.press); }}
            style={styles.headerBtn}
            accessibilityLabel="Close"
            accessibilityRole="button"
          >
            <Ionicons name="close" size={16} color={THEME.colors.white} />
          </Pressable>
        </Animated.View>

        <View style={styles.headerRight}>
          <Animated.View style={sharePressStyle}>
            <Pressable
              onPress={handleShare}
              onPressIn={() => { shareScale.value = withSpring(0.92, THEME.animation.press); }}
              onPressOut={() => { shareScale.value = withSpring(1, THEME.animation.press); }}
              style={styles.headerBtn}
              accessibilityLabel="Share post"
              accessibilityRole="button"
            >
              <Ionicons name="share-outline" size={16} color={THEME.colors.white} />
            </Pressable>
          </Animated.View>

          <Animated.View style={menuPressStyle}>
            <Pressable
              onPress={toggleMenu}
              onPressIn={() => { menuScale.value = withSpring(0.92, THEME.animation.press); }}
              onPressOut={() => { menuScale.value = withSpring(1, THEME.animation.press); }}
              style={styles.headerBtn}
              accessibilityLabel="More options"
              accessibilityRole="button"
            >
              <Ionicons name="ellipsis-horizontal" size={16} color={THEME.colors.white} />
            </Pressable>
          </Animated.View>
        </View>
      </View>

      {/* Post actions dropdown */}
      <DropdownMenu
        visible={menuVisible}
        onClose={closeMenu}
        items={menuItems}
        anchorPosition={{ top: insets.top + 12 + 32 + 4, right: 20 }}
      />

      {/* Deleting overlay */}
      {isDeleting && (
        <View style={styles.deletingOverlay}>
          <ActivityIndicator size="large" color={THEME.colors.textPrimary} />
          <Text style={styles.deletingText}>Deleting...</Text>
        </View>
      )}

      <CommentsSheet
        visible={commentsVisible}
        postId={postId ?? ""}
        onClose={() => setCommentsVisible(false)}
        onCommentPosted={handleCommentPosted}
      />
    </>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: THEME.colors.bg,
  },
  scrollView: {
    flex: 1,
  },

  // ─── Header (floating) ──────────────────────────────────────────────────
  headerRow: {
    position: "absolute",
    top: 0,
    left: 0,
    right: 0,
    zIndex: 10,
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    paddingHorizontal: THEME.spacing.xl,
  },
  headerRight: {
    flexDirection: "row",
    gap: THEME.spacing.md,
  },
  headerBtn: {
    width: 32,
    height: 32,
    borderRadius: 16,
    backgroundColor: OVERLAY_LIGHT,
    alignItems: "center",
    justifyContent: "center",
  },

  // ─── Images ─────────────────────────────────────────────────────────────
  fullImage: {
    width: "100%",
    aspectRatio: 3 / 4,
  },
  imageGap: {
    height: 2,
    backgroundColor: THEME.colors.bg,
  },
  beforeLabelWrap: {
    position: "absolute",
    top: 10,
    left: 12,
    zIndex: 1,
  },
  beforeLabel: {
    paddingHorizontal: 8,
    paddingVertical: 4,
    borderRadius: THEME.radius.sm,
    backgroundColor: OVERLAY_LIGHT,
  },
  afterLabelWrap: {
    position: "absolute",
    top: 10,
    left: 12,
    zIndex: 1,
  },
  afterLabel: {
    paddingHorizontal: 8,
    paddingVertical: 4,
    borderRadius: THEME.radius.sm,
    // backgroundColor set dynamically via theme.accent in render
  },
  labelText: {
    fontFamily: FONTS.bodySemiBold,
    fontSize: 10,
    color: THEME.colors.white,
    letterSpacing: 1,
    textTransform: "uppercase",
  },

  // ─── Footer ─────────────────────────────────────────────────────────────
  footer: {
    paddingHorizontal: THEME.spacing.lg,
    paddingVertical: THEME.spacing.md,
  },
  actionsRow: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
  },
  actionsLeft: {
    flexDirection: "row",
    alignItems: "center",
    gap: THEME.spacing.md,
  },
  commentButton: {
    flexDirection: "row",
    alignItems: "center",
    gap: THEME.spacing.xs,
    minHeight: 44,
    paddingHorizontal: THEME.spacing.xs,
    paddingVertical: THEME.spacing.sm,
  },
  commentCountText: {
    fontFamily: FONTS.bodyMedium,
    fontSize: 14,
    color: THEME.colors.textSecondary,
  },
  timeAgo: {
    fontFamily: FONTS.body,
    fontSize: 13,
    color: THEME.colors.textSecondary,
  },
  caption: {
    fontFamily: FONTS.body,
    fontSize: 15,
    lineHeight: 23,
    color: THEME.colors.textPrimary,
    marginTop: THEME.spacing.sm,
  },

  // ─── Deleting overlay ───────────────────────────────────────────────────
  deletingOverlay: {
    ...StyleSheet.absoluteFillObject,
    backgroundColor: OVERLAY_MEDIUM,
    alignItems: "center",
    justifyContent: "center",
    zIndex: 100,
    gap: THEME.spacing.md,
  },
  deletingText: {
    fontFamily: FONTS.bodyMedium,
    fontSize: 16,
    color: THEME.colors.textPrimary,
  },
});
