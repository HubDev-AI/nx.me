import React from "react";
import {
  Pressable,
  type PressableProps,
  type StyleProp,
  type ViewStyle,
} from "react-native";
import Animated, {
  useAnimatedStyle,
  useSharedValue,
  withSpring,
} from "react-native-reanimated";
import { THEME } from "../../constants/theme";
import { hapticLight } from "../../lib/haptics";

interface PressableScaleProps extends Omit<PressableProps, "style"> {
  scale?: number;
  haptic?: boolean;
  children: React.ReactNode;
  /**
   * Static style applied to the wrapping Animated.View.
   * Pressable's function-form style is not supported here — the wrapper
   * owns the transform so per-state style callbacks don't fit.
   */
  style?: StyleProp<ViewStyle>;
}

export function PressableScale({
  scale = 0.96,
  haptic = true,
  onPress,
  children,
  style,
  ...rest
}: PressableScaleProps) {
  const sv = useSharedValue(1);
  const animStyle = useAnimatedStyle(() => ({
    transform: [{ scale: sv.value }],
  }));

  return (
    <Animated.View style={[animStyle, style]}>
      <Pressable
        onPressIn={() => {
          sv.value = withSpring(scale, THEME.animation.press);
        }}
        onPressOut={() => {
          sv.value = withSpring(1, THEME.animation.press);
        }}
        onPress={(e) => {
          if (haptic) hapticLight();
          onPress?.(e);
        }}
        {...rest}
      >
        {children}
      </Pressable>
    </Animated.View>
  );
}
