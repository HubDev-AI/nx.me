/**
 * NudgeCard — individual nudge card with unread badge and tap-to-read.
 *
 * Unread nudges show a coral dot indicator. Tapping marks as read.
 */
import { memo, useCallback } from "react";
import { Pressable, StyleSheet, View } from "react-native";
import { Ionicons } from "@expo/vector-icons";

import { THEME } from "../../constants/theme";
import { useTheme } from "../../lib/theme-context";
import { Body, Caption } from "../ui/Text";
import { MIN_TOUCH_TARGET } from "../../constants/config";
import { formatTimeAgo } from "../../lib/format";
import type { Nudge } from "../../lib/advisor";

interface NudgeCardProps {
  nudge: Nudge;
  /**
   * Called on every tap. The parent owns side-effects: marking the
   * nudge as read, opening a detail modal, navigating, etc. Kept as
   * a single callback so the card stays presentational — it never
   * decides whether a tap is meaningful or not.
   */
  onPress: (nudge: Nudge) => void;
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

function NudgeCardInner({ nudge, onPress }: NudgeCardProps) {
  const { theme } = useTheme();
  const isRead = nudge.read_at !== null;
  const handlePress = useCallback(() => onPress(nudge), [nudge, onPress]);

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
      accessibilityHint="Tap to open the full nudge"
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
          <Body
            weight={isRead ? "semibold" : "bold"}
            color="primary"
            numberOfLines={1}
            style={styles.title}
          >
            {nudgeLabel(nudge.trigger)}
          </Body>
          {!isRead && <View style={[styles.unreadDot, { backgroundColor: theme.accent }]} />}
        </View>
        <Caption color="secondary" numberOfLines={3} style={styles.body}>
          {nudge.content}
        </Caption>
        <Caption color="muted" style={styles.time}>
          {formatTimeAgo(nudge.created_at)}
        </Caption>
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
    borderCurve: "continuous",
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
    textTransform: "capitalize",
    flex: 1,
  },
  unreadDot: {
    width: 8,
    height: 8,
    borderRadius: 4,
  },
  body: {
    lineHeight: 20,
  },
  time: {
    marginTop: THEME.spacing.xs / 2,
  },
});
