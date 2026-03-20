import { useState, useCallback } from "react";
import {
  View,
  TextInput,
  Pressable,
  Text,
  ActivityIndicator,
  StyleSheet,
  Platform,
} from "react-native";
import { Ionicons } from "@expo/vector-icons";

import {
  BG_ELEVATED,
  INPUT_FILL,
  TEXT_PRIMARY,
  TEXT_SECONDARY,
  TEXT_DISABLED,
  CTA_PRIMARY,
  FEED_DIVIDER,
} from "../../constants/colors";
import { COMMENTS_CONFIG, MIN_TOUCH_TARGET } from "../../constants/config";
import { FONTS } from "../../hooks/useFonts";

interface CommentInputProps {
  isAuthenticated: boolean;
  isPosting: boolean;
  onSubmit: (content: string) => void;
  onAuthPrompt: () => void;
}

/**
 * Comment text input with send button.
 * Guest users tapping the input get an auth prompt instead.
 */
export function CommentInput({
  isAuthenticated,
  isPosting,
  onSubmit,
  onAuthPrompt,
}: CommentInputProps) {
  const [text, setText] = useState("");

  const trimmedText = text.trim();
  const canSend = trimmedText.length > 0 && !isPosting;

  const handleSend = useCallback(() => {
    if (!canSend) return;
    onSubmit(trimmedText);
    setText("");
  }, [canSend, trimmedText, onSubmit]);

  const handleFocus = useCallback(() => {
    if (!isAuthenticated) {
      onAuthPrompt();
    }
  }, [isAuthenticated, onAuthPrompt]);

  return (
    <View style={styles.container}>
      <View style={styles.divider} />
      <View style={styles.inputRow}>
        {isAuthenticated ? (
          <>
            <TextInput
              style={styles.textInput}
              value={text}
              onChangeText={setText}
              placeholder="Add a comment..."
              placeholderTextColor={TEXT_DISABLED}
              maxLength={COMMENTS_CONFIG.MAX_COMMENT_LENGTH}
              multiline
              returnKeyType="send"
              onSubmitEditing={handleSend}
              blurOnSubmit
              editable={!isPosting}
              accessibilityLabel="Comment input"
              accessibilityHint="Type your comment here"
            />
            <Pressable
              onPress={handleSend}
              disabled={!canSend}
              style={[
                styles.sendButton,
                canSend ? styles.sendButtonActive : styles.sendButtonDisabled,
              ]}
              accessibilityLabel="Send comment"
              accessibilityRole="button"
              accessibilityState={{ disabled: !canSend }}
            >
              {isPosting ? (
                <ActivityIndicator size="small" color={CTA_PRIMARY} />
              ) : (
                <Ionicons
                  name="send"
                  size={18}
                  color={canSend ? CTA_PRIMARY : TEXT_DISABLED}
                />
              )}
            </Pressable>
          </>
        ) : (
          <Pressable
            style={styles.guestInput}
            onPress={handleFocus}
            accessibilityLabel="Sign in to comment"
            accessibilityRole="button"
            accessibilityHint="Opens sign-in flow"
          >
            <Ionicons
              name="chatbubble-outline"
              size={16}
              color={TEXT_DISABLED}
            />
            <Text style={styles.guestText}>Sign in to comment</Text>
          </Pressable>
        )}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    paddingBottom: 8,
  },
  divider: {
    height: 1,
    backgroundColor: FEED_DIVIDER,
  },
  inputRow: {
    flexDirection: "row",
    alignItems: "flex-end",
    paddingHorizontal: 12,
    paddingTop: 8,
    gap: 8,
  },
  textInput: {
    flex: 1,
    minHeight: MIN_TOUCH_TARGET,
    maxHeight: 100,
    backgroundColor: INPUT_FILL,
    borderRadius: 20,
    paddingHorizontal: 16,
    paddingVertical: 10,
    fontSize: 14,
    color: TEXT_PRIMARY,
    fontFamily: FONTS.body,
    textAlignVertical: "center",
    // @ts-ignore — web-only: remove browser default blue focus outline
    ...(Platform.OS === "web" ? { outlineStyle: "none" } : {}),
  },
  sendButton: {
    width: MIN_TOUCH_TARGET,
    height: MIN_TOUCH_TARGET,
    borderRadius: 22,
    alignItems: "center",
    justifyContent: "center",
  },
  sendButtonActive: {
    backgroundColor: BG_ELEVATED,
  },
  sendButtonDisabled: {
    backgroundColor: "transparent",
  },
  guestInput: {
    flex: 1,
    flexDirection: "row",
    alignItems: "center",
    gap: 8,
    minHeight: MIN_TOUCH_TARGET,
    backgroundColor: INPUT_FILL,
    borderRadius: 20,
    paddingHorizontal: 16,
  },
  guestText: {
    fontSize: 14,
    color: TEXT_SECONDARY,
    fontFamily: FONTS.body,
  },
});
