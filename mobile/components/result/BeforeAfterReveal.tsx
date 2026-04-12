/**
 * BeforeAfterReveal — animated reveal sequence for glow-up results.
 *
 * Sequence:
 * 1. Before image fades/slides in
 * 2. After image wipes in from right with accent border
 * 3. CTAs fade in (handled by parent via onRevealComplete)
 *
 * Respects reduced-motion preference.
 */
import { useState, useEffect, useCallback } from "react";
import {
  View,
  Image,
  Pressable,
  StyleSheet,
  Dimensions,
  Modal,
  AccessibilityInfo,
  Text,
} from "react-native";
import Animated, {
  FadeIn,
  SlideInLeft,
  SlideInRight,
  runOnJS,
} from "react-native-reanimated";
import { Ionicons } from "@expo/vector-icons";

import { THEME } from "../../constants/theme";
import { FONTS } from "../../hooks/useFonts";
import { useTheme } from "../../lib/theme-context";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface BeforeAfterRevealProps {
  beforeUrl: string;
  afterUrl: string;
  /** Called when the reveal animation completes (after image fully visible) */
  onRevealComplete?: () => void;
}

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const { width: SCREEN_WIDTH } = Dimensions.get("window");
const IMAGE_WIDTH = SCREEN_WIDTH - 48; // 24px padding each side
const BEFORE_DELAY_MS = 100;
const AFTER_DELAY_MS = 500;
const SPRING_CONFIG = { damping: 20, stiffness: 170, mass: 0.9 };

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export default function BeforeAfterReveal({
  beforeUrl,
  afterUrl,
  onRevealComplete,
}: BeforeAfterRevealProps) {
  const { theme } = useTheme();
  const [showAfter, setShowAfter] = useState(false);
  const [lightboxUri, setLightboxUri] = useState<string | null>(null);
  const [reducedMotion, setReducedMotion] = useState(false);

  // Check reduced motion preference
  useEffect(() => {
    AccessibilityInfo.isReduceMotionEnabled().then(setReducedMotion);
  }, []);

  // Trigger after-image reveal after before slides in
  useEffect(() => {
    const delay = reducedMotion ? 0 : AFTER_DELAY_MS;
    const timer = setTimeout(() => {
      setShowAfter(true);
    }, delay);
    return () => clearTimeout(timer);
  }, [reducedMotion]);

  const handleRevealDone = useCallback(() => {
    onRevealComplete?.();
  }, [onRevealComplete]);

  const beforeEntering = reducedMotion
    ? FadeIn.duration(150)
    : SlideInLeft.delay(BEFORE_DELAY_MS)
        .springify()
        .damping(SPRING_CONFIG.damping)
        .stiffness(SPRING_CONFIG.stiffness)
        .mass(SPRING_CONFIG.mass);

  const afterEntering = reducedMotion
    ? FadeIn.duration(150).withCallback((finished) => {
        "worklet";
        if (finished) runOnJS(handleRevealDone)();
      })
    : SlideInRight.springify()
        .damping(SPRING_CONFIG.damping)
        .stiffness(SPRING_CONFIG.stiffness)
        .mass(SPRING_CONFIG.mass)
        .withCallback((finished) => {
          "worklet";
          if (finished) runOnJS(handleRevealDone)();
        });

  return (
    <View style={styles.container}>
      {/* Before */}
      <Animated.View entering={beforeEntering} style={styles.imageCard}>
        <Pressable
          onPress={() => setLightboxUri(beforeUrl)}
          accessibilityLabel="View before photo fullscreen"
          accessibilityRole="imagebutton"
        >
          <Image
            source={{ uri: beforeUrl }}
            style={styles.image}
            accessibilityLabel="Before photo"
          />
          <View style={styles.labelBadge}>
            <Text style={styles.labelText}>BEFORE</Text>
          </View>
        </Pressable>
      </Animated.View>

      {/* After */}
      {showAfter && (
        <Animated.View entering={afterEntering} style={styles.imageCard}>
          <Pressable
            onPress={() => setLightboxUri(afterUrl)}
            accessibilityLabel="View after photo fullscreen"
            accessibilityRole="imagebutton"
          >
            <Image
              source={{ uri: afterUrl }}
              style={[styles.image, styles.afterImage, { borderColor: theme.accent + "66" }]}
              accessibilityLabel="After photo"
            />
            <View style={[styles.labelBadge, { backgroundColor: theme.accent + "CC" }]}>
              <Text style={[styles.labelText, styles.labelTextAfter]}>AFTER</Text>
            </View>
          </Pressable>
        </Animated.View>
      )}

      {/* Fullscreen lightbox modal */}
      <Modal
        visible={lightboxUri !== null}
        transparent
        animationType="fade"
        onRequestClose={() => setLightboxUri(null)}
        statusBarTranslucent
      >
        <View style={styles.lightboxBackdrop}>
          <Pressable
            style={styles.lightboxClose}
            onPress={() => setLightboxUri(null)}
            accessibilityLabel="Close fullscreen view"
            accessibilityRole="button"
            hitSlop={12}
          >
            <Ionicons name="close" size={28} color={THEME.colors.textPrimary} />
          </Pressable>
          {lightboxUri && (
            <Image
              source={{ uri: lightboxUri }}
              style={styles.lightboxImage}
              resizeMode="contain"
              accessibilityLabel="Fullscreen photo"
            />
          )}
        </View>
      </Modal>
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
    gap: THEME.spacing.lg,
  },
  imageCard: {
    borderRadius: THEME.radius.lg,
    overflow: "hidden",
  },
  image: {
    width: IMAGE_WIDTH,
    aspectRatio: 3 / 4,
    borderRadius: THEME.radius.lg,
    backgroundColor: THEME.colors.surface,
  },
  afterImage: {
    borderWidth: 2,
  },
  labelBadge: {
    position: "absolute",
    bottom: THEME.spacing.md,
    left: THEME.spacing.md,
    backgroundColor: "rgba(0,0,0,0.55)",
    paddingHorizontal: THEME.spacing.md,
    paddingVertical: THEME.spacing.xs + 2,
    borderRadius: THEME.radius.sm,
  },
  labelText: {
    fontFamily: FONTS.bodyBold,
    fontSize: 13,
    color: THEME.colors.textPrimary,
    letterSpacing: 1,
  },
  labelTextAfter: {
    color: THEME.colors.white,
  },
  // Lightbox
  lightboxBackdrop: {
    flex: 1,
    backgroundColor: "rgba(0,0,0,0.95)",
    alignItems: "center",
    justifyContent: "center",
  },
  lightboxClose: {
    position: "absolute",
    top: 56,
    right: THEME.spacing.xl,
    zIndex: 10,
    backgroundColor: THEME.colors.glass,
    borderRadius: THEME.radius.pill,
    width: 44,
    height: 44,
    alignItems: "center",
    justifyContent: "center",
  },
  lightboxImage: {
    width: SCREEN_WIDTH - 32,
    height: undefined,
    aspectRatio: 3 / 4,
    borderRadius: THEME.radius.md,
  },
});
