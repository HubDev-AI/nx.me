import React, { useRef, useEffect, useCallback } from "react";
import {
  View,
  Text,
  Image,
  Pressable,
  Animated,
  AccessibilityInfo,
  ActionSheetIOS,
  Platform,
  Alert,
  StyleSheet,
  Share,
} from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { useRouter } from "expo-router";

import {
  BG_CARD,
  BG_ELEVATED,
  TEXT_PRIMARY,
  TEXT_SECONDARY,
  FEED_DIVIDER,
  BEFORE_OVERLAY,
  AFTER_OVERLAY_STRONG,
} from "../../constants/colors";
import { THEME } from "../../constants/theme";
import { FEED_CONFIG, UNIVERSAL_LINK_ORIGIN } from "../../constants/config";
import { formatTimeAgo } from "../../lib/format";
import { ReactionButton } from "./ReactionButton";
import { FONTS } from "../../hooks/useFonts";
import { useTheme } from "../../lib/theme-context";
import type { FeedPost } from "./types";

const CARD_BORDER_RADIUS = 16;
const IMAGE_HEIGHT = 220;
const BEFORE_LABEL_HEIGHT = 22;
const LONG_PRESS_DELAY_MS = 500;

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
 * Feed post card showing before/after images side-by-side,
 * caption, reaction button, comment count.
 * Long-press triggers share/report context menu.
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
  const fadeAnim = useRef(new Animated.Value(0)).current;
  const translateAnim = useRef(new Animated.Value(20)).current;

  // Stagger entrance animation (respects reduced motion)
  useEffect(() => {
    let cancelled = false;
    AccessibilityInfo.isReduceMotionEnabled().then((reduceMotion) => {
      if (cancelled) return;
      if (reduceMotion) {
        fadeAnim.setValue(1);
        translateAnim.setValue(0);
        return;
      }
      const delay = Math.min(index, FEED_CONFIG.MAX_STAGGER_ITEMS) * FEED_CONFIG.STAGGER_DELAY_MS;
      const animation = Animated.parallel([
        Animated.timing(fadeAnim, {
          toValue: 1,
          duration: 300,
          delay,
          useNativeDriver: true,
        }),
        Animated.timing(translateAnim, {
          toValue: 0,
          duration: 300,
          delay,
          useNativeDriver: true,
        }),
      ]);
      animation.start();
    });
    return () => { cancelled = true; };
  }, [fadeAnim, translateAnim, index]);

  const handleReact = useCallback(() => {
    onReact(post.post_id);
  }, [onReact, post.post_id]);

  const handleComment = useCallback(() => {
    onCommentPress(post.post_id);
  }, [onCommentPress, post.post_id]);

  const handlePostPress = useCallback(() => {
    router.push({
      pathname: "/post/[postId]",
      params: {
        postId: post.post_id,
        beforeImage: post.before_image_url,
        afterImage: post.after_image_url,
        caption: post.caption ?? "",
        displayName: post.display_name ?? "",
        reactionCount: String(post.reaction_count),
        commentCount: String(post.comment_count),
        timeAgo: formatTimeAgo(post.created_at),
        hasReacted: String(hasReacted),
      },
    });
  }, [router, post]);

  const handleLongPress = useCallback(() => {
    const shareUrl = `${UNIVERSAL_LINK_ORIGIN}/posts/${post.post_id}`;
    const blockLabel = post.display_name
      ? `Block ${post.display_name}`
      : "Block User";

    if (Platform.OS === "ios") {
      ActionSheetIOS.showActionSheetWithOptions(
        {
          options: ["Share", blockLabel, "Report", "Cancel"],
          cancelButtonIndex: 3,
          destructiveButtonIndex: 2,
        },
        (buttonIndex) => {
          if (buttonIndex === 0) {
            Share.share({ url: shareUrl });
          } else if (buttonIndex === 1) {
            onBlock(post.user_id, post.display_name ?? "this user");
          } else if (buttonIndex === 2) {
            onReport(post.post_id);
          }
        },
      );
    } else {
      // Android: use Alert as ActionSheet alternative
      Alert.alert("Options", undefined, [
        {
          text: "Share",
          onPress: () => Share.share({ message: shareUrl }),
        },
        {
          text: blockLabel,
          onPress: () => onBlock(post.user_id, post.display_name ?? "this user"),
        },
        {
          text: "Report",
          style: "destructive",
          onPress: () => onReport(post.post_id),
        },
        { text: "Cancel", style: "cancel" },
      ]);
    }
  }, [post.post_id, post.user_id, post.display_name, onReport, onBlock]);

  const timeAgo = formatTimeAgo(post.created_at);

  return (
    <Animated.View
      style={[
        styles.card,
        {
          opacity: fadeAnim,
          transform: [{ translateY: translateAnim }],
        },
      ]}
    >
      <View
        accessibilityLabel={`Post${post.caption ? `: ${post.caption}` : ""}, ${post.reaction_count} reactions, ${post.comment_count} comments, ${timeAgo}`}
      >
        {/* Before / After images side by side */}
        <Pressable
          onPress={handlePostPress}
          onLongPress={handleLongPress}
          delayLongPress={LONG_PRESS_DELAY_MS}
          accessibilityHint="Tap to view post. Long press for share, block, and report options"
        >
        <View style={styles.imageRow}>
          {/* Glow-up icon — top-left of the card */}
          <View style={[styles.featureIcon, { backgroundColor: theme.accent + "33" }]}>
            <Ionicons name="sparkles" size={12} color={theme.accent} />
          </View>

          <View style={styles.imageContainer}>
            <Image
              source={{ uri: post.before_image_url }}
              style={styles.image}
              resizeMode="cover"
              accessibilityLabel={`Before photo by ${post.display_name ?? "user"}`}
            />
            <View style={styles.imageLabel}>
              <Text style={styles.imageLabelText}>Before</Text>
            </View>
          </View>
          <View style={styles.imageDivider} />
          <View style={styles.imageContainer}>
            <Image
              source={{ uri: post.after_image_url }}
              style={styles.image}
              resizeMode="cover"
              accessibilityLabel={`After photo by ${post.display_name ?? "user"}`}
            />
            <View style={styles.afterLabelAnchor}>
              <View style={[styles.afterLabelInner, { backgroundColor: theme.accent + "CC" }]}>
                <Text style={[styles.imageLabelText, styles.afterLabelText]}>
                  After
                </Text>
              </View>
            </View>
          </View>
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

          <Pressable
            onPress={handleComment}
            style={styles.commentBadge}
            accessibilityLabel={`${post.comment_count} comments, tap to view`}
            accessibilityRole="button"
          >
            <Ionicons
              name="chatbubble-outline"
              size={18}
              color={TEXT_SECONDARY}
            />
            <Text style={styles.commentCount}>{post.comment_count}</Text>
          </Pressable>

          <Text style={styles.timestamp}>{timeAgo}</Text>
        </View>
      </View>
    </Animated.View>
  );
});

const styles = StyleSheet.create({
  card: {
    backgroundColor: THEME.colors.surface,
    borderRadius: THEME.radius.lg,
    marginHorizontal: THEME.spacing.xl,
    marginBottom: THEME.spacing.xl,
    overflow: "hidden",
    borderWidth: 1,
    borderColor: THEME.colors.border,
    shadowColor: "rgba(0, 0, 0, 0.4)",
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 1,
    shadowRadius: 12,
    elevation: 6,
  },
  imageRow: {
    flexDirection: "row",
    height: IMAGE_HEIGHT,
  },
  featureIcon: {
    position: "absolute",
    top: 8,
    left: 8,
    width: 24,
    height: 24,
    borderRadius: 12,
    alignItems: "center",
    justifyContent: "center",
    zIndex: 2,
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
    backgroundColor: FEED_DIVIDER,
  },
  imageLabel: {
    position: "absolute",
    bottom: 8,
    left: 8,
    right: undefined,
    height: BEFORE_LABEL_HEIGHT,
    paddingHorizontal: 8,
    borderRadius: 4,
    backgroundColor: BEFORE_OVERLAY,
    justifyContent: "center",
    flexShrink: 1,
  },
  afterLabelAnchor: {
    position: "absolute",
    bottom: 8,
    left: 8,
    flexDirection: "row",
  },
  afterLabelInner: {
    height: BEFORE_LABEL_HEIGHT,
    paddingHorizontal: 8,
    borderRadius: 4,
    justifyContent: "center",
  },
  imageLabelText: {
    fontFamily: FONTS.bodyMedium,
    fontSize: 11,
    fontWeight: "700",
    color: "#F8F8F8",
    textTransform: "uppercase",
    letterSpacing: 0.5,
  },
  afterLabelText: {
    color: "#FFFFFF",
  },
  caption: {
    fontFamily: FONTS.body,
    fontSize: 15,
    lineHeight: 22,
    color: TEXT_PRIMARY,
    paddingHorizontal: 16,
    paddingTop: 12,
  },
  actionsRow: {
    flexDirection: "row",
    alignItems: "center",
    paddingHorizontal: 16,
    paddingVertical: 10,
    gap: 12,
  },
  commentBadge: {
    flexDirection: "row",
    alignItems: "center",
    gap: 5,
    minHeight: 44,
    paddingHorizontal: 4,
    paddingVertical: 6,
  },
  commentCount: {
    fontFamily: FONTS.bodyMedium,
    fontSize: 14,
    fontWeight: "600",
    color: TEXT_SECONDARY,
  },
  timestamp: {
    fontFamily: FONTS.body,
    fontSize: 13,
    color: TEXT_SECONDARY,
    marginLeft: "auto",
  },
});
