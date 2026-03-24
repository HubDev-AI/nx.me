import { useEffect } from "react";
import { Tabs, useRouter } from "expo-router";
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

import { THEME } from "../../constants/theme";
import { BG_PAGE, TEXT_PRIMARY, TAB_BAR_BG, TAB_BAR_BORDER, TAB_BAR_GLOW, SCROLL_TOP_BG } from "../../constants/colors";
import { useTheme } from "../../lib/theme-context";
import { FONTS } from "../../hooks/useFonts";
import { BrandLabel } from "../../components/ui/BrandLabel";
import { FeedCreditBadge } from "../../components/feed/FeedCreditBadge";
import { TabBarProvider, useTabBar } from "../../lib/tab-bar-context";

/** Height of the floating tab bar + bottom inset — used for paddingBottom in scroll views */
export const TAB_BAR_HEIGHT = 90;

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
    <View
      style={[
        styles.iconContainer,
        styles.iconPill,
        focused && {
          backgroundColor: accentColor + "26",
          shadowColor: accentColor,
          shadowOffset: { width: 0, height: 0 },
          shadowOpacity: 0.25,
          shadowRadius: 8,
          elevation: 4,
        },
      ]}
      accessible={false}
    >
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
        <Ionicons name="arrow-up" size={16} color={BG_PAGE} />
        <Text style={styles.scrollToTopText}>Top</Text>
      </Pressable>
    </Animated.View>
  );
}

/** Tappable brand label that navigates to the feed/home tab */
function HeaderBrandLabel() {
  const router = useRouter();
  return (
    <Pressable onPress={() => router.push("/(tabs)")}>
      <BrandLabel />
    </Pressable>
  );
}

/** Stable wrapper so FeedCreditBadge hooks don't cause re-render mismatch */
function HeaderCreditBadge() {
  return (
    <View style={styles.headerRight}>
      <FeedCreditBadge />
    </View>
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
        tabBarInactiveTintColor: "rgba(255, 255, 255, 0.45)",
        tabBarStyle: {
          position: "absolute",
          bottom: Platform.OS === "ios" ? 24 : 16,
          left: THEME.spacing.xl,
          right: THEME.spacing.xl,
          height: 64,
          borderRadius: 32,
          backgroundColor: TAB_BAR_BG,
          borderTopWidth: StyleSheet.hairlineWidth,
          borderTopColor: TAB_BAR_GLOW,
          borderWidth: 1,
          borderColor: TAB_BAR_BORDER,
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
          backgroundColor: SCROLL_TOP_BG,
        },
        headerTintColor: TEXT_PRIMARY,
        headerShadowVisible: false,
        headerTitle: () => <HeaderBrandLabel />,
      }}
    >
      <Tabs.Screen
        name="index"
        options={{
          title: "Home",
          headerRight: () => <HeaderCreditBadge />,
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
  headerRight: {
    marginRight: THEME.spacing.lg,
  },
  iconContainer: {
    alignItems: "center",
    justifyContent: "center",
    width: 48,
  },
  iconPill: {
    paddingHorizontal: THEME.spacing.lg,
    paddingVertical: 6,
    borderRadius: THEME.radius.lg,
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
    gap: THEME.spacing.xs,
    height: 40,
    paddingHorizontal: THEME.spacing.lg,
    borderRadius: THEME.radius.xl,
    ...THEME.shadow.glass,
  },
  scrollToTopText: {
    fontFamily: FONTS.bodySemiBold,
    fontSize: 13,
    color: BG_PAGE,
    letterSpacing: 0.5,
  },
});
