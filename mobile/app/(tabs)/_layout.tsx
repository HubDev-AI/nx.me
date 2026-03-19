import { Tabs } from "expo-router";
import { Ionicons } from "@expo/vector-icons";
import { View, StyleSheet } from "react-native";

import {
  TAB_ACTIVE_COLOR,
  TAB_INACTIVE_COLOR,
  BG_PAGE,
  COLORS,
} from "../../constants/colors";

type IoniconsName = React.ComponentProps<typeof Ionicons>["name"];

interface TabIconProps {
  name: IoniconsName;
  color: string;
  focused: boolean;
}

/** Tab icon with 2px coral top strip when active */
function TabIcon({ name, color, focused }: TabIconProps) {
  return (
    <View style={styles.iconContainer} accessible={false}>
      <View
        style={[
          styles.activeStrip,
          { backgroundColor: focused ? TAB_ACTIVE_COLOR : "transparent" },
        ]}
      />
      <Ionicons name={name} size={24} color={color} style={styles.icon} />
    </View>
  );
}

export default function TabLayout() {
  return (
    <Tabs
      screenOptions={{
        tabBarActiveTintColor: TAB_ACTIVE_COLOR,
        tabBarInactiveTintColor: TAB_INACTIVE_COLOR,
        tabBarStyle: {
          backgroundColor: BG_PAGE,
          borderTopColor: COLORS.neutral.dark[400],
          borderTopWidth: StyleSheet.hairlineWidth,
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
  },
  activeStrip: {
    width: 24,
    height: 2,
    borderRadius: 1,
    marginBottom: 4,
  },
  icon: {
    marginBottom: -2,
  },
});
