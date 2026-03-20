/**
 * GlassCard — semi-transparent card matching card-web's dark surface style.
 */
import { type ReactNode } from "react";
import { StyleSheet, type ViewStyle } from "react-native";
import Animated, { FadeIn } from "react-native-reanimated";

interface GlassCardProps {
  children: ReactNode;
  style?: ViewStyle;
  animate?: boolean;
}

export function GlassCard({
  children,
  style,
  animate = true,
}: GlassCardProps) {
  return (
    <Animated.View
      entering={animate ? FadeIn.duration(500) : undefined}
      style={[styles.card, style]}
    >
      {children}
    </Animated.View>
  );
}

const styles = StyleSheet.create({
  card: {
    backgroundColor: "rgba(17, 17, 17, 0.85)",
    borderRadius: 16,
    padding: 20,
    borderWidth: 1,
    borderColor: "rgba(255, 255, 255, 0.06)",
  },
});
