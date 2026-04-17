/**
 * EmptyState — unified empty/zero-state component for every feed, list, and
 * signed-out screen. Enforces one visual rhythm across the app:
 *
 *   icon (56, textMuted, outline) → title (Heading md, primary, centered)
 *   → optional description (Body, secondary, centered)
 *   → optional action (Button primary, session accent, pill)
 *
 * Also used for error variants by passing `icon="alert-circle-outline"` and
 * a `"Try Again"` action — the component auto-renders a refresh icon when
 * the action label looks like a retry.
 */
import { Ionicons } from "@expo/vector-icons";
import { StyleSheet, View, type StyleProp, type ViewStyle } from "react-native";

import { THEME } from "../../constants/theme";
import { useTheme } from "../../lib/theme-context";
import { Button } from "./Button";
import { Body, Heading } from "./Text";

/** Icon size used in every empty state across the app — single source of truth. */
const EMPTY_STATE_ICON_SIZE = 56;

/**
 * Vertical bias applied as bottom padding on every centered empty state so
 * the title lands above geometric center. Geometric center makes hero copy
 * read as "low" because the eye expects optical center (≈40% from top).
 * Re-export so any sibling that does its own centering (overlays, chat
 * seed states, QueryStateView) can match the lift exactly.
 */
export const EMPTY_STATE_OPTICAL_LIFT = 96;

/** Matches labels like "Try Again", "Retry", "Retry now" — triggers leading refresh icon. */
const RETRY_LABEL_PATTERN = /retry|try again/i;

export interface EmptyStateAction {
  label: string;
  onPress: () => void;
  accessibilityLabel?: string;
}

export interface EmptyStateProps {
  icon: React.ComponentProps<typeof Ionicons>["name"];
  title: string;
  description?: string;
  action?: EmptyStateAction;
  /** Render inside a flex-center container (default true). Set false if parent already centers. */
  center?: boolean;
  /** Optional extra style on the outer container. */
  style?: StyleProp<ViewStyle>;
  /** Test ID for the outer container. */
  testID?: string;
}

export function EmptyState({
  icon,
  title,
  description,
  action,
  center = true,
  style,
  testID,
}: EmptyStateProps) {
  const { theme } = useTheme();
  const isRetryAction =
    action !== undefined && RETRY_LABEL_PATTERN.test(action.label);

  return (
    <View
      style={[center ? styles.centered : styles.inline, style]}
      testID={testID}
    >
      <Ionicons
        name={icon}
        size={EMPTY_STATE_ICON_SIZE}
        color={THEME.colors.textMuted}
      />
      <Heading
        size="md"
        display={false}
        color="primary"
        style={styles.title}
      >
        {title}
      </Heading>
      {description ? (
        <Body color="secondary" style={styles.description}>
          {description}
        </Body>
      ) : null}
      {action ? (
        <Button
          title={action.label}
          onPress={action.onPress}
          variant="primary"
          size="md"
          accentColor={theme.accent}
          accessibilityLabel={action.accessibilityLabel ?? action.label}
          leftIcon={
            isRetryAction ? (
              <Ionicons
                name="refresh-outline"
                size={18}
                color={THEME.colors.bg}
              />
            ) : undefined
          }
          style={styles.action}
        />
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  centered: {
    flex: 1,
    alignItems: "center",
    justifyContent: "center",
    paddingHorizontal: THEME.spacing.xxxl,
    paddingBottom: EMPTY_STATE_OPTICAL_LIFT,
    gap: THEME.spacing.md,
  },
  inline: {
    alignItems: "center",
    paddingHorizontal: THEME.spacing.xxxl,
    gap: THEME.spacing.md,
  },
  title: {
    marginTop: THEME.spacing.sm,
    textAlign: "center",
  },
  description: {
    textAlign: "center",
  },
  action: {
    // Extra breathing room so the CTA feels like a separate beat, not glued
    // to the description. Stacked on top of the container's `gap` so the
    // total distance from description → button is `gap + marginTop`.
    marginTop: THEME.spacing.xxl,
    alignSelf: "center",
  },
});
