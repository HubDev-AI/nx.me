import { Pressable, StyleSheet, View } from "react-native";
import { THEME } from "../../constants/theme";
import { Label } from "../ui/Text";
import type { MakeupIntensity } from "../../lib/makeup";
import { INTENSITY_LABELS } from "../../constants/presets";

interface IntensitySegmentedProps {
  value: MakeupIntensity;
  options: MakeupIntensity[];
  onChange: (v: MakeupIntensity) => void;
  accent: string;
}

export function IntensitySegmented({
  value,
  options,
  onChange,
  accent,
}: IntensitySegmentedProps) {
  return (
    <View style={styles.row}>
      {options.map((opt) => {
        const active = opt === value;
        return (
          <Pressable
            key={opt}
            style={[
              styles.segment,
              active
                ? { backgroundColor: accent + THEME.alpha.soft, borderColor: accent + THEME.alpha.strong }
                : styles.segmentInactive,
            ]}
            onPress={() => onChange(opt)}
            accessibilityRole="radio"
            accessibilityState={{ checked: active }}
          >
            <Label
              style={[styles.label, { color: active ? accent : THEME.colors.textSecondary }]}
            >
              {INTENSITY_LABELS[opt]}
            </Label>
          </Pressable>
        );
      })}
    </View>
  );
}

const styles = StyleSheet.create({
  row: {
    flexDirection: "row",
    gap: THEME.spacing.xs,
  },
  segment: {
    flex: 1,
    paddingVertical: THEME.spacing.sm,
    borderRadius: THEME.radius.md,
    borderCurve: "continuous",
    borderWidth: 1,
    alignItems: "center",
  },
  segmentInactive: {
    backgroundColor: THEME.colors.surface,
    borderColor: THEME.colors.border,
  },
  label: {
    fontSize: 11,
    letterSpacing: 0.5,
  },
});
