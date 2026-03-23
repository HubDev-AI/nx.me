/**
 * FloatingParticles -- magical shimmer dust effect over the hero image.
 * Renders 14 tiny glowing dots that drift slowly upward in a continuous loop.
 * Each particle has a random size (3-6 px), random opacity (15-30%), and a
 * unique drift speed (15-25 s per cycle). When a particle reaches the top it
 * wraps back to the bottom with a fresh random X position.
 *
 * Uses Reanimated withRepeat + withTiming for butter-smooth 60 fps animation.
 * The entire layer is pointer-events="none" so it never blocks touches.
 */
import { useEffect, useMemo } from "react";
import { StyleSheet, useWindowDimensions } from "react-native";
import Animated, {
  useSharedValue,
  useAnimatedStyle,
  withRepeat,
  withTiming,
  withDelay,
  Easing,
} from "react-native-reanimated";

const PARTICLE_COUNT = 14;

/** Generate stable random config for each particle on mount. */
function buildParticleConfigs(screenWidth: number, screenHeight: number) {
  const configs = [];
  for (let i = 0; i < PARTICLE_COUNT; i++) {
    const size = 3 + Math.random() * 3; // 3-6 px
    const opacity = 0.15 + Math.random() * 0.15; // 0.15-0.30
    const startX = Math.random() * (screenWidth - size);
    const startY = screenHeight * 0.3 + Math.random() * screenHeight * 0.7; // start in lower 70%
    const duration = 15000 + Math.random() * 10000; // 15-25 seconds
    const delay = Math.random() * 6000; // stagger so they don't all start at once
    // Gentle horizontal sway amplitude
    const swayAmplitude = 20 + Math.random() * 30; // 20-50 px sway
    const swayDuration = 4000 + Math.random() * 3000; // 4-7 seconds per sway cycle
    configs.push({ size, opacity, startX, startY, duration, delay, swayAmplitude, swayDuration });
  }
  return configs;
}

interface ParticleProps {
  size: number;
  opacity: number;
  startX: number;
  startY: number;
  duration: number;
  delay: number;
  screenHeight: number;
  swayAmplitude: number;
  swayDuration: number;
}

function Particle({
  size,
  opacity,
  startX,
  startY,
  duration,
  delay,
  screenHeight,
  swayAmplitude,
  swayDuration,
}: ParticleProps) {
  const translateY = useSharedValue(0);
  const translateX = useSharedValue(0);
  const particleOpacity = useSharedValue(0);

  useEffect(() => {
    // Vertical drift: from start position upward past the top of screen
    const totalDrift = startY + size + 40; // drift far enough to exit top
    translateY.value = withDelay(
      delay,
      withRepeat(
        withTiming(-totalDrift, {
          duration,
          easing: Easing.linear,
        }),
        -1,
        false,
      ),
    );

    // Horizontal sway: gentle back and forth
    translateX.value = withDelay(
      delay,
      withRepeat(
        withTiming(swayAmplitude, {
          duration: swayDuration,
          easing: Easing.inOut(Easing.sin),
        }),
        -1,
        true, // reverse each cycle for oscillation
      ),
    );

    // Fade in after delay
    particleOpacity.value = withDelay(
      delay,
      withTiming(1, { duration: 1200, easing: Easing.out(Easing.ease) }),
    );
  }, []);

  const animatedStyle = useAnimatedStyle(() => ({
    transform: [
      { translateY: translateY.value },
      { translateX: translateX.value },
    ],
    opacity: particleOpacity.value * opacity,
  }));

  return (
    <Animated.View
      style={[
        {
          position: "absolute",
          left: startX,
          top: startY,
          width: size,
          height: size,
          borderRadius: size / 2,
          backgroundColor: "#FFFFFF",
        },
        animatedStyle,
      ]}
    />
  );
}

export function FloatingParticles() {
  const { width, height } = useWindowDimensions();

  const configs = useMemo(
    () => buildParticleConfigs(width, height),
    [width, height],
  );

  return (
    <Animated.View style={styles.container} pointerEvents="none">
      {configs.map((cfg, i) => (
        <Particle
          key={i}
          size={cfg.size}
          opacity={cfg.opacity}
          startX={cfg.startX}
          startY={cfg.startY}
          duration={cfg.duration}
          delay={cfg.delay}
          screenHeight={height}
          swayAmplitude={cfg.swayAmplitude}
          swayDuration={cfg.swayDuration}
        />
      ))}
    </Animated.View>
  );
}

const styles = StyleSheet.create({
  container: {
    ...StyleSheet.absoluteFillObject,
    overflow: "hidden",
  },
});
