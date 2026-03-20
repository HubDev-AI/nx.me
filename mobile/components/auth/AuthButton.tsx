import { useRef, useCallback } from "react";
import {
  Pressable,
  Text,
  ActivityIndicator,
  StyleSheet,
  Animated,
} from "react-native";

import { THEME } from "../../constants/theme";
import { FONTS } from "../../hooks/useFonts";
import { useTheme } from "../../lib/theme-context";

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
  const { theme } = useTheme();
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
          { backgroundColor: theme.accent },
          pressed && !isDisabled && styles.buttonPressed,
        ]}
        accessibilityLabel={isLoading ? `${title}, loading` : title}
        accessibilityRole="button"
        accessibilityState={{ disabled: isDisabled, busy: isLoading }}
      >
        {isLoading ? (
          <ActivityIndicator color={THEME.colors.bg} size="small" />
        ) : (
          <Text style={styles.text}>{title}</Text>
        )}
      </Pressable>
    </Animated.View>
  );
}

const styles = StyleSheet.create({
  button: {
    minHeight: BUTTON_HEIGHT,
    borderRadius: THEME.radius.pill,
    alignItems: "center",
    justifyContent: "center",
    paddingVertical: THEME.spacing.md,
    paddingHorizontal: THEME.spacing.xxl,
  },
  buttonPressed: {
    opacity: 0.85,
  },
  text: {
    fontFamily: FONTS.bodySemiBold,
    color: THEME.colors.bg,
    fontSize: 16,
  },
  disabledWrapper: {
    opacity: 0.5,
  },
});
