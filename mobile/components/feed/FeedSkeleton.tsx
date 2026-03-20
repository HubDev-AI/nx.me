import { useEffect, useRef } from "react";
import { View, Animated, StyleSheet } from "react-native";

import { THEME } from "../../constants/theme";

const SHIMMER_DURATION_MS = 1200;
const SKELETON_CARD_COUNT = 3;
const IMAGE_HEIGHT = 180;

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
    paddingHorizontal: THEME.spacing.xl,
    paddingTop: THEME.spacing.sm,
  },
  card: {
    backgroundColor: THEME.colors.glass,
    borderRadius: THEME.radius.lg,
    marginBottom: THEME.spacing.xl,
    overflow: "hidden",
    borderWidth: 1,
    borderColor: THEME.colors.glassBorder,
  },
  imagePlaceholder: {
    height: IMAGE_HEIGHT,
    backgroundColor: "rgba(255,255,255,0.08)",
  },
  contentArea: {
    padding: THEME.spacing.md,
    gap: THEME.spacing.sm,
  },
  captionLine: {
    height: 14,
    borderRadius: THEME.radius.md,
    backgroundColor: "rgba(255,255,255,0.08)",
    width: "100%",
  },
  captionLineShort: {
    width: "60%",
  },
  actionsRow: {
    flexDirection: "row",
    gap: THEME.spacing.md,
    paddingHorizontal: THEME.spacing.md,
    paddingBottom: THEME.spacing.md,
  },
  actionPill: {
    height: 32,
    width: 64,
    borderRadius: THEME.radius.lg,
    backgroundColor: "rgba(255,255,255,0.08)",
  },
});
