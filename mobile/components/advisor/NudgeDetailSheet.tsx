/**
 * NudgeDetailSheet — bottom sheet showing a single nudge's full body.
 *
 * The feed card truncates body copy at three lines; tapping a card opens
 * this sheet so the user can read the whole nudge. The CTA chip
 * rendered on the card also renders here (same `next_step_label`, same
 * handler) so an unexpanded list tap still lets the user action the
 * nudge without bouncing back to the feed.
 */
import { useCallback, useRef, useState } from "react";
import {
  ActivityIndicator,
  Modal,
  Pressable,
  ScrollView,
  StyleSheet,
  View,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { Ionicons } from "@expo/vector-icons";

import { THEME } from "../../constants/theme";
import { useTheme } from "../../lib/theme-context";
import { Body, Caption, Heading } from "../ui/Text";
import { formatTimeAgo } from "../../lib/format";
import {
  MIN_TOUCH_TARGET,
  POST_GLOWUP_LABEL,
} from "../../constants/config";
import type { Nudge } from "../../lib/advisor";

/**
 * Fixed icon for every `post_glowup` card. Mirrors `NudgeCard`'s
 * `POST_GLOWUP_ICON` — kept inline here instead of imported so the two
 * surfaces can diverge without spooky-action coupling (chip vs. sheet
 * can pick different icons if design asks).
 */
const POST_GLOWUP_ICON: React.ComponentProps<typeof Ionicons>["name"] =
  "bulb-outline";

interface NudgeDetailSheetProps {
  nudge: Nudge | null;
  onClose: () => void;
  /**
   * Called when the CTA button in the sheet is tapped. Same contract
   * as `NudgeCard.onCtaPress` so the parent can route through a single
   * handler.
   */
  onCtaPress?: (nudge: Nudge) => Promise<void> | void;
}

export function NudgeDetailSheet({
  nudge,
  onClose,
  onCtaPress,
}: NudgeDetailSheetProps) {
  const { theme } = useTheme();
  const handleBackdropPress = useCallback(() => onClose(), [onClose]);

  // Single-flight guard — mirrors NudgeCard so a double-tap inside the
  // sheet can't fire two requests.
  const isFiringRef = useRef(false);
  const [isFiring, setIsFiring] = useState(false);

  const handleCtaPress = useCallback(async () => {
    if (!nudge || !onCtaPress) return;
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

  const showCta =
    !!onCtaPress && !!nudge && nudge.next_step_label.trim().length > 0;

  return (
    <Modal
      visible={nudge !== null}
      animationType="fade"
      transparent
      onRequestClose={onClose}
      statusBarTranslucent
    >
      {/* Backdrop — tappable to dismiss; `pointerEvents` ensures the
          child card absorbs its own taps without propagating. */}
      <Pressable
        style={styles.backdrop}
        onPress={handleBackdropPress}
        accessibilityLabel="Dismiss nudge"
        accessibilityRole="button"
      />
      <SafeAreaView
        style={styles.sheetContainer}
        edges={["bottom"]}
        pointerEvents="box-none"
      >
        <View style={styles.sheet}>
          <View style={styles.header}>
            <View
              style={[
                styles.iconContainer,
                { backgroundColor: theme.accentMuted },
              ]}
            >
              <Ionicons
                name={POST_GLOWUP_ICON}
                size={22}
                color={theme.accent}
              />
            </View>
            <View style={styles.titleColumn}>
              <Heading size="md" display={false}>
                {POST_GLOWUP_LABEL}
              </Heading>
              {nudge && (
                <Caption color="muted">
                  {formatTimeAgo(nudge.created_at)}
                </Caption>
              )}
            </View>
            <Pressable
              onPress={onClose}
              style={styles.closeButton}
              accessibilityLabel="Close"
              accessibilityRole="button"
              hitSlop={8}
            >
              <Ionicons
                name="close"
                size={22}
                color={THEME.colors.textSecondary}
              />
            </Pressable>
          </View>

          <ScrollView
            style={styles.body}
            contentContainerStyle={styles.bodyContent}
            showsVerticalScrollIndicator={false}
          >
            <Body color="primary" style={styles.bodyText}>
              {nudge?.body ?? ""}
            </Body>
          </ScrollView>

          {showCta && nudge && (
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
                  style={[styles.ctaLabel, { color: THEME.colors.bg }]}
                  numberOfLines={1}
                >
                  {nudge.next_step_label}
                </Body>
              )}
            </Pressable>
          )}
        </View>
      </SafeAreaView>
    </Modal>
  );
}

const styles = StyleSheet.create({
  backdrop: {
    ...StyleSheet.absoluteFillObject,
    backgroundColor: "rgba(0, 0, 0, 0.65)",
  },
  sheetContainer: {
    flex: 1,
    justifyContent: "flex-end",
  },
  sheet: {
    backgroundColor: THEME.colors.bg,
    borderTopLeftRadius: THEME.radius.xl,
    borderTopRightRadius: THEME.radius.xl,
    borderCurve: "continuous",
    paddingTop: THEME.spacing.lg,
    paddingHorizontal: THEME.spacing.lg,
    paddingBottom: THEME.spacing.lg,
    maxHeight: "80%",
    borderTopWidth: StyleSheet.hairlineWidth,
    borderLeftWidth: StyleSheet.hairlineWidth,
    borderRightWidth: StyleSheet.hairlineWidth,
    borderColor: THEME.colors.glassBorder,
  },
  header: {
    flexDirection: "row",
    alignItems: "center",
    gap: THEME.spacing.md,
    marginBottom: THEME.spacing.md,
  },
  iconContainer: {
    width: 40,
    height: 40,
    borderRadius: 20,
    alignItems: "center",
    justifyContent: "center",
  },
  titleColumn: {
    flex: 1,
    gap: THEME.spacing.xs / 2,
  },
  closeButton: {
    width: MIN_TOUCH_TARGET,
    height: MIN_TOUCH_TARGET,
    alignItems: "center",
    justifyContent: "center",
  },
  body: {
    flexGrow: 0,
  },
  bodyContent: {
    paddingVertical: THEME.spacing.sm,
  },
  bodyText: {
    lineHeight: 22,
  },
  cta: {
    alignSelf: "flex-start",
    borderRadius: THEME.radius.pill,
    borderCurve: "continuous",
    paddingHorizontal: THEME.spacing.xl,
    paddingVertical: THEME.spacing.sm,
    minHeight: MIN_TOUCH_TARGET,
    alignItems: "center",
    justifyContent: "center",
    marginTop: THEME.spacing.md,
  },
  ctaPressed: {
    opacity: 0.85,
  },
  ctaLabel: {
    textAlign: "center",
  },
});
