/**
 * NudgeCard — single actionable nudge row.
 *
 * Unread nudges show a coral dot indicator; tapping anywhere outside the
 * CTA chip opens the detail sheet and marks the nudge read. Top-5 cards
 * (by newest-first order in the feed) render an in-card CTA chip whose
 * label comes from `nudge.next_step_label`; the quieter variant shown
 * for older cards drops the chip but keeps the body + chrome. Chrome is
 * static — the backend collapsed to a single `post_glowup` trigger in
 * Unit 3, so the label and icon no longer vary per nudge.
 */
import { memo, useCallback, useRef, useState } from "react";
import {
  ActivityIndicator,
  Pressable,
  StyleSheet,
  View,
} from "react-native";
import { Ionicons } from "@expo/vector-icons";

import { THEME } from "../../constants/theme";
import { useTheme } from "../../lib/theme-context";
import { Body, Caption } from "../ui/Text";
import {
  MIN_TOUCH_TARGET,
  NUDGES_CTA_VISIBLE_RECENT_CAP,
  POST_GLOWUP_LABEL,
} from "../../constants/config";
import { formatTimeAgo } from "../../lib/format";
import type { Nudge } from "../../lib/advisor";

/**
 * Fixed Ionicon for every `post_glowup` card. Historical `nudgeIcon()`
 * helpers had no explicit `post_glowup` case and fell through to
 * `bulb-outline`; this constant preserves that choice without keeping
 * the dead per-trigger switch statement.
 */
const POST_GLOWUP_ICON: React.ComponentProps<typeof Ionicons>["name"] =
  "bulb-outline";

interface NudgeCardProps {
  nudge: Nudge;
  /**
   * Newest-first position in the feed. Used to decide whether the
   * actionable CTA chip renders — only the first
   * `NUDGES_CTA_VISIBLE_RECENT_CAP` cards show it. Defaults to `0` so
   * callers that forget to pass the index don't silently hide every
   * chip.
   */
  index?: number;
  /** Called when the card body (not the CTA) is tapped. */
  onPress: (nudge: Nudge) => void;
  /**
   * Called when the CTA chip is tapped. Parent owns routing + error
   * handling + "stale nudge" refresh. Kept as a pass-through so the
   * card stays presentational.
   */
  onCtaPress?: (nudge: Nudge) => Promise<void> | void;
}

function NudgeCardInner({
  nudge,
  index = 0,
  onPress,
  onCtaPress,
}: NudgeCardProps) {
  const { theme } = useTheme();
  const isRead = nudge.read_at !== null;
  const showCta =
    index < NUDGES_CTA_VISIBLE_RECENT_CAP &&
    nudge.next_step_label.trim().length > 0;

  const handlePress = useCallback(() => onPress(nudge), [nudge, onPress]);

  // -------------------------------------------------------------------------
  // CTA press — single-flight guard via ref + UI spinner.
  // The ref is the actual re-entrancy guard; the `isFiring` state only
  // drives the spinner. Disabled UI is a bug per napkin rule 9, so the
  // Pressable stays tappable — the ref just blocks the second call.
  // -------------------------------------------------------------------------
  const isFiringRef = useRef(false);
  const [isFiring, setIsFiring] = useState(false);

  const handleCtaPress = useCallback(async () => {
    if (!onCtaPress) return;
    if (isFiringRef.current) return;
    isFiringRef.current = true;
    setIsFiring(true);
    try {
      await onCtaPress(nudge);
    } finally {
      isFiringRef.current = false;
      setIsFiring(false);
    }
  }, [nudge, onCtaPress]);

  return (
    <Pressable
      onPress={handlePress}
      style={({ pressed }) => [
        styles.card,
        !isRead && styles.unreadCard,
        pressed && styles.pressed,
      ]}
      accessibilityLabel={`${isRead ? "" : "Unread "}nudge: ${POST_GLOWUP_LABEL}`}
      accessibilityRole="button"
      accessibilityHint="Tap to open the full nudge"
    >
      {/* Icon */}
      <View
        style={[styles.iconContainer, { backgroundColor: theme.accentMuted }]}
      >
        <Ionicons
          name={POST_GLOWUP_ICON}
          size={22}
          color={isRead ? THEME.colors.textSecondary : theme.accent}
        />
      </View>

      {/* Content */}
      <View style={styles.content}>
        <View style={styles.titleRow}>
          <Body
            weight={isRead ? "semibold" : "bold"}
            color="primary"
            numberOfLines={1}
            style={styles.title}
          >
            {POST_GLOWUP_LABEL}
          </Body>
          {!isRead && (
            <View
              style={[styles.unreadDot, { backgroundColor: theme.accent }]}
            />
          )}
        </View>
        <Caption color="secondary" numberOfLines={3} style={styles.body}>
          {nudge.body}
        </Caption>

        {showCta && (
          <Pressable
            onPress={handleCtaPress}
            style={({ pressed }) => [
              styles.cta,
              {
                backgroundColor: theme.accent,
                ...THEME.shadow.glow(theme.accent),
              },
              pressed && styles.ctaPressed,
            ]}
            accessibilityLabel={nudge.next_step_label}
            accessibilityRole="button"
            hitSlop={8}
          >
            {isFiring ? (
              <ActivityIndicator size="small" color={THEME.colors.bg} />
            ) : (
              <Body
                weight="semibold"
                color="primary"
                numberOfLines={1}
                style={[styles.ctaLabel, { color: THEME.colors.bg }]}
              >
                {nudge.next_step_label}
              </Body>
            )}
          </Pressable>
        )}

        <Caption color="muted" style={styles.time}>
          {formatTimeAgo(nudge.created_at)}
        </Caption>
      </View>
    </Pressable>
  );
}

export const NudgeCard = memo(NudgeCardInner);

const styles = StyleSheet.create({
  card: {
    flexDirection: "row",
    backgroundColor: THEME.colors.glass,
    borderRadius: THEME.radius.lg,
    borderCurve: "continuous",
    borderWidth: 1,
    borderColor: THEME.colors.glassBorder,
    padding: THEME.spacing.lg,
    gap: THEME.spacing.md,
    minHeight: MIN_TOUCH_TARGET,
    ...THEME.shadow.glass,
  },
  unreadCard: {
    backgroundColor: THEME.colors.glassLight,
    borderColor: THEME.colors.glassBorder,
  },
  pressed: {
    opacity: 0.8,
  },
  iconContainer: {
    width: 36,
    height: 36,
    borderRadius: 18,
    alignItems: "center",
    justifyContent: "center",
    marginTop: THEME.spacing.xs / 2,
  },
  content: {
    flex: 1,
    gap: THEME.spacing.xs,
  },
  titleRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: THEME.spacing.sm,
  },
  title: {
    flex: 1,
  },
  unreadDot: {
    width: 8,
    height: 8,
    borderRadius: 4,
  },
  body: {
    lineHeight: 20,
  },
  cta: {
    alignSelf: "flex-start",
    borderRadius: THEME.radius.pill,
    borderCurve: "continuous",
    paddingHorizontal: THEME.spacing.lg,
    paddingVertical: THEME.spacing.sm,
    minHeight: MIN_TOUCH_TARGET,
    alignItems: "center",
    justifyContent: "center",
    marginTop: THEME.spacing.sm,
  },
  ctaPressed: {
    opacity: 0.85,
  },
  ctaLabel: {
    textAlign: "center",
  },
  time: {
    marginTop: THEME.spacing.xs / 2,
  },
});
