/**
 * HeaderBackButton — shared back-chevron button for Stack headers and custom
 * header rows.
 *
 * Mirrors the subscription screen pattern (chevron-back icon, 44x44 touch
 * target). Use in `Stack.Screen` via `headerLeft` or inline inside a custom
 * header row.
 */
import { Pressable, StyleSheet, View } from "react-native";
import { Ionicons } from "@expo/vector-icons";

import { MIN_TOUCH_TARGET } from "../../constants/config";
import { THEME } from "../../constants/theme";

const BACK_ICON_SIZE = 24;
const BACK_HIT_SLOP = { top: 8, bottom: 8, left: 8, right: 8 } as const;

interface HeaderBackButtonProps {
  onPress: () => void;
  accessibilityLabel?: string;
  tintColor?: string;
}

export function HeaderBackButton({
  onPress,
  accessibilityLabel = "Go back",
  tintColor = THEME.colors.textPrimary,
}: HeaderBackButtonProps) {
  return (
    <Pressable
      onPress={onPress}
      style={styles.button}
      accessibilityLabel={accessibilityLabel}
      accessibilityRole="button"
      hitSlop={BACK_HIT_SLOP}
    >
      <Ionicons name="chevron-back" size={BACK_ICON_SIZE} color={tintColor} />
    </Pressable>
  );
}

/**
 * Spacer matching HeaderBackButton dimensions — use on the right side of a
 * custom header row to balance a centered title.
 */
export function HeaderBackButtonSpacer() {
  return <View style={styles.button} />;
}

const styles = StyleSheet.create({
  button: {
    width: MIN_TOUCH_TARGET,
    height: MIN_TOUCH_TARGET,
    alignItems: "center",
    justifyContent: "center",
  },
});
