import { useRef, useCallback } from "react";
import {
  Pressable,
  Text,
  ActivityIndicator,
  StyleSheet,
  Animated,
} from "react-native";

import { CTA_PRIMARY, CTA_PRESSED } from "../../constants/colors";
import { FONTS } from "../../hooks/useFonts";

interface AuthButtonProps {
  title: string;
  onPress: () => void;
  isLoading?: boolean;
  disabled?: boolean;
}

const BUTTON_HEIGHT = 48;
const PRESS_SCALE = 0.98;
const PRESS_OPACITY = 0.9;
const ANIMATION_DURATION = 150;

export function AuthButton({
  title,
  onPress,
  isLoading = false,
  disabled = false,
}: AuthButtonProps) {
  const scaleAnim = useRef(new Animated.Value(1)).current;
  const opacityAnim = useRef(new Animated.Value(1)).current;

  const isDisabled = disabled || isLoading;

  const handlePressIn = useCallback(() => {
    Animated.parallel([
      Animated.timing(scaleAnim, {
        toValue: PRESS_SCALE,
        duration: ANIMATION_DURATION,
        useNativeDriver: true,
      }),
      Animated.timing(opacityAnim, {
        toValue: PRESS_OPACITY,
        duration: ANIMATION_DURATION,
        useNativeDriver: true,
      }),
    ]).start();
  }, [scaleAnim, opacityAnim]);

  const handlePressOut = useCallback(() => {
    Animated.parallel([
      Animated.timing(scaleAnim, {
        toValue: 1,
        duration: ANIMATION_DURATION,
        useNativeDriver: true,
      }),
      Animated.timing(opacityAnim, {
        toValue: 1,
        duration: ANIMATION_DURATION,
        useNativeDriver: true,
      }),
    ]).start();
  }, [scaleAnim, opacityAnim]);

  return (
    <Animated.View
      style={[
        { transform: [{ scale: scaleAnim }], opacity: opacityAnim },
        isDisabled && styles.disabledWrapper,
      ]}
    >
      <Pressable
        onPress={onPress}
        onPressIn={handlePressIn}
        onPressOut={handlePressOut}
        disabled={isDisabled}
        style={({ pressed }) => [
          styles.button,
          pressed && !isDisabled && { backgroundColor: CTA_PRESSED },
        ]}
        accessibilityLabel={isLoading ? `${title}, loading` : title}
        accessibilityRole="button"
        accessibilityState={{ disabled: isDisabled, busy: isLoading }}
      >
        {isLoading ? (
          <ActivityIndicator color="#FFFFFF" size="small" />
        ) : (
          <Text style={styles.text}>{title}</Text>
        )}
      </Pressable>
    </Animated.View>
  );
}

const styles = StyleSheet.create({
  button: {
    backgroundColor: CTA_PRIMARY,
    minHeight: BUTTON_HEIGHT,
    borderRadius: 12,
    alignItems: "center",
    justifyContent: "center",
    paddingVertical: 12,
    paddingHorizontal: 24,
  },
  text: {
    fontFamily: FONTS.bodySemiBold,
    color: "#FFFFFF",
    fontSize: 16,
  },
  disabledWrapper: {
    opacity: 0.5,
  },
});
