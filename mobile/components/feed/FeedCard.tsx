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

import {
  BG_CARD,
  BG_ELEVATED,
  TEXT_PRIMARY,
  TEXT_SECONDARY,
  FEED_DIVIDER,
  BEFORE_OVERLAY,
  AFTER_OVERLAY_STRONG,
} from "../../constants/colors";
import { FEED_CONFIG, UNIVERSAL_LINK_ORIGIN } from "../../constants/config";
import { formatTimeAgo } from "../../lib/format";
import { ReactionButton } from "./ReactionButton";
import type { FeedPost } from "./types";

const CARD_BORDER_RADIUS = 12;
const IMAGE_HEIGHT = 200;
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
      <Pressable
        onLongPress={handleLongPress}
        delayLongPress={LONG_PRESS_DELAY_MS}
        accessibilityLabel={`Post${post.caption ? `: ${post.caption}` : ""}, ${post.reaction_count} reactions, ${post.comment_count} comments, ${timeAgo}`}
        accessibilityRole="button"
        accessibilityHint="Long press for share, block, and report options"
      >
        {/* Before / After images side by side */}
        <View style={styles.imageRow}>
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
            <View style={[styles.imageLabel, styles.afterLabel]}>
              <Text style={[styles.imageLabelText, styles.afterLabelText]}>
                After
              </Text>
            </View>
          </View>
        </View>

        {/* Caption */}
        {post.caption ? (
          <Text style={styles.caption} numberOfLines={3}>
            {post.caption}
          </Text>
        ) : null}

        {/* Actions row */}
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
      </Pressable>
    </Animated.View>
  );
});

const styles = StyleSheet.create({
  card: {
    backgroundColor: BG_CARD,
    borderRadius: CARD_BORDER_RADIUS,
    marginHorizontal: 16,
    marginBottom: 16,
    overflow: "hidden",
  },
  imageRow: {
    flexDirection: "row",
    height: IMAGE_HEIGHT,
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
    height: BEFORE_LABEL_HEIGHT,
    paddingHorizontal: 8,
    borderRadius: 4,
    backgroundColor: BEFORE_OVERLAY,
    justifyContent: "center",
  },
  afterLabel: {
    left: undefined,
    right: 8,
    backgroundColor: AFTER_OVERLAY_STRONG,
  },
  imageLabelText: {
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
    fontSize: 14,
    lineHeight: 20,
    color: TEXT_PRIMARY,
    paddingHorizontal: 12,
    paddingTop: 10,
  },
  actionsRow: {
    flexDirection: "row",
    alignItems: "center",
    paddingHorizontal: 12,
    paddingVertical: 8,
    gap: 8,
  },
  commentBadge: {
    flexDirection: "row",
    alignItems: "center",
    gap: 4,
    minHeight: 44,
    paddingHorizontal: 8,
    paddingVertical: 6,
    borderRadius: 20,
    backgroundColor: BG_ELEVATED,
  },
  commentCount: {
    fontSize: 14,
    fontWeight: "600",
    color: TEXT_SECONDARY,
  },
  timestamp: {
    fontSize: 12,
    color: TEXT_SECONDARY,
    marginLeft: "auto",
  },
});
