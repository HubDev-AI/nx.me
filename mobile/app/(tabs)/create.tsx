import { View, Text, StyleSheet } from "react-native";

import {
  BG_PAGE,
  TEXT_PRIMARY,
  TEXT_SECONDARY,
  COLORS,
} from "../../constants/colors";

/** Create / Upload tab — placeholder for future story */
export default function CreateScreen() {
  return (
    <View style={styles.container}>
      <View style={styles.iconCircle}>
        <Text style={styles.plus}>+</Text>
      </View>
      <Text style={styles.title}>Create</Text>
      <Text style={styles.subtitle}>Upload a photo for your glow-up</Text>
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
  iconCircle: {
    width: 64,
    height: 64,
    borderRadius: 32,
    backgroundColor: COLORS.after[500],
    alignItems: "center",
    justifyContent: "center",
    marginBottom: 16,
  },
  plus: {
    fontSize: 32,
    fontWeight: "300",
    color: "#FFFFFF",
    marginTop: -2,
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
