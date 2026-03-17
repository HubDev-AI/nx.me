import { useEffect, useRef } from "react";
import { View, Animated, StyleSheet } from "react-native";

import { BG_ELEVATED } from "../../constants/colors";

const AVATAR_SIZE = 32;
const PULSE_DURATION_MS = 1000;
const SKELETON_COUNT = 5;

/**
 * Loading skeleton for the comment list.
 * Displays placeholder rows with a pulsing opacity animation.
 */
export function CommentSkeleton() {
  const pulseAnim = useRef(new Animated.Value(0.3)).current;

  useEffect(() => {
    const animation = Animated.loop(
      Animated.sequence([
        Animated.timing(pulseAnim, {
          toValue: 0.7,
          duration: PULSE_DURATION_MS,
          useNativeDriver: true,
        }),
        Animated.timing(pulseAnim, {
          toValue: 0.3,
          duration: PULSE_DURATION_MS,
          useNativeDriver: true,
        }),
      ]),
    );
    animation.start();
    return () => animation.stop();
  }, [pulseAnim]);

  return (
    <View accessibilityLabel="Loading comments">
      {Array.from({ length: SKELETON_COUNT }, (_, i) => (
        <Animated.View
          key={i}
          style={[styles.row, { opacity: pulseAnim }]}
        >
          <View style={styles.avatar} />
          <View style={styles.content}>
            <View style={styles.nameLine} />
            <View style={styles.textLine} />
            <View style={styles.textLineShort} />
          </View>
        </Animated.View>
      ))}
    </View>
  );
}

const styles = StyleSheet.create({
  row: {
    flexDirection: "row",
    paddingHorizontal: 16,
    paddingVertical: 10,
    gap: 10,
  },
  avatar: {
    width: AVATAR_SIZE,
    height: AVATAR_SIZE,
    borderRadius: AVATAR_SIZE / 2,
    backgroundColor: BG_ELEVATED,
  },
  content: {
    flex: 1,
    gap: 6,
    paddingTop: 2,
  },
  nameLine: {
    width: 80,
    height: 12,
    borderRadius: 4,
    backgroundColor: BG_ELEVATED,
  },
  textLine: {
    width: "90%",
    height: 12,
    borderRadius: 4,
    backgroundColor: BG_ELEVATED,
  },
  textLineShort: {
    width: "60%",
    height: 12,
    borderRadius: 4,
    backgroundColor: BG_ELEVATED,
  },
});
