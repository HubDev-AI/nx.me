import { memo } from "react";
import { View, Text, Image, StyleSheet } from "react-native";
import { Ionicons } from "@expo/vector-icons";

import {
  BG_ELEVATED,
  TEXT_PRIMARY,
  TEXT_SECONDARY,
  TEXT_DISABLED,
} from "../../constants/colors";
import { COMMENTS_CONFIG } from "../../constants/config";
import { FONTS } from "../../hooks/useFonts";
import { formatTimeAgo } from "../../lib/format";
import type { Comment } from "./types";

const AVATAR_SIZE = 32;
const AVATAR_BORDER_RADIUS = 16;

interface CommentItemProps {
  comment: Comment;
}

/**
 * Individual comment row: avatar, display name, timestamp, text.
 * Deleted comments show "Comment removed" placeholder.
 */
function CommentItemInner({ comment }: CommentItemProps) {
  if (comment.is_deleted) {
    return (
      <View style={styles.container}>
        <View style={styles.avatarPlaceholder}>
          <Ionicons name="person-outline" size={16} color={TEXT_DISABLED} />
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
    );
  }

  const timeAgo = formatTimeAgo(comment.created_at);
  const displayName = comment.display_name ?? "User";

  return (
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
          <Ionicons name="person" size={16} color={TEXT_DISABLED} />
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
  );
}

export const CommentItem = memo(CommentItemInner);

const styles = StyleSheet.create({
  container: {
    flexDirection: "row",
    paddingHorizontal: 16,
    paddingVertical: 10,
    gap: 10,
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
    backgroundColor: BG_ELEVATED,
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
    gap: 8,
  },
  displayName: {
    fontSize: 13,
    fontWeight: "700",
    fontFamily: FONTS.bodyBold,
    color: TEXT_PRIMARY,
    flexShrink: 1,
  },
  timestamp: {
    fontSize: 12,
    color: TEXT_SECONDARY,
    fontFamily: FONTS.body,
  },
  commentText: {
    fontSize: 14,
    lineHeight: 20,
    color: TEXT_PRIMARY,
    fontFamily: FONTS.body,
  },
  deletedText: {
    fontSize: 14,
    fontStyle: "italic",
    color: TEXT_DISABLED,
    fontFamily: FONTS.body,
    paddingVertical: 2,
  },
});
