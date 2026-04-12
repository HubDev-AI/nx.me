/**
 * FaceModConsent — first-use face-modification consent modal.
 *
 * Shown before the user's first Glow Up analysis if they haven't consented.
 * Acceptance triggers POST /users/me/face-mod-consent via the onAccept callback.
 *
 * Design: bottom sheet pattern (consistent with PaywallModal). Scale+fade entry.
 * The modal is informational — one required action (Accept) + escape (Cancel /
 * dismiss). Per UX rule: Accept button always visible, never hidden.
 */
import { useEffect, useCallback, useRef } from "react";
import {
  View,
  Text,
  Modal,
  Pressable,
  StyleSheet,
  Animated,
  ScrollView,
} from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { THEME } from "../../constants/theme";
import { FONTS } from "../../hooks/useFonts";
import {
  CTA_PRIMARY,
  TEXT_SECONDARY,
  OVERLAY_MEDIUM,
} from "../../constants/colors";
import { hapticLight, hapticMedium } from "../../lib/haptics";
import { MIN_TOUCH_TARGET } from "../../constants/config";

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

/** Modal entry/exit animation duration (ms). */
const ENTER_DURATION_MS = 280;
const EXIT_DURATION_MS = 220;

/** Scrim opacity when modal is visible. */
const SCRIM_OPACITY = 0.6;

/** Height of the bottom inset to respect safe area. */
const BOTTOM_SHEET_RADIUS = THEME.radius.xl;

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface FaceModConsentProps {
  visible: boolean;
  /** Called when user explicitly accepts. Triggers API call in parent. */
  onAccept: () => void;
  /** Called when user dismisses without accepting (optional). */
  onDismiss?: () => void;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function FaceModConsent({ visible, onAccept, onDismiss }: FaceModConsentProps) {
  const insets = useSafeAreaInsets();

  const backdropOpacity = useRef(new Animated.Value(0)).current;
  const sheetTranslateY = useRef(new Animated.Value(300)).current;

  useEffect(() => {
    if (visible) {
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
          toValue: 300,
          duration: EXIT_DURATION_MS,
          useNativeDriver: true,
        }),
      ]).start();
    }
  }, [visible, backdropOpacity, sheetTranslateY]);

  const handleAccept = useCallback(() => {
    hapticMedium();
    onAccept();
  }, [onAccept]);

  const handleDismiss = useCallback(() => {
    hapticLight();
    onDismiss?.();
  }, [onDismiss]);

  return (
    <Modal
      visible={visible}
      transparent
      animationType="none"
      onRequestClose={handleDismiss}
      statusBarTranslucent
    >
      {/* Scrim */}
      <Animated.View
        style={[styles.scrim, { opacity: backdropOpacity }]}
        pointerEvents="none"
      />

      {/* Tap-outside-to-dismiss */}
      <Pressable
        style={styles.dismissArea}
        onPress={handleDismiss}
        accessible={false}
      />

      {/* Bottom sheet */}
      <Animated.View
        style={[
          styles.sheet,
          {
            transform: [{ translateY: sheetTranslateY }],
            paddingBottom: Math.max(insets.bottom, THEME.spacing.xl),
          },
        ]}
      >
        {/* Drag indicator */}
        <View style={styles.dragIndicator} />

        {/* Close button */}
        <Pressable
          onPress={handleDismiss}
          style={styles.closeButton}
          accessibilityLabel="Close"
          accessibilityRole="button"
          hitSlop={12}
        >
          <Ionicons name="close" size={22} color={THEME.colors.textSecondary} />
        </Pressable>

        <ScrollView
          contentContainerStyle={styles.content}
          showsVerticalScrollIndicator={false}
          bounces={false}
        >
          {/* Icon */}
          <View style={styles.iconContainer}>
            <Ionicons name="shield-checkmark-outline" size={40} color={CTA_PRIMARY} />
          </View>

          {/* Title */}
          <Text style={styles.title}>AI Face Modification</Text>

          {/* Body */}
          <Text style={styles.body}>
            nxme uses AI to analyze and apply enhancements to your facial photo. By
            continuing, you allow nxme to:
          </Text>

          {/* Bullet points */}
          <View style={styles.bulletList}>
            {CONSENT_BULLETS.map((bullet) => (
              <View key={bullet} style={styles.bulletRow}>
                <Ionicons
                  name="checkmark-circle"
                  size={16}
                  color={CTA_PRIMARY}
                  style={styles.bulletIcon}
                />
                <Text style={styles.bulletText}>{bullet}</Text>
              </View>
            ))}
          </View>

          {/* Footnote */}
          <Text style={styles.footnote}>
            Results are AI-generated and do not represent a real photograph.
            Your photo is processed securely and not shared with third parties.
          </Text>

          {/* Accept CTA */}
          <Pressable
            onPress={handleAccept}
            style={styles.acceptButton}
            accessibilityLabel="Accept and continue"
            accessibilityRole="button"
          >
            <Text style={styles.acceptButtonText}>Accept and Continue</Text>
          </Pressable>

          {/* Cancel link */}
          <Pressable
            onPress={handleDismiss}
            style={styles.cancelButton}
            accessibilityLabel="Cancel"
            accessibilityRole="button"
          >
            <Text style={styles.cancelText}>Not now</Text>
          </Pressable>
        </ScrollView>
      </Animated.View>
    </Modal>
  );
}

// ---------------------------------------------------------------------------
// Data
// ---------------------------------------------------------------------------

const CONSENT_BULLETS: string[] = [
  "Detect and analyze your facial features",
  "Apply AI-generated style enhancements to your photo",
  "Temporarily store the processed result (auto-deleted after 7 days unless saved)",
];

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
    backgroundColor: THEME.colors.surfaceElevated,
    borderTopLeftRadius: BOTTOM_SHEET_RADIUS,
    borderTopRightRadius: BOTTOM_SHEET_RADIUS,
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
    minWidth: MIN_TOUCH_TARGET,
    minHeight: MIN_TOUCH_TARGET,
    alignItems: "center",
    justifyContent: "center",
  },
  content: {
    paddingHorizontal: THEME.spacing.xxl,
    paddingTop: THEME.spacing.lg,
    paddingBottom: THEME.spacing.lg,
    gap: THEME.spacing.lg,
  },
  iconContainer: {
    alignItems: "center",
    paddingTop: THEME.spacing.sm,
  },
  title: {
    fontFamily: FONTS.display,
    fontSize: 24,
    color: THEME.colors.textPrimary,
    textAlign: "center",
    letterSpacing: -0.3,
  },
  body: {
    fontFamily: FONTS.body,
    fontSize: 15,
    color: TEXT_SECONDARY,
    lineHeight: 22,
    textAlign: "center",
  },
  bulletList: {
    gap: THEME.spacing.sm,
  },
  bulletRow: {
    flexDirection: "row",
    alignItems: "flex-start",
    gap: THEME.spacing.sm,
  },
  bulletIcon: {
    marginTop: 1,
    flexShrink: 0,
  },
  bulletText: {
    fontFamily: FONTS.body,
    fontSize: 14,
    color: THEME.colors.textPrimary,
    lineHeight: 20,
    flex: 1,
  },
  footnote: {
    fontFamily: FONTS.body,
    fontSize: 12,
    color: TEXT_SECONDARY,
    lineHeight: 17,
    textAlign: "center",
    opacity: 0.8,
  },
  acceptButton: {
    backgroundColor: CTA_PRIMARY,
    borderRadius: THEME.radius.pill,
    minHeight: MIN_TOUCH_TARGET + 4,
    alignItems: "center",
    justifyContent: "center",
    paddingVertical: THEME.spacing.md,
    paddingHorizontal: THEME.spacing.xxl,
  },
  acceptButtonText: {
    fontFamily: FONTS.bodyMedium,
    fontSize: 16,
    color: THEME.colors.bg,
    letterSpacing: 0.3,
  },
  cancelButton: {
    alignItems: "center",
    justifyContent: "center",
    minHeight: MIN_TOUCH_TARGET,
  },
  cancelText: {
    fontFamily: FONTS.body,
    fontSize: 14,
    color: TEXT_SECONDARY,
    letterSpacing: 0.1,
  },
});
