import { useEffect } from "react";
import { Tabs } from "expo-router";
import { Ionicons } from "@expo/vector-icons";
import { View, StyleSheet, Platform } from "react-native";
import Animated, {
  useSharedValue,
  useAnimatedStyle,
  withSpring,
  withRepeat,
  withSequence,
  withTiming,
  Easing,
} from "react-native-reanimated";

import {
  TAB_INACTIVE_COLOR,
  BG_PAGE,
  COLORS,
} from "../../constants/colors";
import { useTheme } from "../../lib/theme-context";

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
      <Animated.View style={iconStyle}>
        <Ionicons name={name} size={24} color={color} />
      </Animated.View>
      {/* Glow dot under active icon */}
      <Animated.View
        style={[
          styles.glowDot,
          {
            backgroundColor: accentColor,
            shadowColor: accentColor,
          },
          glowDotStyle,
        ]}
      />
    </View>
  );
}

export default function TabLayout() {
  const { theme } = useTheme();

  return (
    <Tabs
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
        headerStyle: {
          backgroundColor: BG_PAGE,
        },
        headerTintColor: COLORS.neutral.dark[900],
        headerShadowVisible: false,
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
  );
}

const styles = StyleSheet.create({
  iconContainer: {
    alignItems: "center",
    justifyContent: "center",
    width: 48,
    height: 48,
  },
  glowDot: {
    width: 5,
    height: 5,
    borderRadius: 2.5,
    marginTop: 4,
    shadowOffset: { width: 0, height: 0 },
    shadowRadius: 6,
    elevation: 4,
  },
});
