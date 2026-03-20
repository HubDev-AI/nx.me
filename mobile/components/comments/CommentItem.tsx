import { memo } from "react";
import { View, Text, Image, StyleSheet } from "react-native";
import Animated, { FadeInDown } from "react-native-reanimated";
import { Ionicons } from "@expo/vector-icons";

import { THEME } from "../../constants/theme";
import { COMMENTS_CONFIG } from "../../constants/config";
import { FONTS } from "../../hooks/useFonts";
import { formatTimeAgo } from "../../lib/format";
import type { Comment } from "./types";

const AVATAR_SIZE = 32;
const AVATAR_BORDER_RADIUS = 16;
const MAX_STAGGER_ITEMS = 8;

interface CommentItemProps {
  comment: Comment;
  index?: number;
}

/**
 * Individual comment row: avatar, display name, timestamp, text.
 * Deleted comments show "Comment removed" placeholder.
 */
function CommentItemInner({ comment, index = 0 }: CommentItemProps) {
  const staggerDelay = Math.min(index, MAX_STAGGER_ITEMS) * 50;

  if (comment.is_deleted) {
    return (
      <Animated.View
        entering={FadeInDown.duration(THEME.animation.duration.normal).delay(staggerDelay)}
      >
        <View style={styles.container}>
          <View style={styles.avatarPlaceholder}>
            <Ionicons name="person-outline" size={16} color={THEME.colors.textDisabled} />
          </View>
          <View style={styles.content}>
            <Text
              style={styles.deletedText}
              accessibilityLabel={COMMENTS_CONFIG.DELETED_PLACEHOLDER}
            >
              {COMMENTS_CONFIG.DELETED_PLACEHOLDER}
            </Text>
          </View>
        </View>
      </Animated.View>
    );
  }

  const timeAgo = formatTimeAgo(comment.created_at);
  const displayName = comment.display_name ?? "User";

  return (
    <Animated.View
      entering={FadeInDown.duration(THEME.animation.duration.normal).delay(staggerDelay)}
    >
      <View
        style={styles.container}
        accessibilityLabel={`${displayName} said ${comment.content}, ${timeAgo}`}
      >
        {/* Avatar */}
        {comment.avatar_url ? (
          <Image
            source={{ uri: comment.avatar_url }}
            style={styles.avatar}
            accessibilityLabel={`${displayName} avatar`}
          />
        ) : (
          <View style={styles.avatarPlaceholder}>
            <Ionicons name="person" size={16} color={THEME.colors.textDisabled} />
          </View>
        )}

        {/* Name, timestamp, text */}
        <View style={styles.content}>
          <View style={styles.headerRow}>
            <Text style={styles.displayName} numberOfLines={1}>
              {displayName}
            </Text>
            <Text style={styles.timestamp}>{timeAgo}</Text>
          </View>
          <Text style={styles.commentText}>{comment.content}</Text>
        </View>
      </View>
    </Animated.View>
  );
}

export const CommentItem = memo(CommentItemInner);

const styles = StyleSheet.create({
  container: {
    flexDirection: "row",
    paddingHorizontal: THEME.spacing.lg,
    paddingVertical: THEME.spacing.md,
    gap: THEME.spacing.md,
  },
  avatar: {
    width: AVATAR_SIZE,
    height: AVATAR_SIZE,
    borderRadius: AVATAR_BORDER_RADIUS,
  },
  avatarPlaceholder: {
    width: AVATAR_SIZE,
    height: AVATAR_SIZE,
    borderRadius: AVATAR_BORDER_RADIUS,
    backgroundColor: THEME.colors.surfaceElevated,
    alignItems: "center",
    justifyContent: "center",
  },
  content: {
    flex: 1,
    gap: 2,
  },
  headerRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: THEME.spacing.sm,
  },
  displayName: {
    fontSize: 13,
    fontFamily: FONTS.bodySemiBold,
    color: THEME.colors.textPrimary,
    flexShrink: 1,
  },
  timestamp: {
    fontSize: 12,
    color: THEME.colors.textMuted,
    fontFamily: FONTS.body,
  },
  commentText: {
    fontSize: 14,
    lineHeight: 20,
    color: THEME.colors.textPrimary,
    fontFamily: FONTS.body,
  },
  deletedText: {
    fontSize: 14,
    fontStyle: "italic",
    color: THEME.colors.textDisabled,
    fontFamily: FONTS.body,
    paddingVertical: 2,
  },
});
