import { Stack } from "expo-router";

import { BG_PAGE, COLORS } from "../../constants/colors";

/**
 * Auth group layout -- no tab bar, clean auth flow with back navigation.
 * headerShown: false on the group so individual screens control their own header.
 */
export default function AuthLayout() {
  return (
    <Stack
      screenOptions={{
        headerStyle: { backgroundColor: BG_PAGE },
        headerTintColor: COLORS.neutral.dark[900],
        headerShadowVisible: false,
        headerTitle: "",
        contentStyle: { backgroundColor: BG_PAGE },
      }}
    />
  );
}
