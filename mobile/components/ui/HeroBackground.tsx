/**
 * HeroBackground — cinematic portrait backdrop.
 * Full-bleed image, NO overlay, NO gradient bands.
 * The portrait is the star. Form inputs have their own frosted backgrounds.
 */
import { useState, useMemo, useCallback } from "react";
import { StyleSheet, Image, type ImageSourcePropType } from "react-native";
import Animated, {
  useSharedValue,
  useAnimatedStyle,
  withTiming,
  Easing,
} from "react-native-reanimated";

// 18 hero portraits from card-web
const HERO_IMAGES: ImageSourcePropType[] = [
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
  require("../../assets/images/heroes/hero-14.jpg"),
  require("../../assets/images/heroes/hero-16.jpg"),
  require("../../assets/images/heroes/hero-17.jpg"),
  require("../../assets/images/heroes/hero-18.jpg"),
  require("../../assets/images/heroes/hero-19.jpg"),
  require("../../assets/images/heroes/hero-20.jpg"),
];

interface HeroBackgroundProps {
  heroIndex?: number;
}

export function HeroBackground({ heroIndex }: HeroBackgroundProps) {
  const source = useMemo(() => {
    if (heroIndex !== undefined) {
      return HERO_IMAGES[heroIndex % HERO_IMAGES.length];
    }
    return HERO_IMAGES[Math.floor(Math.random() * HERO_IMAGES.length)];
  }, [heroIndex]);

  const opacity = useSharedValue(0);

  const animatedStyle = useAnimatedStyle(() => ({
    opacity: opacity.value,
  }));

  const handleLoad = useCallback(() => {
    opacity.value = withTiming(1, {
      duration: 600,
      easing: Easing.out(Easing.ease),
    });
  }, [opacity]);

  return (
    <Animated.View style={[styles.container, animatedStyle]} pointerEvents="none">
      <Image
        source={source}
        style={styles.image}
        resizeMode="cover"
        onLoad={handleLoad}
        accessibilityRole="image"
        accessibilityLabel="Style portrait"
      />
      {/* NO gradient overlay. Zero. The raw portrait is the design. */}
    </Animated.View>
  );
}

const styles = StyleSheet.create({
  container: {
    ...StyleSheet.absoluteFillObject,
    overflow: "hidden",
  },
  image: {
    position: "absolute",
    top: 0,
    left: 0,
    right: 0,
    bottom: 0,
    width: "100%",
    height: "100%",
  },
});
