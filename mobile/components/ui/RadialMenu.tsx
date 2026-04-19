/**
 * RadialMenu — full-screen circular menu overlay.
 *
 * A bright glowing violet hollow ring sits at the geometric center of the
 * screen. Around it, item circles "explode" outward to fixed corners
 * (TL/TR/BL/BR), connected visually by a faint dashed orbital ring that
 * passes through every item center.
 *
 * Built with Reanimated 4 shared values for 120 fps UI-thread animations
 * and expo-blur for the glass aesthetic.
 */
import React, { useCallback, useMemo } from "react";
import {
  View,
  Text,
  Pressable,
  StyleSheet,
  Platform,
  useWindowDimensions,
  Modal,
} from "react-native";
import Animated, {
  useSharedValue,
  useAnimatedStyle,
  withSpring,
  withTiming,
  withDelay,
  Easing,
  type SharedValue,
} from "react-native-reanimated";
import { BlurView } from "expo-blur";
import { Ionicons } from "@expo/vector-icons";

import { THEME } from "../../constants/theme";
import { FONTS } from "../../hooks/useFonts";
import { hapticLight, hapticMedium } from "../../lib/haptics";

// ─── Backdrop tuning ─────────────────────────────────────────────────────────
// The radial overlay must fully obscure the screen behind it so large CTAs
// (e.g. the signed-out "Sign In" pill) don't bleed through. Raised from the
// initial intensity=30 / scrim 0.55 after a real-world test showed the pill
// was clearly readable through the backdrop.

/** BlurView intensity on native (iOS/Android). iOS caps at 100. */
const BACKDROP_BLUR_INTENSITY = 70;

/** Solid black scrim opacity layered on top of the blur. */
const BACKDROP_SCRIM_OPACITY = 0.82;

/** CSS blur radius used for the web fallback GlassView. */
const WEB_BACKDROP_BLUR_PX = 70;

/** Platform-conditional glass view: BlurView on native, CSS backdrop-filter on web */
const GlassView = Platform.OS === "web"
  ? ({ children, style, ...props }: any) => (
      <View
        style={[
          style,
          {
            backgroundColor: `rgba(0, 0, 0, ${BACKDROP_SCRIM_OPACITY})`,
            backdropFilter: `blur(${WEB_BACKDROP_BLUR_PX}px)`,
          } as any,
        ]}
        {...props}
      >
        {children}
      </View>
    )
  : BlurView;

// ─── Types ───────────────────────────────────────────────────────────────────

export interface RadialMenuItem {
  label: string;
  icon: keyof typeof Ionicons.glyphMap;
  onPress: () => void;
  destructive?: boolean;
  /** Optional small caption below the main label. */
  sublabel?: string;
}

interface RadialMenuProps {
  visible: boolean;
  onClose: () => void;
  items: RadialMenuItem[];
  /** Session accent color for the ring glow */
  accentColor?: string;
}

// ─── Layout Constants ────────────────────────────────────────────────────────

/** Radius of the invisible circle along which items are placed. */
const ORBIT_RADIUS = 150;

/** Size of the decorative center ring (hollow, glowing). */
const RING_SIZE = 108;

/** Thick violet stroke width on the main ring. */
const RING_STROKE_WIDTH = 6;

/** Inset (negative = outer) for the soft-bloom halo around the main ring. */
const RING_HALO_INSET = -14;

/** Soft-bloom outer halo shadow radius. */
const RING_HALO_SHADOW_RADIUS = 40;

/** Bright on-stroke shadow radius for the ring itself. */
const RING_MAIN_SHADOW_RADIUS = 20;

/** Width of the inner soft rim painted just inside the main ring. */
const RING_INNER_INSET = 6;

/** Size of each item's icon circle. */
const ICON_CIRCLE_SIZE = 76;

/** Diameter of the Ionicons glyph rendered inside each item. */
const ICON_SIZE = 28;

/** Border width of the glassy item circle. */
const ICON_CIRCLE_BORDER_WIDTH = 2.5;

/** Outer halo glow radius around each item. */
const ICON_CIRCLE_SHADOW_RADIUS = 20;

/** Outer halo glow opacity around each item. */
const ICON_CIRCLE_SHADOW_OPACITY = 0.9;

/** Width reserved per item — label + sublabel render under icon, centered. */
const ITEM_WIDTH = 110;

/** Approx. full visual height of an item (icon + gap + label + sublabel). */
const ITEM_VERTICAL_BLOCK = 120;

/** Maximum number of radial items supported. */
const MAX_ITEMS = 4;

/** Stagger delay between items (ms). */
const STAGGER_MS = 45;

/** Default fallback accent when the caller hasn't provided one. */
const FALLBACK_ACCENT = "#7C5CFF";

/** Destructive red used across the item (halo, icon, text). */
const DESTRUCTIVE_ACCENT = THEME.colors.destructive;

/** Default sublabel applied to destructive items when none is explicit. */
const DEFAULT_DESTRUCTIVE_SUBLABEL = undefined;

/** Hex alpha suffix (~19%) for the dashed orbital ring stroke. */
const ORBIT_RING_ALPHA = "30";

/** Hex alpha suffix (~80%) used by the item border (slightly translucent). */
const ITEM_BORDER_ALPHA = "CC";

/** Hex alpha suffix (~27%) for the soft halo ring around each item. */
const ITEM_HALO_ALPHA = "44";

/** Hex alpha suffix (~53%) for the inner rim of the main center ring. */
const RING_INNER_ALPHA = "88";

/** Hex alpha suffix (~50%) for the destructive sublabel tint. */
const DESTRUCTIVE_SUBLABEL_ALPHA = "CC";

/** Z-index ordering between the orbital ring and the item containers. */
const Z_ORBIT_RING = 5;
const Z_ITEM = 10;

// ─── Angle distribution ──────────────────────────────────────────────────────
// Items always anchor at the four corner angles of the orbital ring so the
// glowing center ring composes BELOW (or in the middle of) the items. The
// horizontal-axis layout (180°/0°) was rejected — it puts the ring beside the
// items rather than below.
//
// Angle 0 = right, 90 = down (screen Y inverted).
//   TL = -135°, TR = -45°, BL = 135°, BR = 45°
function anglesForCount(count: number): readonly number[] {
  "worklet";
  if (count <= 1) return [-135]; // single item — top-left corner
  if (count === 2) return [-135, -45]; // crown above the ring
  if (count === 3) return [-135, -45, 45]; // top two + bottom-right
  return [-135, -45, 135, 45]; // four corners
}

function degToRad(deg: number): number {
  "worklet";
  return (deg * Math.PI) / 180;
}

// ─── Spring configs ──────────────────────────────────────────────────────────

const OPEN_SPRING = { damping: 14, stiffness: 160, mass: 0.8 };
const CLOSE_SPRING = { damping: 20, stiffness: 300 };
const PRESS_SPRING = THEME.animation.press;

// ─── Component ───────────────────────────────────────────────────────────────

export function RadialMenu({
  visible,
  onClose,
  items,
  accentColor,
}: RadialMenuProps) {
  const { width: screenW, height: screenH } = useWindowDimensions();

  // Resolve accent once for ring + spoke tinting.
  const accent = accentColor ?? FALLBACK_ACCENT;

  // Geometric screen center. The empty space at the top (below status bar)
  // is intentional — it lets the blurred avatar peek through under the items.
  const cx = screenW / 2;
  const cy = screenH / 2;

  // Backdrop opacity (separate so we can fade faster)
  const backdropOpacity = useSharedValue(0);
  // Ring scale
  const ringScale = useSharedValue(0.3);
  const ringOpacity = useSharedValue(0);

  // Per-item progress values — always allocate MAX_ITEMS to keep hook count stable
  const ip0 = useSharedValue(0);
  const ip1 = useSharedValue(0);
  const ip2 = useSharedValue(0);
  const ip3 = useSharedValue(0);
  const itemProgress = useMemo(() => [ip0, ip1, ip2, ip3], [ip0, ip1, ip2, ip3]);

  // ── Open animation ──

  const animateOpen = useCallback(() => {
    // Backdrop
    backdropOpacity.value = withTiming(1, { duration: 250 });
    // Ring
    ringScale.value = withSpring(1, OPEN_SPRING);
    ringOpacity.value = withTiming(1, { duration: 200 });
    // Items stagger outward
    const count = Math.min(items.length, MAX_ITEMS);
    for (let i = 0; i < count; i++) {
      itemProgress[i]!.value = withDelay(
        i * STAGGER_MS,
        withSpring(1, OPEN_SPRING),
      );
    }
  }, [items.length, backdropOpacity, ringScale, ringOpacity, itemProgress]);

  // ── Close animation ──

  const animateClose = useCallback(() => {
    // Items collapse inward (reverse stagger)
    const count = Math.min(items.length, MAX_ITEMS);
    for (let i = count - 1; i >= 0; i--) {
      itemProgress[i]!.value = withDelay(
        (count - 1 - i) * 30,
        withSpring(0, CLOSE_SPRING),
      );
    }
    // Ring
    ringScale.value = withDelay(60, withSpring(0.3, CLOSE_SPRING));
    ringOpacity.value = withDelay(60, withTiming(0, { duration: 180 }));
    // Backdrop — slightly delayed so items visually lead
    backdropOpacity.value = withDelay(
      80,
      withTiming(0, { duration: 200, easing: Easing.out(Easing.quad) }),
    );
  }, [items.length, backdropOpacity, ringScale, ringOpacity, itemProgress]);

  // ── Trigger open when visible changes ──

  React.useEffect(() => {
    if (!visible) return;

    // Reset before opening
    ringScale.value = 0.3;
    ringOpacity.value = 0;
    backdropOpacity.value = 0;
    for (const ip of itemProgress) ip.value = 0;

    // Small delay to let Modal mount
    const t = setTimeout(() => {
      animateOpen();
      hapticMedium();
    }, 30);
    return () => clearTimeout(t);
  }, [visible]); // eslint-disable-line react-hooks/exhaustive-deps

  const handleBackdropPress = useCallback(() => {
    animateClose();
    hapticLight();
    // Wait for animation to finish before unmounting
    setTimeout(() => onClose(), 280);
  }, [onClose, animateClose]);

  const handleItemPress = useCallback(
    (item: RadialMenuItem) => {
      hapticLight();
      animateClose();
      setTimeout(() => {
        onClose();
        item.onPress();
      }, 280);
    },
    [onClose, animateClose],
  );

  // ── Animated styles ──

  const backdropStyle = useAnimatedStyle(() => ({
    opacity: backdropOpacity.value,
  }));

  const ringAnimatedStyle = useAnimatedStyle(() => ({
    opacity: ringOpacity.value,
    transform: [{ scale: ringScale.value }],
  }));

  // The dashed orbital ring fades in alongside the center ring but skips the
  // scale "pop" — it should look like a stable backdrop guide.
  const orbitRingAnimatedStyle = useAnimatedStyle(() => ({
    opacity: ringOpacity.value * 0.9,
  }));

  if (!visible) return null;

  const ringHaloSize = RING_SIZE - RING_HALO_INSET * 2;
  const orbitDiameter = ORBIT_RADIUS * 2;

  return (
    <Modal
      visible={visible}
      transparent
      animationType="none"
      onRequestClose={handleBackdropPress}
      statusBarTranslucent
    >
      {/* Backdrop */}
      <Pressable
        style={StyleSheet.absoluteFill}
        onPress={handleBackdropPress}
        accessibilityLabel="Close menu"
        accessibilityRole="button"
      >
        <Animated.View style={[styles.backdrop, backdropStyle]}>
          <GlassView
            intensity={BACKDROP_BLUR_INTENSITY}
            tint="dark"
            style={StyleSheet.absoluteFill}
          />
          <View style={styles.backdropScrim} />
        </Animated.View>
      </Pressable>

      {/* Decorative dashed orbital ring — passes through every item center.
          Sits between backdrop and items so it reads as a faint guide. */}
      <Animated.View
        pointerEvents="none"
        style={[
          styles.orbitRing,
          {
            left: cx - ORBIT_RADIUS,
            top: cy - ORBIT_RADIUS,
            width: orbitDiameter,
            height: orbitDiameter,
            borderRadius: ORBIT_RADIUS,
            borderColor: `${accent}${ORBIT_RING_ALPHA}`,
          },
          orbitRingAnimatedStyle,
        ]}
      />

      {/* Center ring — hollow, bright violet glow with soft halo */}
      <Animated.View
        style={[
          styles.ringWrapper,
          {
            left: cx - ringHaloSize / 2,
            top: cy - ringHaloSize / 2,
            width: ringHaloSize,
            height: ringHaloSize,
          },
          ringAnimatedStyle,
        ]}
        pointerEvents="none"
      >
        {/* Outer halo — wide soft glow */}
        <View
          style={[
            styles.ringHalo,
            {
              width: ringHaloSize,
              height: ringHaloSize,
              borderRadius: ringHaloSize / 2,
              borderColor: `${accent}30`,
              shadowColor: accent,
            },
          ]}
        />
        {/* Main bright ring */}
        <View
          style={[
            styles.ringMain,
            {
              borderColor: accent,
              shadowColor: accent,
            },
          ]}
        >
          {/* Inner rim lift — softer violet inner stroke */}
          <View
            style={[
              styles.ringInner,
              { borderColor: `${accent}${RING_INNER_ALPHA}` },
            ]}
          />
        </View>
      </Animated.View>

      {/* Menu items */}
      {items.slice(0, MAX_ITEMS).map((item, index) => {
        const angles = anglesForCount(Math.min(items.length, MAX_ITEMS));
        const angleDeg = angles[index] ?? -135;
        const angleRad = degToRad(angleDeg);
        const targetX = Math.cos(angleRad) * ORBIT_RADIUS;
        const targetY = Math.sin(angleRad) * ORBIT_RADIUS;

        return (
          <RadialMenuItemView
            key={item.label}
            item={item}
            centerX={cx}
            centerY={cy}
            targetX={targetX}
            targetY={targetY}
            progress={itemProgress[index]!}
            onPress={handleItemPress}
            accentColor={accent}
          />
        );
      })}
    </Modal>
  );
}

// ─── Individual Item ─────────────────────────────────────────────────────────

interface RadialMenuItemViewProps {
  item: RadialMenuItem;
  centerX: number;
  centerY: number;
  targetX: number;
  targetY: number;
  progress: SharedValue<number>;
  onPress: (item: RadialMenuItem) => void;
  accentColor: string;
}

function RadialMenuItemView({
  item,
  centerX,
  centerY,
  targetX,
  targetY,
  progress,
  onPress,
  accentColor,
}: RadialMenuItemViewProps) {
  const pressScale = useSharedValue(1);

  // Effective tint for this item — destructive uses red, otherwise the session accent.
  const tint = item.destructive ? DESTRUCTIVE_ACCENT : accentColor;

  // Resolved sublabel: explicit > destructive default > none.
  const sublabel =
    item.sublabel ??
    (item.destructive ? DEFAULT_DESTRUCTIVE_SUBLABEL : undefined);

  const containerStyle = useAnimatedStyle(() => {
    const t = progress.value;
    return {
      opacity: t,
      transform: [
        { translateX: targetX * t },
        { translateY: targetY * t },
        { scale: 0.3 + t * 0.7 },
      ],
    };
  });

  // Motion-trail "ghost" — a translucent, half-scale clone of the icon circle
  // that lags behind the real item along the animation vector. Visible only
  // mid-flight: it fades in around t≈0.15 and fades out by the time the item
  // has nearly landed.
  const ghostStyle = useAnimatedStyle(() => {
    const t = progress.value;
    const lag = Math.max(0, t - 0.18);
    // Smear strength: peaks mid-flight, drops to 0 once the item has landed.
    const fade = Math.max(0, Math.min(1, t * 1.4)) * Math.max(0, 1 - t * 1.1);
    return {
      opacity: fade * 0.4,
      transform: [
        { translateX: targetX * lag },
        { translateY: targetY * lag },
        { scale: 0.3 + lag * 0.5 },
      ],
    };
  });

  const pressStyle = useAnimatedStyle(() => ({
    transform: [{ scale: pressScale.value }],
  }));

  const handlePressIn = useCallback(() => {
    pressScale.value = withSpring(0.9, PRESS_SPRING);
  }, [pressScale]);

  const handlePressOut = useCallback(() => {
    pressScale.value = withSpring(1, PRESS_SPRING);
  }, [pressScale]);

  const iconColor = tint;
  const iconBg = item.destructive
    ? "rgba(239, 68, 68, 0.10)"
    : "rgba(20, 16, 36, 0.72)";
  const iconBorder = `${tint}${ITEM_BORDER_ALPHA}`;

  // Anchor the ICON CENTER on the orbit point (not the whole block). Labels
  // render below and sit *outside* the dashed orbital ring — so the ring
  // visibly crosses each item through the center of its icon circle.
  const containerTop = centerY - ICON_CIRCLE_SIZE / 2;
  const containerLeft = centerX - ITEM_WIDTH / 2;

  return (
    <>
      {/* Ghost / motion-trail clone — sibling so its translate values can lag
          independently of the real item's containerStyle. Sits below the item
          and is purely decorative. */}
      <Animated.View
        pointerEvents="none"
        style={[
          styles.ghostContainer,
          {
            left: containerLeft,
            top: containerTop,
            width: ITEM_WIDTH,
            height: ITEM_VERTICAL_BLOCK,
          },
          ghostStyle,
        ]}
      >
        <View style={styles.iconWrap}>
          <View
            style={[
              styles.iconCircle,
              styles.ghostCircle,
              {
                backgroundColor: iconBg,
                borderColor: `${tint}${ITEM_HALO_ALPHA}`,
                shadowColor: tint,
              },
            ]}
          >
            <Ionicons name={item.icon} size={ICON_SIZE} color={`${tint}99`} />
          </View>
        </View>
      </Animated.View>

      <Animated.View
        style={[
          styles.itemContainer,
          {
            left: containerLeft,
            top: containerTop,
            width: ITEM_WIDTH,
            height: ITEM_VERTICAL_BLOCK,
          },
          containerStyle,
        ]}
        pointerEvents="box-none"
      >
        <Animated.View style={[styles.itemInner, pressStyle]}>
          <Pressable
            onPress={() => onPress(item)}
            onPressIn={handlePressIn}
            onPressOut={handlePressOut}
            style={styles.itemPressable}
            accessibilityLabel={item.label}
            accessibilityRole="menuitem"
          >
            <View style={styles.iconWrap}>
              {/* Icon circle with strong colored halo via shadow */}
              <View
                style={[
                  styles.iconCircle,
                  {
                    backgroundColor: iconBg,
                    borderColor: iconBorder,
                    shadowColor: tint,
                  },
                ]}
              >
                <Ionicons name={item.icon} size={ICON_SIZE} color={iconColor} />
              </View>
            </View>

            {/* Label + optional sublabel */}
            <View style={styles.labelStack}>
              <Text
                style={[
                  styles.itemLabel,
                  item.destructive && {
                    color: DESTRUCTIVE_ACCENT,
                    textShadowColor: `${DESTRUCTIVE_ACCENT}80`,
                  },
                ]}
                numberOfLines={1}
              >
                {item.label}
              </Text>
              {sublabel ? (
                <Text
                  style={[
                    styles.itemSublabel,
                    item.destructive && {
                      color: `${DESTRUCTIVE_ACCENT}${DESTRUCTIVE_SUBLABEL_ALPHA}`,
                    },
                  ]}
                  numberOfLines={1}
                >
                  {sublabel}
                </Text>
              ) : null}
            </View>
          </Pressable>
        </Animated.View>
      </Animated.View>
    </>
  );
}

// ─── Styles ──────────────────────────────────────────────────────────────────

const styles = StyleSheet.create({
  backdrop: {
    ...StyleSheet.absoluteFillObject,
  },
  backdropScrim: {
    ...StyleSheet.absoluteFillObject,
    backgroundColor: `rgba(0, 0, 0, ${BACKDROP_SCRIM_OPACITY})`,
  },

  // ── Dashed orbital ring (passes through every item center) ──
  orbitRing: {
    position: "absolute",
    borderWidth: 1,
    borderStyle: "dashed",
    backgroundColor: "transparent",
    zIndex: Z_ORBIT_RING,
  },

  // ── Center ring ──
  ringWrapper: {
    position: "absolute",
    alignItems: "center",
    justifyContent: "center",
    zIndex: Z_ORBIT_RING,
  },
  ringHalo: {
    position: "absolute",
    borderWidth: 1.5,
    backgroundColor: "transparent",
    // Wide soft bloom — accentColor shadow set inline.
    shadowOpacity: 0.7,
    shadowRadius: RING_HALO_SHADOW_RADIUS,
    shadowOffset: { width: 0, height: 0 },
    elevation: 14,
  },
  ringMain: {
    width: RING_SIZE,
    height: RING_SIZE,
    borderRadius: RING_SIZE / 2,
    borderWidth: RING_STROKE_WIDTH,
    backgroundColor: "transparent",
    alignItems: "center",
    justifyContent: "center",
    // Tight bright glow directly on the stroke.
    shadowOpacity: 0.95,
    shadowRadius: RING_MAIN_SHADOW_RADIUS,
    shadowOffset: { width: 0, height: 0 },
    elevation: 10,
  },
  ringInner: {
    width: RING_SIZE - RING_STROKE_WIDTH * 2 - RING_INNER_INSET * 2,
    height: RING_SIZE - RING_STROKE_WIDTH * 2 - RING_INNER_INSET * 2,
    borderRadius:
      (RING_SIZE - RING_STROKE_WIDTH * 2 - RING_INNER_INSET * 2) / 2,
    borderWidth: 1,
    backgroundColor: "transparent",
  },

  // ── Item container — absolutely positioned ──
  itemContainer: {
    position: "absolute",
    zIndex: Z_ITEM,
    overflow: "visible",
    alignItems: "center",
    justifyContent: "flex-start",
  },
  ghostContainer: {
    position: "absolute",
    zIndex: Z_ORBIT_RING,
    overflow: "visible",
    alignItems: "center",
    justifyContent: "flex-start",
  },
  ghostCircle: {
    // Slightly suppressed halo so the trail reads as smear, not as a ghost item.
    shadowOpacity: 0.55,
  },
  itemInner: {
    alignItems: "center",
  },
  itemPressable: {
    alignItems: "center",
    gap: THEME.spacing.sm,
  },

  // ── Icon ──
  iconWrap: {
    width: ICON_CIRCLE_SIZE,
    height: ICON_CIRCLE_SIZE,
    alignItems: "center",
    justifyContent: "center",
  },
  iconCircle: {
    width: ICON_CIRCLE_SIZE,
    height: ICON_CIRCLE_SIZE,
    borderRadius: ICON_CIRCLE_SIZE / 2,
    borderWidth: ICON_CIRCLE_BORDER_WIDTH,
    alignItems: "center",
    justifyContent: "center",
    shadowOpacity: ICON_CIRCLE_SHADOW_OPACITY,
    shadowRadius: ICON_CIRCLE_SHADOW_RADIUS,
    shadowOffset: { width: 0, height: 0 },
    elevation: 8,
  },

  // ── Labels ──
  labelStack: {
    alignItems: "center",
  },
  // Labels sit inside the glow design language — softer weight, subdued
  // color, generous tracking. Bright white ("textPrimary") reads as foreign
  // UI chrome; we tint toward the muted/secondary scale so the text feels
  // like part of the menu aesthetic rather than bolted on top of it.
  itemLabel: {
    fontFamily: FONTS.bodyMedium,
    fontSize: 12,
    lineHeight: 16,
    color: THEME.colors.textSecondary,
    letterSpacing: 0.6,
    textAlign: "center",
    textTransform: "uppercase",
  },
  itemSublabel: {
    fontFamily: FONTS.body,
    fontSize: 10,
    lineHeight: 13,
    marginTop: 3,
    color: THEME.colors.textMuted,
    letterSpacing: 0.3,
    textAlign: "center",
    opacity: 0.75,
  },
});
