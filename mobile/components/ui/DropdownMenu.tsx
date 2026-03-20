import React, { useEffect, useRef } from "react";
import {
  View,
  Text,
  Pressable,
  StyleSheet,
  Animated as RNAnimated,
  Modal,
} from "react-native";
import { Ionicons } from "@expo/vector-icons";

import { FONTS } from "../../hooks/useFonts";

export interface DropdownMenuItem {
  label: string;
  icon: string;
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
 * small card of menu items positioned at the given anchor coordinates.
 * Uses RN core Animated for a quick opacity fade — no platform-specific APIs.
 */
export function DropdownMenu({
  visible,
  onClose,
  items,
  anchorPosition,
}: DropdownMenuProps) {
  const opacity = useRef(new RNAnimated.Value(0)).current;

  useEffect(() => {
    if (visible) {
      RNAnimated.timing(opacity, {
        toValue: 1,
        duration: 150,
        useNativeDriver: true,
      }).start();
    } else {
      opacity.setValue(0);
    }
  }, [visible, opacity]);

  if (!visible) return null;

  const handleItemPress = (item: DropdownMenuItem) => {
    onClose();
    // Small delay so the menu visually closes before the action fires
    // (avoids flash on navigation or modal open)
    setTimeout(() => {
      item.onPress();
    }, 50);
  };

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
            },
          ]}
        >
          <Pressable
            /* Prevent touches inside the card from bubbling to the backdrop */
            onPress={(e) => e.stopPropagation?.()}
          >
            {items.map((item, index) => (
              <React.Fragment key={item.label}>
                {index > 0 && <View style={styles.divider} />}
                <Pressable
                  onPress={() => handleItemPress(item)}
                  style={({ pressed }) => [
                    styles.item,
                    pressed && styles.itemPressed,
                  ]}
                  accessibilityLabel={item.label}
                  accessibilityRole="menuitem"
                >
                  <Ionicons
                    name={item.icon as any}
                    size={18}
                    color={item.destructive ? "#ef4444" : "#e8e8e8"}
                  />
                  <Text
                    style={[
                      styles.itemLabel,
                      item.destructive && styles.itemLabelDestructive,
                    ]}
                  >
                    {item.label}
                  </Text>
                </Pressable>
              </React.Fragment>
            ))}
          </Pressable>
        </RNAnimated.View>
      </Pressable>
    </Modal>
  );
}

const styles = StyleSheet.create({
  backdrop: {
    ...StyleSheet.absoluteFillObject,
    backgroundColor: "transparent",
  },
  card: {
    position: "absolute",
    minWidth: 180,
    backgroundColor: "#111111",
    borderRadius: 12,
    borderWidth: 1,
    borderColor: "rgba(255,255,255,0.06)",
    shadowColor: "#000",
    shadowOffset: { width: 0, height: 8 },
    shadowOpacity: 0.5,
    shadowRadius: 16,
    elevation: 16,
    overflow: "hidden",
  },
  divider: {
    height: 1,
    backgroundColor: "rgba(255,255,255,0.06)",
  },
  item: {
    flexDirection: "row",
    alignItems: "center",
    gap: 12,
    paddingVertical: 12,
    paddingHorizontal: 16,
  },
  itemPressed: {
    backgroundColor: "rgba(255,255,255,0.06)",
  },
  itemLabel: {
    fontFamily: FONTS.bodyMedium,
    fontSize: 15,
    color: "#e8e8e8",
  },
  itemLabelDestructive: {
    color: "#ef4444",
  },
});
