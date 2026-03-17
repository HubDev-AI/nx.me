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

/** Format ISO date to relative time string */
function formatTimeAgo(isoDate: string): string {
  const now = Date.now();
  const then = new Date(isoDate).getTime();
  const diffSeconds = Math.floor((now - then) / 1000);

  if (diffSeconds < 60) return "just now";
  const diffMinutes = Math.floor(diffSeconds / 60);
  if (diffMinutes < 60) return `${diffMinutes}m`;
  const diffHours = Math.floor(diffMinutes / 60);
  if (diffHours < 24) return `${diffHours}h`;
  const diffDays = Math.floor(diffHours / 24);
  if (diffDays < 7) return `${diffDays}d`;
  const diffWeeks = Math.floor(diffDays / 7);
  if (diffWeeks < 4) return `${diffWeeks}w`;
  const diffMonths = Math.floor(diffDays / 30);
  return `${diffMonths}mo`;
}

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
    color: TEXT_PRIMARY,
    flexShrink: 1,
  },
  timestamp: {
    fontSize: 12,
    color: TEXT_SECONDARY,
  },
  commentText: {
    fontSize: 14,
    lineHeight: 20,
    color: TEXT_PRIMARY,
  },
  deletedText: {
    fontSize: 14,
    fontStyle: "italic",
    color: TEXT_DISABLED,
    paddingVertical: 2,
  },
});
