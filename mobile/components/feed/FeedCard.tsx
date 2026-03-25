import React, { useCallback, useRef, useState } from "react";
import {
  View,
  Text,
  Image,
  Pressable,
  StyleSheet,
  Share,
  Alert,
  Platform,
  Dimensions,
} from "react-native";
import ReanimatedAnimated, {
  useSharedValue,
  useAnimatedStyle,
  withSpring,
  interpolate,
  FadeInDown,
  FadeIn,
  FadeOut,
} from "react-native-reanimated";
import { Ionicons } from "@expo/vector-icons";
import { useRouter } from "expo-router";

import { THEME } from "../../constants/theme";
import { FEED_CONFIG, UNIVERSAL_LINK_ORIGIN } from "../../constants/config";
import { formatTimeAgo } from "../../lib/format";
import { ReactionButton } from "./ReactionButton";
import { DropdownMenu, type DropdownMenuItem } from "../ui/DropdownMenu";
import { FONTS } from "../../hooks/useFonts";
import { useTheme } from "../../lib/theme-context";
import { hapticLight, hapticMedium } from "../../lib/haptics";
import type { FeedPost } from "./types";

const IMAGE_HEIGHT = 240;
const LONG_PRESS_DELAY_MS = 500;
const DOUBLE_TAP_DELAY_MS = 300;
const HEART_OVERLAY_SIZE = 60;

interface FeedCardProps {
  post: FeedPost;
  index: number;
  hasReacted: boolean;
  onReact: (postId: string) => void;
  onReport: (postId: string) => void;
  onBlock: (userId: string, displayName: string) => void;
  onCommentPress: (postId: string) => void;
}

/**
 * Feed post card showing user info, before/after images side-by-side,
 * caption, reaction button, comment count.
 * Long-press triggers a cross-platform dropdown menu.
 * Double-tap on the image area triggers a like with heart overlay.
 */
export const FeedCard = React.memo(function FeedCard({
  post,
  index,
  hasReacted,
  onReact,
  onReport,
  onBlock,
  onCommentPress,
}: FeedCardProps) {
  const { theme } = useTheme();
  const router = useRouter();

  // Press scale + shadow animation (Reanimated — runs on UI thread)
  const pressScale = useSharedValue(1);
  const commentScale = useSharedValue(1);
  const commentPressStyle = useAnimatedStyle(() => ({
    transform: [{ scale: commentScale.value }],
  }));
  const pressAnimStyle = useAnimatedStyle(() => ({
    transform: [{ scale: pressScale.value }],
    shadowRadius: interpolate(pressScale.value, [0.98, 1], [4, 8]),
    shadowOffset: {
      width: 0,
      height: interpolate(pressScale.value, [0.98, 1], [1, 2]),
    },
  }));
  const handleCardPressIn = useCallback(() => {
    pressScale.value = withSpring(0.98, THEME.animation.press);
  }, [pressScale]);
  const handleCardPressOut = useCallback(() => {
    pressScale.value = withSpring(1, THEME.animation.press);
  }, [pressScale]);

  const handleReact = useCallback(() => {
    onReact(post.post_id);
  }, [onReact, post.post_id]);

  const handleComment = useCallback(() => {
    onCommentPress(post.post_id);
  }, [onCommentPress, post.post_id]);

  const handleCommentPressIn = useCallback(() => {
    commentScale.value = withSpring(0.96, THEME.animation.press);
  }, [commentScale]);
  const handleCommentPressOut = useCallback(() => {
    commentScale.value = withSpring(1, THEME.animation.press);
  }, [commentScale]);

  const handlePostPress = useCallback(() => {
    router.push({
      pathname: "/post/[postId]",
      params: {
        postId: post.post_id,
        beforeImage: post.before_image_url,
        afterImage: post.after_image_url,
        caption: post.caption ?? "",
        displayName: post.display_name ?? "",
        username: post.username ?? "",
        avatarUrl: post.avatar_url ?? "",
        userId: post.user_id,
        reactionCount: String(post.reaction_count),
        commentCount: String(post.comment_count),
        timeAgo: formatTimeAgo(post.created_at),
        hasReacted: String(hasReacted),
      },
    });
  }, [router, post, hasReacted]);

  // ─── Long-press dropdown menu ────────────────────────────────────────────
  const [menuVisible, setMenuVisible] = useState(false);
  const [menuAnchor, setMenuAnchor] = useState({ top: 0, right: 0 });
  const cardRef = useRef<View>(null);

  const handleLongPress = useCallback(() => {
    if (doubleTapFiredRef.current) return; // Don't show menu if double-tap just fired
    hapticLight();
    // Measure card position to anchor the dropdown near the top-right
    cardRef.current?.measureInWindow((x, y, width, _height) => {
      const { width: screenWidth } = Dimensions.get("window");
      setMenuAnchor({
        top: y + THEME.spacing.sm,
        right: Math.max(THEME.spacing.xl, screenWidth ? screenWidth - x - width + THEME.spacing.xl : THEME.spacing.xl),
      });
      setMenuVisible(true);
    });
  }, []);

  const shareMessage = post.caption
    ? `${post.caption} — Check it out on NXME ${UNIVERSAL_LINK_ORIGIN}`
    : `Check out this glow-up on NXME ${UNIVERSAL_LINK_ORIGIN}`;
  const blockLabel = post.display_name
    ? `Block ${post.display_name}`
    : "Block User";

  const menuItems: DropdownMenuItem[] = [
    {
      label: "Share",
      icon: "share-outline",
      onPress: async () => {
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
      },
    },
    {
      label: blockLabel,
      icon: "ban-outline",
      onPress: () => {
        onBlock(post.user_id, post.display_name ?? "this user");
      },
    },
    {
      label: "Report",
      icon: "flag-outline",
      onPress: () => {
        onReport(post.post_id);
      },
      destructive: true,
    },
  ];

  // ─── Double-tap to like ──────────────────────────────────────────────────
  const lastTapRef = useRef<number>(0);
  const doubleTapFiredRef = useRef(false);
  const [showHeartOverlay, setShowHeartOverlay] = useState(false);

  const handleImageTap = useCallback(() => {
    const now = Date.now();
    if (now - lastTapRef.current < DOUBLE_TAP_DELAY_MS) {
      // Double-tap detected — set flag to suppress long-press
      lastTapRef.current = 0; // Reset to avoid triple-tap
      doubleTapFiredRef.current = true;
      setTimeout(() => { doubleTapFiredRef.current = false; }, 600);
      hapticMedium();
      onReact(post.post_id);
      setShowHeartOverlay(true);
      setTimeout(() => setShowHeartOverlay(false), 600);
    } else {
      lastTapRef.current = now;
      // Single tap — navigate to post detail after a brief delay to
      // distinguish from double-tap. If a second tap arrives within
      // DOUBLE_TAP_DELAY_MS, the navigation won't fire.
      setTimeout(() => {
        if (Date.now() - lastTapRef.current >= DOUBLE_TAP_DELAY_MS && lastTapRef.current !== 0) {
          lastTapRef.current = 0;
          handlePostPress();
        }
      }, DOUBLE_TAP_DELAY_MS);
    }
  }, [onReact, post.post_id, handlePostPress]);

  // ─── Navigate to user profile ────────────────────────────────────────────
  const handleUserPress = useCallback(() => {
    hapticLight();
    if (post.username) {
      router.push({
        pathname: "/card/[username]",
        params: { username: post.username },
      });
    }
  }, [router, post.username]);

  const timeAgo = formatTimeAgo(post.created_at);
  const staggerDelay = Math.min(index, FEED_CONFIG.MAX_STAGGER_ITEMS) * 50;
  const displayName = post.display_name || "User";

  return (
    <ReanimatedAnimated.View
      style={styles.card}
      entering={FadeInDown.duration(THEME.animation.duration.normal).delay(staggerDelay).damping(18)}
    >
      <ReanimatedAnimated.View style={pressAnimStyle}>
      <Pressable
        onPressIn={handleCardPressIn}
        onPressOut={handleCardPressOut}
        accessibilityLabel={`Post by ${displayName}${post.caption ? `: ${post.caption}` : ""}, ${post.reaction_count} reactions, ${post.comment_count} comments, ${timeAgo}`}
      >
        {/* User info row — avatar + display name + Before/After indicator */}
        <View style={styles.headerRow}>
          <Pressable
            onPress={handleUserPress}
            style={styles.userRow}
            accessibilityLabel={`View ${displayName}'s profile`}
            accessibilityRole="link"
            disabled={!post.username}
          >
            <View style={[styles.sparkleIcon, { backgroundColor: theme.accent + "33" }]}>
              <Ionicons name="sparkles" size={10} color={theme.accent} />
            </View>
            {post.avatar_url ? (
              <Image
                source={{ uri: post.avatar_url }}
                style={styles.avatar}
                accessibilityLabel={`${displayName}'s avatar`}
              />
            ) : (
              <View style={[styles.avatar, styles.avatarPlaceholder]}>
                <Ionicons name="person" size={14} color={THEME.colors.textSecondary} />
              </View>
            )}
            <Text style={styles.displayName} numberOfLines={1}>
              {displayName}
            </Text>
          </Pressable>
          <View style={styles.beforeAfterRow}>
            <Text style={styles.beforeAfterLabel}>Before</Text>
            <Ionicons name="arrow-forward" size={10} color={theme.accent} />
            <Text style={[styles.beforeAfterLabel, { color: theme.accent }]}>After</Text>
          </View>
        </View>

        {/* Before / After images side by side */}
        <Pressable
          onPress={handleImageTap}
          onLongPress={handleLongPress}
          delayLongPress={LONG_PRESS_DELAY_MS}
          accessibilityHint="Double-tap to like. Long press for share, block, and report options"
        >
        <View style={styles.imageRow} ref={cardRef}>
          <View style={styles.imageContainer}>
            <Image
              source={{ uri: post.before_image_url }}
              style={styles.image}
              resizeMode="cover"
              accessibilityLabel={`Before photo by ${displayName}`}
            />
          </View>
          <View style={styles.imageDivider} />
          <View style={styles.imageContainer}>
            <Image
              source={{ uri: post.after_image_url }}
              style={styles.image}
              resizeMode="cover"
              accessibilityLabel={`After photo by ${displayName}`}
            />
          </View>

          {/* Heart overlay — double-tap feedback */}
          {showHeartOverlay ? (
            <ReanimatedAnimated.View
              entering={FadeIn.duration(150)}
              exiting={FadeOut.duration(450)}
              style={styles.heartOverlay}
              pointerEvents="none"
            >
              <Ionicons name="heart" size={HEART_OVERLAY_SIZE} color={THEME.colors.white} />
            </ReanimatedAnimated.View>
          ) : null}
        </View>

        {/* Caption */}
        {post.caption ? (
          <Text style={styles.caption} numberOfLines={3}>
            {post.caption}
          </Text>
        ) : null}
        </Pressable>

        {/* Actions row — outside the long-press Pressable to avoid button-in-button */}
        <View style={styles.actionsRow}>
          <ReactionButton
            reactionCount={post.reaction_count}
            hasReacted={hasReacted}
            onReact={handleReact}
          />

          <ReanimatedAnimated.View style={commentPressStyle}>
            <Pressable
              onPress={handleComment}
              onPressIn={handleCommentPressIn}
              onPressOut={handleCommentPressOut}
              style={styles.commentBadge}
              accessibilityLabel={`${post.comment_count} comments, tap to view`}
              accessibilityRole="button"
            >
              <Ionicons
                name="chatbubble-outline"
                size={20}
                color={THEME.colors.textSecondary}
              />
              <Text style={styles.commentCount}>{post.comment_count}</Text>
            </Pressable>
          </ReanimatedAnimated.View>

          <Text style={styles.timestamp}>{timeAgo}</Text>
        </View>
      </Pressable>
      </ReanimatedAnimated.View>

      {/* Context menu — cross-platform dropdown */}
      <DropdownMenu
        visible={menuVisible}
        onClose={() => setMenuVisible(false)}
        items={menuItems}
        anchorPosition={menuAnchor}
      />
    </ReanimatedAnimated.View>
  );
});

const styles = StyleSheet.create({
  card: {
    backgroundColor: THEME.colors.glass,
    borderRadius: THEME.radius.lg,
    marginHorizontal: THEME.spacing.xl,
    marginBottom: THEME.spacing.xl,
    overflow: "hidden",
    borderWidth: 1,
    borderColor: THEME.colors.glassBorder,
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: "rgba(255,255,255,0.1)",
    ...THEME.shadow.glass,
  },
  // ─── Header row (user info + Before -> After) ─────────────────────────
  headerRow: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    paddingHorizontal: THEME.spacing.lg,
    paddingVertical: THEME.spacing.sm + 2,
  },
  userRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: THEME.spacing.sm,
    flexShrink: 1,
  },
  sparkleIcon: {
    width: 20,
    height: 20,
    borderRadius: 10,
    alignItems: "center",
    justifyContent: "center",
  },
  avatar: {
    width: 28,
    height: 28,
    borderRadius: 14,
  },
  avatarPlaceholder: {
    backgroundColor: THEME.colors.surfaceElevated,
    alignItems: "center",
    justifyContent: "center",
  },
  displayName: {
    fontFamily: FONTS.bodySemiBold,
    fontSize: 14,
    color: THEME.colors.textPrimary,
    flexShrink: 1,
  },
  beforeAfterRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: THEME.spacing.xs,
    marginLeft: THEME.spacing.sm,
  },
  beforeAfterLabel: {
    fontFamily: FONTS.bodyMedium,
    fontSize: 11,
    fontWeight: "600",
    color: THEME.colors.textSecondary,
    textTransform: "uppercase",
    letterSpacing: 0.5,
  },
  // ─── Image area ─────────────────────────────────────────────────────────
  imageRow: {
    flexDirection: "row",
    height: IMAGE_HEIGHT,
    overflow: "hidden",
  },
  imageContainer: {
    flex: 1,
    position: "relative",
  },
  image: {
    width: "100%",
    height: "100%",
  },
  imageDivider: {
    width: 2,
    backgroundColor: "rgba(255,255,255,0.05)",
  },
  // ─── Heart overlay ──────────────────────────────────────────────────────
  heartOverlay: {
    ...StyleSheet.absoluteFillObject,
    alignItems: "center",
    justifyContent: "center",
    zIndex: 10,
  },
  // ─── Caption & actions ──────────────────────────────────────────────────
  caption: {
    fontFamily: FONTS.body,
    ...THEME.typography.body,
    color: THEME.colors.textPrimary,
    paddingHorizontal: THEME.spacing.lg,
    paddingTop: THEME.spacing.md,
  },
  actionsRow: {
    flexDirection: "row",
    alignItems: "center",
    paddingHorizontal: THEME.spacing.lg,
    paddingVertical: THEME.spacing.sm + 2,
    gap: THEME.spacing.md,
  },
  commentBadge: {
    flexDirection: "row",
    alignItems: "center",
    gap: THEME.spacing.xs,
    minHeight: 44,
    paddingHorizontal: THEME.spacing.xs,
    paddingVertical: THEME.spacing.sm,
  },
  commentCount: {
    fontFamily: FONTS.bodyMedium,
    fontSize: 14,
    fontWeight: "600",
    color: THEME.colors.textSecondary,
  },
  timestamp: {
    fontFamily: FONTS.body,
    ...THEME.typography.caption,
    color: THEME.colors.textSecondary,
    marginLeft: "auto",
  },
});
