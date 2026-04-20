import { useCallback, useState } from "react";
import {
  ActivityIndicator,
  Platform,
  Pressable,
  StyleSheet,
  TextInput,
  View,
} from "react-native";
import Animated, {
  useAnimatedStyle,
  useSharedValue,
  withSpring,
} from "react-native-reanimated";
import { Ionicons } from "@expo/vector-icons";

import { THEME } from "../../constants/theme";
import { useTheme } from "../../lib/theme-context";
import { COMMENTS_CONFIG, MIN_TOUCH_TARGET } from "../../constants/config";
import { FONTS } from "../../hooks/useFonts";
import { Caption } from "../ui/Text";

interface CommentInputProps {
  isAuthenticated: boolean;
  isPosting: boolean;
  onSubmit: (content: string) => void;
  onAuthPrompt: () => void;
}

/**
 * Comment text input with send button. Unauthenticated users tapping the
 * input get an auth prompt instead.
 */
export function CommentInput({
  isAuthenticated,
  isPosting,
  onSubmit,
  onAuthPrompt,
}: CommentInputProps) {
  const { theme } = useTheme();
  const [text, setText] = useState("");

  // Press scale animations
  const sendScale = useSharedValue(1);
  const promptScale = useSharedValue(1);
  const sendPressStyle = useAnimatedStyle(() => ({
    transform: [{ scale: sendScale.value }],
  }));
  const promptPressStyle = useAnimatedStyle(() => ({
    transform: [{ scale: promptScale.value }],
  }));

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
              placeholderTextColor={THEME.colors.textDisabled}
              maxLength={COMMENTS_CONFIG.MAX_COMMENT_LENGTH}
              multiline
              returnKeyType="send"
              onSubmitEditing={handleSend}
              blurOnSubmit
              editable={!isPosting}
              accessibilityLabel="Comment input"
              accessibilityHint="Type your comment here"
            />
            {text.length > 0 && (
              <Caption color="muted">
                {text.length}/{COMMENTS_CONFIG.MAX_COMMENT_LENGTH}
              </Caption>
            )}
            <Animated.View style={sendPressStyle}>
              <Pressable
                onPress={handleSend}
                onPressIn={() => {
                  if (canSend) sendScale.value = withSpring(0.92, THEME.animation.press);
                }}
                onPressOut={() => {
                  sendScale.value = withSpring(1, THEME.animation.press);
                }}
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
                  <ActivityIndicator size="small" color={theme.accent} />
                ) : (
                  <Ionicons
                    name="send"
                    size={18}
                    color={canSend ? theme.accent : THEME.colors.textDisabled}
                  />
                )}
              </Pressable>
            </Animated.View>
          </>
        ) : (
          <Animated.View style={[{ flex: 1 }, promptPressStyle]}>
            <Pressable
              style={styles.authPromptInput}
              onPress={handleFocus}
              onPressIn={() => { promptScale.value = withSpring(0.98, THEME.animation.press); }}
              onPressOut={() => { promptScale.value = withSpring(1, THEME.animation.press); }}
              accessibilityLabel="Sign in to comment"
              accessibilityRole="button"
              accessibilityHint="Opens sign-in flow"
            >
              <Ionicons
                name="chatbubble-outline"
                size={16}
                color={THEME.colors.textDisabled}
              />
              <Caption color="secondary">Sign in to comment</Caption>
            </Pressable>
          </Animated.View>
        )}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    paddingBottom: THEME.spacing.sm,
  },
  divider: {
    height: 1,
    backgroundColor: THEME.colors.glassBorder,
  },
  inputRow: {
    flexDirection: "row",
    alignItems: "center",
    paddingHorizontal: THEME.spacing.md,
    paddingTop: THEME.spacing.sm,
    gap: THEME.spacing.sm,
  },
  textInput: {
    flex: 1,
    minHeight: 40,
    maxHeight: 100,
    backgroundColor: THEME.colors.glass,
    borderRadius: THEME.radius.pill,
    borderCurve: "continuous",
    borderWidth: 1,
    borderColor: THEME.colors.glassBorder,
    paddingHorizontal: THEME.spacing.lg,
    paddingVertical: 8,
    fontSize: 14,
    color: THEME.colors.textPrimary,
    fontFamily: FONTS.body,
    textAlignVertical: "center",
    ...(Platform.OS === "web" ? { outlineStyle: "none" as any } : {}),
  },
  sendButton: {
    width: 40,
    height: 40,
    borderRadius: THEME.radius.pill,
    alignItems: "center",
    justifyContent: "center",
  },
  sendButtonActive: {
    backgroundColor: THEME.colors.surfaceElevated,
  },
  sendButtonDisabled: {
    backgroundColor: "transparent",
  },
  authPromptInput: {
    flex: 1,
    flexDirection: "row",
    alignItems: "center",
    gap: THEME.spacing.sm,
    minHeight: MIN_TOUCH_TARGET,
    backgroundColor: THEME.colors.glass,
    borderRadius: THEME.radius.pill,
    borderCurve: "continuous",
    borderWidth: 1,
    borderColor: THEME.colors.glassBorder,
    paddingHorizontal: THEME.spacing.lg,
  },
});
