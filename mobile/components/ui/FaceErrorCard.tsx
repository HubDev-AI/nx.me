import { StyleSheet, View } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { THEME } from "../../constants/theme";
import { useTheme } from "../../lib/theme-context";
import { Body, Caption, Heading } from "./Text";
import { Button } from "./Button";
import type { AppError, FaceErrorZone } from "../../lib/errors";

interface FaceErrorCardProps {
  error: Extract<AppError, { kind: "faceAnalysis" }>;
  onTryAgain: () => void;
}

const TIPS: readonly string[] = [
  "Good lighting on your face",
  "Clear, front-facing angle",
  "Remove sunglasses or hats",
];

export function FaceErrorCard({ error, onTryAgain }: FaceErrorCardProps) {
  const { theme } = useTheme();
  return (
    <View style={styles.card} accessibilityRole="alert">
      <FaceDiagram highlightedZone={error.zone} />

      <Heading size="md" display={false} color="primary" style={styles.title}>
        {error.message}
      </Heading>

      {error.reason ? (
        <Body color="secondary" style={styles.reason}>
          {error.reason}
        </Body>
      ) : null}

      <View style={styles.tipsCard}>
        <Caption weight="semibold" color="secondary" style={styles.tipsHeader}>
          Common reasons
        </Caption>
        {TIPS.map((tip) => (
          <View key={tip} style={styles.tipRow}>
            <Ionicons
              name="checkmark-circle-outline"
              size={14}
              color={theme.accent}
            />
            <Caption color="primary">{tip}</Caption>
          </View>
        ))}
      </View>

      <Button
        title="Try a different photo"
        onPress={onTryAgain}
        variant="primary"
        size="md"
        block
        accentColor={theme.accent}
      />
    </View>
  );
}

function FaceDiagram({ highlightedZone }: { highlightedZone?: FaceErrorZone }) {
  const isHighlighted = highlightedZone !== undefined;
  const color = isHighlighted ? THEME.colors.destructive : THEME.colors.textSecondary;
  return (
    <View style={styles.diagram}>
      <Ionicons name="person-circle-outline" size={72} color={color} />
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    padding: THEME.spacing.xl,
    borderRadius: THEME.radius.lg,
    borderCurve: "continuous",
    backgroundColor: THEME.colors.surfaceElevated,
    borderWidth: 1,
    borderColor: THEME.colors.border,
    gap: THEME.spacing.md,
    alignItems: "center",
  },
  diagram: {
    alignItems: "center",
    justifyContent: "center",
  },
  title: {
    textAlign: "center",
  },
  reason: {
    textAlign: "center",
  },
  tipsCard: {
    alignSelf: "stretch",
    backgroundColor: THEME.colors.surface,
    borderRadius: THEME.radius.md,
    borderCurve: "continuous",
    borderWidth: 1,
    borderColor: THEME.colors.border,
    padding: THEME.spacing.md,
    gap: THEME.spacing.sm,
  },
  tipsHeader: {
    letterSpacing: 0.8,
  },
  tipRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: THEME.spacing.sm,
  },
});
