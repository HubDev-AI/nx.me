/**
 * BeforeAfterReveal — animated reveal sequence for glow-up results.
 *
 * Sequence:
 * 1. Before image slides in from left
 * 2. After image wipes in from right with glow ring
 * 3. Suggestion pills stagger up (handled by parent)
 * 4. CTAs fade in (handled by parent)
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
  Platform,
} from "react-native";
import Animated, {
  FadeIn,
  SlideInLeft,
  SlideInRight,
  useSharedValue,
  useAnimatedStyle,
  withTiming,
  withSpring,
  withDelay,
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
const IMAGE_SIZE = Math.min(SCREEN_WIDTH - 64, 320);
const GLOW_SIZE = IMAGE_SIZE + 16;
const BEFORE_DELAY_MS = 100;
const AFTER_DELAY_MS = 500;
const GLOW_DELAY_MS = 400;
const SPRING_CONFIG = { damping: 18, stiffness: 120, mass: 0.8 };

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

  const glowOpacity = useSharedValue(0);
  const glowScale = useSharedValue(0.8);

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

  // Glow ring animation
  useEffect(() => {
    if (!showAfter) return;
    const delay = reducedMotion ? 0 : GLOW_DELAY_MS;
    glowOpacity.value = withDelay(delay, withTiming(1, { duration: 300 }));
    glowScale.value = withDelay(
      delay,
      withSpring(1, SPRING_CONFIG),
    );
  }, [showAfter, reducedMotion, glowOpacity, glowScale]);

  const handleRevealDone = useCallback(() => {
    onRevealComplete?.();
  }, [onRevealComplete]);

  const glowStyle = useAnimatedStyle(() => ({
    opacity: glowOpacity.value,
    transform: [{ scale: glowScale.value }],
  }));

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
      {/* Before / After side by side */}
      <View style={styles.imagesRow}>
        {/* Before */}
        <Animated.View entering={beforeEntering} style={styles.imageWrapper}>
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
            <View style={styles.beforeOverlay} />
            <View style={styles.labelBadge}>
              <Animated.Text style={styles.labelText}>Before</Animated.Text>
            </View>
          </Pressable>
        </Animated.View>

        {/* After with glow ring */}
        {showAfter && (
          <Animated.View entering={afterEntering} style={styles.imageWrapper}>
            {/* Glow ring behind */}
            <Animated.View style={[styles.glowRing, glowStyle, { borderColor: theme.accent }]} />
            <Pressable
              onPress={() => setLightboxUri(afterUrl)}
              accessibilityLabel="View after photo fullscreen"
              accessibilityRole="imagebutton"
            >
              <Image
                source={{ uri: afterUrl }}
                style={styles.image}
                accessibilityLabel="After photo"
              />
              <View style={styles.afterOverlay} />
              <View style={[styles.labelBadge, styles.labelBadgeAfter, { backgroundColor: theme.accent + "B3" }]}>
                <Animated.Text style={[styles.labelText, styles.labelTextAfter]}>
                  After
                </Animated.Text>
              </View>
            </Pressable>
          </Animated.View>
        )}
      </View>

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
    alignItems: "center",
    paddingVertical: THEME.spacing.lg,
  },
  imagesRow: {
    flexDirection: "row",
    gap: THEME.spacing.md,
    alignItems: "center",
    justifyContent: "center",
  },
  imageWrapper: {
    position: "relative",
    alignItems: "center",
    justifyContent: "center",
  },
  image: {
    width: IMAGE_SIZE / 2 + 16,
    height: IMAGE_SIZE / 2 + 16,
    borderRadius: THEME.radius.lg,
    backgroundColor: THEME.colors.surface,
  },
  beforeOverlay: {
    ...StyleSheet.absoluteFillObject,
    backgroundColor: "rgba(15,23,42,0.72)",
    borderRadius: THEME.radius.lg,
  },
  afterOverlay: {
    ...StyleSheet.absoluteFillObject,
    backgroundColor: "rgba(244, 63, 94, 0.08)",
    borderRadius: THEME.radius.lg,
  },
  glowRing: {
    position: "absolute",
    width: GLOW_SIZE / 2 + 24,
    height: GLOW_SIZE / 2 + 24,
    borderRadius: (GLOW_SIZE / 2 + 24) / 2,
    borderWidth: 2,
    ...Platform.select({
      ios: {
        shadowOffset: { width: 0, height: 0 },
        shadowOpacity: 0.6,
        shadowRadius: 12,
      },
      android: {
        elevation: 8,
      },
    }),
  },
  labelBadge: {
    position: "absolute",
    bottom: THEME.spacing.sm,
    left: THEME.spacing.sm,
    backgroundColor: "rgba(0,0,0,0.6)",
    paddingHorizontal: THEME.spacing.sm,
    paddingVertical: THEME.spacing.xs,
    borderRadius: THEME.radius.sm,
  },
  labelBadgeAfter: {
    // backgroundColor applied inline with theme.accent
  },
  labelText: {
    fontFamily: FONTS.bodyBold,
    fontSize: 11,
    color: THEME.colors.textPrimary,
    textTransform: "uppercase",
    letterSpacing: 0.5,
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
