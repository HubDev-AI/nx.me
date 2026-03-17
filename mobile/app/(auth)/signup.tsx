import { View, Text, StyleSheet } from "react-native";
import { useLocalSearchParams, Stack } from "expo-router";

import {
  BG_PAGE,
  TEXT_PRIMARY,
  TEXT_SECONDARY,
  COLORS,
} from "../../constants/colors";

/**
 * Signup screen — deep link target for nxme.ai/signup?card={username}.
 * The `card` param tracks which card brought the user to sign up.
 * Full implementation in Story 2-3.
 */
export default function SignupScreen() {
  const { card } = useLocalSearchParams<{ card?: string }>();

  return (
    <>
      <Stack.Screen
        options={{
          title: "Sign Up",
          headerStyle: { backgroundColor: BG_PAGE },
          headerTintColor: COLORS.neutral.dark[900],
          headerShadowVisible: false,
        }}
      />
      <View style={styles.container}>
        <Text style={styles.title}>Create Account</Text>
        {card ? (
          <Text style={styles.subtitle}>
            Invited via @{card}&apos;s card
          </Text>
        ) : (
          <Text style={styles.subtitle}>Sign up coming in Story 2-3</Text>
        )}
      </View>
    </>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: BG_PAGE,
    alignItems: "center",
    justifyContent: "center",
    padding: 24,
  },
  title: {
    fontSize: 24,
    fontWeight: "700",
    color: TEXT_PRIMARY,
    marginBottom: 8,
  },
  subtitle: {
    fontSize: 16,
    color: TEXT_SECONDARY,
  },
});
