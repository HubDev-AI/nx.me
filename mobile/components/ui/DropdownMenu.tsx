import React, { useEffect, useRef } from "react";
import {
  View,
  Text,
  Pressable,
  StyleSheet,
  Platform,
  Animated as RNAnimated,
  Modal,
} from "react-native";
import Animated, {
  useSharedValue,
  useAnimatedStyle,
  withSpring,
} from "react-native-reanimated";
import { BlurView } from "expo-blur";
import { Ionicons } from "@expo/vector-icons";

import { THEME } from "../../constants/theme";
import { FONTS } from "../../hooks/useFonts";

/** Platform-conditional glass view: BlurView on native, CSS backdrop-filter on web */
const GlassView = Platform.OS === "web"
  ? ({ children, style, ...props }: any) => (
      <View style={[style, { backgroundColor: "rgba(17, 17, 17, 0.85)", backdropFilter: "blur(20px)" } as any]} {...props}>
        {children}
      </View>
    )
  : BlurView;

export interface DropdownMenuItem {
  label: string;
  icon: keyof typeof Ionicons.glyphMap;
  onPress: () => void;
  destructive?: boolean;
}

interface DropdownMenuProps {
  visible: boolean;
  onClose: () => void;
  items: DropdownMenuItem[];
  anchorPosition: { top: number; right: number };
}

/**
 * Cross-platform dropdown menu that works on iOS, Android, and Web.
 *
 * Renders a full-screen transparent backdrop (tap to dismiss) with a
 * glass-style card of menu items positioned at the given anchor coordinates.
 * Uses RN core Animated for a quick opacity + scale entrance.
 */
export function DropdownMenu({
  visible,
  onClose,
  items,
  anchorPosition,
}: DropdownMenuProps) {
  const opacity = useRef(new RNAnimated.Value(0)).current;
  const scale = useRef(new RNAnimated.Value(0.92)).current;

  useEffect(() => {
    if (visible) {
      RNAnimated.parallel([
        RNAnimated.timing(opacity, {
          toValue: 1,
          duration: 180,
          useNativeDriver: true,
        }),
        RNAnimated.spring(scale, {
          toValue: 1,
          damping: THEME.animation.press.damping,
          stiffness: THEME.animation.press.stiffness,
          useNativeDriver: true,
        }),
      ]).start();
    } else {
      opacity.setValue(0);
      scale.setValue(0.92);
    }
  }, [visible, opacity, scale]);

  if (!visible) return null;

  const handleItemPress = (item: DropdownMenuItem) => {
    onClose();
    // Small delay so the menu visually closes before the action fires
    // (avoids flash on navigation or modal open)
    setTimeout(() => {
      item.onPress();
    }, 50);
  };

  // Find the index of the first destructive item to insert a divider above it
  const firstDestructiveIndex = items.findIndex((item) => item.destructive);

  return (
    <Modal
      visible={visible}
      transparent
      animationType="none"
      onRequestClose={onClose}
      statusBarTranslucent
    >
      {/* Backdrop — tapping anywhere outside the card closes the menu */}
      <Pressable
        style={styles.backdrop}
        onPress={onClose}
        accessibilityLabel="Close menu"
        accessibilityRole="button"
      >
        {/* Card — stop propagation so tapping the card doesn't close */}
        <RNAnimated.View
          style={[
            styles.card,
            {
              top: anchorPosition.top,
              right: anchorPosition.right,
              opacity,
              transform: [{ scale }],
            },
          ]}
        >
          <GlassView intensity={40} tint="dark" style={styles.blurFill}>
            <View style={styles.cardInner}>
              <Pressable
                /* Prevent touches inside the card from bubbling to the backdrop */
                onPress={(e) => e.stopPropagation?.()}
              >
                {items.map((item, index) => (
                  <React.Fragment key={item.label}>
                    {/* Destructive divider — thicker, more visible separator above destructive items */}
                    {index === firstDestructiveIndex && index > 0 && (
                      <View style={styles.destructiveDivider} />
                    )}
                    <MenuItemRow
                      item={item}
                      onPress={handleItemPress}
                    />
                  </React.Fragment>
                ))}
              </Pressable>
            </View>
          </GlassView>
        </RNAnimated.View>
      </Pressable>
    </Modal>
  );
}

/** Individual menu item with spring press scale */
function MenuItemRow({
  item,
  onPress,
}: {
  item: DropdownMenuItem;
  onPress: (item: DropdownMenuItem) => void;
}) {
  const itemScale = useSharedValue(1);
  const itemPressStyle = useAnimatedStyle(() => ({
    transform: [{ scale: itemScale.value }],
  }));

  return (
    <Animated.View style={itemPressStyle}>
      <Pressable
        onPress={() => onPress(item)}
        onPressIn={() => { itemScale.value = withSpring(0.97, THEME.animation.press); }}
        onPressOut={() => { itemScale.value = withSpring(1, THEME.animation.press); }}
        style={({ pressed }) => [
          styles.item,
          pressed && styles.itemPressed,
        ]}
        accessibilityLabel={item.label}
        accessibilityRole="menuitem"
      >
        <View style={[
          styles.iconWrapper,
          item.destructive && styles.iconWrapperDestructive,
        ]}>
          <Ionicons
            name={item.icon}
            size={18}
            color={item.destructive ? THEME.colors.destructive : THEME.colors.textPrimary}
          />
        </View>
        <Text
          style={[
            styles.itemLabel,
            item.destructive && styles.itemLabelDestructive,
          ]}
        >
          {item.label}
        </Text>
      </Pressable>
    </Animated.View>
  );
}

const styles = StyleSheet.create({
  backdrop: {
    ...StyleSheet.absoluteFillObject,
    backgroundColor: "rgba(0, 0, 0, 0.25)",
  },
  card: {
    position: "absolute",
    minWidth: 200,
    borderRadius: THEME.radius.xl,
    borderWidth: 1,
    borderColor: THEME.colors.glassBorder,
    overflow: "hidden",
    ...THEME.shadow.card,
  },
  blurFill: {
    overflow: "hidden",
    borderRadius: THEME.radius.xl,
  },
  cardInner: {
    backgroundColor: THEME.colors.glass,
    paddingVertical: THEME.spacing.xs,
  },
  destructiveDivider: {
    height: 1,
    backgroundColor: THEME.colors.glassBorder,
    marginHorizontal: THEME.spacing.xl,
    marginVertical: THEME.spacing.xs,
  },
  item: {
    flexDirection: "row",
    alignItems: "center",
    gap: THEME.spacing.md,
    paddingVertical: 14,
    paddingHorizontal: 20,
  },
  itemPressed: {
    backgroundColor: "rgba(255, 255, 255, 0.06)",
  },
  iconWrapper: {
    width: 28,
    height: 28,
    borderRadius: 8,
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: "rgba(255, 255, 255, 0.05)",
  },
  iconWrapperDestructive: {
    backgroundColor: "rgba(239, 68, 68, 0.10)",
  },
  itemLabel: {
    fontFamily: FONTS.bodyMedium,
    fontSize: 15,
    color: THEME.colors.textPrimary,
  },
  itemLabelDestructive: {
    color: THEME.colors.destructive,
  },
});
