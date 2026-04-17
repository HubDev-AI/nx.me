/**
 * MessageBubble — renders a single chat message with Ada vs user styling.
 *
 * Ada messages: accent-tinted bubble, left-aligned.
 * User messages: dark glass overlay (matches app-wide glass surfaces), right-aligned.
 */
import { memo, useCallback, useEffect, useRef, useState } from "react";
import { View, Text, StyleSheet, Pressable } from "react-native";
import * as Clipboard from "expo-clipboard";

import { THEME } from "../../constants/theme";
import { useTheme } from "../../lib/theme-context";
import { FONTS } from "../../hooks/useFonts";
import { hapticMedium } from "../../lib/haptics";
import type { AdvisorMessage } from "../../lib/advisor";

interface MessageBubbleProps {
  message: AdvisorMessage;
}

const COPIED_RESET_MS = 1500;

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
  const [copied, setCopied] = useState(false);
  const resetTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    return () => {
      if (resetTimeoutRef.current) {
        clearTimeout(resetTimeoutRef.current);
      }
    };
  }, []);

  const handleLongPress = useCallback(async () => {
    await Clipboard.setStringAsync(message.content);
    hapticMedium();
    setCopied(true);
    if (resetTimeoutRef.current) {
      clearTimeout(resetTimeoutRef.current);
    }
    resetTimeoutRef.current = setTimeout(() => {
      setCopied(false);
      resetTimeoutRef.current = null;
    }, COPIED_RESET_MS);
  }, [message.content]);

  return (
    <View style={[styles.row, isAda ? styles.rowLeft : styles.rowRight]}>
      <Pressable
        onLongPress={handleLongPress}
        delayLongPress={350}
        accessibilityRole="button"
        accessibilityLabel={
          isAda
            ? `Ada said: ${message.content}. Long press to copy.`
            : `You said: ${message.content}. Long press to copy.`
        }
        accessibilityHint="Long press to copy message"
        style={({ pressed }) => [
          styles.bubble,
          isAda
            ? [styles.adaBubble, { backgroundColor: theme.accentMuted }]
            : styles.userBubble,
          pressed && styles.bubblePressed,
        ]}
      >
        {isAda && <Text style={[styles.senderLabel, { color: theme.accent }]}>Ada</Text>}
        <Text style={styles.content}>{message.content}</Text>
        <Text style={[styles.timestamp, copied && { color: theme.accent }]}>
          {copied ? "Copied" : formatTime(message.created_at)}
        </Text>
      </Pressable>
    </View>
  );
}

export const MessageBubble = memo(MessageBubbleInner);

const styles = StyleSheet.create({
  row: {
    flexDirection: "row",
    paddingHorizontal: THEME.spacing.lg,
    paddingVertical: THEME.spacing.xs,
    width: "100%",
  },
  rowLeft: {
    justifyContent: "flex-start",
  },
  rowRight: {
    justifyContent: "flex-end",
  },
  bubble: {
    maxWidth: "80%",
    borderRadius: THEME.radius.lg,
    paddingHorizontal: THEME.spacing.lg - 2,
    paddingVertical: THEME.spacing.md - 2,
  },
  adaBubble: {
    borderTopLeftRadius: THEME.radius.sm / 2,
  },
  userBubble: {
    backgroundColor: THEME.colors.glass,
    borderWidth: 1,
    borderColor: THEME.colors.glassBorder,
    borderTopRightRadius: THEME.radius.sm / 2,
  },
  bubblePressed: {
    opacity: 0.7,
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
