import { Stack } from "expo-router";

import { THEME } from "../../constants/theme";

/**
 * Auth group layout -- no tab bar, clean auth flow with back navigation.
 * headerShown: false on the group so individual screens control their own header.
 */
export default function AuthLayout() {
  return (
    <Stack
      screenOptions={{
        headerStyle: { backgroundColor: THEME.colors.bg },
        headerTintColor: THEME.colors.textPrimary,
        headerShadowVisible: false,
        headerTitle: "",
        contentStyle: { backgroundColor: THEME.colors.bg },
      }}
    />
  );
}
