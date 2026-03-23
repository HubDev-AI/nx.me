/**
 * TypingIndicator — three-dot bouncing animation shown while Ada is responding.
 * Respects the system reduced-motion preference: shows static "..." instead of
 * animated dots when reduce-motion is enabled.
 */
import { useEffect, useRef, useState } from "react";
import { View, Text, Animated, StyleSheet, AccessibilityInfo } from "react-native";

import { THEME } from "../../constants/theme";
import { FONTS } from "../../hooks/useFonts";
import { ADVISOR_CONFIG } from "../../constants/config";

const DOT_COUNT = 3;

export function TypingIndicator() {
  const [reduceMotion, setReduceMotion] = useState(false);

  const dots = useRef(
    Array.from({ length: DOT_COUNT }, () => new Animated.Value(0)),
  ).current;

  useEffect(() => {
    AccessibilityInfo.isReduceMotionEnabled().then(setReduceMotion);
    const sub = AccessibilityInfo.addEventListener(
      "reduceMotionChanged",
      setReduceMotion,
    );
    return () => sub.remove();
  }, []);

  useEffect(() => {
    if (reduceMotion) return;

    const animations = dots.map((dot, index) =>
      Animated.loop(
        Animated.sequence([
          Animated.delay(index * ADVISOR_CONFIG.TYPING_DOT_DELAY_MS),
          Animated.timing(dot, {
            toValue: 1,
            duration: ADVISOR_CONFIG.TYPING_DOT_DURATION_MS,
            useNativeDriver: true,
          }),
          Animated.timing(dot, {
            toValue: 0,
            duration: ADVISOR_CONFIG.TYPING_DOT_DURATION_MS,
            useNativeDriver: true,
          }),
        ]),
      ),
    );

    const parallel = Animated.parallel(animations);
    parallel.start();

    return () => parallel.stop();
  }, [dots, reduceMotion]);

  if (reduceMotion) {
    return (
      <View style={styles.container} accessibilityLabel="Ada is typing">
        <View style={styles.bubble}>
          <Text style={styles.staticDots}>...</Text>
        </View>
      </View>
    );
  }

  return (
    <View style={styles.container} accessibilityLabel="Ada is typing">
      <View style={styles.bubble}>
        {dots.map((dot, index) => (
          <Animated.View
            key={index}
            style={[
              styles.dot,
              {
                opacity: dot.interpolate({
                  inputRange: [0, 1],
                  outputRange: [0.3, 1],
                }),
                transform: [
                  {
                    translateY: dot.interpolate({
                      inputRange: [0, 1],
                      outputRange: [0, -4],
                    }),
                  },
                ],
              },
            ]}
          />
        ))}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    alignSelf: "flex-start",
    paddingHorizontal: THEME.spacing.lg,
    paddingVertical: THEME.spacing.xs,
  },
  bubble: {
    flexDirection: "row",
    alignItems: "center",
    gap: THEME.spacing.sm,
    backgroundColor: THEME.colors.glass,
    borderWidth: 1,
    borderColor: THEME.colors.glassBorder,
    borderRadius: THEME.radius.lg,
    paddingHorizontal: THEME.spacing.lg,
    paddingVertical: THEME.spacing.md,
  },
  dot: {
    width: 7,
    height: 7,
    borderRadius: 3.5,
    backgroundColor: THEME.colors.textSecondary,
  },
  staticDots: {
    fontFamily: FONTS.body,
    fontSize: 16,
    color: THEME.colors.textSecondary,
    letterSpacing: 2,
  },
});
