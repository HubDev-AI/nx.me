import { View, Text, StyleSheet } from "react-native";
import { useLocalSearchParams, Stack } from "expo-router";

import {
  BG_PAGE,
  BG_CARD,
  TEXT_PRIMARY,
  TEXT_SECONDARY,
  COLORS,
} from "../../constants/colors";

/**
 * Card detail view — deep link target for nxme.ai/{username}.
 * Full implementation in a later story; this renders the skeleton.
 */
export default function CardDetailScreen() {
  const { username } = useLocalSearchParams<{ username: string }>();

  return (
    <>
      <Stack.Screen
        options={{
          title: `@${username}`,
          headerStyle: { backgroundColor: BG_PAGE },
          headerTintColor: COLORS.neutral.dark[900],
          headerShadowVisible: false,
        }}
      />
      <View style={styles.container}>
        <View style={styles.card}>
          <View style={styles.avatar}>
            <Text style={styles.avatarText}>
              {username?.charAt(0).toUpperCase() ?? "?"}
            </Text>
          </View>
          <Text style={styles.username}>@{username}</Text>
          <Text style={styles.subtitle}>Card details loading...</Text>
        </View>
      </View>
    </>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: BG_PAGE,
    alignItems: "center",
    paddingTop: 48,
    padding: 24,
  },
  card: {
    backgroundColor: BG_CARD,
    borderRadius: 16,
    padding: 32,
    alignItems: "center",
    width: "100%",
    maxWidth: 360,
  },
  avatar: {
    width: 80,
    height: 80,
    borderRadius: 40,
    backgroundColor: COLORS.after[500],
    alignItems: "center",
    justifyContent: "center",
    marginBottom: 16,
  },
  avatarText: {
    fontSize: 32,
    fontWeight: "700",
    color: "#FFFFFF",
  },
  username: {
    fontSize: 20,
    fontWeight: "700",
    color: TEXT_PRIMARY,
    marginBottom: 8,
  },
  subtitle: {
    fontSize: 14,
    color: TEXT_SECONDARY,
  },
});
