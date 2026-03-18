/**
 * TypingIndicator — three-dot bouncing animation shown while Ada is responding.
 * Respects the system reduced-motion preference: shows static "..." instead of
 * animated dots when reduce-motion is enabled.
 */
import { useEffect, useRef, useState } from "react";
import { View, Text, Animated, StyleSheet, AccessibilityInfo } from "react-native";

import { ADA_BUBBLE_BG, ADA_BUBBLE_BORDER, TEXT_SECONDARY } from "../../constants/colors";
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
    paddingHorizontal: 16,
    paddingVertical: 4,
  },
  bubble: {
    flexDirection: "row",
    alignItems: "center",
    gap: 6,
    backgroundColor: ADA_BUBBLE_BG,
    borderLeftWidth: 3,
    borderLeftColor: ADA_BUBBLE_BORDER,
    borderRadius: 16,
    borderTopLeftRadius: 4,
    paddingHorizontal: 16,
    paddingVertical: 12,
  },
  dot: {
    width: 7,
    height: 7,
    borderRadius: 3.5,
    backgroundColor: TEXT_SECONDARY,
  },
  staticDots: {
    fontSize: 16,
    color: TEXT_SECONDARY,
    letterSpacing: 2,
  },
});
