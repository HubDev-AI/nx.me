/**
 * CancelSubscriptionSheet — in-app confirmation sheet for ending a premium
 * subscription. Replaces the native `Alert.alert` used pre-PR4 so the
 * confirmation matches the rest of the checkout surface (scale+fade sheet,
 * scrim, destructive action).
 *
 * The sheet is stateless: the parent screen wires `visible` + `onConfirm`
 * via `usePurchaseFlow` state (`isCancelSheetOpen`, `confirmCancel`,
 * `dismissCancelSheet`). While `isCancelling` is true the destructive
 * button shows a spinner and the close/dismiss affordances are disabled.
 */
import { useCallback, useEffect, useRef, useState } from "react";
import {
  Animated,
  Modal,
  Pressable,
  StyleSheet,
  View,
} from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { THEME } from "../../constants/theme";
import { OVERLAY_MEDIUM } from "../../constants/colors";
import { PAYWALL_ANIMATION } from "../../constants/config";
import { hapticLight, hapticMedium } from "../../lib/haptics";
import { useTheme } from "../../lib/theme-context";
import { Body, Heading } from "../ui/Text";
import { Button } from "../ui/Button";

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const ENTER_DURATION_MS = PAYWALL_ANIMATION.ENTER_DURATION_MS;
const EXIT_DURATION_MS = PAYWALL_ANIMATION.EXIT_DURATION_MS;
const SCRIM_OPACITY = PAYWALL_ANIMATION.SCRIM_OPACITY;
const BOTTOM_SHEET_RADIUS = THEME.radius.xl;
const ICON_SIZE = 40;
const ICON_RING_SIZE = 72;
const ICON_RING_RADIUS = 36;
const CLOSE_HIT_SLOP = 16;
/** translateY starting / exit position (off-screen). */
const SHEET_OFFSCREEN_Y = 600;

// ---------------------------------------------------------------------------
// Copy
// ---------------------------------------------------------------------------

const TITLE = "Cancel Subscription";
const BODY =
  "Your premium benefits stay active until the end of your current billing period. You'll keep access until then, and no further charges will be made.";
const CONFIRM_LABEL = "End subscription";
const DISMISS_LABEL = "Keep subscription";

const EXPIRY_DATE_FORMAT: Intl.DateTimeFormatOptions = {
  month: "short",
  day: "numeric",
  year: "numeric",
};

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface CancelSubscriptionSheetProps {
  visible: boolean;
  /** In-flight state for the cancel API call — disables actions and shows spinner. */
  isCancelling: boolean;
  /** Optional billing period end ISO string; when present the body surfaces an exact date. */
  billingPeriodEnd?: string | null;
  /** Invoked when the user confirms cancellation. */
  onConfirm: () => void;
  /** Invoked when the user dismisses without confirming. */
  onDismiss: () => void;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function CancelSubscriptionSheet({
  visible,
  isCancelling,
  billingPeriodEnd,
  onConfirm,
  onDismiss,
}: CancelSubscriptionSheetProps) {
  const insets = useSafeAreaInsets();
  const { theme } = useTheme();

  // Keep the modal mounted through the exit animation.
  const [mounted, setMounted] = useState(visible);

  const backdropOpacity = useRef(new Animated.Value(0)).current;
  const sheetTranslateY = useRef(new Animated.Value(SHEET_OFFSCREEN_Y)).current;

  useEffect(() => {
    if (visible) {
      setMounted(true);
      Animated.parallel([
        Animated.timing(backdropOpacity, {
          toValue: SCRIM_OPACITY,
          duration: ENTER_DURATION_MS,
          useNativeDriver: true,
        }),
        Animated.spring(sheetTranslateY, {
          toValue: 0,
          useNativeDriver: true,
          damping: THEME.animation.press.damping,
          stiffness: THEME.animation.press.stiffness,
        }),
      ]).start();
    } else {
      Animated.parallel([
        Animated.timing(backdropOpacity, {
          toValue: 0,
          duration: EXIT_DURATION_MS,
          useNativeDriver: true,
        }),
        Animated.timing(sheetTranslateY, {
          toValue: SHEET_OFFSCREEN_Y,
          duration: EXIT_DURATION_MS,
          useNativeDriver: true,
        }),
      ]).start(({ finished }) => {
        if (finished) setMounted(false);
      });
    }
  }, [visible, backdropOpacity, sheetTranslateY]);

  const handleConfirm = useCallback(() => {
    hapticMedium();
    onConfirm();
  }, [onConfirm]);

  const handleDismiss = useCallback(() => {
    if (isCancelling) return;
    hapticLight();
    onDismiss();
  }, [isCancelling, onDismiss]);

  const expiryDate =
    billingPeriodEnd != null
      ? new Date(billingPeriodEnd).toLocaleDateString(undefined, EXPIRY_DATE_FORMAT)
      : null;

  return (
    <Modal
      visible={mounted}
      transparent
      animationType="none"
      onRequestClose={handleDismiss}
      statusBarTranslucent
    >
      <Animated.View
        style={[styles.scrim, { opacity: backdropOpacity }]}
        pointerEvents="none"
      />

      <Pressable
        style={styles.dismissArea}
        onPress={handleDismiss}
        accessible={false}
      />

      <Animated.View
        style={[
          styles.sheet,
          {
            transform: [{ translateY: sheetTranslateY }],
            paddingBottom: Math.max(insets.bottom, THEME.spacing.xl),
          },
        ]}
      >
        <View style={styles.dragIndicator} />

        <Pressable
          onPress={handleDismiss}
          disabled={isCancelling}
          style={styles.closeButton}
          accessibilityLabel="Close"
          accessibilityRole="button"
          hitSlop={CLOSE_HIT_SLOP}
        >
          <Ionicons name="close" size={22} color={THEME.colors.textSecondary} />
        </Pressable>

        <View style={styles.content}>
          <View style={styles.iconWrap}>
            <View
              style={[styles.iconRing, { borderColor: theme.accent + THEME.alpha.med }]}
            >
              <Ionicons
                name="alert-circle-outline"
                size={ICON_SIZE}
                color={theme.accent}
              />
            </View>
          </View>

          <Heading size="md" color="primary" style={styles.title}>
            {TITLE}
          </Heading>

          <Body color="secondary" style={styles.body}>
            {BODY}
          </Body>

          {expiryDate && (
            <Body color="primary" weight="medium" style={styles.expiry}>
              You&rsquo;ll keep access until {expiryDate}.
            </Body>
          )}

          <Button
            title={CONFIRM_LABEL}
            onPress={handleConfirm}
            variant="destructive"
            size="lg"
            block
            isLoading={isCancelling}
            disabled={isCancelling}
            haptic="none"
            accessibilityLabel={CONFIRM_LABEL}
          />

          <Button
            title={DISMISS_LABEL}
            onPress={handleDismiss}
            variant="ghost"
            size="md"
            block
            disabled={isCancelling}
            haptic="none"
          />
        </View>
      </Animated.View>
    </Modal>
  );
}

// ---------------------------------------------------------------------------
// Styles
// ---------------------------------------------------------------------------

const styles = StyleSheet.create({
  scrim: {
    ...StyleSheet.absoluteFillObject,
    backgroundColor: OVERLAY_MEDIUM,
  },
  dismissArea: {
    flex: 1,
  },
  sheet: {
    position: "absolute",
    left: 0,
    right: 0,
    bottom: 0,
    backgroundColor: THEME.colors.surfaceElevated,
    borderTopLeftRadius: BOTTOM_SHEET_RADIUS,
    borderTopRightRadius: BOTTOM_SHEET_RADIUS,
    borderCurve: "continuous",
    borderTopWidth: 1,
    borderColor: THEME.colors.glassBorder,
    paddingTop: THEME.spacing.sm,
  },
  dragIndicator: {
    width: 36,
    height: 4,
    borderRadius: THEME.radius.pill,
    backgroundColor: THEME.colors.border,
    alignSelf: "center",
    marginBottom: THEME.spacing.sm,
  },
  closeButton: {
    position: "absolute",
    top: THEME.spacing.lg,
    right: THEME.spacing.xl,
    width: 44,
    height: 44,
    alignItems: "center",
    justifyContent: "center",
    zIndex: 1,
  },
  content: {
    paddingHorizontal: THEME.spacing.xxl,
    paddingTop: THEME.spacing.lg,
    paddingBottom: THEME.spacing.lg,
    gap: THEME.spacing.lg,
  },
  iconWrap: {
    alignItems: "center",
    paddingTop: THEME.spacing.sm,
  },
  iconRing: {
    width: ICON_RING_SIZE,
    height: ICON_RING_SIZE,
    borderRadius: ICON_RING_RADIUS,
    borderWidth: 2,
    alignItems: "center",
    justifyContent: "center",
  },
  title: {
    textAlign: "center",
  },
  body: {
    textAlign: "center",
  },
  expiry: {
    textAlign: "center",
  },
});
