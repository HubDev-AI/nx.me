import { Tabs, useRouter } from "expo-router";
import { Ionicons } from "@expo/vector-icons";
import { View, Text, StyleSheet, Pressable } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import Animated, {
  useAnimatedStyle,
  interpolate,
  Extrapolation,
} from "react-native-reanimated";
import type { BottomTabBarProps } from "@react-navigation/bottom-tabs";

import { THEME } from "../../constants/theme";
import { BG_PAGE, TEXT_PRIMARY, TAB_BAR_BG, TAB_BAR_BORDER, SCROLL_TOP_BG, TAB_INACTIVE_COLOR } from "../../constants/colors";
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
  return (
    <View
      style={[
        styles.iconContainer,
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

/**
 * Fully custom tab bar — replaces BottomTabBar entirely.
 * BottomTabBar adds internal safe-area padding we cannot override,
 * so we render a simple row of Pressables instead.
 */
function CustomTabBar({ state, descriptors, navigation }: BottomTabBarProps) {
  const { tabBarTranslateY } = useTabBar();
  const { theme } = useTheme();
  const insets = useSafeAreaInsets();
  const tabBarBottom = Math.max(insets.bottom, 16) + 8;

  const animatedStyle = useAnimatedStyle(() => ({
    transform: [{ translateY: tabBarTranslateY.value }],
  }));

  return (
    <Animated.View style={[styles.tabBar, { bottom: tabBarBottom }, animatedStyle]}>
      {state.routes.map((route, index) => {
        const { options } = descriptors[route.key];
        const isFocused = state.index === index;

        const onPress = () => {
          const event = navigation.emit({
            type: "tabPress",
            target: route.key,
            canPreventDefault: true,
          });
          if (!isFocused && !event.defaultPrevented) {
            navigation.navigate(route.name, route.params);
          }
        };

        const onLongPress = () => {
          navigation.emit({ type: "tabLongPress", target: route.key });
        };

        const color = isFocused
          ? theme.accent
          : TAB_INACTIVE_COLOR;

        // Render the icon using the tabBarIcon option
        const icon = options.tabBarIcon?.({
          focused: isFocused,
          color,
          size: 24,
        });

        return (
          <Pressable
            key={route.key}
            accessibilityRole="button"
            accessibilityState={isFocused ? { selected: true } : {}}
            accessibilityLabel={options.tabBarAccessibilityLabel ?? options.title}
            onPress={onPress}
            onLongPress={onLongPress}
            style={styles.tabButton}
          >
            {icon}
          </Pressable>
        );
      })}
    </Animated.View>
  );
}

/** Small floating pill that appears when the tab bar is hidden */
function ScrollToTopPill() {
  const { tabBarTranslateY, scrollToTop } = useTabBar();
  const { theme } = useTheme();
  const insets = useSafeAreaInsets();

  const animatedStyle = useAnimatedStyle(() => {
    const opacity = interpolate(
      tabBarTranslateY.value,
      [50, 100],
      [0, 1],
      Extrapolation.CLAMP,
    );
    return {
      opacity,
      pointerEvents: opacity > 0.1 ? "auto" : "none",
    } as any;
  });

  return (
    <Animated.View style={[styles.scrollToTopContainer, { bottom: Math.max(insets.bottom, 16) + 12 }, animatedStyle]}>
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
      tabBar={(props) => <CustomTabBar {...props} />}
      screenOptions={{
        tabBarActiveTintColor: theme.accent,
        tabBarInactiveTintColor: TAB_INACTIVE_COLOR,
        tabBarShowLabel: false,
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
  tabBar: {
    position: "absolute",
    left: THEME.spacing.xxl,
    right: THEME.spacing.xxl,
    height: 64,
    borderRadius: 32,
    backgroundColor: TAB_BAR_BG,
    borderWidth: 1,
    borderColor: TAB_BAR_BORDER,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-evenly",
    shadowColor: "#000",
    shadowOffset: { width: 0, height: 8 },
    shadowOpacity: 0.4,
    shadowRadius: 24,
    elevation: 12,
  },
  tabButton: {
    flex: 1,
    alignItems: "center",
    justifyContent: "center",
    height: "100%",
  },
  iconContainer: {
    alignItems: "center",
    justifyContent: "center",
    width: 48,
    height: 40,
    borderRadius: THEME.radius.lg,
  },
  scrollToTopContainer: {
    position: "absolute",
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
