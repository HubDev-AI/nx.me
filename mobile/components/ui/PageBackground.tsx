/**
 * PageBackground — subtle background image with overlay for non-auth pages.
 * Uses a random hero image at low opacity for visual depth.
 * Every page gets a different background per session.
 */
import { useState, useMemo, useCallback } from "react";
import { StyleSheet, Image, View, type ImageSourcePropType } from "react-native";
import Animated, {
  useSharedValue,
  useAnimatedStyle,
  withTiming,
  Easing,
} from "react-native-reanimated";
import { THEME } from "../../constants/theme";

// Reuse the hero images — they work great as subtle backgrounds
const BG_IMAGES: ImageSourcePropType[] = [
  require("../../assets/images/heroes/hero-1.jpg"),
  require("../../assets/images/heroes/hero-2.jpg"),
  require("../../assets/images/heroes/hero-3.jpg"),
  require("../../assets/images/heroes/hero-4.jpg"),
  require("../../assets/images/heroes/hero-5.jpg"),
  require("../../assets/images/heroes/hero-6.jpg"),
  require("../../assets/images/heroes/hero-7.jpg"),
  require("../../assets/images/heroes/hero-8.jpg"),
  require("../../assets/images/heroes/hero-9.jpg"),
  require("../../assets/images/heroes/hero-10.jpg"),
  require("../../assets/images/heroes/hero-11.jpg"),
  require("../../assets/images/heroes/hero-12.jpg"),
];

interface PageBackgroundProps {
  /** Overlay opacity — higher = darker. Default 0.82 (very subtle image) */
  overlayOpacity?: number;
  /** Override image index */
  imageIndex?: number;
}

export function PageBackground({ overlayOpacity = 0.82, imageIndex }: PageBackgroundProps) {
  const source = useMemo(() => {
    if (imageIndex !== undefined) return BG_IMAGES[imageIndex % BG_IMAGES.length];
    return BG_IMAGES[Math.floor(Math.random() * BG_IMAGES.length)];
  }, [imageIndex]);

  const opacity = useSharedValue(0);

  const animatedStyle = useAnimatedStyle(() => ({
    opacity: opacity.value,
  }));

  const handleLoad = useCallback(() => {
    opacity.value = withTiming(1, { duration: 800, easing: Easing.out(Easing.ease) });
  }, [opacity]);

  return (
    <Animated.View style={[styles.container, animatedStyle]} pointerEvents="none">
      <Image
        source={source}
        style={styles.image}
        resizeMode="cover"
        onLoad={handleLoad}
      />
      <View style={[styles.overlay, { backgroundColor: `rgba(10, 10, 10, ${overlayOpacity})` }]} />
    </Animated.View>
  );
}

const styles = StyleSheet.create({
  container: {
    ...StyleSheet.absoluteFillObject,
  },
  image: {
    ...StyleSheet.absoluteFillObject,
    width: "100%",
    height: "100%",
  },
  overlay: {
    ...StyleSheet.absoluteFillObject,
  },
});
