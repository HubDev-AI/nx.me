import { View, Text, StyleSheet } from "react-native";

import { BG_PAGE, TEXT_PRIMARY, TEXT_SECONDARY } from "../../constants/colors";

/** Login screen — placeholder for Story 2-3 */
export default function LoginScreen() {
  return (
    <View style={styles.container}>
      <Text style={styles.title}>Sign In</Text>
      <Text style={styles.subtitle}>Authentication coming in Story 2-3</Text>
    </View>
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
