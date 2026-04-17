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
  ScrollView,
  StyleSheet,
  Alert,
} from "react-native";
import { useLocalSearchParams, useRouter, Stack } from "expo-router";
import { SafeAreaView } from "react-native-safe-area-context";
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
import { ResultActions, type SaveState } from "../../components/result/ResultActions";
import { useShareComposite } from "../../components/result/ShareComposite";
import {
  getJobStatus,
  saveJob,
  type JobResult,
} from "../../lib/analysis";
import { THEME } from "../../constants/theme";
import { PageBackground } from "../../components/ui/PageBackground";
import { PressableScale } from "../../components/ui/PressableScale";
import { QueryStateView } from "../../components/ui/QueryStateView";
import { useTheme } from "../../lib/theme-context";
import { FONTS } from "../../hooks/useFonts";
import {
  AI_DISCLOSURE,
  RESULT_HARD_TIMEOUT_COPY,
  RESULT_SCREEN_HARD_TIMEOUT_MS,
  RESULT_SCREEN_IMAGE_URL_TIMEOUT_MS,
  RESULT_WAITING_BODY,
  RESULT_WAITING_TITLE,
  UNIVERSAL_LINK_ORIGIN,
} from "../../constants/config";
import { useAppQuery } from "../../lib/hooks/use-app-query";
import { useAppMutation } from "../../lib/hooks/use-app-mutation";
import { showToast } from "../../lib/toast";
import { useAuth } from "../../lib/auth-context";
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

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export default function ResultScreen() {
  const { jobId } = useLocalSearchParams<{ jobId: string }>();
  const router = useRouter();
  const { theme } = useTheme();

  const [saveState, setSaveState] = useState<SaveState>("pending");
  const { username } = useAuth();

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

  // Save mutation
  const saveMutation = useAppMutation<{ saved_at: string }, void>({
    mutationKey: ["job.save", jobId],
    mutationFn: () => saveJob(jobId as string),
    onSuccess: () => {
      setSaveState("saved");
      showToast({ kind: "success", message: "Result saved." });
    },
    onError: () => {
      setSaveState("pending");
      showToast({ kind: "error", message: "Save failed. Try again." });
    },
  });

  const handleSave = useCallback(() => {
    if (saveState !== "pending") return;
    setSaveState("saving");
    saveMutation.mutate();
  }, [saveState, saveMutation]);

  const handleShare = useCallback(async () => {
    if (!result?.before_image_url || !result.after_image_url) return;
    // Authenticated users get a clickable link back to their latest card on
    // the web surface (card-web /{username}). Guests share the PNG only.
    const shareUrl = username
      ? `${UNIVERSAL_LINK_ORIGIN}/${username}`
      : undefined;
    try {
      await generateAndShare({
        beforeUrl: result.before_image_url,
        afterUrl: result.after_image_url,
        rightLabel: "Glow Up",
        shareUrl,
        shareMessage: shareUrl
          ? `My NXME glow-up — ${shareUrl}`
          : undefined,
      });
    } catch (err) {
      if (err instanceof Error && err.message.includes("timeout")) {
        Alert.alert(
          "Share failed",
          "Images didn't finish loading. Try again in a moment.",
        );
      }
      // User-cancelled native share sheet — not an error
    }
  }, [result, generateAndShare, username]);

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

  const failureCopy = useMemo(() => {
    if (!terminalFailure) return null;
    if (result?.status === "cancelled") return "Generation was cancelled.";
    if (result?.status === "failed")
      return result.failure_reason ?? "Generation failed.";
    if (hardTimedOut) return RESULT_HARD_TIMEOUT_COPY;
    return "Images didn't come through for this run.";
  }, [terminalFailure, result, hardTimedOut]);

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
      withTiming(360, {
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

  return (
    <>
      {/* Header with native back button — stays visible across every
          branch (loading, error, waiting, failed, success) so the user
          is never stranded on a screen with no way back. */}
      <Stack.Screen
        options={{
          title: isSuccess ? "Your Glow-Up" : "Result",
          headerStyle: { backgroundColor: THEME.colors.bg },
          headerTintColor: THEME.colors.textPrimary,
          headerShadowVisible: false,
        }}
      />
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
          /* Success — before/after reveal + actions */
          <>
            <SafeAreaView style={styles.safeArea} edges={["bottom"]}>
              <PageBackground overlayOpacity={0.88} />
              <ScrollView
                style={styles.scroll}
                contentContainerStyle={styles.scrollContent}
              >
                <BeforeAfterSlider
                  beforeUrl={result.before_image_url!}
                  afterUrl={result.after_image_url!}
                  rightLabel="Glow Up"
                />

                <Animated.View entering={FadeIn.duration(300).delay(400)}>
                  <ResultActions
                    onSave={handleSave}
                    onShare={handleShare}
                    onTryAnother={handleTryAgain}
                    saveState={saveState}
                  />
                </Animated.View>

                <Text style={styles.aiDisclosure}>{AI_DISCLOSURE}</Text>

                {/* Capturing overlay hint */}
                {isCapturing && (
                  <Animated.View
                    entering={FadeIn.duration(150)}
                    style={styles.capturingBadge}
                  >
                    <Text style={styles.capturingText}>Preparing share…</Text>
                  </Animated.View>
                )}
              </ScrollView>
            </SafeAreaView>

            {/* Offscreen composite for share (must be in tree) */}
            {ShareCompositeView}
          </>
        ) : null}
      </QueryStateView>
    </>
  );
}

// ---------------------------------------------------------------------------
// Styles
// ---------------------------------------------------------------------------

const styles = StyleSheet.create({
  safeArea: {
    flex: 1,
    backgroundColor: THEME.colors.bg,
  },
  scroll: {
    flex: 1,
  },
  scrollContent: {
    paddingBottom: THEME.spacing.xxxl * 2,
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
  // AI disclosure
  aiDisclosure: {
    fontFamily: FONTS.body,
    fontSize: 12,
    color: THEME.colors.textMuted,
    textAlign: "center",
    paddingHorizontal: THEME.spacing.xl,
    paddingBottom: THEME.spacing.lg,
    opacity: 0.7,
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
