/**
 * Result Screen — before/after slider with save/share actions and AI disclosure.
 *
 * Route: /result/[jobId]
 *
 * State machine:
 *   waiting   — initial load, pending status, tolerated 404 within the hard
 *               timeout, or completed-without-URLs within the image-URL
 *               timeout. Hourglass + "leave is safe" copy.
 *   success   — completed + both image URLs present.
 *   terminal  — failed/cancelled, hard timeout exceeded, or
 *               completed-without-URLs after the image-URL timeout. CTAs to
 *               retry or go to profile.
 *   error     — non-recoverable error that's neither a tolerable 404 nor a
 *               retryable transient (e.g., auth, permission). QueryStateView
 *               surfaces these with its own UI.
 *
 * Polling (`refetchInterval`) honors the same timeout windows so it stops
 * scheduling refetches once the screen flips to a terminal branch.
 */
import { useEffect, useMemo, useRef, useState, useCallback } from "react";
import {
  View,
  Text,
  StyleSheet,
  Alert,
  Pressable,
} from "react-native";
import { useLocalSearchParams, useRouter, Stack } from "expo-router";
import {
  SafeAreaView,
  useSafeAreaInsets,
} from "react-native-safe-area-context";
import { useQueryClient } from "@tanstack/react-query";
import Animated, {
  Easing,
  FadeIn,
  useAnimatedStyle,
  useReducedMotion,
  useSharedValue,
  withRepeat,
  withTiming,
} from "react-native-reanimated";
import { Ionicons } from "@expo/vector-icons";

import BeforeAfterSlider from "../../components/result/BeforeAfterSlider";
import {
  GlowupOverflowMenu,
  OVERFLOW_MENU_EXIT_DURATION_MS,
} from "../../components/result/GlowupOverflowMenu";
import { ResultActions, type SaveState } from "../../components/result/ResultActions";
import { useShareComposite } from "../../components/result/ShareComposite";
import { ShareDialog } from "../../components/result/ShareDialog";
import { useShareDialog } from "../../components/result/useShareDialog";
import { HeaderBackButton } from "../../components/ui/HeaderBackButton";
import { TryAnotherPresetButton } from "../../components/makeup/TryAnotherPresetButton";
import { ZoomableImageModal } from "../../components/ui/ZoomableImageModal";
import {
  getJobFailureMessage,
  getJobStatus,
  saveJob,
  type JobResult,
} from "../../lib/analysis";
import { apiFetch } from "../../lib/api";
import { THEME } from "../../constants/theme";
import { PageBackground } from "../../components/ui/PageBackground";
import { PressableScale } from "../../components/ui/PressableScale";
import { QueryStateView } from "../../components/ui/QueryStateView";
import { Heading } from "../../components/ui/Text";
import { useTheme } from "../../lib/theme-context";
import { FONTS } from "../../hooks/useFonts";
import {
  MIN_TOUCH_TARGET,
  RESULT_HARD_TIMEOUT_COPY,
  RESULT_SCREEN_HARD_TIMEOUT_MS,
  RESULT_SCREEN_IMAGE_URL_TIMEOUT_MS,
  RESULT_WAITING_BODY,
  RESULT_WAITING_TITLE,
} from "../../constants/config";
import { useAppQuery } from "../../lib/hooks/use-app-query";
import { useRefundToast } from "../../lib/hooks/use-refund-toast";
import { showToast } from "../../lib/toast";
import { useAuth } from "../../lib/auth-context";
import { useCapabilities } from "../../lib/capabilities";
import { parseApiError, shouldRetry } from "../../lib/errors";

// ---------------------------------------------------------------------------
// Constants — local
// ---------------------------------------------------------------------------

const TERMINAL_STATUSES = new Set(["completed", "failed", "cancelled"]);

/** Generic "wait at least this long before giving up on a 404" gate. */
const JOB_CREATION_GRACE_MS = 10_000;

/** Poll cadence — matches pending-cell poller in profile/useProfile.ts. */
const POLL_INTERVAL_MS = 2_000;

/** UI tick cadence — drives timeout transitions when polling has stopped. */
const TICK_INTERVAL_MS = 1_000;

/** Hourglass rotation period (ms) — slow enough to read as patient, not stuck. */
const HOURGLASS_ROTATION_MS = 2_400;

/** One full clockwise turn in degrees — target value for the hourglass spin. */
const HOURGLASS_FULL_ROTATION_DEG = 360;

/**
 * Share-dialog entry animation timing. The delay lets the result
 * before/after finish its own fade before the action row enters, so
 * the user isn't hit with two simultaneous animations on arrival.
 */
const SHARE_DIALOG_FADE_IN_MS = 300;
const SHARE_DIALOG_ENTRY_DELAY_MS = 400;

// TODO(writer-review): Delete-confirm copy must name external-link
// breakage per `feedback_female_user_targeting` + plan §Risks table
// ("Links you've already shared will stop working").
const DELETE_CONFIRM_TITLE = "Delete this glow-up?";
const DELETE_CONFIRM_BODY =
  "Links you've already shared will stop working. This can't be undone.";
const DELETE_CONFIRM_CANCEL_LABEL = "Cancel";
const DELETE_CONFIRM_DELETE_LABEL = "Delete";

/** Header-right overflow accessibility label. */
const HEADER_OVERFLOW_LABEL = "More options";

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

/** Title font size — matches Upload's custom header (Heading size="md"). */
const HEADER_TITLE_FONT_SIZE = 20;

export default function ResultScreen() {
  const { jobId } = useLocalSearchParams<{ jobId: string }>();
  const router = useRouter();
  const { theme } = useTheme();
  const insets = useSafeAreaInsets();
  const queryClient = useQueryClient();
  const capabilities = useCapabilities();

  const [saveState, setSaveState] = useState<SaveState>("pending");
  // Zoom viewer — which image, if any, is currently presented full-screen.
  const [zoomTarget, setZoomTarget] = useState<"before" | "after" | null>(null);
  const { username } = useAuth();

  // ShareDialog state — owned by the screen so the dialog can open from
  // either the primary button or (future) other entry points. The
  // Save/Share/Publish handler triplet lives in `useShareDialog` so this
  // screen and the profile long-press path stay in lockstep on the
  // R5/R8 blocking-auto-save invariant.
  const [shareDialogVisible, setShareDialogVisible] = useState(false);
  // Overflow menu visibility — opened by the header ellipsis. Delete
  // confirm still uses Alert.alert, raised after the menu's exit animation
  // completes so the stacked Modal + Alert doesn't race on iOS.
  const [overflowMenuVisible, setOverflowMenuVisible] = useState(false);
  /**
   * Client-side mirror of `post_id` + `share_hash`. Populated from either
   * the latest `GET /v1/jobs/{id}` poll (backend Unit 3) or the
   * `POST /v1/posts` response (via `useShareDialog` `onPublishSuccess`)
   * so the dialog + share URL pick up a fresh publish without a
   * round-trip refetch.
   */
  const [postState, setPostState] = useState<{
    post_id: string | null;
    share_hash: string | null;
  }>({ post_id: null, share_hash: null });

  // Share composite hook — ShareCompositeView must be in the tree
  const { ShareCompositeView, generateAndShare, isCapturing } =
    useShareComposite();

  // Refs that drive timeout windows. Reading them inside refetchInterval
  // keeps the polling cadence in lockstep with the user-facing render.
  const mountedAtRef = useRef<number>(Date.now());
  const completedSeenAtRef = useRef<number | null>(null);

  // Wall-clock tick — re-renders once per second so derived timeout state
  // (hardTimedOut, imageUrlTimedOut) flips even after polling has stopped.
  // A pure setTimeout pair would also work but adds two effects per
  // transition; this is one effect for both windows.
  const [, setNowTick] = useState(0);
  useEffect(() => {
    const id = setInterval(() => {
      setNowTick((n) => n + 1);
    }, TICK_INTERVAL_MS);
    return () => clearInterval(id);
  }, []);

  // Poll job until terminal status. The `refetchInterval` mirrors the
  // render-side state machine so polling stops at the same boundaries
  // the UI uses to flip into terminal-failure (hard timeout, image-URL
  // timeout). Without this mirroring the screen would render
  // terminal-failure while quietly hammering the API forever.
  const jobQuery = useAppQuery<JobResult>({
    queryKey: ["job", jobId],
    queryFn: () => getJobStatus(jobId as string),
    enabled: !!jobId,
    refetchInterval: (query) => {
      // Hard timeout — cap the screen lifetime regardless of state.
      if (Date.now() - mountedAtRef.current >= RESULT_SCREEN_HARD_TIMEOUT_MS) {
        return false;
      }

      const err = query.state.error;
      if (err) {
        const appError = parseApiError(err);
        // Tolerate 404 within the hard timeout — covers the legitimate
        // race where the worker's row hasn't replicated to the read path
        // yet (the JOB_CREATION_GRACE_MS window is the soft hint; the
        // hard timeout is the real backstop).
        if (appError.kind === "notFound") {
          return POLL_INTERVAL_MS;
        }
        return shouldRetry(appError) ? POLL_INTERVAL_MS : false;
      }

      const data = query.state.data;
      if (!data) return POLL_INTERVAL_MS;

      // Failed / cancelled — terminal, stop polling.
      if (data.status === "failed" || data.status === "cancelled") return false;

      if (data.status === "completed") {
        const hasImages = !!(data.before_image_url && data.after_image_url);
        if (hasImages) return false;

        // Completed but URLs not yet visible — record the first sighting
        // and keep polling within the image-URL timeout. Past that
        // window the worker is unlikely to write the URL (single
        // UPDATE on the row), so we stop polling and let the render
        // surface a terminal failure.
        if (completedSeenAtRef.current === null) {
          completedSeenAtRef.current = Date.now();
        }
        const sinceCompleted = Date.now() - completedSeenAtRef.current;
        if (sinceCompleted >= RESULT_SCREEN_IMAGE_URL_TIMEOUT_MS) {
          return false;
        }
        return POLL_INTERVAL_MS;
      }

      // Non-terminal status (queued / processing / finalizing) — keep
      // polling.
      return POLL_INTERVAL_MS;
    },
  });

  const result = jobQuery.data;
  const error = jobQuery.appError;

  // Hydrate the save button from the server-known state: if the job was
  // already saved (persisted `saved_at`), start in "saved" so the button
  // renders as disabled and the check-mark shows. Without this, re-opening
  // a previously-saved job would let the user click Save again.
  useEffect(() => {
    if (result?.saved_at && saveState === "pending") {
      setSaveState("saved");
    }
  }, [result?.saved_at, saveState]);

  // Hydrate post_id/share_hash from the latest poll so the dialog and
  // share-URL derivation see the server-known state. Only promotes (never
  // clears) so an in-flight Publish response isn't clobbered by a stale
  // poll window.
  useEffect(() => {
    if (result?.post_id && result.post_id !== postState.post_id) {
      setPostState({
        post_id: result.post_id,
        share_hash: result.share_hash ?? null,
      });
    }
  }, [result?.post_id, result?.share_hash, postState.post_id]);

  // Surface the one-time refund toast when the worker auto-refunds a
  // failed/cancelled job. Module-level dedup ensures the user sees
  // the banner exactly once per device per job, even if the result
  // screen + a profile pending cell observe the same job.
  useRefundToast(result);

  // Unified save-path wrapper. Both the primary "Save on profile" button
  // (`handleSave` below) and the dialog's Save row (via
  // `useShareDialog.handleSave`) / Share-path blocking auto-save
  // (`useShareDialog.handleShare`) funnel through this single helper.
  //
  // One codepath for every save surface: one POST per tap, one shared
  // invalidation of the `["job", jobId]` query (so the next render sees
  // the fresh `saved_at` without waiting for the next 2s poll), and
  // consistent error surfacing upstream. Callers handle their own
  // success/error UX (toasts, state flips) because the two entry points
  // differ — the primary button shows a toast, the dialog auto-save on
  // the Share path intentionally suppresses it.
  const saveJobFn = useCallback(
    async (id: string) => {
      const response = await saveJob(id);
      // Invalidate the job query so the next render picks up the new
      // `saved_at` from the cache instead of the stale snapshot the
      // current render is still holding. Without this the outline
      // "Save on profile" button and the dialog's Save row would rely
      // purely on `saveState` drift until the next 2s poll lands.
      queryClient.invalidateQueries({ queryKey: ["job", id] });
      return response;
    },
    [queryClient],
  );

  const handleSave = useCallback(async () => {
    if (saveState !== "pending") return;
    setSaveState("saving");
    try {
      await saveJobFn(jobId as string);
      setSaveState("saved");
      showToast({ kind: "success", message: "Saved on your profile." });
    } catch {
      setSaveState("pending");
      showToast({
        kind: "error",
        message: "Couldn't save on profile. Try again.",
      });
    }
  }, [saveState, saveJobFn, jobId]);

  // ---- ShareDialog handlers -------------------------------------------
  //
  // The triplet (Save / Share / Publish) lives in `useShareDialog` so
  // this screen and the profile long-press entry share the R5/R8
  // blocking-auto-save invariant. Parent still owns visibility + the
  // postState mirror; hook owns in-flight + error state.
  const closeShareDialog = useCallback(() => {
    setShareDialogVisible(false);
  }, []);

  // Don't build a dialogJob before `jobId` has hydrated — coercing
  // `undefined` to `""` would leave every callsite treating the
  // snapshot as truthy and fire POST /v1/jobs//save (or
  // /v1/posts with glow_up_job_id="") if the user tapped Save or
  // Publish during the params-hydration race. Gating on `!jobId`
  // matches the `enabled: !!jobId` narrowing used by the job query
  // above, and `useShareDialog` already treats a null `job` as a
  // universal no-op on every handler.
  const dialogJob = useMemo(
    () =>
      jobId
        ? {
            id: jobId,
            saved_at: result?.saved_at ?? null,
            post_id: postState.post_id,
            share_hash: postState.share_hash,
          }
        : null,
    [jobId, result?.saved_at, postState.post_id, postState.share_hash],
  );

  const getShareImageUrls = useCallback(
    async () => ({
      before: result?.before_image_url ?? null,
      after: result?.after_image_url ?? null,
    }),
    [result?.before_image_url, result?.after_image_url],
  );

  const handleDialogSaveSuccess = useCallback(() => {
    // Reuse the primary-row mutation's "saved" state so both the
    // outline Save-on-profile button and the dialog Save row stay in
    // lockstep. No-op if already saved.
    setSaveState("saved");
  }, []);

  const handleDialogPublishSuccess = useCallback(
    (post_id: string, share_hash: string) => {
      setPostState({ post_id, share_hash });
    },
    [],
  );

  const {
    saveState: dialogSaveState,
    isPublishing,
    publishError,
    handleSave: handleDialogSave,
    handleShare: handleDialogShare,
    handlePublish: handleDialogPublish,
    resetPublishError,
  } = useShareDialog({
    job: dialogJob,
    username,
    generateAndShare,
    getImageUrls: getShareImageUrls,
    onDialogClose: closeShareDialog,
    saveJobFn,
    onSaveSuccess: handleDialogSaveSuccess,
    onPublishSuccess: handleDialogPublishSuccess,
  });

  // Dialog-entry tap from the primary button. Clears any stale publish
  // error so a re-open starts clean.
  const handleOpenShareDialog = useCallback(() => {
    resetPublishError();
    setShareDialogVisible(true);
  }, [resetPublishError]);

  const handleCloseShareDialog = useCallback(() => {
    // Don't let the user dismiss mid-publish — parent-owned lifecycle
    // mirrors ShareDialog's internal guard so state stays consistent.
    if (isPublishing) return;
    setShareDialogVisible(false);
  }, [isPublishing]);

  // ---- Delete overflow (header-right) ---------------------------------

  const runDelete = useCallback(async () => {
    try {
      await apiFetch<void>(`/v1/jobs/${jobId}`, { method: "DELETE" });
      // Drop the stale job query so navigating back doesn't flash the
      // deleted content; invalidate the profile grid so it refetches.
      queryClient.removeQueries({ queryKey: ["job", jobId] });
      if (username) {
        queryClient.invalidateQueries({
          queryKey: ["profile.glowups", username],
        });
      }
      router.replace("/(tabs)/profile");
    } catch (err) {
      // Best-effort 204 — toast and keep the user on the screen per
      // plan §Unit 8 ("do not auto-retry").
      const app = parseApiError(err);
      showToast({ kind: "error", message: app.message });
    }
  }, [jobId, queryClient, username, router]);

  const handleDeletePress = useCallback(() => {
    Alert.alert(
      DELETE_CONFIRM_TITLE,
      DELETE_CONFIRM_BODY,
      [
        { text: DELETE_CONFIRM_CANCEL_LABEL, style: "cancel" },
        {
          text: DELETE_CONFIRM_DELETE_LABEL,
          style: "destructive",
          onPress: runDelete,
        },
      ],
    );
  }, [runDelete]);

  // Ellipsis taps open the overflow menu instead of firing the destructive
  // confirm directly. The menu row then chains to `handleDeletePress`.
  const handleOpenOverflowMenu = useCallback(() => {
    setOverflowMenuVisible(true);
  }, []);

  const handleCloseOverflowMenu = useCallback(() => {
    setOverflowMenuVisible(false);
  }, []);

  // Stacked Modal + Alert races on iOS — close the menu first and defer
  // the native destructive confirm until after the sheet's exit animation
  // completes, or Alert buttons can swallow the first tap. The timer
  // handle is tracked in a ref so:
  //   (a) a rapid double-tap on Delete cancels the pending alert before
  //       scheduling a fresh one (prevents two stacked Alert.alerts), and
  //   (b) the unmount cleanup below cancels any in-flight defer so an
  //       orphan timer can't raise Alert.alert on a navigated-away screen
  //       and silently run runDelete via the captured jobId closure.
  const menuDeleteTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const handleMenuDelete = useCallback(() => {
    setOverflowMenuVisible(false);
    if (menuDeleteTimerRef.current) {
      clearTimeout(menuDeleteTimerRef.current);
    }
    menuDeleteTimerRef.current = setTimeout(() => {
      menuDeleteTimerRef.current = null;
      handleDeletePress();
    }, OVERFLOW_MENU_EXIT_DURATION_MS);
  }, [handleDeletePress]);

  useEffect(() => {
    return () => {
      if (menuDeleteTimerRef.current) {
        clearTimeout(menuDeleteTimerRef.current);
        menuDeleteTimerRef.current = null;
      }
    };
  }, []);

  // Post-result navigation targets. Kept distinct so copy can match the
  // user's mental model at each state: "Try Again" = start a new attempt
  // from the upload screen; "Go to Profile" = leave this screen and pick
  // up the result from the profile feed later.
  const handleTryAgain = useCallback(() => {
    router.replace("/upload");
  }, [router]);

  const handleGoToProfile = useCallback(() => {
    router.replace("/(tabs)/profile");
  }, [router]);

  // Back chevron: prefer native back when possible. Falls through to
  // profile when the route was opened directly (dev-feature focus,
  // deep link) — matches the feedback rule that close/back stays
  // clickable whenever an action is available.
  const handleBack = useCallback(() => {
    if (router.canGoBack()) {
      router.back();
      return;
    }
    router.replace("/(tabs)/profile");
  }, [router]);

  // Tap-to-zoom handlers — gated on URLs so a pre-load tap is a no-op.
  const handleZoomBefore = useCallback(() => {
    if (result?.before_image_url) setZoomTarget("before");
  }, [result?.before_image_url]);
  const handleZoomAfter = useCallback(() => {
    if (result?.after_image_url) setZoomTarget("after");
  }, [result?.after_image_url]);
  const handleCloseZoom = useCallback(() => setZoomTarget(null), []);

  // ---------------------------------------------------------------------------
  // Derived state
  // ---------------------------------------------------------------------------

  const hasImages = !!(result?.before_image_url && result?.after_image_url);
  const isCompletedWithoutImages =
    result?.status === "completed" && !hasImages;

  // Reset the completed-seen timestamp if the row regresses out of the
  // completed-without-URLs state. Avoids a stale ref leaking into a later
  // attempt on the same screen mount.
  useEffect(() => {
    if (!isCompletedWithoutImages) {
      completedSeenAtRef.current = null;
    } else if (completedSeenAtRef.current === null) {
      completedSeenAtRef.current = Date.now();
    }
  }, [isCompletedWithoutImages]);

  const elapsed = Date.now() - mountedAtRef.current;
  const hardTimedOut = elapsed >= RESULT_SCREEN_HARD_TIMEOUT_MS;
  // Treat the early grace window as part of the "wait through transient
  // 404s" branch — the user shouldn't see any error UI until at least
  // JOB_CREATION_GRACE_MS has passed even if the hard timeout would
  // otherwise allow the QueryStateView fallback to fire.
  const withinJobCreationGrace = elapsed < JOB_CREATION_GRACE_MS;

  const imageUrlTimedOut =
    isCompletedWithoutImages &&
    completedSeenAtRef.current !== null &&
    Date.now() - completedSeenAtRef.current >=
      RESULT_SCREEN_IMAGE_URL_TIMEOUT_MS;

  const isToleratedNotFound =
    error?.kind === "notFound" && !hardTimedOut;

  const isPendingStatus =
    result !== undefined && !TERMINAL_STATUSES.has(result.status);

  const isWaiting =
    !hardTimedOut &&
    (jobQuery.isLoading ||
      isToleratedNotFound ||
      isPendingStatus ||
      (isCompletedWithoutImages && !imageUrlTimedOut) ||
      // Within the early grace window, suppress any other transient
      // error and stay on the waiting view.
      (withinJobCreationGrace && error !== null));

  const isSuccess = result?.status === "completed" && hasImages;

  const terminalFailure =
    !isWaiting &&
    !isSuccess &&
    (result?.status === "failed" ||
      result?.status === "cancelled" ||
      hardTimedOut ||
      imageUrlTimedOut);

  const isMakeup = result?.source_type === "makeup_session";

  const failureCopy = useMemo(() => {
    if (!terminalFailure) return null;
    if (result?.status === "cancelled") return "Generation was cancelled.";
    if (result?.status === "failed") {
      if (isMakeup && result.makeup_failure_reason) {
        if (result.makeup_failure_reason === "refused")
          return "This look isn't available on your current plan. Upgrade to unlock more styles.";
        if (result.makeup_failure_reason === "non_retryable")
          return "We couldn't apply this look to your photo. Try a different photo.";
        if (result.makeup_failure_reason === "retryable")
          return "Something went wrong applying your look. Your credit is safe — please try again.";
      }
      return getJobFailureMessage(result.failure_reason, result.user_guidance);
    }
    if (hardTimedOut) return RESULT_HARD_TIMEOUT_COPY;
    return "Images didn't come through for this run.";
  }, [terminalFailure, result, hardTimedOut, isMakeup]);

  // QueryStateView's error UI fires only when nothing else applies. Any
  // tolerable / waiting / terminal state takes precedence so the user
  // sees one branch at a time.
  const queryStateError =
    !isWaiting && !isSuccess && !terminalFailure ? error : null;

  // ---------------------------------------------------------------------------
  // Hourglass rotation — gated on reduced motion.
  // ---------------------------------------------------------------------------

  const rotation = useSharedValue(0);
  const reducedMotion = useReducedMotion();
  useEffect(() => {
    if (!isWaiting) return;
    if (reducedMotion) {
      rotation.value = 0;
      return;
    }
    rotation.value = withRepeat(
      withTiming(HOURGLASS_FULL_ROTATION_DEG, {
        duration: HOURGLASS_ROTATION_MS,
        easing: Easing.inOut(Easing.quad),
      }),
      -1,
      false,
    );
  }, [isWaiting, reducedMotion, rotation]);

  const hourglassStyle = useAnimatedStyle(() => ({
    transform: [{ rotate: `${rotation.value}deg` }],
  }));

  // ---------------------------------------------------------------------------
  // Render
  // ---------------------------------------------------------------------------

  const headerTitle = isSuccess ? (isMakeup ? "Your Makeup" : "Your Glow-Up") : "Result";

  return (
    <View style={styles.screen}>
      {/* Root layout is <Slot/>, not <Stack/>, so this Stack.Screen is
          an inert defensive marker. The visible header is the custom row
          below, which mirrors the Upload-screen header (Heading size="md",
          manual top inset). */}
      <Stack.Screen options={{ headerShown: false }} />
      <View style={[styles.header, { paddingTop: insets.top }]}>
        <HeaderBackButton onPress={handleBack} />
        <Heading
          size="md"
          style={styles.headerTitle}
          numberOfLines={1}
          maxFontSizeMultiplier={1.3}
        >
          {headerTitle}
        </Heading>
        {/* Right slot: Delete overflow on success; spacer in every other
            state so the centered title stays balanced. `navigation.setOptions`
            can't be used — the native-stack header is `headerShown: false`
            on this screen, so we render directly into the custom header. */}
        {isSuccess ? (
          <Pressable
            onPress={handleOpenOverflowMenu}
            style={styles.headerOverflow}
            accessibilityLabel={HEADER_OVERFLOW_LABEL}
            accessibilityRole="button"
            hitSlop={8}
            testID="result-header-overflow"
          >
            <Ionicons
              name="ellipsis-horizontal"
              size={20}
              color={THEME.colors.textSecondary}
            />
          </Pressable>
        ) : (
          <View style={styles.headerOverflow} />
        )}
      </View>
      <QueryStateView
        isLoading={false}
        error={queryStateError}
        onRetry={() => jobQuery.refetch()}
        errorAction={{ label: "Go to Profile", onPress: handleGoToProfile }}
      >
        {isWaiting ? (
          <View style={styles.centeredContainer}>
            <PageBackground overlayOpacity={0.88} />
            <Animated.View style={hourglassStyle}>
              <Ionicons
                name="hourglass-outline"
                size={48}
                color={THEME.colors.textSecondary}
              />
            </Animated.View>
            <Text style={styles.waitingTitle}>{RESULT_WAITING_TITLE}</Text>
            <Text style={styles.waitingBody}>{RESULT_WAITING_BODY}</Text>
            <PressableScale
              onPress={handleGoToProfile}
              style={[styles.retryButton, { backgroundColor: theme.accent }]}
              accessibilityLabel="Go to profile"
              accessibilityRole="button"
            >
              <Text style={styles.retryText}>Go to Profile</Text>
            </PressableScale>
          </View>
        ) : terminalFailure ? (
          <View style={styles.centeredContainer}>
            <PageBackground overlayOpacity={0.88} />
            <Ionicons
              name={
                result?.status === "cancelled"
                  ? "close-circle-outline"
                  : "alert-circle-outline"
              }
              size={48}
              color={
                result?.status === "cancelled"
                  ? THEME.colors.textSecondary
                  : THEME.colors.destructive
              }
            />
            <Text style={styles.errorText}>{failureCopy}</Text>
            <PressableScale
              onPress={handleTryAgain}
              style={[styles.retryButton, { backgroundColor: theme.accent }]}
              accessibilityLabel="Try again with a new photo"
              accessibilityRole="button"
            >
              <Text style={styles.retryText}>Try Again</Text>
            </PressableScale>
            <PressableScale
              onPress={handleGoToProfile}
              style={styles.cancelButton}
              accessibilityLabel="Go to profile"
              accessibilityRole="button"
            >
              <Text style={styles.cancelText}>Go to Profile</Text>
            </PressableScale>
          </View>
        ) : isSuccess ? (
          /* Success — before/after reveal + actions. Non-scrolling
             column so the slider's horizontal pan never competes with
             a parent ScrollView's vertical gesture (feedback #4). */
          <>
            <SafeAreaView style={styles.safeArea} edges={["bottom"]}>
              <PageBackground overlayOpacity={0.88} />
              <View style={styles.content}>
                <View style={styles.sliderSlot}>
                  <BeforeAfterSlider
                    beforeUrl={result.before_image_url!}
                    afterUrl={result.after_image_url!}
                    rightLabel={isMakeup ? "Makeup" : "Glow Up"}
                    onPressBeforeImage={handleZoomBefore}
                    onPressAfterImage={handleZoomAfter}
                  />
                </View>

                <Animated.View
                  entering={FadeIn.duration(SHARE_DIALOG_FADE_IN_MS).delay(
                    SHARE_DIALOG_ENTRY_DELAY_MS,
                  )}
                >
                  <ResultActions
                    onSave={() => {
                      void handleSave();
                    }}
                    onOpenShareDialog={handleOpenShareDialog}
                    onTryAnother={handleTryAgain}
                    saveState={saveState}
                    canPublishGlowup={capabilities.canPublishGlowup}
                  />
                  {isMakeup ? (
                    <TryAnotherPresetButton onPress={handleTryAgain} />
                  ) : null}
                </Animated.View>

                {/* Capturing overlay hint */}
                {isCapturing && (
                  <Animated.View
                    entering={FadeIn.duration(150)}
                    style={styles.capturingBadge}
                  >
                    <Text style={styles.capturingText}>Preparing share…</Text>
                  </Animated.View>
                )}
              </View>
            </SafeAreaView>

            {/* Offscreen composite for share (must be in tree) */}
            {ShareCompositeView}
          </>
        ) : null}
      </QueryStateView>

      {/* Zoom viewer — mounted outside QueryStateView so it can open over
          any branch. Gated on a non-null target; when target flips the
          modal opens with the matching URL. */}
      <ZoomableImageModal
        visible={zoomTarget !== null}
        sourceUri={
          zoomTarget === "before"
            ? result?.before_image_url ?? null
            : zoomTarget === "after"
              ? result?.after_image_url ?? null
              : null
        }
        altText={zoomTarget === "before" ? "Before photo" : "Glow-up photo"}
        onClose={handleCloseZoom}
      />

      {/* ShareDialog — only rendered once `jobId` has hydrated, so the
          dialog's `job` prop is never built from a missing param (which
          would otherwise coerce to id="" and fire malformed API calls on
          Save/Publish during the params-hydration race). The mount-only-
          when-ready pattern matches profile.tsx's gate on `dialogJob`.
          The dialog's internal `visible` flag still drives enter/exit
          animations for the dialog lifecycle once mounted. */}
      {dialogJob ? (
        <ShareDialog
          visible={shareDialogVisible}
          onClose={handleCloseShareDialog}
          job={dialogJob}
          onSave={handleDialogSave}
          onShare={handleDialogShare}
          onPublish={handleDialogPublish}
          saveState={dialogSaveState}
          isPublishing={isPublishing}
          publishError={publishError}
        />
      ) : null}

      <GlowupOverflowMenu
        visible={overflowMenuVisible}
        onClose={handleCloseOverflowMenu}
        onDelete={handleMenuDelete}
      />
    </View>
  );
}

// ---------------------------------------------------------------------------
// Styles
// ---------------------------------------------------------------------------

const styles = StyleSheet.create({
  // Root frame — vertical stack: header row on top, content below.
  screen: {
    flex: 1,
    backgroundColor: THEME.colors.bg,
  },
  // Header row — mirrors Upload (app/upload.tsx): HeaderBackButton on
  // the left, Heading size="md" centered, spacer on the right so the
  // title is perfectly balanced. Top inset comes from useSafeAreaInsets.
  header: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    paddingHorizontal: THEME.spacing.sm,
    paddingBottom: THEME.spacing.sm,
    backgroundColor: THEME.colors.bg,
  },
  headerTitle: {
    fontSize: HEADER_TITLE_FONT_SIZE,
  },
  /* Overflow slot — sized to MIN_TOUCH_TARGET so the header row stays
     visually centered whether the Delete affordance is live or spacer-only. */
  headerOverflow: {
    width: MIN_TOUCH_TARGET,
    height: MIN_TOUCH_TARGET,
    alignItems: "center",
    justifyContent: "center",
  },
  safeArea: {
    flex: 1,
    backgroundColor: THEME.colors.bg,
  },
  // Success content lives in a flex column (no ScrollView) so the
  // before/after slider owns its gesture cleanly. Top gap keeps the
  // image away from the header (feedback #4).
  content: {
    flex: 1,
    paddingTop: THEME.spacing.lg,
    paddingBottom: THEME.spacing.md,
  },
  sliderSlot: {
    alignItems: "center",
  },
  // Centered container shared between waiting + terminal-failure states
  centeredContainer: {
    flex: 1,
    backgroundColor: THEME.colors.bg,
    alignItems: "center",
    justifyContent: "center",
    padding: THEME.spacing.xxxl,
    gap: THEME.spacing.lg,
  },
  waitingTitle: {
    fontFamily: FONTS.bodySemiBold,
    ...THEME.typography.heading,
    color: THEME.colors.textPrimary,
    textAlign: "center",
  },
  waitingBody: {
    fontFamily: FONTS.body,
    ...THEME.typography.body,
    color: THEME.colors.textSecondary,
    textAlign: "center",
    maxWidth: 320,
  },
  errorText: {
    fontFamily: FONTS.body,
    ...THEME.typography.body,
    color: THEME.colors.textSecondary,
    textAlign: "center",
  },
  retryButton: {
    borderRadius: THEME.radius.pill,
    paddingHorizontal: THEME.spacing.xxxl,
    paddingVertical: THEME.spacing.md,
    marginTop: THEME.spacing.sm,
    minHeight: 48,
    alignItems: "center",
    justifyContent: "center",
  },
  retryText: {
    fontFamily: FONTS.bodySemiBold,
    fontSize: 15,
    color: THEME.colors.bg,
  },
  // Secondary action on terminal-failure / cancelled — styled as a
  // text-only link so the primary CTA (Try Again) stays visually
  // dominant. Matches the muted-button pattern in QueryStateView.
  cancelButton: {
    paddingVertical: THEME.spacing.sm,
    paddingHorizontal: THEME.spacing.xl,
    alignItems: "center",
    justifyContent: "center",
    minHeight: 44,
  },
  cancelText: {
    fontFamily: FONTS.body,
    fontSize: 15,
    color: THEME.colors.textSecondary,
  },
  // Capturing badge
  capturingBadge: {
    alignSelf: "center",
    backgroundColor: THEME.colors.glass,
    borderRadius: THEME.radius.pill,
    borderWidth: 1,
    borderColor: THEME.colors.glassBorder,
    paddingHorizontal: THEME.spacing.lg,
    paddingVertical: THEME.spacing.sm,
    marginBottom: THEME.spacing.md,
  },
  capturingText: {
    fontFamily: FONTS.body,
    fontSize: 13,
    color: THEME.colors.textSecondary,
  },
});
