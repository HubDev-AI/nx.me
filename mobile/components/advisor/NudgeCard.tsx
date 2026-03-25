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

function nudgeLabel(trigger: string): string {
  const labels: Record<string, string> = {
    check_in: "Check-in",
    tip: "Tip",
    reminder: "Reminder",
    welcome: "Welcome",
    milestone: "Milestone",
    outfit_post: "Outfit Post",
  };
  return labels[trigger] ?? trigger.replace(/_/g, " ").replace(/^\w/, (c) => c.toUpperCase());
}

function nudgeIcon(trigger: string): React.ComponentProps<typeof Ionicons>["name"] {
  switch (trigger) {
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
  const isRead = nudge.read_at !== null;
  const handlePress = useCallback(() => {
    if (!isRead) {
      onMarkRead(nudge.id);
    }
  }, [nudge.id, isRead, onMarkRead]);

  return (
    <Pressable
      onPress={handlePress}
      style={({ pressed }) => [
        styles.card,
        !isRead && styles.unreadCard,
        pressed && styles.pressed,
      ]}
      accessibilityLabel={`${isRead ? "" : "Unread "}nudge: ${nudgeLabel(nudge.trigger)}`}
      accessibilityRole="button"
      accessibilityHint={isRead ? undefined : "Tap to mark as read"}
    >
      {/* Icon */}
      <View style={[styles.iconContainer, { backgroundColor: theme.accentMuted }]}>
        <Ionicons
          name={nudgeIcon(nudge.trigger)}
          size={22}
          color={isRead ? THEME.colors.textSecondary : theme.accent}
        />
      </View>

      {/* Content */}
      <View style={styles.content}>
        <View style={styles.titleRow}>
          <Text
            style={[styles.title, !isRead && styles.unreadTitle]}
            numberOfLines={1}
          >
            {nudgeLabel(nudge.trigger)}
          </Text>
          {!isRead && <View style={[styles.unreadDot, { backgroundColor: theme.accent }]} />}
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
    borderRadius: THEME.radius.lg,
    borderWidth: 1,
    borderColor: THEME.colors.glassBorder,
    padding: THEME.spacing.lg,
    gap: THEME.spacing.md,
    minHeight: MIN_TOUCH_TARGET,
    ...THEME.shadow.glass,
  },
  unreadCard: {
    backgroundColor: THEME.colors.glassLight,
    borderColor: THEME.colors.glassBorder,
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
    fontFamily: FONTS.bodySemiBold,
    ...THEME.typography.body,
    color: THEME.colors.textPrimary,
    textTransform: "capitalize",
    flex: 1,
  },
  unreadTitle: {
    fontFamily: FONTS.bodyBold,
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
