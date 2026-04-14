/**
 * Subscription screen support views — error state + empty-options hint.
 *
 * Kept together because both render small status-icon + body-text cards
 * and don't merit their own files. Used exclusively by `subscription.tsx`.
 */
import { Pressable, StyleSheet, Text, View } from "react-native";
import { Ionicons } from "@expo/vector-icons";

import { THEME } from "../../constants/theme";
import { MIN_TOUCH_TARGET } from "../../constants/config";
import { Body } from "../ui/Text";
import { useTheme } from "../../lib/theme-context";
import { FONTS } from "../../hooks/useFonts";

const ERROR_ICON_SIZE = 48;
const HINT_ICON_SIZE = 24;
const RETRY_BUTTON_FONT_SIZE = 15;

interface SubscriptionErrorStateProps {
  message: string;
  onRetry: () => void;
}

export function SubscriptionErrorState({
  message,
  onRetry,
}: SubscriptionErrorStateProps) {
  const { theme } = useTheme();
  return (
    <View style={styles.centered}>
      <Ionicons
        name="alert-circle-outline"
        size={ERROR_ICON_SIZE}
        color={THEME.colors.destructive}
      />
      <Body color="secondary" style={styles.errorText}>
        {message}
      </Body>
      <Pressable
        onPress={onRetry}
        style={[styles.retryButton, { backgroundColor: theme.accent }]}
        accessibilityLabel="Retry"
        accessibilityRole="button"
      >
        <Text style={styles.retryButtonText}>Retry</Text>
      </Pressable>
    </View>
  );
}

interface SubscriptionEmptyHintProps {
  message: string;
}

export function SubscriptionEmptyHint({ message }: SubscriptionEmptyHintProps) {
  return (
    <View style={styles.hintCard}>
      <Ionicons
        name="information-circle-outline"
        size={HINT_ICON_SIZE}
        color={THEME.colors.textSecondary}
      />
      <Body color="secondary" style={styles.hintText}>
        {message}
      </Body>
    </View>
  );
}

const styles = StyleSheet.create({
  centered: {
    flex: 1,
    alignItems: "center",
    justifyContent: "center",
    padding: THEME.spacing.xxl,
    gap: THEME.spacing.md,
  },
  errorText: {
    textAlign: "center",
  },
  retryButton: {
    borderRadius: THEME.radius.pill,
    paddingHorizontal: THEME.spacing.xxl,
    paddingVertical: THEME.spacing.md,
    minHeight: MIN_TOUCH_TARGET,
    alignItems: "center",
    justifyContent: "center",
    marginTop: THEME.spacing.sm,
  },
  retryButtonText: {
    fontFamily: FONTS.bodyMedium,
    fontSize: RETRY_BUTTON_FONT_SIZE,
    color: THEME.colors.bg,
  },
  hintCard: {
    flexDirection: "row",
    alignItems: "flex-start",
    gap: THEME.spacing.md,
    backgroundColor: THEME.colors.glass,
    borderRadius: THEME.radius.lg,
    borderWidth: 1,
    borderColor: THEME.colors.glassBorder,
    padding: THEME.spacing.xl,
    marginTop: THEME.spacing.xxl,
  },
  hintText: {
    flex: 1,
    lineHeight: 22,
  },
});
