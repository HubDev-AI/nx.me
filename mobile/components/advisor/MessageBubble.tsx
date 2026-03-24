/**
 * MessageBubble — renders a single chat message with Ada vs user styling.
 *
 * Ada messages: elevated card with subtle left border accent (#161616 bg, coral left border).
 * User messages: coral-tinted background (rgba(244,63,94,0.08)), right-aligned.
 */
import { memo } from "react";
import { View, Text, StyleSheet } from "react-native";

import { THEME } from "../../constants/theme";
import { useTheme } from "../../lib/theme-context";
import { FONTS } from "../../hooks/useFonts";
import type { AdvisorMessage } from "../../lib/advisor";

interface MessageBubbleProps {
  message: AdvisorMessage;
}

function formatTime(isoDate: string): string {
  const date = new Date(isoDate);
  return date.toLocaleTimeString(undefined, {
    hour: "numeric",
    minute: "2-digit",
  });
}

function MessageBubbleInner({ message }: MessageBubbleProps) {
  const { theme } = useTheme();
  const isAda = message.role === "assistant";

  return (
    <View
      style={[styles.row, isAda ? styles.rowLeft : styles.rowRight]}
      accessibilityLabel={
        isAda
          ? `Ada said: ${message.content}`
          : `You said: ${message.content}`
      }
    >
      <View style={[
        styles.bubble,
        isAda
          ? styles.adaBubble
          : [styles.userBubble, { backgroundColor: theme.accentMuted }],
      ]}>
        {isAda && <Text style={[styles.senderLabel, { color: theme.accent }]}>Ada</Text>}
        <Text style={styles.content}>{message.content}</Text>
        <Text style={styles.timestamp}>{formatTime(message.created_at)}</Text>
      </View>
    </View>
  );
}

export const MessageBubble = memo(MessageBubbleInner);

const styles = StyleSheet.create({
  row: {
    paddingHorizontal: THEME.spacing.lg,
    paddingVertical: THEME.spacing.xs,
    maxWidth: "100%",
  },
  rowLeft: {
    alignSelf: "flex-start",
  },
  rowRight: {
    alignSelf: "flex-end",
  },
  bubble: {
    maxWidth: "80%",
    borderRadius: THEME.radius.lg,
    paddingHorizontal: THEME.spacing.lg - 2,
    paddingVertical: THEME.spacing.md - 2,
  },
  adaBubble: {
    backgroundColor: THEME.colors.glass,
    borderWidth: 1,
    borderColor: THEME.colors.glassBorder,
  },
  userBubble: {
    borderTopRightRadius: THEME.radius.sm / 2,
  },
  senderLabel: {
    fontFamily: FONTS.bodySemiBold,
    fontSize: 13,
    marginBottom: THEME.spacing.xs / 2,
  },
  content: {
    fontFamily: FONTS.body,
    ...THEME.typography.body,
    color: THEME.colors.textPrimary,
  },
  timestamp: {
    fontFamily: FONTS.body,
    fontSize: 11,
    color: THEME.colors.textMuted,
    marginTop: THEME.spacing.xs,
    alignSelf: "flex-end",
  },
});
