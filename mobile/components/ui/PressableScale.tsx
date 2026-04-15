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

const AnimatedPressable = Animated.createAnimatedComponent(Pressable);

interface PressableScaleProps extends Omit<PressableProps, "style"> {
  scale?: number;
  haptic?: boolean;
  children: React.ReactNode;
  /**
   * Style applied directly to the underlying Pressable. Use this for layout
   * (flex, flexDirection, padding, etc) — children of the Pressable respect
   * its flexDirection.
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
    <AnimatedPressable
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
      style={[style, animStyle]}
      {...rest}
    >
      {children}
    </AnimatedPressable>
  );
}
