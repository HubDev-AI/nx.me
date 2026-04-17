/**
 * ResultActions — Save / Share / Try-again button bar for result screens.
 *
 * Rules per AGENTS.md:
 *   - Action buttons stay VISIBLE when disabled — never hide them.
 *   - Visual opacity conveys disabled state; button is always rendered.
 *   - creditsRemaining badge is optional; rendered only when a number is passed.
 */
import { useCallback } from "react";
import {
  View,
  Text,
  Pressable,
  ActivityIndicator,
  StyleSheet,
} from "react-native";
import { Ionicons } from "@expo/vector-icons";
import Animated, {
  useSharedValue,
  useAnimatedStyle,
  withSpring,
} from "react-native-reanimated";

import { THEME } from "../../constants/theme";
import { FONTS } from "../../hooks/useFonts";
import {
  CTA_PRIMARY,
  TEXT_SECONDARY,
  CREDIT_BADGE_BG,
  CREDIT_BADGE_TEXT,
  CREDIT_BADGE_ICON,
} from "../../constants/colors";
import { hapticLight, hapticMedium } from "../../lib/haptics";
import { MIN_TOUCH_TARGET } from "../../constants/config";

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

/** Spring config for press-scale feedback. */
const PRESS_SPRING = THEME.animation.press;

/** Icon size for action buttons. */
const ICON_SIZE = 22;

/** Opacity applied to the button wrapper when disabled. */
const DISABLED_OPACITY = 0.4;

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export type SaveState = "pending" | "saving" | "saved";

export interface ResultActionsProps {
  onSave: () => void;
  onShare: () => void;
  onTryAnother: () => void;
  saveState: SaveState;
  /** When provided, renders a small credit badge next to Try-again. */
  creditsRemaining?: number | null;
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

interface ActionButtonProps {
  label: string;
  iconName: React.ComponentProps<typeof Ionicons>["name"];
  onPress: () => void;
  disabled?: boolean;
  loading?: boolean;
  variant?: "primary" | "secondary" | "outline";
}

function ActionButton({
  label,
  iconName,
  onPress,
  disabled = false,
  loading = false,
  variant = "secondary",
}: ActionButtonProps) {
  const scale = useSharedValue(1);
  const isInteractable = !disabled && !loading;

  const handlePressIn = useCallback(() => {
    if (!isInteractable) return;
    scale.value = withSpring(0.95, PRESS_SPRING);
  }, [isInteractable, scale]);

  const handlePressOut = useCallback(() => {
    scale.value = withSpring(1, PRESS_SPRING);
  }, [scale]);

  const handlePress = useCallback(() => {
    if (!isInteractable) return;
    hapticLight();
    onPress();
  }, [isInteractable, onPress]);

  const animatedStyle = useAnimatedStyle(() => ({
    transform: [{ scale: scale.value }],
    // Disabled state: visual opacity only. Button stays visible and tappable-
    // but we gate the onPress above. This matches feedback_disabled_button_ux.
    opacity: disabled ? DISABLED_OPACITY : 1,
  }));

  const bgColor =
    variant === "primary"
      ? CTA_PRIMARY
      : variant === "outline"
        ? "transparent"
        : THEME.colors.surfaceElevated;

  const borderStyle =
    variant === "outline"
      ? { borderWidth: 1, borderColor: THEME.colors.borderFocused }
      : {};

  return (
    <Animated.View style={[styles.buttonWrapper, animatedStyle]}>
      <Pressable
        onPress={handlePress}
        onPressIn={handlePressIn}
        onPressOut={handlePressOut}
        style={[styles.button, { backgroundColor: bgColor }, borderStyle]}
        accessibilityLabel={loading ? `${label}, loading` : label}
        accessibilityRole="button"
        accessibilityState={{ disabled, busy: loading }}
      >
        {loading ? (
          <ActivityIndicator
            size="small"
            color={variant === "primary" ? THEME.colors.bg : THEME.colors.textPrimary}
          />
        ) : (
          <>
            <Ionicons
              name={iconName}
              size={ICON_SIZE}
              color={
                variant === "primary"
                  ? THEME.colors.bg
                  : disabled
                    ? TEXT_SECONDARY
                    : THEME.colors.textPrimary
              }
            />
            <Text
              style={[
                styles.buttonLabel,
                variant === "primary" && styles.buttonLabelPrimary,
                disabled && styles.buttonLabelDisabled,
              ]}
            >
              {label}
            </Text>
          </>
        )}
      </Pressable>
    </Animated.View>
  );
}

// ---------------------------------------------------------------------------
// Main Component
// ---------------------------------------------------------------------------

export function ResultActions({
  onSave,
  onShare,
  onTryAnother,
  saveState,
  creditsRemaining,
}: ResultActionsProps) {
  const handleShare = useCallback(() => {
    hapticMedium();
    onShare();
  }, [onShare]);

  // "Save on profile" framing — the endpoint persists the result to
  // the user's profile (indefinite retention). The old bare "Save"
  // read as "save to phone gallery"; Share handles that path
  // separately. Pairs with the retention disclosure on Upload
  // ("Saved results stay on your profile.") so the surface reads
  // the same everywhere.
  const saveLabel =
    saveState === "saved"
      ? "Saved on profile"
      : saveState === "saving"
        ? "Saving…"
        : "Save on profile";

  const saveIcon: React.ComponentProps<typeof Ionicons>["name"] =
    saveState === "saved" ? "checkmark-circle" : "bookmark-outline";

  return (
    <View style={styles.container}>
      {/* Primary row: Save + Share */}
      <View style={styles.primaryRow}>
        <View style={styles.primaryButton}>
          <ActionButton
            label={saveLabel}
            iconName={saveIcon}
            onPress={onSave}
            disabled={saveState === "saved"}
            loading={saveState === "saving"}
            variant="outline"
          />
        </View>
        <View style={styles.primaryButton}>
          <ActionButton
            label="Share"
            iconName="share-outline"
            onPress={handleShare}
            variant="primary"
          />
        </View>
      </View>

      {/* Secondary row: Start a new glow-up with a different photo. */}
      <View style={styles.secondaryRow}>
        <ActionButton
          label="New glow-up"
          iconName="add-circle-outline"
          onPress={onTryAnother}
          variant="secondary"
        />

        {/* Credit badge (optional) */}
        {creditsRemaining != null && (
          <View style={styles.creditBadge}>
            <Ionicons name="flash" size={12} color={CREDIT_BADGE_ICON} />
            <Text style={styles.creditBadgeText}>{creditsRemaining}</Text>
          </View>
        )}
      </View>
    </View>
  );
}

// ---------------------------------------------------------------------------
// Styles
// ---------------------------------------------------------------------------

const styles = StyleSheet.create({
  container: {
    paddingHorizontal: THEME.spacing.xl,
    paddingTop: THEME.spacing.lg,
    paddingBottom: THEME.spacing.xl,
    gap: THEME.spacing.md,
  },
  primaryRow: {
    flexDirection: "row",
    gap: THEME.spacing.md,
  },
  primaryButton: {
    flex: 1,
  },
  buttonWrapper: {
    borderRadius: THEME.radius.pill,
  },
  button: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    gap: THEME.spacing.xs + 2,
    minHeight: MIN_TOUCH_TARGET,
    paddingVertical: THEME.spacing.sm + 2,
    paddingHorizontal: THEME.spacing.lg,
    borderRadius: THEME.radius.pill,
  },
  buttonLabel: {
    fontFamily: FONTS.bodyMedium,
    fontSize: 15,
    color: THEME.colors.textPrimary,
    letterSpacing: 0.2,
  },
  buttonLabelPrimary: {
    color: THEME.colors.bg,
  },
  buttonLabelDisabled: {
    color: TEXT_SECONDARY,
  },
  secondaryRow: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    gap: THEME.spacing.sm,
  },
  creditBadge: {
    flexDirection: "row",
    alignItems: "center",
    gap: 3,
    backgroundColor: CREDIT_BADGE_BG,
    paddingHorizontal: THEME.spacing.sm,
    paddingVertical: THEME.spacing.xs,
    borderRadius: THEME.radius.pill,
  },
  creditBadgeText: {
    fontFamily: FONTS.bodySemiBold,
    fontSize: 12,
    color: CREDIT_BADGE_TEXT,
    letterSpacing: 0.3,
  },
});
