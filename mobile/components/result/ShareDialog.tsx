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
 *     the exit animation completes so a re-open never flashes a stale panel.
 *
 * Animation + header chrome mirror `components/profile/EditProfileSheet`
 * (legacy `Animated.Value` + `Animated.timing`, 300ms enter / 200ms exit,
 * Cancel text button + centered title). Confirm-mode button layout is
 * unchanged.
 *
 * Copy strings are placeholders pending writer review — see the
 * `TODO(writer-review)` markers.
 */
import { useCallback, useEffect, useRef, useState } from "react";
import {
  Animated,
  Modal,
  Pressable,
  StyleSheet,
  View,
} from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { THEME } from "../../constants/theme";
import { MIN_TOUCH_TARGET } from "../../constants/config";
import { hapticLight, hapticMedium } from "../../lib/haptics";
import { useCapabilities } from "../../lib/capabilities";
import { Body, Caption, Heading } from "../ui/Text";
import { Button } from "../ui/Button";
import type { SaveState } from "./ResultActions";

// ---------------------------------------------------------------------------
// Animation constants — inlined to match EditProfileSheet verbatim.
// ---------------------------------------------------------------------------

const ENTER_DURATION_MS = 300;
const EXIT_DURATION_MS = 200;
const SCRIM_TARGET_OPACITY = 0.5;
/** translateY starting / exit position (off-screen below). */
const SHEET_OFFSCREEN_Y = 400;

const ROW_ICON_SIZE = 22;
/** Width of each header side-slot so the centered title reads balanced. */
const HEADER_SLOT_MIN_WIDTH = 60;

// ---------------------------------------------------------------------------
// Copy — all strings placeholder pending writer review.
// ---------------------------------------------------------------------------

const TITLE = "Share your glow-up";
const CANCEL_LABEL = "Cancel";

// TODO(writer-review): "Private. Only you can see it."
const SAVE_SUBTITLE = "Private. Only you can see it.";
const SAVE_TITLE = "Save";

// TODO(writer-review): "Sends the image and keeps it on your profile" —
// MUST disclose auto-save side-effect (R8, per plan).
const SHARE_SUBTITLE = "Sends the image and keeps it on your profile.";
const SHARE_TITLE = "Share";

// TODO(writer-review): "Public. Appears on the social feed and your
// card-web page."
const PUBLISH_SUBTITLE =
  "Public. Appears on the social feed and your card-web page.";
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
  // window would otherwise let the stale completion callback (enqueued when
  // the previous `visible=false` ran) unmount the now-open dialog — a
  // visible flicker. Flipped to `true` when the exit animation starts and
  // back to `false` when a new open fires; the completion callback checks
  // the ref and no-ops when the dialog has been re-opened.
  const isClosingRef = useRef(false);

  const slideAnim = useRef(new Animated.Value(0)).current;
  const scrimAnim = useRef(new Animated.Value(0)).current;

  const handleExitComplete = useCallback(
    ({ finished }: { finished: boolean }) => {
      if (!finished) return;
      if (!isClosingRef.current) return;
      isClosingRef.current = false;
      // Reset the internal panel state AFTER the exit animation completes
      // so the user doesn't see the confirm panel flicker back to the
      // rows view while the sheet is sliding away. Guarantees a re-open
      // always starts from the rows view.
      setMounted(false);
      setMode("rows");
    },
    [],
  );

  useEffect(() => {
    if (visible) {
      // Re-opening during a still-running exit animation — clear the
      // closing gate so any pending completion callback no-ops when it
      // finally fires. Also reset `mode` here (not just on exit completion)
      // so a rapid close → re-open that interrupts the exit animation
      // doesn't flash the stale confirm panel.
      isClosingRef.current = false;
      setMode("rows");
      setMounted(true);
      Animated.parallel([
        Animated.timing(slideAnim, {
          toValue: 1,
          duration: ENTER_DURATION_MS,
          useNativeDriver: true,
        }),
        Animated.timing(scrimAnim, {
          toValue: 1,
          duration: ENTER_DURATION_MS,
          useNativeDriver: true,
        }),
      ]).start();
    } else {
      isClosingRef.current = true;
      Animated.parallel([
        Animated.timing(slideAnim, {
          toValue: 0,
          duration: EXIT_DURATION_MS,
          useNativeDriver: true,
        }),
        Animated.timing(scrimAnim, {
          toValue: 0,
          duration: EXIT_DURATION_MS,
          useNativeDriver: true,
        }),
      ]).start(handleExitComplete);
    }
    // Stop in-flight animations on unmount so the legacy `Animated.timing`
    // completion callback can't fire `setMounted` / `setMode` on a dead
    // tree. `stopAnimation` invokes the callback with `finished: false`;
    // `handleExitComplete`'s `if (!finished) return` guard traps it.
    return () => {
      slideAnim.stopAnimation();
      scrimAnim.stopAnimation();
    };
  }, [visible, slideAnim, scrimAnim, handleExitComplete]);

  // ---- Row visibility --------------------------------------------------

  const showSaveRow = job.saved_at === null && capabilities.canEditProfile;
  const showPublishRow =
    capabilities.canPublishGlowup && job.post_id === null;

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

  // ---- Animated styles -------------------------------------------------

  const translateY = slideAnim.interpolate({
    inputRange: [0, 1],
    outputRange: [SHEET_OFFSCREEN_Y, 0],
  });

  const scrimOpacity = scrimAnim.interpolate({
    inputRange: [0, 1],
    outputRange: [0, SCRIM_TARGET_OPACITY],
  });

  const headerTitle = mode === "confirm" ? PUBLISH_CONFIRM_TITLE : TITLE;

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
      <View style={styles.modalContainer}>
        {/* Scrim */}
        <Animated.View style={[styles.scrim, { opacity: scrimOpacity }]}>
          <Pressable
            style={StyleSheet.absoluteFill}
            onPress={handleClose}
            accessibilityLabel="Close share dialog"
            accessibilityRole="button"
          />
        </Animated.View>

        {/* Sheet */}
        <Animated.View
          style={[
            styles.sheet,
            {
              transform: [{ translateY }],
              paddingBottom: Math.max(insets.bottom, THEME.spacing.xl),
            },
          ]}
        >
          {/* Glass top border */}
          <View style={styles.sheetTopBorder} />

          {/* Handle bar */}
          <View style={styles.handleBar} />

          {/* Header */}
          <View style={styles.header}>
            <Pressable
              onPress={handleClose}
              disabled={isPublishing}
              style={styles.headerSlotLeft}
              accessibilityLabel={CANCEL_LABEL}
              accessibilityRole="button"
              testID="share-dialog-cancel"
            >
              <Body color="secondary">{CANCEL_LABEL}</Body>
            </Pressable>

            <Heading
              size="md"
              style={styles.headerTitle}
              numberOfLines={1}
              maxFontSizeMultiplier={1.3}
            >
              {headerTitle}
            </Heading>

            <View style={styles.headerSlotRight} />
          </View>

          {/* Body */}
          <View style={styles.content}>
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

                {/* Share is always rendered when the dialog opens. */}
                {showSaveRow && <View style={styles.divider} />}
                <DialogRow
                  iconName="share-outline"
                  title={SHARE_TITLE}
                  subtitle={SHARE_SUBTITLE}
                  onPress={handleShare}
                  accessibilityLabel={SHARE_TITLE}
                  testID="share-dialog-row-share"
                />

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
      </View>
    </Modal>
  );
}

// ---------------------------------------------------------------------------
// Styles
// ---------------------------------------------------------------------------

const styles = StyleSheet.create({
  modalContainer: {
    flex: 1,
    justifyContent: "flex-end",
  },
  scrim: {
    ...StyleSheet.absoluteFillObject,
    backgroundColor: THEME.colors.backdrop,
  },
  sheet: {
    backgroundColor: THEME.colors.glass,
    borderTopLeftRadius: THEME.radius.xl,
    borderTopRightRadius: THEME.radius.xl,
    overflow: "hidden",
  },
  sheetTopBorder: {
    position: "absolute",
    top: 0,
    left: 0,
    right: 0,
    height: StyleSheet.hairlineWidth,
    backgroundColor: THEME.colors.sheetTopBorder,
  },
  handleBar: {
    width: 36,
    height: 4,
    borderRadius: THEME.radius.pill,
    backgroundColor: THEME.colors.borderFocused,
    alignSelf: "center",
    marginTop: THEME.spacing.sm,
    marginBottom: THEME.spacing.sm,
  },
  header: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    paddingHorizontal: THEME.spacing.lg,
    paddingVertical: THEME.spacing.sm,
    minHeight: MIN_TOUCH_TARGET,
  },
  headerSlotLeft: {
    minWidth: HEADER_SLOT_MIN_WIDTH,
    minHeight: MIN_TOUCH_TARGET,
    justifyContent: "center",
    alignItems: "flex-start",
  },
  headerSlotRight: {
    minWidth: HEADER_SLOT_MIN_WIDTH,
    minHeight: MIN_TOUCH_TARGET,
  },
  headerTitle: {
    textAlign: "center",
    flex: 1,
  },
  content: {
    paddingHorizontal: THEME.spacing.xl,
    paddingTop: THEME.spacing.md,
    paddingBottom: THEME.spacing.lg,
    gap: THEME.spacing.lg,
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
