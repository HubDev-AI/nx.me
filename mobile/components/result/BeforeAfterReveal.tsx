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
  FadeOut,
  SlideInLeft,
  SlideInRight,
  useSharedValue,
  useAnimatedStyle,
  withTiming,
  withSpring,
  withDelay,
  Easing,
  runOnJS,
} from "react-native-reanimated";
import { Ionicons } from "@expo/vector-icons";

import {
  BG_PAGE,
  BG_CARD,
  TEXT_PRIMARY,
  GLOW_AMBER,
  BEFORE_OVERLAY,
  AFTER_OVERLAY,
  COLORS,
} from "../../constants/colors";

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
            <Animated.View style={[styles.glowRing, glowStyle]} />
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
              <View style={[styles.labelBadge, styles.labelBadgeAfter]}>
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
            <Ionicons name="close" size={28} color={TEXT_PRIMARY} />
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
    paddingVertical: 16,
  },
  imagesRow: {
    flexDirection: "row",
    gap: 12,
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
    borderRadius: 16,
    backgroundColor: BG_CARD,
  },
  beforeOverlay: {
    ...StyleSheet.absoluteFillObject,
    backgroundColor: BEFORE_OVERLAY,
    borderRadius: 16,
  },
  afterOverlay: {
    ...StyleSheet.absoluteFillObject,
    backgroundColor: AFTER_OVERLAY,
    borderRadius: 16,
  },
  glowRing: {
    position: "absolute",
    width: GLOW_SIZE / 2 + 24,
    height: GLOW_SIZE / 2 + 24,
    borderRadius: (GLOW_SIZE / 2 + 24) / 2,
    borderWidth: 2,
    borderColor: GLOW_AMBER,
    ...Platform.select({
      ios: {
        shadowColor: GLOW_AMBER,
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
    bottom: 8,
    left: 8,
    backgroundColor: "rgba(0,0,0,0.6)",
    paddingHorizontal: 8,
    paddingVertical: 4,
    borderRadius: 6,
  },
  labelBadgeAfter: {
    backgroundColor: "rgba(244,63,94,0.7)",
  },
  labelText: {
    fontSize: 11,
    fontWeight: "700",
    color: TEXT_PRIMARY,
    textTransform: "uppercase",
    letterSpacing: 0.5,
  },
  labelTextAfter: {
    color: "#FFFFFF",
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
    right: 20,
    zIndex: 10,
    backgroundColor: "rgba(255,255,255,0.15)",
    borderRadius: 20,
    width: 40,
    height: 40,
    alignItems: "center",
    justifyContent: "center",
  },
  lightboxImage: {
    width: SCREEN_WIDTH - 32,
    height: SCREEN_WIDTH - 32,
    borderRadius: 12,
  },
});
