import { useEffect, useRef } from "react";
import { View, Animated, StyleSheet } from "react-native";

import { BG_CARD, BG_ELEVATED } from "../../constants/colors";

const SHIMMER_DURATION_MS = 1200;
const SKELETON_CARD_COUNT = 3;
const IMAGE_HEIGHT = 180;
const CARD_BORDER_RADIUS = 12;

/** Single skeleton card matching FeedCard layout */
function SkeletonCard() {
  const shimmerAnim = useRef(new Animated.Value(0)).current;

  useEffect(() => {
    const loop = Animated.loop(
      Animated.sequence([
        Animated.timing(shimmerAnim, {
          toValue: 1,
          duration: SHIMMER_DURATION_MS,
          useNativeDriver: true,
        }),
        Animated.timing(shimmerAnim, {
          toValue: 0,
          duration: SHIMMER_DURATION_MS,
          useNativeDriver: true,
        }),
      ]),
    );
    loop.start();
    return () => loop.stop();
  }, [shimmerAnim]);

  const opacity = shimmerAnim.interpolate({
    inputRange: [0, 1],
    outputRange: [0.3, 0.7],
  });

  return (
    <View style={styles.card} accessibilityLabel="Loading post">
      {/* Image placeholder */}
      <Animated.View style={[styles.imagePlaceholder, { opacity }]} />

      {/* Caption placeholder */}
      <View style={styles.contentArea}>
        <Animated.View style={[styles.captionLine, { opacity }]} />
        <Animated.View
          style={[styles.captionLine, styles.captionLineShort, { opacity }]}
        />
      </View>

      {/* Actions placeholder */}
      <View style={styles.actionsRow}>
        <Animated.View style={[styles.actionPill, { opacity }]} />
        <Animated.View style={[styles.actionPill, { opacity }]} />
      </View>
    </View>
  );
}

/** Renders multiple skeleton cards for feed loading state */
export function FeedSkeleton() {
  return (
    <View
      style={styles.container}
      accessibilityRole="none"
      accessibilityLabel="Feed loading"
    >
      {Array.from({ length: SKELETON_CARD_COUNT }).map((_, i) => (
        <SkeletonCard key={i} />
      ))}
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    paddingHorizontal: 16,
    paddingTop: 8,
  },
  card: {
    backgroundColor: BG_CARD,
    borderRadius: CARD_BORDER_RADIUS,
    marginBottom: 16,
    overflow: "hidden",
  },
  imagePlaceholder: {
    height: IMAGE_HEIGHT,
    backgroundColor: BG_ELEVATED,
  },
  contentArea: {
    padding: 12,
    gap: 8,
  },
  captionLine: {
    height: 14,
    borderRadius: 4,
    backgroundColor: BG_ELEVATED,
    width: "100%",
  },
  captionLineShort: {
    width: "60%",
  },
  actionsRow: {
    flexDirection: "row",
    gap: 12,
    paddingHorizontal: 12,
    paddingBottom: 12,
  },
  actionPill: {
    height: 32,
    width: 64,
    borderRadius: 16,
    backgroundColor: BG_ELEVATED,
  },
});
