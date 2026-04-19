/**
 * ShareDialog — bottom-sheet modal exposing Save / Share / Publish rows
 * with plain-language disclosure of what each action does.
 *
 * Visibility rules (computed on render from `useCapabilities()` + job state):
 *   - Save row    → shown when `saved_at` is null AND user can edit profile
 *                   (real users always; guests when auth_required=false).
 *   - Share row   → always shown.
 *   - Publish row → shown when `canPublishGlowup` is true AND `post_id`
 *                   is null (not yet published).
 *
 * The dialog always opens — no one-row skip (plan decision). When the
 * user taps Publish, the rows view is replaced in-place by a confirm
 * panel (Cancel / Publish buttons). No second modal is stacked.
 *
 * State ownership:
 *   - `visible`, `saveState`, `isPublishing`, `publishError` are parent-owned.
 *     Parent closes the dialog on Save/Publish success. Share is
 *     fire-and-forget from this component; the parent (Unit 8) owns the
 *     auto-save + native-share chain and closes the dialog after invoking
 *     it.
 *   - `mode` ("rows" | "confirm") is local. It resets to "rows" whenever
 *     `visible` flips to false so a re-open never flashes a stale panel.
 *
 * Shape follows `mobile/components/subscription/CancelSubscriptionSheet.tsx`
 * (Modal + Reanimated backdrop + slide-up sheet) and uses the unified
 * `Button` (not the private `ActionButton` in ResultActions) for the
 * confirm-panel actions.
 *
 * Copy strings are placeholders pending writer review — see the
 * `TODO(writer-review)` markers. Per plan §Unit 7 and
 * `feedback_female_user_targeting`, writer review blocks merge.
 */
import { useCallback, useEffect, useRef, useState } from "react";
import {
  Modal,
  Pressable,
  StyleSheet,
  View,
} from "react-native";
import Animated, {
  runOnJS,
  useAnimatedStyle,
  useSharedValue,
  withSpring,
  withTiming,
} from "react-native-reanimated";
import { Ionicons } from "@expo/vector-icons";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { THEME } from "../../constants/theme";
import { OVERLAY_MEDIUM } from "../../constants/colors";
import { PAYWALL_ANIMATION, MIN_TOUCH_TARGET } from "../../constants/config";
import { hapticLight, hapticMedium } from "../../lib/haptics";
import { useCapabilities } from "../../lib/capabilities";
import { Body, Caption, Heading } from "../ui/Text";
import { Button } from "../ui/Button";
import type { SaveState } from "./ResultActions";

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const ENTER_DURATION_MS = PAYWALL_ANIMATION.ENTER_DURATION_MS;
const EXIT_DURATION_MS = PAYWALL_ANIMATION.EXIT_DURATION_MS;
const SCRIM_OPACITY = PAYWALL_ANIMATION.SCRIM_OPACITY;
const BOTTOM_SHEET_RADIUS = THEME.radius.lg;
const CLOSE_HIT_SLOP = 16;
const ROW_ICON_SIZE = 22;
/** translateY starting / exit position (off-screen). */
const SHEET_OFFSCREEN_Y = 600;

// ---------------------------------------------------------------------------
// Copy — all strings placeholder pending writer review.
// ---------------------------------------------------------------------------

const TITLE = "Share your glow-up";

// TODO(writer-review): "Private. Only you can see it."
const SAVE_SUBTITLE = "Private. Only you can see it.";
const SAVE_TITLE = "Save";

// TODO(writer-review): "Sends the image and keeps it on your profile" —
// MUST disclose auto-save side-effect (R8, per plan).
const SHARE_SUBTITLE = "Sends the image and keeps it on your profile.";
const SHARE_TITLE = "Share";

// TODO(writer-review): "Public. Appears on the social feed and your
// card-web page."
const PUBLISH_SUBTITLE = "Public. Appears on the social feed and your card-web page.";
const PUBLISH_TITLE = "Publish to feed";

const PUBLISH_CONFIRM_TITLE = "Publish to the feed?";
// TODO(writer-review): "Your before/after will appear on the public feed
// and at nxme.ai/{username}." — MUST name public-ness.
const PUBLISH_CONFIRM_BODY =
  "Your before/after will appear on the public feed and on your public card-web page.";
const PUBLISH_CONFIRM_LABEL = "Publish";
const PUBLISH_CANCEL_LABEL = "Cancel";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface ShareDialogJob {
  id: string;
  saved_at: string | null;
  post_id: string | null;
  share_hash: string | null;
}

export interface ShareDialogProps {
  visible: boolean;
  onClose: () => void;
  job: ShareDialogJob;
  onSave: () => void;
  onShare: () => void;
  onPublish: () => void;
  /** Save-row flight state — owned by parent. Mirrors ResultActions. */
  saveState: SaveState;
  /**
   * Publish-in-flight flag — owned by parent. Drives the spinner on the
   * Publish confirm button. Cancel stays enabled (per
   * `feedback_disabled_button_ux`).
   */
  isPublishing?: boolean;
  /**
   * Inline error shown below the Publish confirm body when the parent's
   * POST /v1/posts call fails. The panel stays open so the user can
   * retry without dismissing.
   */
  publishError?: string | null;
}

type Mode = "rows" | "confirm";

// ---------------------------------------------------------------------------
// Row sub-component
// ---------------------------------------------------------------------------

interface DialogRowProps {
  iconName: React.ComponentProps<typeof Ionicons>["name"];
  title: string;
  subtitle: string;
  onPress: () => void;
  disabled?: boolean;
  accessibilityLabel: string;
  testID?: string;
}

function DialogRow({
  iconName,
  title,
  subtitle,
  onPress,
  disabled = false,
  accessibilityLabel,
  testID,
}: DialogRowProps) {
  const handlePress = useCallback(() => {
    if (disabled) return;
    hapticLight();
    onPress();
  }, [disabled, onPress]);

  return (
    <Pressable
      onPress={handlePress}
      disabled={disabled}
      style={({ pressed }) => [
        styles.row,
        pressed && !disabled && styles.rowPressed,
        disabled && styles.rowDisabled,
      ]}
      accessibilityRole="button"
      accessibilityLabel={accessibilityLabel}
      accessibilityState={{ disabled }}
      testID={testID}
    >
      <View style={styles.rowIcon}>
        <Ionicons
          name={iconName}
          size={ROW_ICON_SIZE}
          color={THEME.colors.textPrimary}
        />
      </View>
      <View style={styles.rowText}>
        <Body color="primary" weight="medium">
          {title}
        </Body>
        <Caption color="secondary">{subtitle}</Caption>
      </View>
    </Pressable>
  );
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function ShareDialog({
  visible,
  onClose,
  job,
  onSave,
  onShare,
  onPublish,
  saveState,
  isPublishing = false,
  publishError = null,
}: ShareDialogProps) {
  const insets = useSafeAreaInsets();
  const capabilities = useCapabilities();

  // Keep the modal mounted through the exit animation.
  const [mounted, setMounted] = useState(visible);
  const [mode, setMode] = useState<Mode>("rows");

  // Exit-animation race guard. A rapid re-open during the EXIT_DURATION_MS
  // window would otherwise fire the stale completion callback (enqueued
  // when the previous `visible=false` ran) and unmount the now-open
  // dialog — a visible flicker. Flipped to `true` when the exit animation
  // starts and back to `false` when a new open fires; the completion
  // callback checks the ref and no-ops when the dialog has been re-opened.
  const isClosingRef = useRef(false);

  const backdropOpacity = useSharedValue(0);
  const sheetTranslateY = useSharedValue(SHEET_OFFSCREEN_Y);

  const backdropStyle = useAnimatedStyle(() => ({
    opacity: backdropOpacity.value,
  }));

  const sheetStyle = useAnimatedStyle(() => ({
    transform: [{ translateY: sheetTranslateY.value }],
  }));

  /**
   * JS-thread tail for the exit animation. Runs the state resets only if
   * the dialog wasn't re-opened during the exit window — the `isClosingRef`
   * gate is the single source of truth for "should the stale exit
   * complete". A separate named callback keeps the `runOnJS` jump
   * unambiguous.
   */
  const handleExitComplete = useCallback(() => {
    if (!isClosingRef.current) return;
    isClosingRef.current = false;
    setMounted(false);
    setMode("rows");
  }, []);

  useEffect(() => {
    if (visible) {
      // Re-opening during a still-running exit animation — clear the
      // closing gate so any pending completion callback no-ops when it
      // finally fires. The animated values snap forward to the open
      // pose via withSpring below.
      isClosingRef.current = false;
      setMounted(true);
      backdropOpacity.value = withTiming(SCRIM_OPACITY, {
        duration: ENTER_DURATION_MS,
      });
      sheetTranslateY.value = withSpring(0, {
        damping: THEME.animation.press.damping,
        stiffness: THEME.animation.press.stiffness,
      });
    } else {
      isClosingRef.current = true;
      backdropOpacity.value = withTiming(0, { duration: EXIT_DURATION_MS });
      sheetTranslateY.value = withTiming(
        SHEET_OFFSCREEN_Y,
        { duration: EXIT_DURATION_MS },
        (finished) => {
          if (finished) {
            // Reset the internal panel state AFTER the exit animation
            // completes so the user doesn't see the confirm panel flicker
            // back to the rows view while the sheet is sliding away.
            // Guarantees a re-open always starts from the rows view.
            // The JS tail re-checks `isClosingRef` before running state
            // resets, so a rapid re-open won't unmount the live dialog.
            runOnJS(handleExitComplete)();
          }
        },
      );
    }
  }, [visible, backdropOpacity, sheetTranslateY, handleExitComplete]);

  // ---- Row visibility --------------------------------------------------

  const showSaveRow = job.saved_at === null && capabilities.canEditProfile;
  const showPublishRow =
    capabilities.canPublishGlowup && job.post_id === null;
  // Share is always rendered when the dialog opens.
  const showShareRow = true;

  // ---- Handlers --------------------------------------------------------

  const handleClose = useCallback(() => {
    // Don't let the user dismiss mid-publish — parent owns the lifecycle.
    if (isPublishing) return;
    hapticLight();
    onClose();
  }, [isPublishing, onClose]);

  const handleSave = useCallback(() => {
    onSave();
  }, [onSave]);

  const handleShare = useCallback(() => {
    // Fire-and-forget from this component. Unit 8 owns the blocking
    // auto-save + native-share chain and closes the dialog after.
    onShare();
  }, [onShare]);

  const handleRequestPublish = useCallback(() => {
    setMode("confirm");
  }, []);

  const handleCancelConfirm = useCallback(() => {
    // Per feedback_disabled_button_ux: Cancel stays live even if a publish
    // were somehow still in flight. In practice the parent closes the
    // dialog on success, so this just unwinds the panel when the user
    // backs out.
    hapticLight();
    setMode("rows");
  }, []);

  const handleConfirmPublish = useCallback(() => {
    hapticMedium();
    onPublish();
  }, [onPublish]);

  // ---------------------------------------------------------------------
  // Render
  // ---------------------------------------------------------------------

  return (
    <Modal
      visible={mounted}
      transparent
      animationType="none"
      onRequestClose={handleClose}
      statusBarTranslucent
    >
      <Animated.View
        style={[styles.scrim, backdropStyle]}
        pointerEvents="none"
      />

      <Pressable
        style={styles.dismissArea}
        onPress={handleClose}
        accessible={false}
      />

      <Animated.View
        style={[
          styles.sheet,
          sheetStyle,
          { paddingBottom: Math.max(insets.bottom, THEME.spacing.xl) },
        ]}
      >
        <View style={styles.dragIndicator} />

        <Pressable
          onPress={handleClose}
          disabled={isPublishing}
          style={styles.closeButton}
          accessibilityLabel="Close"
          accessibilityRole="button"
          hitSlop={CLOSE_HIT_SLOP}
          testID="share-dialog-close"
        >
          <Ionicons name="close" size={22} color={THEME.colors.textSecondary} />
        </Pressable>

        <View style={styles.content}>
          <Heading size="md" color="primary" style={styles.title}>
            {mode === "confirm" ? PUBLISH_CONFIRM_TITLE : TITLE}
          </Heading>

          {mode === "rows" ? (
            <View style={styles.rows}>
              {showSaveRow && (
                <DialogRow
                  iconName={
                    saveState === "saved"
                      ? "checkmark-circle"
                      : "bookmark-outline"
                  }
                  title={SAVE_TITLE}
                  subtitle={SAVE_SUBTITLE}
                  onPress={handleSave}
                  disabled={saveState !== "pending"}
                  accessibilityLabel={SAVE_TITLE}
                  testID="share-dialog-row-save"
                />
              )}

              {showShareRow && (
                <>
                  {showSaveRow && <View style={styles.divider} />}
                  <DialogRow
                    iconName="share-outline"
                    title={SHARE_TITLE}
                    subtitle={SHARE_SUBTITLE}
                    onPress={handleShare}
                    accessibilityLabel={SHARE_TITLE}
                    testID="share-dialog-row-share"
                  />
                </>
              )}

              {showPublishRow && (
                <>
                  <View style={styles.divider} />
                  <DialogRow
                    iconName="globe-outline"
                    title={PUBLISH_TITLE}
                    subtitle={PUBLISH_SUBTITLE}
                    onPress={handleRequestPublish}
                    accessibilityLabel={PUBLISH_TITLE}
                    testID="share-dialog-row-publish"
                  />
                </>
              )}
            </View>
          ) : (
            <View style={styles.confirmPanel}>
              <Body color="secondary" style={styles.confirmBody}>
                {PUBLISH_CONFIRM_BODY}
              </Body>

              {publishError != null && (
                <Body color="destructive" style={styles.confirmError}>
                  {publishError}
                </Body>
              )}

              <View style={styles.confirmButtons}>
                <View style={styles.confirmButtonSlot}>
                  <Button
                    title={PUBLISH_CANCEL_LABEL}
                    onPress={handleCancelConfirm}
                    variant="outline"
                    size="md"
                    block
                    haptic="none"
                    testID="share-dialog-confirm-cancel"
                  />
                </View>
                <View style={styles.confirmButtonSlot}>
                  <Button
                    title={PUBLISH_CONFIRM_LABEL}
                    onPress={handleConfirmPublish}
                    variant="primary"
                    size="md"
                    block
                    isLoading={isPublishing}
                    disabled={isPublishing}
                    haptic="none"
                    testID="share-dialog-confirm-publish"
                  />
                </View>
              </View>
            </View>
          )}
        </View>
      </Animated.View>
    </Modal>
  );
}

// ---------------------------------------------------------------------------
// Styles
// ---------------------------------------------------------------------------

const styles = StyleSheet.create({
  scrim: {
    ...StyleSheet.absoluteFillObject,
    backgroundColor: OVERLAY_MEDIUM,
  },
  dismissArea: {
    flex: 1,
  },
  sheet: {
    position: "absolute",
    left: 0,
    right: 0,
    bottom: 0,
    backgroundColor: THEME.colors.surfaceElevated,
    borderTopLeftRadius: BOTTOM_SHEET_RADIUS,
    borderTopRightRadius: BOTTOM_SHEET_RADIUS,
    borderCurve: "continuous",
    borderTopWidth: 1,
    borderColor: THEME.colors.glassBorder,
    paddingTop: THEME.spacing.sm,
  },
  dragIndicator: {
    width: 36,
    height: 4,
    borderRadius: THEME.radius.pill,
    backgroundColor: THEME.colors.border,
    alignSelf: "center",
    marginBottom: THEME.spacing.sm,
  },
  closeButton: {
    position: "absolute",
    top: THEME.spacing.lg,
    right: THEME.spacing.xl,
    width: MIN_TOUCH_TARGET,
    height: MIN_TOUCH_TARGET,
    alignItems: "center",
    justifyContent: "center",
    zIndex: 1,
  },
  content: {
    paddingHorizontal: THEME.spacing.xl,
    paddingTop: THEME.spacing.lg,
    paddingBottom: THEME.spacing.lg,
    gap: THEME.spacing.lg,
  },
  title: {
    textAlign: "center",
  },
  rows: {
    gap: 0,
  },
  row: {
    flexDirection: "row",
    alignItems: "center",
    gap: THEME.spacing.md,
    paddingVertical: THEME.spacing.md,
    minHeight: MIN_TOUCH_TARGET,
  },
  rowPressed: {
    opacity: 0.6,
  },
  rowDisabled: {
    opacity: 0.4,
  },
  rowIcon: {
    width: MIN_TOUCH_TARGET,
    height: MIN_TOUCH_TARGET,
    borderRadius: THEME.radius.pill,
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: THEME.colors.surface,
  },
  rowText: {
    flex: 1,
    gap: THEME.spacing.xs / 2,
  },
  divider: {
    height: StyleSheet.hairlineWidth,
    backgroundColor: THEME.colors.border,
    marginLeft: MIN_TOUCH_TARGET + THEME.spacing.md,
  },
  confirmPanel: {
    gap: THEME.spacing.lg,
  },
  confirmBody: {
    textAlign: "center",
  },
  confirmError: {
    textAlign: "center",
  },
  confirmButtons: {
    flexDirection: "row",
    gap: THEME.spacing.md,
  },
  confirmButtonSlot: {
    flex: 1,
  },
});
