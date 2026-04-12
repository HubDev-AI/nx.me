import React, { useEffect, useRef } from 'react';
import { Animated, StyleSheet, type ViewStyle } from 'react-native';
import { THEME } from '../../constants/theme';

interface LoadingSkeletonProps {
  height?: number;
  width?: number | string;
  borderRadius?: number;
  style?: ViewStyle;
}

export function LoadingSkeleton({
  height = 20,
  width = '100%',
  borderRadius = THEME.radius.sm,
  style,
}: LoadingSkeletonProps) {
  const opacity = useRef(new Animated.Value(0.3)).current;

  useEffect(() => {
    const loop = Animated.loop(
      Animated.sequence([
        Animated.timing(opacity, { toValue: 0.7, duration: 600, useNativeDriver: true }),
        Animated.timing(opacity, { toValue: 0.3, duration: 600, useNativeDriver: true }),
      ]),
    );
    loop.start();
    return () => loop.stop();
  }, [opacity]);

  return (
    <Animated.View
      style={[
        styles.base,
        { height, width: width as ViewStyle['width'], borderRadius, opacity },
        style,
      ]}
    />
  );
}

const styles = StyleSheet.create({
  base: {
    backgroundColor: THEME.colors.surfaceElevated,
  },
});
