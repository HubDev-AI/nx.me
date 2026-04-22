import { Pressable, StyleSheet } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { THEME } from "../../constants/theme";
import { Body } from "../ui/Text";

interface TryAnotherPresetButtonProps {
  onPress: () => void;
}

export function TryAnotherPresetButton({ onPress }: TryAnotherPresetButtonProps) {
  return (
    <Pressable onPress={onPress} style={styles.button} accessibilityRole="button">
      <Ionicons name="color-palette-outline" size={18} color={THEME.colors.textSecondary} />
      <Body color="secondary" weight="semibold">
        Try another preset
      </Body>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  button: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    gap: THEME.spacing.sm,
    paddingVertical: THEME.spacing.md,
    paddingHorizontal: THEME.spacing.xl,
    backgroundColor: THEME.colors.surface,
    borderRadius: THEME.radius.pill,
    borderWidth: 1,
    borderCurve: "continuous",
    borderColor: THEME.colors.border,
  },
});
