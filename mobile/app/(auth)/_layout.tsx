import { Stack } from "expo-router";

import { THEME } from "../../constants/theme";

/**
 * Auth group layout — no tab bar, clean auth flow with back navigation.
 * Per `expo:building-native-ui` skill: minimal back button, no header
 * shadow, theme-background, individual screens control headerShown.
 */
export default function AuthLayout() {
  return (
    <Stack
      screenOptions={{
        headerStyle: { backgroundColor: THEME.colors.bg },
        headerTintColor: THEME.colors.textPrimary,
        headerShadowVisible: false,
        headerTitle: "",
        headerBackButtonDisplayMode: "minimal",
        contentStyle: { backgroundColor: THEME.colors.bg },
      }}
    />
  );
}
