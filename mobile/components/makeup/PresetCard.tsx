import { Pressable, StyleSheet, View } from "react-native";
import Animated, { useAnimatedStyle, useSharedValue, withSpring } from "react-native-reanimated";
import { Ionicons } from "@expo/vector-icons";
import { THEME } from "../../constants/theme";
import { Body, Caption } from "../ui/Text";
import type { MakeupPresetDefinition } from "../../constants/presets";

interface PresetCardProps {
  preset: MakeupPresetDefinition;
  selected: boolean;
  onPress: () => void;
  accent: string;
}

const PRESET_ICONS: Record<string, keyof typeof Ionicons.glyphMap> = {
  natural_glow: "leaf-outline",
  soft_glam: "sparkles-outline",
  bold_red: "heart-outline",
  smoky_eye: "moon-outline",
  bridal: "flower-outline",
  dramatic_night: "star-outline",
  groomed: "cut-outline",
};

export function PresetCard({ preset, selected, onPress, accent }: PresetCardProps) {
  const scale = useSharedValue(1);
  const pressStyle = useAnimatedStyle(() => ({ transform: [{ scale: scale.value }] }));
  const icon = PRESET_ICONS[preset.slug] ?? "color-palette-outline";

  return (
    <Animated.View style={[styles.cell, pressStyle]}>
      <Pressable
        onPress={onPress}
        onPressIn={() => { scale.value = withSpring(0.97, THEME.animation.press); }}
        onPressOut={() => { scale.value = withSpring(1, THEME.animation.press); }}
        style={[
          styles.card,
          selected
            ? { borderColor: accent + THEME.alpha.strong, backgroundColor: accent + THEME.alpha.faint }
            : styles.cardInactive,
        ]}
        accessibilityRole="radio"
        accessibilityState={{ checked: selected }}
        accessibilityLabel={preset.displayName}
      >
        <View
          style={[
            styles.iconWrap,
            { backgroundColor: selected ? accent + THEME.alpha.soft : "rgba(255,255,255,0.04)" },
          ]}
        >
          <Ionicons
            name={icon}
            size={24}
            color={selected ? accent : THEME.colors.textMuted}
          />
        </View>
        <Body
          weight="semibold"
          color={selected ? "primary" : "secondary"}
          style={styles.name}
          numberOfLines={1}
        >
          {preset.displayName}
        </Body>
        <Caption
          color={selected ? "secondary" : "disabled"}
          style={styles.desc}
          numberOfLines={2}
        >
          {preset.description}
        </Caption>
      </Pressable>
    </Animated.View>
  );
}

const styles = StyleSheet.create({
  cell: {
    flexBasis: "48%",
    flexGrow: 1,
    flexShrink: 0,
  },
  card: {
    borderWidth: 1,
    borderRadius: THEME.radius.lg,
    borderCurve: "continuous",
    padding: THEME.spacing.md,
    minHeight: 130,
  },
  cardInactive: {
    backgroundColor: THEME.colors.surface,
    borderColor: THEME.colors.border,
  },
  iconWrap: {
    width: 40,
    height: 40,
    borderRadius: THEME.radius.sm,
    borderCurve: "continuous",
    alignItems: "center",
    justifyContent: "center",
    marginBottom: THEME.spacing.sm,
  },
  name: {
    marginBottom: 2,
    fontSize: 13,
  },
  desc: {
    lineHeight: 15,
    fontSize: 11,
  },
});
