/**
 * MessageBubble — renders a single chat message with Ada vs user styling.
 *
 * Ada messages: elevated card with subtle left border accent (#161616 bg, coral left border).
 * User messages: coral-tinted background (rgba(244,63,94,0.08)), right-aligned.
 */
import { memo } from "react";
import { View, Text, StyleSheet } from "react-native";

import {
  ADA_BUBBLE_BG,
  ADA_BUBBLE_BORDER,
  USER_BUBBLE_BG,
  TEXT_PRIMARY,
  TEXT_SECONDARY,
} from "../../constants/colors";
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
      <View style={[styles.bubble, isAda ? styles.adaBubble : styles.userBubble]}>
        {isAda && <Text style={styles.senderLabel}>Ada</Text>}
        <Text style={styles.content}>{message.content}</Text>
        <Text style={styles.timestamp}>{formatTime(message.created_at)}</Text>
      </View>
    </View>
  );
}

export const MessageBubble = memo(MessageBubbleInner);

const styles = StyleSheet.create({
  row: {
    paddingHorizontal: 16,
    paddingVertical: 4,
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
    borderRadius: 16,
    paddingHorizontal: 14,
    paddingVertical: 10,
  },
  adaBubble: {
    backgroundColor: ADA_BUBBLE_BG,
    borderLeftWidth: 3,
    borderLeftColor: ADA_BUBBLE_BORDER,
    borderTopLeftRadius: 4,
  },
  userBubble: {
    backgroundColor: USER_BUBBLE_BG,
    borderTopRightRadius: 4,
  },
  senderLabel: {
    fontSize: 12,
    fontWeight: "600",
    color: ADA_BUBBLE_BORDER,
    marginBottom: 2,
  },
  content: {
    fontSize: 15,
    lineHeight: 22,
    color: TEXT_PRIMARY,
  },
  timestamp: {
    fontSize: 11,
    color: TEXT_SECONDARY,
    marginTop: 4,
    alignSelf: "flex-end",
  },
});
