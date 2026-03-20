import { useEffect } from "react";
import { Tabs } from "expo-router";
import { Ionicons } from "@expo/vector-icons";
import { View, Text, StyleSheet, Platform, Pressable } from "react-native";
import Animated, {
  useSharedValue,
  useAnimatedStyle,
  withSpring,
  withRepeat,
  withSequence,
  withTiming,
  Easing,
  interpolate,
  Extrapolation,
} from "react-native-reanimated";
import { BottomTabBar, type BottomTabBarProps } from "@react-navigation/bottom-tabs";

import {
  TAB_INACTIVE_COLOR,
  BG_PAGE,
  TEXT_PRIMARY,
  COLORS,
} from "../../constants/colors";
import { useTheme } from "../../lib/theme-context";
import { FONTS } from "../../hooks/useFonts";
import { BrandLabel } from "../../components/ui/BrandLabel";
import { TabBarProvider, useTabBar } from "../../lib/tab-bar-context";

type IoniconsName = React.ComponentProps<typeof Ionicons>["name"];

interface TabIconProps {
  name: IoniconsName;
  color: string;
  focused: boolean;
  accentColor: string;
}

/** Floating tab icon with glow dot when active */
function TabIcon({ name, color, focused, accentColor }: TabIconProps) {
  const scale = useSharedValue(1);
  const glowOpacity = useSharedValue(0);

  useEffect(() => {
    if (focused) {
      scale.value = withSpring(1.15, { damping: 12, stiffness: 200 });
      glowOpacity.value = withRepeat(
        withSequence(
          withTiming(1, { duration: 1500, easing: Easing.inOut(Easing.sin) }),
          withTiming(0.4, { duration: 1500, easing: Easing.inOut(Easing.sin) }),
        ),
        -1,
        false,
      );
    } else {
      scale.value = withSpring(1, { damping: 12, stiffness: 200 });
      glowOpacity.value = withTiming(0, { duration: 200 });
    }
  }, [focused]);

  const iconStyle = useAnimatedStyle(() => ({
    transform: [{ scale: scale.value }],
  }));

  const glowDotStyle = useAnimatedStyle(() => ({
    opacity: glowOpacity.value,
    shadowOpacity: glowOpacity.value * 0.8,
  }));

  return (
    <View style={styles.iconContainer} accessible={false}>
      <Ionicons name={name} size={24} color={color} />
    </View>
  );
}

/** Custom animated tab bar that slides down when the user scrolls */
function AnimatedTabBar(props: BottomTabBarProps) {
  const { tabBarTranslateY } = useTabBar();

  const animatedStyle = useAnimatedStyle(() => ({
    transform: [{ translateY: tabBarTranslateY.value }],
  }));

  return (
    <Animated.View style={animatedStyle}>
      <BottomTabBar {...props} />
    </Animated.View>
  );
}

/** Small floating pill that appears when the tab bar is hidden */
function ScrollToTopPill() {
  const { tabBarTranslateY, scrollToTop } = useTabBar();
  const { theme } = useTheme();

  const animatedStyle = useAnimatedStyle(() => {
    const opacity = interpolate(
      tabBarTranslateY.value,
      [50, 100],
      [0, 1],
      Extrapolation.CLAMP,
    );
    return {
      opacity,
      // Keep it non-interactive when invisible
      pointerEvents: opacity > 0.1 ? "auto" : "none",
    } as any;
  });

  return (
    <Animated.View style={[styles.scrollToTopContainer, animatedStyle]}>
      <Pressable
        onPress={scrollToTop}
        style={[styles.scrollToTopPill, { backgroundColor: theme.accent }]}
        accessibilityLabel="Scroll to top"
        accessibilityRole="button"
      >
        <Ionicons name="arrow-up" size={16} color="#0a0a0a" />
        <Text style={styles.scrollToTopText}>Top</Text>
      </Pressable>
    </Animated.View>
  );
}

function TabLayoutInner() {
  const { theme } = useTheme();

  return (
    <>
    <Tabs
      tabBar={(props) => <AnimatedTabBar {...props} />}
      screenOptions={{
        tabBarActiveTintColor: theme.accent,
        tabBarInactiveTintColor: TAB_INACTIVE_COLOR,
        tabBarStyle: {
          position: "absolute",
          bottom: Platform.OS === "ios" ? 24 : 16,
          left: 20,
          right: 20,
          height: 64,
          borderRadius: 32,
          backgroundColor: "rgba(17, 17, 17, 0.85)",
          borderTopWidth: 0,
          borderWidth: 1,
          borderColor: "rgba(255, 255, 255, 0.08)",
          shadowColor: "#000",
          shadowOffset: { width: 0, height: 8 },
          shadowOpacity: 0.4,
          shadowRadius: 24,
          elevation: 12,
          paddingBottom: 0,
        },
        tabBarShowLabel: false,
        tabBarIconStyle: {
          flex: 1,
        },
        headerStyle: {
          backgroundColor: "#0a0a0a",
        },
        headerTintColor: "#e8e8e8",
        headerShadowVisible: false,
        headerTitle: () => <BrandLabel />,
      }}
    >
      <Tabs.Screen
        name="index"
        options={{
          title: "Home",
          tabBarIcon: ({ color, focused }) => (
            <TabIcon
              name={focused ? "home" : "home-outline"}
              color={color}
              focused={focused}
              accentColor={theme.accent}
            />
          ),
        }}
      />
      <Tabs.Screen
        name="create"
        options={{
          title: "Create",
          tabBarIcon: ({ color, focused }) => (
            <TabIcon
              name={focused ? "add-circle" : "add-circle-outline"}
              color={color}
              focused={focused}
              accentColor={theme.accent}
            />
          ),
        }}
      />
      <Tabs.Screen
        name="profile"
        options={{
          title: "Profile",
          tabBarIcon: ({ color, focused }) => (
            <TabIcon
              name={focused ? "person" : "person-outline"}
              color={color}
              focused={focused}
              accentColor={theme.accent}
            />
          ),
        }}
      />
      <Tabs.Screen
        name="advisor"
        options={{
          title: "Advisor",
          href: "/advisor",
          tabBarIcon: ({ color, focused }) => (
            <TabIcon
              name={focused ? "sparkles" : "sparkles-outline"}
              color={color}
              focused={focused}
              accentColor={theme.accent}
            />
          ),
        }}
      />
    </Tabs>
    <ScrollToTopPill />
    </>
  );
}

export default function TabLayout() {
  return (
    <TabBarProvider>
      <TabLayoutInner />
    </TabBarProvider>
  );
}

const styles = StyleSheet.create({
  iconContainer: {
    alignItems: "center",
    justifyContent: "center",
    width: 48,
  },
  glowDot: {
    width: 5,
    height: 5,
    borderRadius: 2.5,
    marginTop: 3,
    shadowOffset: { width: 0, height: 0 },
    shadowRadius: 6,
    elevation: 4,
  },
  scrollToTopContainer: {
    position: "absolute",
    bottom: Platform.OS === "ios" ? 28 : 20,
    alignSelf: "center",
    zIndex: 100,
  },
  scrollToTopPill: {
    flexDirection: "row",
    alignItems: "center",
    gap: 4,
    height: 40,
    paddingHorizontal: 16,
    borderRadius: 20,
    shadowColor: "#000",
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.3,
    shadowRadius: 8,
    elevation: 8,
  },
  scrollToTopText: {
    fontFamily: FONTS.bodySemiBold,
    fontSize: 13,
    color: "#0a0a0a",
    letterSpacing: 0.5,
  },
});
