/**
 * BrandLabel — tiny "N X M E" label used in headers and auth screens.
 * Single source of truth for the brand wordmark styling.
 */
import { Text, StyleSheet } from "react-native";
import { FONTS } from "../../hooks/useFonts";

export function BrandLabel() {
  return <Text style={styles.label}>N X M E</Text>;
}

const styles = StyleSheet.create({
  label: {
    fontFamily: FONTS.bodyMedium,
    fontSize: 11,
    letterSpacing: 4,
    color: "rgba(255, 255, 255, 0.7)",
    textTransform: "uppercase",
  },
});
