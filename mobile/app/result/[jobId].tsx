/**
 * Result Screen — before/after slider with save/share actions and AI disclosure.
 *
 * Route: /result/[jobId]
 *
 * Flow:
 * 1. Poll job result from GET /v1/jobs/{jobId} every 2s until terminal status
 * 2. BeforeAfterSlider with spring entrance plays on completion
 * 3. ResultActions bar: Save / Share / Try-another
 * 4. "AI-generated · not a photo" footer below actions
 * 5. Save: calls POST /v1/jobs/{jobId}/save, tracks saveState
 * 6. Share: view-shot composite via useShareComposite()
 * 7. Try-another: navigate back to upload
 */
import { useState, useCallback } from "react";
import {
  View,
  Text,
  ScrollView,
  StyleSheet,
  Alert,
} from "react-native";
import { useLocalSearchParams, useRouter, Stack } from "expo-router";
import { SafeAreaView } from "react-native-safe-area-context";
import Animated, { FadeIn } from "react-native-reanimated";
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
import { AI_DISCLOSURE, UNIVERSAL_LINK_ORIGIN } from "../../constants/config";
import { useAppQuery } from "../../lib/hooks/use-app-query";
import { useAppMutation } from "../../lib/hooks/use-app-mutation";
import { showToast } from "../../lib/toast";
import { useAuth } from "../../lib/auth-context";
import { parseApiError, shouldRetry } from "../../lib/errors";

// ---------------------------------------------------------------------------
// Terminal statuses — polling stops when job reaches these
// ---------------------------------------------------------------------------

const TERMINAL_STATUSES = new Set(["completed", "failed", "cancelled"]);

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

  // Poll job until terminal status. `refetchInterval` must also stop on
  // non-retryable errors (404, 403, 401) — otherwise a missing/forbidden
  // job ID triggers a 2s poll loop that never resolves and hammers the
  // API for the lifetime of the screen.
  const jobQuery = useAppQuery<JobResult>({
    queryKey: ["job", jobId],
    queryFn: () => getJobStatus(jobId as string),
    enabled: !!jobId,
    refetchInterval: (query) => {
      const err = query.state.error;
      if (err) {
        return shouldRetry(parseApiError(err)) ? 2000 : false;
      }
      const data = query.state.data;
      if (!data) return 2000;
      if (TERMINAL_STATUSES.has(data.status)) return false;
      return 2000;
    },
  });

  const result = jobQuery.data;

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

  const handleTryAnother = useCallback(() => {
    router.replace("/upload");
  }, [router]);

  // ---------------------------------------------------------------------------
  // Render
  // ---------------------------------------------------------------------------

  return (
    <>
      {/* Header with native back button — stays visible across every
          branch (loading, error, failed-job, success) so the user is
          never stranded on a screen with no way back. */}
      <Stack.Screen
        options={{
          title: "Result",
          headerStyle: { backgroundColor: THEME.colors.bg },
          headerTintColor: THEME.colors.textPrimary,
          headerShadowVisible: false,
        }}
      />
    <QueryStateView
      isLoading={jobQuery.isLoading}
      error={jobQuery.appError}
      onRetry={() => jobQuery.refetch()}
      errorAction={{ label: "Upload Another", onPress: handleTryAnother }}
    >
      {/* Job failed/cancelled */}
      {result && (result.status === "failed" || result.status === "cancelled") ? (
        <>
          <View style={styles.centeredContainer}>
            <PageBackground overlayOpacity={0.88} />
            <Ionicons
              name={result.status === "cancelled" ? "close-circle-outline" : "alert-circle-outline"}
              size={48}
              color={result.status === "cancelled" ? THEME.colors.textSecondary : THEME.colors.destructive}
            />
            <Text style={styles.errorText}>
              {result.status === "cancelled"
                ? "Generation was cancelled."
                : result.failure_reason ?? "Generation failed."}
            </Text>
            <PressableScale
              onPress={handleTryAnother}
              style={[styles.retryButton, { backgroundColor: theme.accent }]}
              accessibilityLabel="Try another photo"
              accessibilityRole="button"
            >
              <Text style={styles.retryText}>Try Another</Text>
            </PressableScale>
          </View>
        </>
      ) : (
        /* Success — before/after reveal + actions */
        <>
          <Stack.Screen options={{ title: "Your Glow-Up" }} />
          <SafeAreaView style={styles.safeArea} edges={["bottom"]}>
            <PageBackground overlayOpacity={0.88} />
            <ScrollView
              style={styles.scroll}
              contentContainerStyle={styles.scrollContent}
            >
              {/* Before / After Slider */}
              {result?.before_image_url && result.after_image_url ? (
                <BeforeAfterSlider
                  beforeUrl={result.before_image_url}
                  afterUrl={result.after_image_url}
                  rightLabel="Glow Up"
                />
              ) : (
                <View style={styles.missingImages}>
                  <Ionicons
                    name="image-outline"
                    size={48}
                    color={THEME.colors.textDisabled}
                  />
                  <Text style={styles.missingText}>
                    {result && TERMINAL_STATUSES.has(result.status)
                      ? "Images didn't come through for this run."
                      : "Images are not available yet."}
                  </Text>
                  {/* Recovery CTA — without this, a completed-but-missing
                      result leaves the user with only the native back
                      button. Always visible while images are absent;
                      harmless during a still-polling state since the
                      user can opt to start over if they want to. */}
                  <PressableScale
                    onPress={handleTryAnother}
                    style={[styles.retryButton, { backgroundColor: theme.accent }]}
                    accessibilityLabel="Upload another photo"
                    accessibilityRole="button"
                  >
                    <Text style={styles.retryText}>Upload Another</Text>
                  </PressableScale>
                </View>
              )}

              {/* ResultActions — Save / Share / Try-another */}
              {result?.before_image_url && result.after_image_url && (
                <Animated.View entering={FadeIn.duration(300).delay(400)}>
                  <ResultActions
                    onSave={handleSave}
                    onShare={handleShare}
                    onTryAnother={handleTryAnother}
                    saveState={saveState}
                  />
                </Animated.View>
              )}

              {/* AI disclosure footer */}
              {result?.before_image_url && result.after_image_url && (
                <Text style={styles.aiDisclosure}>{AI_DISCLOSURE}</Text>
              )}

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
      )}
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
  // Error / failed states
  centeredContainer: {
    flex: 1,
    backgroundColor: THEME.colors.bg,
    alignItems: "center",
    justifyContent: "center",
    padding: THEME.spacing.xxxl,
    gap: THEME.spacing.lg,
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
  // Missing images
  missingImages: {
    alignItems: "center",
    justifyContent: "center",
    padding: THEME.spacing.xxxl + THEME.spacing.lg,
    gap: THEME.spacing.lg,
  },
  missingText: {
    fontFamily: FONTS.body,
    ...THEME.typography.caption,
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
