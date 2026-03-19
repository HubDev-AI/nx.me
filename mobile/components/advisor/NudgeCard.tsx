/**
 * NudgeCard — individual nudge card with unread badge and tap-to-read.
 *
 * Unread nudges show a coral dot indicator. Tapping marks as read.
 */
import { memo, useCallback } from "react";
import { View, Text, Pressable, StyleSheet } from "react-native";
import { Ionicons } from "@expo/vector-icons";

import {
  BG_CARD,
  BG_ELEVATED,
  TEXT_PRIMARY,
  TEXT_SECONDARY,
  NUDGE_UNREAD_DOT,
  ADA_BUBBLE_BORDER,
} from "../../constants/colors";
import { MIN_TOUCH_TARGET } from "../../constants/config";
import { formatTimeAgo } from "../../lib/format";
import type { Nudge } from "../../lib/advisor";

interface NudgeCardProps {
  nudge: Nudge;
  onMarkRead: (id: string) => void;
}

function nudgeIcon(type: string): React.ComponentProps<typeof Ionicons>["name"] {
  switch (type) {
    case "tip":
      return "sparkles-outline";
    case "check_in":
      return "chatbubble-outline";
    case "reminder":
      return "alarm-outline";
    default:
      return "bulb-outline";
  }
}

function NudgeCardInner({ nudge, onMarkRead }: NudgeCardProps) {
  const handlePress = useCallback(() => {
    if (!nudge.is_read) {
      onMarkRead(nudge.id);
    }
  }, [nudge.id, nudge.is_read, onMarkRead]);

  return (
    <Pressable
      onPress={handlePress}
      style={({ pressed }) => [
        styles.card,
        !nudge.is_read && styles.unreadCard,
        pressed && styles.pressed,
      ]}
      accessibilityLabel={`${nudge.is_read ? "" : "Unread "}nudge: ${nudge.title}`}
      accessibilityRole="button"
      accessibilityHint={nudge.is_read ? undefined : "Tap to mark as read"}
    >
      {/* Icon */}
      <View style={styles.iconContainer}>
        <Ionicons
          name={nudgeIcon(nudge.type)}
          size={22}
          color={nudge.is_read ? TEXT_SECONDARY : ADA_BUBBLE_BORDER}
        />
      </View>

      {/* Content */}
      <View style={styles.content}>
        <View style={styles.titleRow}>
          <Text
            style={[styles.title, !nudge.is_read && styles.unreadTitle]}
            numberOfLines={1}
          >
            {nudge.title}
          </Text>
          {!nudge.is_read && <View style={styles.unreadDot} />}
        </View>
        <Text style={styles.body} numberOfLines={3}>
          {nudge.content}
        </Text>
        <Text style={styles.time}>{formatTimeAgo(nudge.created_at)}</Text>
      </View>
    </Pressable>
  );
}

export const NudgeCard = memo(NudgeCardInner);

const styles = StyleSheet.create({
  card: {
    flexDirection: "row",
    backgroundColor: BG_CARD,
    borderRadius: 14,
    padding: 14,
    gap: 12,
    minHeight: MIN_TOUCH_TARGET,
  },
  unreadCard: {
    backgroundColor: BG_ELEVATED,
  },
  pressed: {
    opacity: 0.8,
  },
  iconContainer: {
    width: 36,
    height: 36,
    borderRadius: 18,
    backgroundColor: "rgba(244,63,94,0.08)",
    alignItems: "center",
    justifyContent: "center",
    marginTop: 2,
  },
  content: {
    flex: 1,
    gap: 4,
  },
  titleRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: 8,
  },
  title: {
    fontSize: 15,
    fontWeight: "600",
    color: TEXT_PRIMARY,
    flex: 1,
  },
  unreadTitle: {
    fontWeight: "700",
  },
  unreadDot: {
    width: 8,
    height: 8,
    borderRadius: 4,
    backgroundColor: NUDGE_UNREAD_DOT,
  },
  body: {
    fontSize: 14,
    lineHeight: 20,
    color: TEXT_SECONDARY,
  },
  time: {
    fontSize: 12,
    color: TEXT_SECONDARY,
    marginTop: 2,
  },
});
