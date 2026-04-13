/**
 * ProcessingHUD — unified progress card for the glow-up flow.
 *
 * Replaces the old single-spinner loading card with:
 *  - 3-step indicator (Upload → Analyze → Generate) with checkmarks on
 *    completed steps and a pulsing dot on the active one
 *  - Linear progress bar estimated from `elapsedSeconds` for smooth motion
 *  - Tabular-nums timer so the digits do not jitter
 *  - Hint copy that swaps at 3s / 15s / 30s to reduce anxiety on slow runs
 */
import { useEffect } from "react";
import { StyleSheet, View } from "react-native";
import Animated, {
  Easing,
  FadeIn,
  useAnimatedStyle,
  useSharedValue,
  withTiming,
} from "react-native-reanimated";
import { Ionicons } from "@expo/vector-icons";
import { THEME } from "../../constants/theme";
import { useTheme } from "../../lib/theme-context";
import { Caption, Heading } from "../ui/Text";

export type ProcessingPhase = "uploading" | "analyzing" | "generating";

interface ProcessingHUDProps {
  phase: ProcessingPhase;
  elapsedSeconds: number;
}

const STEPS: { key: ProcessingPhase; label: string }[] = [
  { key: "uploading", label: "Upload" },
  { key: "analyzing", label: "Analyze" },
  { key: "generating", label: "Generate" },
];

const HINT_EARLY = "Usually takes 20–30s.";
const HINT_MID = "Almost there…";
const HINT_LATE = "Still working — worth the wait.";
const HINT_APPEAR_AT = 3;
const HINT_MID_AT = 15;
const HINT_LATE_AT = 30;

const DOT_SIZE = 20;
const CONNECTOR_HEIGHT = 2;
const TRACK_HEIGHT = 4;
const PROGRESS_ANIM_MS = 800;

function estimatedProgress(phase: ProcessingPhase, seconds: number): number {
  switch (phase) {
    case "uploading":
      return Math.min(0.25, (seconds / 5) * 0.25);
    case "analyzing":
      return 0.25 + Math.min(0.35, (seconds / 15) * 0.35);
    case "generating":
      return 0.6 + Math.min(0.38, (seconds / 20) * 0.38);
  }
}

function hintForSeconds(s: number): string {
  if (s >= HINT_LATE_AT) return HINT_LATE;
  if (s >= HINT_MID_AT) return HINT_MID;
  return HINT_EARLY;
}

function formatElapsed(seconds: number): string {
  const mins = Math.floor(seconds / 60);
  const secs = seconds % 60;
  if (mins === 0) return `${secs}s`;
  return `${mins}m ${secs.toString().padStart(2, "0")}s`;
}

export default function ProcessingHUD({ phase, elapsedSeconds }: ProcessingHUDProps) {
  const { theme } = useTheme();
  const activeIndex = STEPS.findIndex((s) => s.key === phase);
  const progressValue = estimatedProgress(phase, elapsedSeconds);
  const progress = useSharedValue(0);

  useEffect(() => {
    progress.value = withTiming(progressValue, {
      duration: PROGRESS_ANIM_MS,
      easing: Easing.out(Easing.cubic),
    });
  }, [progressValue, progress]);

  const barStyle = useAnimatedStyle(() => ({ width: `${progress.value * 100}%` }));

  const showHint = elapsedSeconds >= HINT_APPEAR_AT;
  const activeStepLabel = STEPS[activeIndex]?.label ?? "Processing";

  return (
    <Animated.View
      entering={FadeIn.duration(200)}
      style={styles.card}
      accessibilityLabel={`${activeStepLabel}, ${elapsedSeconds} seconds elapsed`}
      accessibilityRole="progressbar"
      accessibilityValue={{ now: Math.round(progressValue * 100), min: 0, max: 100 }}
    >
      <View style={styles.stepsRow}>
        {STEPS.map((step, i) => {
          const done = i < activeIndex;
          const active = i === activeIndex;
          const dotColor = done || active ? theme.accent : THEME.colors.border;
          const dotBg = done ? theme.accent : "transparent";
          const leftActive = i > 0 && i <= activeIndex;
          const rightActive = i < STEPS.length - 1 && i < activeIndex;
          return (
            <View key={step.key} style={styles.stepItem}>
              <View style={styles.dotLine}>
                <View
                  style={[
                    styles.connector,
                    i === 0 && styles.connectorInvisible,
                    leftActive && { backgroundColor: theme.accent },
                  ]}
                />
                <View style={[styles.dot, { borderColor: dotColor, backgroundColor: dotBg }]}>
                  {done ? (
                    <Ionicons name="checkmark" size={12} color={THEME.colors.bg} />
                  ) : active ? (
                    <View style={[styles.innerDot, { backgroundColor: theme.accent }]} />
                  ) : null}
                </View>
                <View
                  style={[
                    styles.connector,
                    i === STEPS.length - 1 && styles.connectorInvisible,
                    rightActive && { backgroundColor: theme.accent },
                  ]}
                />
              </View>
              <Caption
                weight={active ? "semibold" : "regular"}
                color={active || done ? "primary" : "muted"}
                style={styles.stepLabel}
              >
                {step.label}
              </Caption>
            </View>
          );
        })}
      </View>

      <View style={styles.track}>
        <Animated.View style={[styles.bar, { backgroundColor: theme.accent }, barStyle]} />
      </View>

      <Heading size="lg" display={false} style={styles.timer}>
        {formatElapsed(elapsedSeconds)}
      </Heading>

      {showHint ? (
        <Caption color="muted" style={styles.hint}>
          {hintForSeconds(elapsedSeconds)}
        </Caption>
      ) : null}
    </Animated.View>
  );
}

const styles = StyleSheet.create({
  card: {
    backgroundColor: THEME.colors.surfaceElevated,
    borderRadius: THEME.radius.lg,
    borderCurve: "continuous",
    borderWidth: 1,
    borderColor: THEME.colors.border,
    padding: THEME.spacing.xl,
    gap: THEME.spacing.lg,
  },
  stepsRow: {
    flexDirection: "row",
    alignItems: "flex-start",
  },
  stepItem: {
    flex: 1,
    alignItems: "center",
    gap: THEME.spacing.sm,
  },
  dotLine: {
    flexDirection: "row",
    alignItems: "center",
    width: "100%",
  },
  connector: {
    flex: 1,
    height: CONNECTOR_HEIGHT,
    backgroundColor: THEME.colors.border,
  },
  connectorInvisible: {
    backgroundColor: "transparent",
  },
  dot: {
    width: DOT_SIZE,
    height: DOT_SIZE,
    borderRadius: DOT_SIZE / 2,
    borderWidth: 2,
    alignItems: "center",
    justifyContent: "center",
  },
  innerDot: {
    width: DOT_SIZE / 2,
    height: DOT_SIZE / 2,
    borderRadius: DOT_SIZE / 4,
  },
  stepLabel: {
    textAlign: "center",
  },
  track: {
    width: "100%",
    height: TRACK_HEIGHT,
    borderRadius: TRACK_HEIGHT / 2,
    backgroundColor: THEME.colors.border,
    overflow: "hidden",
  },
  bar: {
    height: "100%",
    borderRadius: TRACK_HEIGHT / 2,
  },
  timer: {
    fontVariant: ["tabular-nums"],
    textAlign: "center",
  },
  hint: {
    textAlign: "center",
  },
});
