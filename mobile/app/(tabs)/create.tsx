import { useEffect } from "react";
import { View, Text, StyleSheet } from "react-native";
import { useRouter } from "expo-router";
import { Ionicons } from "@expo/vector-icons";
import Animated, {
  useSharedValue,
  useAnimatedStyle,
  withRepeat,
  withSequence,
  withTiming,
  Easing,
  interpolate,
  FadeInDown,
} from "react-native-reanimated";

import {
  BG_PAGE,
  TEXT_PRIMARY,
  TEXT_SECONDARY,
  CTA_PRIMARY,
} from "../../constants/colors";
import { HeroBackground } from "../../components/ui/HeroBackground";
import { FloatingParticles } from "../../components/ui/FloatingParticles";
import { GlowButton } from "../../components/ui/GlowButton";
import { useTheme } from "../../lib/theme-context";
import { FONTS } from "../../hooks/useFonts";

/**
 * Create tab — navigates to the upload screen.
 * Futuristic version with pulsing icon, aurora bg, glow CTA.
 */
export default function CreateScreen() {
  const router = useRouter();
  const { theme } = useTheme();

  const pulse = useSharedValue(0);
  const float = useSharedValue(0);

  useEffect(() => {
    pulse.value = withRepeat(
      withSequence(
        withTiming(1, { duration: 2000, easing: Easing.inOut(Easing.sin) }),
        withTiming(0, { duration: 2000, easing: Easing.inOut(Easing.sin) }),
      ),
      -1,
      false,
    );

    float.value = withRepeat(
      withSequence(
        withTiming(1, { duration: 3000, easing: Easing.inOut(Easing.sin) }),
        withTiming(0, { duration: 3000, easing: Easing.inOut(Easing.sin) }),
      ),
      -1,
      false,
    );
  }, []);

  const iconCircleStyle = useAnimatedStyle(() => ({
    transform: [
      { scale: 1 + pulse.value * 0.08 },
      { translateY: interpolate(float.value, [0, 1], [0, -8]) },
    ],
    shadowOpacity: 0.3 + pulse.value * 0.5,
    shadowRadius: 12 + pulse.value * 20,
  }));

  const handlePress = () => {
    router.push("/upload");
  };

  return (
    <View style={styles.container}>
      <HeroBackground />
      <FloatingParticles />

      {/* Sparkle icon with glow */}
      <Animated.View
        entering={FadeInDown.duration(600).delay(100)}
        style={[
          styles.iconCircle,
          { shadowColor: theme.accent, backgroundColor: theme.accent },
          iconCircleStyle,
        ]}
      >
        <Ionicons name="sparkles" size={36} color="#FFFFFF" />
      </Animated.View>

      <Animated.Text
        entering={FadeInDown.duration(600).delay(200)}
        style={styles.title}
      >
        Create your glow-up
      </Animated.Text>
      <Animated.Text
        entering={FadeInDown.duration(600).delay(300)}
        style={[styles.tagline, { color: theme.accent }]}
      >
        Transform your look
      </Animated.Text>
      <Animated.Text
        entering={FadeInDown.duration(600).delay(400)}
        style={styles.subtitle}
      >
        Upload a photo and get AI-powered style suggestions
      </Animated.Text>

      <Animated.View
        entering={FadeInDown.duration(600).delay(500)}
        style={styles.ctaWrapper}
      >
        <GlowButton
          title="Upload Photo"
          onPress={handlePress}
          glowColor={theme.accent}
          size="large"
        />
      </Animated.View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: BG_PAGE,
    alignItems: "center",
    justifyContent: "center",
    padding: 24,
  },
  iconCircle: {
    width: 80,
    height: 80,
    borderRadius: 40,
    backgroundColor: CTA_PRIMARY,
    alignItems: "center",
    justifyContent: "center",
    marginBottom: 24,
    shadowOffset: { width: 0, height: 4 },
    elevation: 10,
  },
  title: {
    fontFamily: FONTS.display,
    fontSize: 36,
    color: TEXT_PRIMARY,
    marginBottom: 6,
    textAlign: "center",
  },
  tagline: {
    fontFamily: FONTS.displayItalic,
    fontSize: 18,
    textAlign: "center",
    marginBottom: 12,
  },
  subtitle: {
    fontFamily: FONTS.body,
    fontSize: 16,
    color: TEXT_SECONDARY,
    textAlign: "center",
    marginBottom: 32,
    lineHeight: 22,
    paddingHorizontal: 16,
  },
  ctaWrapper: {
    width: "100%",
    maxWidth: 280,
  },
});
