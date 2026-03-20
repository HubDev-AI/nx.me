/**
 * GlassCard — frosted glass card using global theme tokens.
 * Use for any container that needs depth + translucency.
 */
import { type ReactNode } from "react";
import { type ViewStyle } from "react-native";
import Animated, { FadeIn } from "react-native-reanimated";
import { THEME, sharedStyles } from "../../constants/theme";

interface GlassCardProps {
  children: ReactNode;
  style?: ViewStyle;
  animate?: boolean;
  /** Use lighter glass — for cards over background images */
  light?: boolean;
}

export function GlassCard({
  children,
  style,
  animate = true,
  light = false,
}: GlassCardProps) {
  return (
    <Animated.View
      entering={animate ? FadeIn.duration(500) : undefined}
      style={[
        sharedStyles.glassCard,
        light && { backgroundColor: THEME.colors.glassLight },
        { padding: THEME.spacing.xl },
        style,
      ]}
    >
      {children}
    </Animated.View>
  );
}
