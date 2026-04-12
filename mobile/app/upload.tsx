/**
 * Upload Screen — photo selection, progressive auto-upload, and Glow Up flow.
 *
 * Tier-3 two-step flow (R7 progressive auto-upload):
 * 1. Photo picked → immediately call POST /v1/uploads (auto-trigger)
 * 2. Phase `uploading` → spinner; on success → phase `uploaded`, store uploadId
 * 3. "Analyze" button is disabled during `uploading`; enabled when `uploaded`
 * 4. Tap Analyze → check consent → call POST /v1/uploads/{id}/glowup/analyze
 * 5. On analyze success → call POST /v1/uploads/{id}/glowup/generate
 * 6. On generate success → navigate to result/[jobId]
 * 7. On 428 FACE_MOD_CONSENT_REQUIRED → show consent modal (via ConsentContext)
 * 8. On FACE_NOT_DETECTED → show face_error state
 * 9. Cancel aborts in-flight requests
 */
import { useState, useEffect, useRef, useCallback } from "react";
import {
  View,
  Text,
  Pressable,
  ScrollView,
  StyleSheet,
  ActivityIndicator,
} from "react-native";
import { useRouter, Stack } from "expo-router";
import { SafeAreaView } from "react-native-safe-area-context";
import Animated, {
  FadeIn,
  FadeInDown,
  FadeOut,
  useSharedValue,
  useAnimatedStyle,
  withSpring,
} from "react-native-reanimated";
import { Ionicons } from "@expo/vector-icons";
import * as Crypto from "expo-crypto";

import PhotoPicker, {
  type SelectedPhoto,
} from "../components/upload/PhotoPicker";
import {
  createUpload,
  analyzeGlowup,
  generateGlowup,
  cancelJob,
  getEntitlement,
  type EntitlementInfo,
} from "../lib/analysis";
import { ApiError } from "../lib/api";
import { THEME } from "../constants/theme";
import { PageBackground } from "../components/ui/PageBackground";
import { useTheme } from "../lib/theme-context";
import {
  ANALYSIS_POLLING,
  HTTP_FACE_MOD_CONSENT_REQUIRED,
  RETENTION_DISCLOSURE,
} from "../constants/config";
import { FONTS } from "../hooks/useFonts";
import { FaceErrorCard } from "../components/ui/FaceErrorCard";
import { useConsent, ConsentDismissedError } from "../lib/consent-context";

const AnimatedPressable = Animated.createAnimatedComponent(Pressable);

// ---------------------------------------------------------------------------
// Upload phase state machine
// ---------------------------------------------------------------------------

type UploadPhase =
  | "idle"
  | "uploading"
  | "uploaded"
  | "analyzing"
  | "face_error"
  | "generating"
  | "error";

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export default function UploadScreen() {
  const router = useRouter();
  const { theme } = useTheme();
  const { requestConsentIfNeeded } = useConsent();

  // Press scale animations
  const analyzeScale = useSharedValue(1);
  const cancelScale = useSharedValue(1);
  const analyzePressStyle = useAnimatedStyle(() => ({
    transform: [{ scale: analyzeScale.value }],
  }));
  const cancelPressStyle = useAnimatedStyle(() => ({
    transform: [{ scale: cancelScale.value }],
  }));

  // State
  const [photo, setPhoto] = useState<SelectedPhoto | null>(null);
  const [phase, setPhase] = useState<UploadPhase>("idle");
  const [uploadId, setUploadId] = useState<string | null>(null);
  const [currentJobId, setCurrentJobId] = useState<string | null>(null);
  const [entitlement, setEntitlement] = useState<EntitlementInfo | null>(null);
  const [elapsedSeconds, setElapsedSeconds] = useState(0);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [isFaceError, setIsFaceError] = useState(false);

  // Refs
  const abortControllerRef = useRef<AbortController | null>(null);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Fetch entitlement on mount
  useEffect(() => {
    getEntitlement()
      .then(setEntitlement)
      .catch(() => {
        // Silently fail — user can still attempt upload
      });
  }, []);

  // Elapsed timer during analyze/generating phases
  const isProcessing = phase === "analyzing" || phase === "generating" || phase === "uploading";
  useEffect(() => {
    if (isProcessing) {
      setElapsedSeconds(0);
      timerRef.current = setInterval(() => {
        setElapsedSeconds((prev) => prev + 1);
      }, 1000);
    } else {
      if (timerRef.current) {
        clearInterval(timerRef.current);
        timerRef.current = null;
      }
    }
    return () => {
      if (timerRef.current) clearInterval(timerRef.current);
    };
  }, [isProcessing]);

  // Cleanup abort controller on unmount
  useEffect(() => {
    return () => {
      abortControllerRef.current?.abort();
    };
  }, []);

  // ---------------------------------------------------------------------------
  // Auto-upload on photo pick
  // ---------------------------------------------------------------------------

  const handlePhotoSelected = useCallback(
    async (selected: SelectedPhoto) => {
      setPhoto(selected);
      setPhase("uploading");
      setUploadId(null);
      setErrorMessage(null);
      setIsFaceError(false);
      setCurrentJobId(null);

      const controller = new AbortController();
      abortControllerRef.current = controller;

      try {
        const result = await createUpload({
          uri: selected.uri,
          name: selected.fileName,
          type: selected.mimeType,
        });

        if (controller.signal.aborted) return;
        setUploadId(result.upload_id);
        setPhase("uploaded");
      } catch (err) {
        if (controller.signal.aborted) return;
        if (err instanceof Error && err.name === "AbortError") return;
        const msg =
          err instanceof ApiError && err.status >= 400 && err.status < 500
            ? "Upload failed. Try a different photo."
            : "Upload failed. Check your connection and try again.";
        setErrorMessage(msg);
        setPhase("error");
      }
    },
    [],
  );

  // ---------------------------------------------------------------------------
  // Handlers
  // ---------------------------------------------------------------------------

  const handlePhotoClear = useCallback(() => {
    abortControllerRef.current?.abort();
    abortControllerRef.current = null;
    setPhoto(null);
    setPhase("idle");
    setUploadId(null);
    setCurrentJobId(null);
    setErrorMessage(null);
    setIsFaceError(false);
  }, []);

  const handleAnalyze = useCallback(async () => {
    if (!uploadId) return;
    if (phase !== "uploaded") return;

    // Gate on consent — shows modal if needed, resolves when granted.
    try {
      await requestConsentIfNeeded();
    } catch (err) {
      if (err instanceof ConsentDismissedError) {
        // User dismissed consent modal — stay on upload screen, do nothing.
        return;
      }
      throw err;
    }

    const controller = new AbortController();
    abortControllerRef.current = controller;
    setPhase("analyzing");
    setErrorMessage(null);
    setIsFaceError(false);

    try {
      // Step 1: analyze
      await analyzeGlowup(uploadId);

      if (controller.signal.aborted) return;

      // Step 2: generate
      setPhase("generating");
      const idempotencyKey = Crypto.randomUUID();
      const { job_id } = await generateGlowup(uploadId, idempotencyKey);

      if (controller.signal.aborted) return;

      setCurrentJobId(job_id);
      router.push(`/result/${job_id}`);
    } catch (err) {
      if (controller.signal.aborted) return;
      if (err instanceof Error && err.name === "AbortError") return;

      if (err instanceof ApiError) {
        if (err.status === HTTP_FACE_MOD_CONSENT_REQUIRED) {
          // Should not happen (consent was granted above), but handle defensively.
          setPhase("uploaded");
          return;
        }
        // Check for face-not-detected error code in body
        try {
          const body = JSON.parse(err.body) as { error?: { code?: string } };
          if (body?.error?.code === "face_not_detected") {
            setIsFaceError(true);
            setPhase("face_error");
            return;
          }
        } catch {
          // Ignore parse failures
        }
        const msg =
          err.status === 402
            ? "You're out of credits. Top up to continue."
            : err.status >= 500
              ? "Something went wrong on our end. Give it a moment."
              : "Analysis failed. Try a different photo.";
        setErrorMessage(msg);
        setPhase("error");
        return;
      }

      setErrorMessage("Something unexpected happened. Give it another try.");
      setPhase("error");
    }
  }, [uploadId, phase, requestConsentIfNeeded, router]);

  const handleCancel = useCallback(async () => {
    abortControllerRef.current?.abort();
    abortControllerRef.current = null;
    setPhase(uploadId ? "uploaded" : "idle");
    setElapsedSeconds(0);

    if (currentJobId) {
      cancelJob(currentJobId).catch(() => {});
      setCurrentJobId(null);
    }
  }, [uploadId, currentJobId]);

  const handleRetry = useCallback(() => {
    setPhase(uploadId ? "uploaded" : "idle");
    setErrorMessage(null);
    setIsFaceError(false);
  }, [uploadId]);

  // ---------------------------------------------------------------------------
  // Derived
  // ---------------------------------------------------------------------------

  const isAnalyzeDisabled = phase !== "uploaded";
  const showTrialCount = entitlement !== null;
  const isActivelyProcessing =
    phase === "uploading" || phase === "analyzing" || phase === "generating";

  function processingLabel(): string {
    switch (phase) {
      case "uploading":
        return "Uploading photo…";
      case "analyzing":
        return "Analyzing your photo…";
      case "generating":
        return "Generating glow-up…";
      default:
        return "Processing…";
    }
  }

  // ---------------------------------------------------------------------------
  // Render
  // ---------------------------------------------------------------------------

  return (
    <>
      <Stack.Screen
        options={{
          title: "Upload",
          headerStyle: { backgroundColor: THEME.colors.bg },
          headerTintColor: THEME.colors.textPrimary,
          headerShadowVisible: false,
        }}
      />
      <SafeAreaView style={styles.safeArea} edges={["bottom"]}>
        <PageBackground overlayOpacity={0.88} />
        <ScrollView
          style={styles.scroll}
          contentContainerStyle={styles.scrollContent}
          keyboardShouldPersistTaps="handled"
        >
          {/* Trial count badge */}
          {showTrialCount && (
            <Animated.View
              entering={FadeIn.duration(200)}
              style={styles.trialBadge}
              accessibilityLabel={`${entitlement.remaining_trials} of ${entitlement.total_trials} free trials remaining`}
            >
              <Ionicons
                name="flash-outline"
                size={16}
                color={theme.accent}
              />
              <Text style={styles.trialText}>
                {entitlement.remaining_trials} / {entitlement.total_trials}{" "}
                trials remaining
              </Text>
            </Animated.View>
          )}

          {/* Photo picker */}
          <Animated.View
            entering={FadeInDown.duration(THEME.animation.duration.normal).delay(50)}
            style={styles.pickerSection}
          >
            <PhotoPicker
              photo={photo}
              onPhotoSelected={handlePhotoSelected}
              onPhotoClear={handlePhotoClear}
              disabled={isActivelyProcessing}
            />
          </Animated.View>

          {/* Face error */}
          {phase === "face_error" && isFaceError && (
            <FaceErrorCard
              error={{
                kind: "faceAnalysis",
                message: "No face detected. Please upload a clear, front-facing selfie.",
                errorCode: "face_not_detected",
              }}
              onTryAgain={handleRetry}
            />
          )}

          {/* Generic error */}
          {phase === "error" && errorMessage && (
            <Animated.View
              entering={FadeIn.duration(200)}
              exiting={FadeOut.duration(150)}
              style={styles.errorCard}
              accessibilityRole="alert"
            >
              <View style={styles.errorHeader}>
                <Ionicons
                  name="warning-outline"
                  size={20}
                  color={THEME.colors.destructive}
                />
                <Text style={styles.errorTitle}>Error</Text>
              </View>
              <Text style={styles.errorGuidance}>{errorMessage}</Text>
              <Pressable
                onPress={handleRetry}
                style={styles.retryButton}
                accessibilityRole="button"
                accessibilityLabel="Try again"
                hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }}
              >
                <Text style={styles.retryText}>Try again</Text>
              </Pressable>
            </Animated.View>
          )}

          {/* Loading state with elapsed timer */}
          {isActivelyProcessing && (
            <Animated.View
              entering={FadeIn.duration(200)}
              style={styles.loadingCard}
              accessibilityLabel={`${processingLabel()} ${elapsedSeconds} seconds elapsed`}
              accessibilityRole="progressbar"
            >
              <ActivityIndicator size="large" color={theme.accent} />
              <Text style={styles.loadingTitle}>{processingLabel()}</Text>
              {(phase === "analyzing" || phase === "generating") && (
                <Text style={[styles.elapsedText, { color: theme.accent }]}>
                  {formatElapsed(elapsedSeconds)}
                </Text>
              )}
              {elapsedSeconds * 1000 > ANALYSIS_POLLING.TIMEOUT_HINT_MS && (
                <Text style={styles.hintText}>
                  Taking longer than usual. Hang tight...
                </Text>
              )}
            </Animated.View>
          )}

          {/* Retention disclosure */}
          <Text style={styles.retentionDisclosure}>{RETENTION_DISCLOSURE}</Text>
        </ScrollView>

        {/* Bottom action area — glass bar with glowing top border */}
        <View style={styles.bottomBar}>
          {/* Subtle glowing top accent line */}
          <View style={[
            styles.bottomBarGlow,
            { backgroundColor: theme.accent + "1A" },
          ]} />
          <View style={[
            styles.bottomBarAccentLine,
            { backgroundColor: theme.accent + "33" },
          ]} />

          {isActivelyProcessing ? (
            <AnimatedPressable
              onPress={handleCancel}
              onPressIn={() => { cancelScale.value = withSpring(0.97, THEME.animation.press); }}
              onPressOut={() => { cancelScale.value = withSpring(1, THEME.animation.press); }}
              style={[styles.cancelButton, cancelPressStyle]}
              accessibilityLabel="Cancel"
              accessibilityRole="button"
            >
              <Ionicons
                name="close-circle-outline"
                size={20}
                color={THEME.colors.textPrimary}
              />
              <Text style={styles.cancelText}>Cancel</Text>
            </AnimatedPressable>
          ) : (
            <AnimatedPressable
              onPress={handleAnalyze}
              onPressIn={() => {
                if (!isAnalyzeDisabled) analyzeScale.value = withSpring(0.97, THEME.animation.press);
              }}
              onPressOut={() => {
                analyzeScale.value = withSpring(1, THEME.animation.press);
              }}
              disabled={isAnalyzeDisabled}
              style={[
                styles.analyzeButton,
                isAnalyzeDisabled
                  ? styles.analyzeButtonDisabled
                  : [
                      { backgroundColor: theme.accent },
                      THEME.shadow.glow(theme.accent),
                    ],
                analyzePressStyle,
              ]}
              accessibilityLabel="Analyze photo"
              accessibilityRole="button"
              accessibilityState={{ disabled: isAnalyzeDisabled }}
            >
              <Ionicons
                name="sparkles"
                size={20}
                color={isAnalyzeDisabled ? THEME.colors.textDisabled : THEME.colors.white}
              />
              <Text
                style={[
                  styles.analyzeText,
                  isAnalyzeDisabled && styles.analyzeTextDisabled,
                ]}
              >
                Analyze
              </Text>
            </AnimatedPressable>
          )}
        </View>
      </SafeAreaView>
    </>
  );
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function formatElapsed(seconds: number): string {
  const mins = Math.floor(seconds / 60);
  const secs = seconds % 60;
  if (mins === 0) return `${secs}s`;
  return `${mins}m ${secs.toString().padStart(2, "0")}s`;
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
    padding: THEME.spacing.xl,
    paddingBottom: THEME.spacing.xxxl,
  },
  // Trial badge
  trialBadge: {
    flexDirection: "row",
    alignItems: "center",
    alignSelf: "center",
    backgroundColor: THEME.colors.glass,
    borderRadius: THEME.radius.pill,
    borderWidth: 1,
    borderColor: THEME.colors.glassBorder,
    paddingHorizontal: THEME.spacing.lg,
    paddingVertical: THEME.spacing.sm,
    marginBottom: THEME.spacing.lg,
    gap: THEME.spacing.sm,
  },
  trialText: {
    fontFamily: FONTS.bodySemiBold,
    fontSize: 13,
    color: THEME.colors.textSecondary,
  },
  // Photo picker section
  pickerSection: {
    alignItems: "center",
    marginBottom: THEME.spacing.xxl,
  },
  // Error card
  errorCard: {
    backgroundColor: THEME.colors.glass,
    borderRadius: THEME.radius.md,
    padding: THEME.spacing.lg,
    marginBottom: THEME.spacing.lg,
    borderWidth: 1,
    borderColor: THEME.colors.glassBorder,
  },
  errorHeader: {
    flexDirection: "row",
    alignItems: "center",
    gap: THEME.spacing.sm,
    marginBottom: THEME.spacing.sm,
  },
  errorTitle: {
    fontFamily: FONTS.bodySemiBold,
    fontSize: 15,
    color: THEME.colors.destructive,
  },
  errorGuidance: {
    fontFamily: FONTS.body,
    ...THEME.typography.body,
    color: THEME.colors.textSecondary,
  },
  retryButton: {
    marginTop: THEME.spacing.md,
    paddingVertical: THEME.spacing.sm,
    paddingHorizontal: THEME.spacing.lg,
    borderRadius: THEME.radius.pill,
    backgroundColor: THEME.colors.surfaceElevated,
    borderWidth: 1,
    borderColor: THEME.colors.border,
    alignSelf: "flex-start",
  },
  retryText: {
    fontFamily: FONTS.bodyMedium,
    fontSize: 14,
    color: THEME.colors.textPrimary,
  },
  // Loading card
  loadingCard: {
    alignItems: "center",
    backgroundColor: THEME.colors.glass,
    borderRadius: THEME.radius.lg,
    borderWidth: 1,
    borderColor: THEME.colors.glassBorder,
    padding: THEME.spacing.xxxl,
    gap: THEME.spacing.md,
  },
  loadingTitle: {
    fontFamily: FONTS.bodySemiBold,
    fontSize: 18,
    color: THEME.colors.textPrimary,
    letterSpacing: THEME.typography.heading.letterSpacing,
  },
  elapsedText: {
    fontFamily: FONTS.bodySemiBold,
    fontSize: 24,
    color: THEME.colors.textPrimary,
    letterSpacing: THEME.typography.heading.letterSpacing,
    fontVariant: ["tabular-nums"],
  },
  hintText: {
    fontFamily: FONTS.body,
    ...THEME.typography.caption,
    color: THEME.colors.textMuted,
    textAlign: "center",
  },
  // Retention disclosure
  retentionDisclosure: {
    fontFamily: FONTS.body,
    fontSize: 12,
    color: THEME.colors.textMuted,
    textAlign: "center",
    marginTop: THEME.spacing.lg,
    opacity: 0.7,
  },
  // Bottom bar
  bottomBar: {
    paddingHorizontal: THEME.spacing.xl,
    paddingVertical: THEME.spacing.md,
    backgroundColor: THEME.colors.glass,
    position: "relative",
  },
  bottomBarGlow: {
    position: "absolute",
    top: -4,
    left: 0,
    right: 0,
    height: 4,
  },
  bottomBarAccentLine: {
    position: "absolute",
    top: 0,
    left: 0,
    right: 0,
    height: StyleSheet.hairlineWidth * 2,
  },
  analyzeButton: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    borderRadius: THEME.radius.pill,
    paddingVertical: THEME.spacing.lg,
    gap: THEME.spacing.sm,
    minHeight: 52,
  },
  analyzeButtonDisabled: {
    backgroundColor: THEME.colors.surfaceElevated,
    borderWidth: 1,
    borderColor: THEME.colors.border,
    borderRadius: THEME.radius.pill,
  },
  analyzeText: {
    fontFamily: FONTS.bodyMedium,
    fontSize: 16,
    color: THEME.colors.bg,
  },
  analyzeTextDisabled: {
    color: THEME.colors.textDisabled,
  },
  cancelButton: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: THEME.colors.glass,
    borderRadius: THEME.radius.pill,
    paddingVertical: THEME.spacing.lg,
    gap: THEME.spacing.sm,
    minHeight: 48,
    borderWidth: 1,
    borderColor: THEME.colors.glassBorder,
  },
  cancelText: {
    fontFamily: FONTS.bodyMedium,
    fontSize: 16,
    color: THEME.colors.textPrimary,
  },
});
