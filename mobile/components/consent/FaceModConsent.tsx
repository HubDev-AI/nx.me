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
import { useCallback, useEffect, useRef, useState } from "react";
import {
  Animated,
  Modal,
  Pressable,
  ScrollView,
  StyleSheet,
  View,
} from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { THEME } from "../../constants/theme";
import { OVERLAY_MEDIUM } from "../../constants/colors";
import { hapticLight, hapticMedium } from "../../lib/haptics";
import { useTheme } from "../../lib/theme-context";
import { Body, Caption, Heading } from "../ui/Text";
import { Button } from "../ui/Button";

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const ENTER_DURATION_MS = 280;
const EXIT_DURATION_MS = 220;
const SCRIM_OPACITY = 0.6;
const BOTTOM_SHEET_RADIUS = THEME.radius.xl;
const ICON_SIZE = 56;
const CLOSE_HIT_SLOP = 16;
/**
 * translateY starting / exit position (off-screen). Large enough to keep
 * the sheet hidden for tall device viewports without measuring.
 */
const SHEET_OFFSCREEN_Y = 600;

// ---------------------------------------------------------------------------
// Copy
// ---------------------------------------------------------------------------

const TITLE = "Transform Your Photo with AI";
const SUBTITLE =
  "Your photo powers a personalized AI glow-up. Here is exactly what happens next.";

const CONSENT_BULLETS: readonly string[] = [
  "Detect and analyze facial features",
  "Apply AI style enhancements",
  "Unsaved results auto-delete after 7 days",
  "Your photo auto-deletes 30 days after last use",
  "Shared posts stay public until you delete them",
];

const PRIVACY_HEADLINE = "Private & secure";
const PRIVACY_DETAIL =
  "Photos are processed on secure servers and never sold or shared with third parties.";

const DISCLAIMER =
  "Results are AI-generated and do not represent a real photograph.";

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
  const { theme } = useTheme();

  // Keep the Modal mounted through the exit animation — otherwise
  // Modal unmounts on visible=false before the exit anim can play.
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
          style={styles.closeButton}
          accessibilityLabel="Close"
          accessibilityRole="button"
          hitSlop={CLOSE_HIT_SLOP}
        >
          <Ionicons name="close" size={22} color={THEME.colors.textSecondary} />
        </Pressable>

        <ScrollView
          contentContainerStyle={styles.content}
          showsVerticalScrollIndicator={false}
          bounces={true}
        >
          <View style={styles.iconWrap}>
            <View style={[styles.iconRing, { borderColor: theme.accent + "66" }]}>
              <Ionicons
                name="sparkles"
                size={ICON_SIZE}
                color={theme.accent}
              />
            </View>
          </View>

          <Heading size="lg" color="primary" style={styles.title}>
            {TITLE}
          </Heading>

          <Body color="secondary" style={styles.subtitle}>
            {SUBTITLE}
          </Body>

          <View style={[styles.privacyCard, { borderColor: theme.accent + "33" }]}>
            <View style={styles.privacyHeader}>
              <Ionicons
                name="shield-checkmark"
                size={18}
                color={theme.accent}
              />
              <Body weight="semibold" color="primary">
                {PRIVACY_HEADLINE}
              </Body>
            </View>
            <Caption color="secondary">{PRIVACY_DETAIL}</Caption>
          </View>

          <View style={styles.bulletList}>
            {CONSENT_BULLETS.map((bullet) => (
              <View key={bullet} style={styles.bulletRow}>
                <Ionicons
                  name="checkmark-circle"
                  size={16}
                  color={theme.accent}
                  style={styles.bulletIcon}
                />
                <Body color="primary" style={styles.bulletText}>
                  {bullet}
                </Body>
              </View>
            ))}
          </View>

          <Caption color="muted" style={styles.disclaimer}>
            {DISCLAIMER}
          </Caption>

          <Button
            title="Accept and Continue"
            onPress={handleAccept}
            variant="primary"
            size="lg"
            block
            haptic="none"
            accentColor={theme.accent}
            accessibilityLabel="Accept and continue"
          />

          <Button
            title="Not now"
            onPress={handleDismiss}
            variant="ghost"
            size="md"
            block
            haptic="none"
          />
        </ScrollView>
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
    width: 96,
    height: 96,
    borderRadius: 48,
    borderWidth: 2,
    alignItems: "center",
    justifyContent: "center",
  },
  title: {
    textAlign: "center",
  },
  subtitle: {
    textAlign: "center",
  },
  privacyCard: {
    backgroundColor: THEME.colors.surface,
    borderRadius: THEME.radius.md,
    borderCurve: "continuous",
    borderWidth: 1,
    padding: THEME.spacing.md,
    gap: THEME.spacing.xs,
  },
  privacyHeader: {
    flexDirection: "row",
    alignItems: "center",
    gap: THEME.spacing.sm,
  },
  bulletList: {
    gap: THEME.spacing.md,
  },
  bulletRow: {
    flexDirection: "row",
    alignItems: "flex-start",
    gap: THEME.spacing.sm,
  },
  bulletIcon: {
    marginTop: 2,
    flexShrink: 0,
  },
  bulletText: {
    flex: 1,
  },
  disclaimer: {
    textAlign: "center",
    opacity: 0.8,
  },
});
