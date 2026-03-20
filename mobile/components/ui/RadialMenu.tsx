/**
 * RadialMenu — full-screen circular menu overlay.
 *
 * Items explode outward from the center of the screen in a spring animation,
 * each positioned at a fixed quadrant (top-left, top-right, bottom-left,
 * bottom-right). A frosted-glass ring provides a visual anchor.
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

// ─── Types ───────────────────────────────────────────────────────────────────

export interface RadialMenuItem {
  label: string;
  icon: string;
  onPress: () => void;
  destructive?: boolean;
}

interface RadialMenuProps {
  visible: boolean;
  onClose: () => void;
  items: RadialMenuItem[];
  /** Session accent color for the ring glow */
  accentColor?: string;
}

// ─── Layout Constants ────────────────────────────────────────────────────────

/** Radius of the invisible circle along which items are placed */
const ORBIT_RADIUS = 120;

/** Size of the decorative center ring */
const RING_SIZE = 64;

/** Size of each item's icon circle */
const ICON_CIRCLE_SIZE = 52;

/** Maximum number of radial items supported */
const MAX_ITEMS = 4;

/** Stagger delay between items (ms) */
const STAGGER_MS = 45;

// ─── Quadrant angles ─────────────────────────────────────────────────────────
// Items are placed at 45-degree diagonals from center.
// Angle 0 = right, 90 = down (standard math convention, Y-inverted for screen).
//
//   Top-Left (-135 deg)    Top-Right (-45 deg)
//              \              /
//               \   [ring]  /
//              /              \
//   Bot-Left (135 deg)     Bot-Right (45 deg)

const QUADRANT_ANGLES_DEG: readonly number[] = [-135, -45, 135, 45]; // TL, TR, BL, BR

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

  // Center of the screen
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

  if (!visible) return null;

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
          <BlurView intensity={30} tint="dark" style={StyleSheet.absoluteFill} />
          <View style={styles.backdropScrim} />
        </Animated.View>
      </Pressable>

      {/* Center ring */}
      <Animated.View
        style={[
          styles.ring,
          {
            left: cx - RING_SIZE / 2,
            top: cy - RING_SIZE / 2,
            borderColor: accentColor
              ? `${accentColor}33`
              : THEME.colors.glassBorder,
          },
          accentColor
            ? {
                shadowColor: accentColor,
                shadowOpacity: 0.25,
                shadowRadius: 20,
                shadowOffset: { width: 0, height: 0 },
                elevation: 6,
              }
            : undefined,
          ringAnimatedStyle,
        ]}
        pointerEvents="none"
      >
        <View
          style={[
            styles.ringInner,
            accentColor ? { borderColor: `${accentColor}22` } : undefined,
          ]}
        />
      </Animated.View>

      {/* Menu items */}
      {items.slice(0, MAX_ITEMS).map((item, index) => {
        const angleDeg = QUADRANT_ANGLES_DEG[index] ?? -135;
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
            accentColor={accentColor}
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
  accentColor?: string;
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

  // Determine horizontal alignment based on quadrant
  const isRight = targetX > 0;

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

  const pressStyle = useAnimatedStyle(() => ({
    transform: [{ scale: pressScale.value }],
  }));

  const handlePressIn = useCallback(() => {
    pressScale.value = withSpring(0.9, PRESS_SPRING);
  }, [pressScale]);

  const handlePressOut = useCallback(() => {
    pressScale.value = withSpring(1, PRESS_SPRING);
  }, [pressScale]);

  // Icon color
  const iconColor = item.destructive
    ? THEME.colors.destructive
    : THEME.colors.textPrimary;

  // Icon bg
  const iconBg = item.destructive
    ? "rgba(239, 68, 68, 0.12)"
    : accentColor
      ? `${accentColor}18`
      : "rgba(255, 255, 255, 0.08)";

  // Icon border
  const iconBorder = item.destructive
    ? "rgba(239, 68, 68, 0.20)"
    : accentColor
      ? `${accentColor}25`
      : THEME.colors.glassBorder;

  return (
    <Animated.View
      style={[
        styles.itemContainer,
        {
          left: centerX - ICON_CIRCLE_SIZE / 2,
          top: centerY - ICON_CIRCLE_SIZE / 2,
        },
        containerStyle,
      ]}
    >
      <Animated.View style={pressStyle}>
        <Pressable
          onPress={() => onPress(item)}
          onPressIn={handlePressIn}
          onPressOut={handlePressOut}
          style={[
            styles.itemPressable,
            isRight ? styles.itemAlignRight : styles.itemAlignLeft,
          ]}
          accessibilityLabel={item.label}
          accessibilityRole="menuitem"
        >
          {/* Label — positioned outside the icon on the outer side */}
          {!isRight && (
            <Text
              style={[
                styles.itemLabel,
                styles.itemLabelLeft,
                item.destructive && styles.itemLabelDestructive,
              ]}
              numberOfLines={1}
            >
              {item.label}
            </Text>
          )}

          {/* Icon circle */}
          <View
            style={[
              styles.iconCircle,
              {
                backgroundColor: iconBg,
                borderColor: iconBorder,
              },
              item.destructive
                ? {
                    shadowColor: THEME.colors.destructive,
                    shadowOpacity: 0.3,
                    shadowRadius: 8,
                    shadowOffset: { width: 0, height: 0 },
                  }
                : undefined,
            ]}
          >
            <Ionicons name={item.icon as any} size={22} color={iconColor} />
          </View>

          {/* Label — right side */}
          {isRight && (
            <Text
              style={[
                styles.itemLabel,
                styles.itemLabelRight,
                item.destructive && styles.itemLabelDestructive,
              ]}
              numberOfLines={1}
            >
              {item.label}
            </Text>
          )}
        </Pressable>
      </Animated.View>
    </Animated.View>
  );
}

// ─── Styles ──────────────────────────────────────────────────────────────────

const styles = StyleSheet.create({
  backdrop: {
    ...StyleSheet.absoluteFillObject,
  },
  backdropScrim: {
    ...StyleSheet.absoluteFillObject,
    backgroundColor: "rgba(0, 0, 0, 0.55)",
  },

  // ── Center ring ──
  ring: {
    position: "absolute",
    width: RING_SIZE,
    height: RING_SIZE,
    borderRadius: RING_SIZE / 2,
    borderWidth: 1.5,
    backgroundColor: THEME.colors.glass,
    alignItems: "center",
    justifyContent: "center",
  },
  ringInner: {
    width: RING_SIZE - 16,
    height: RING_SIZE - 16,
    borderRadius: (RING_SIZE - 16) / 2,
    borderWidth: 1,
    borderColor: THEME.colors.glassBorder,
    backgroundColor: "rgba(255, 255, 255, 0.03)",
  },

  // ── Item container — absolutely positioned at center, animated outward ──
  itemContainer: {
    position: "absolute",
    width: ICON_CIRCLE_SIZE,
    height: ICON_CIRCLE_SIZE,
    zIndex: 10,
    // overflow visible so label can extend
    overflow: "visible",
  },

  itemPressable: {
    flexDirection: "row",
    alignItems: "center",
    // Allow label to extend beyond the icon circle
    overflow: "visible",
  },
  itemAlignLeft: {
    flexDirection: "row-reverse",
  },
  itemAlignRight: {
    flexDirection: "row",
  },

  // ── Icon circle ──
  iconCircle: {
    width: ICON_CIRCLE_SIZE,
    height: ICON_CIRCLE_SIZE,
    borderRadius: ICON_CIRCLE_SIZE / 2,
    borderWidth: 1,
    alignItems: "center",
    justifyContent: "center",
    ...THEME.shadow.glass,
  },

  // ── Labels ──
  itemLabel: {
    fontFamily: FONTS.bodySemiBold,
    fontSize: 13,
    color: THEME.colors.textPrimary,
    letterSpacing: 0.3,
  },
  itemLabelLeft: {
    marginRight: THEME.spacing.md,
    textAlign: "right",
  },
  itemLabelRight: {
    marginLeft: THEME.spacing.md,
    textAlign: "left",
  },
  itemLabelDestructive: {
    color: THEME.colors.destructive,
  },
});
