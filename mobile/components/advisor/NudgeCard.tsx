/**
 * NudgeCard — individual nudge card with unread badge and tap-to-read.
 *
 * Unread nudges show a coral dot indicator. Tapping marks as read.
 */
import { memo, useCallback } from "react";
import { View, Text, Pressable, StyleSheet } from "react-native";
import { Ionicons } from "@expo/vector-icons";

import { THEME } from "../../constants/theme";
import { useTheme } from "../../lib/theme-context";
import { FONTS } from "../../hooks/useFonts";
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
  const { theme } = useTheme();
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
      <View style={[styles.iconContainer, { backgroundColor: theme.accentMuted }]}>
        <Ionicons
          name={nudgeIcon(nudge.type)}
          size={22}
          color={nudge.is_read ? THEME.colors.textSecondary : theme.accent}
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
          {!nudge.is_read && <View style={[styles.unreadDot, { backgroundColor: theme.accent }]} />}
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
    backgroundColor: THEME.colors.glass,
    borderRadius: THEME.radius.lg - 2,
    borderWidth: 1,
    borderColor: THEME.colors.glassBorder,
    padding: THEME.spacing.lg - 2,
    gap: THEME.spacing.md,
    minHeight: MIN_TOUCH_TARGET,
  },
  unreadCard: {
    backgroundColor: THEME.colors.surfaceElevated,
    borderColor: THEME.colors.border,
  },
  pressed: {
    opacity: 0.8,
  },
  iconContainer: {
    width: 36,
    height: 36,
    borderRadius: 18,
    alignItems: "center",
    justifyContent: "center",
    marginTop: THEME.spacing.xs / 2,
  },
  content: {
    flex: 1,
    gap: THEME.spacing.xs,
  },
  titleRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: THEME.spacing.sm,
  },
  title: {
    fontFamily: FONTS.display,
    ...THEME.typography.body,
    letterSpacing: THEME.typography.heading.letterSpacing,
    color: THEME.colors.textPrimary,
    flex: 1,
  },
  unreadTitle: {
    fontFamily: FONTS.display,
  },
  unreadDot: {
    width: 8,
    height: 8,
    borderRadius: 4,
  },
  body: {
    fontFamily: FONTS.body,
    ...THEME.typography.caption,
    fontSize: 14,
    lineHeight: 20,
    color: THEME.colors.textSecondary,
  },
  time: {
    fontFamily: FONTS.body,
    fontSize: 12,
    color: THEME.colors.textMuted,
    marginTop: THEME.spacing.xs / 2,
  },
});
