/**
 * Upload Screen — photo selection, face validation, and generation trigger.
 *
 * Flow:
 * 1. User selects photo via camera/gallery
 * 2. "Analyze" button uploads to POST /v1/analyses
 * 3. Face validation result displayed (error guidance if failed)
 * 4. On success, POST /v1/analyses/{id}/generate starts a job
 * 5. Elapsed timer shown during generation polling
 * 6. On completion, navigate to result/[jobId]
 * 7. Cancel button calls POST /v1/jobs/{id}/cancel
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

import PhotoPicker, {
  type SelectedPhoto,
} from "../components/upload/PhotoPicker";
import {
  createAnalysis,
  startGeneration,
  pollJob,
  cancelJob,
  getEntitlement,
  getFaceErrorGuidance,
  type FaceErrorCode,
  type EntitlementInfo,
} from "../lib/analysis";
import { ApiError } from "../lib/api";
import { THEME } from "../constants/theme";
import { PageBackground } from "../components/ui/PageBackground";
import { useTheme } from "../lib/theme-context";
import { ANALYSIS_POLLING } from "../constants/config";
import { FONTS } from "../hooks/useFonts";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

type UploadPhase =
  | "idle"
  | "uploading"
  | "face_error"
  | "generating"
  | "error";

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export default function UploadScreen() {
  const router = useRouter();
  const { theme } = useTheme();

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
  const [entitlement, setEntitlement] = useState<EntitlementInfo | null>(null);
  const [faceErrorCode, setFaceErrorCode] = useState<FaceErrorCode | null>(
    null,
  );
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [elapsedSeconds, setElapsedSeconds] = useState(0);
  const [currentJobId, setCurrentJobId] = useState<string | null>(null);

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

  // Elapsed timer during generation
  useEffect(() => {
    if (phase === "generating") {
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
  }, [phase]);

  // Cleanup abort controller on unmount
  useEffect(() => {
    return () => {
      abortControllerRef.current?.abort();
    };
  }, []);

  // ---------------------------------------------------------------------------
  // Handlers
  // ---------------------------------------------------------------------------

  const handlePhotoClear = useCallback(() => {
    setPhoto(null);
    setPhase("idle");
    setFaceErrorCode(null);
    setErrorMessage(null);
  }, []);

  const handleAnalyze = useCallback(async () => {
    if (!photo) return;

    setPhase("uploading");
    setFaceErrorCode(null);
    setErrorMessage(null);

    try {
      // Step 1: Upload for analysis
      const analysis = await createAnalysis(
        photo.uri,
        photo.fileName,
        photo.mimeType,
      );

      // Step 2: Check face validation
      if (analysis.face_validation && !analysis.face_validation.passed) {
        setPhase("face_error");
        setFaceErrorCode(
          analysis.face_validation.error_code ?? "FACE_NOT_DETECTED",
        );
        return;
      }

      // Step 3: Start generation
      setPhase("generating");
      const { job_id } = await startGeneration(analysis.id);
      setCurrentJobId(job_id);

      // Step 4: Poll for completion
      const controller = new AbortController();
      abortControllerRef.current = controller;

      const finalResult = await pollJob(
        job_id,
        () => {
          // onUpdate — we just keep the timer running
        },
        controller.signal,
      );

      if (finalResult.status === "completed") {
        router.replace(`/result/${job_id}`);
      } else if (finalResult.status === "cancelled") {
        setPhase("idle");
        setCurrentJobId(null);
      } else {
        setPhase("error");
        setErrorMessage(
          finalResult.error_message ?? "Generation failed. Please try again.",
        );
      }
    } catch (err) {
      if (err instanceof DOMException && err.name === "AbortError") {
        // User cancelled — already handled
        return;
      }
      setPhase("error");
      if (err instanceof ApiError) {
        setErrorMessage(`Upload failed (${err.status}). Please try again.`);
      } else {
        setErrorMessage("Something went wrong. Please try again.");
      }
    }
  }, [photo, router]);

  const handleCancel = useCallback(async () => {
    abortControllerRef.current?.abort();
    abortControllerRef.current = null;

    if (currentJobId) {
      try {
        await cancelJob(currentJobId);
      } catch {
        // Best-effort cancel
      }
    }

    setPhase("idle");
    setCurrentJobId(null);
  }, [currentJobId]);

  // ---------------------------------------------------------------------------
  // Derived
  // ---------------------------------------------------------------------------

  const isAnalyzeDisabled =
    !photo || phase === "uploading" || phase === "generating";
  const isLoading = phase === "uploading" || phase === "generating";
  const showTrialCount = entitlement !== null;

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
              onPhotoSelected={setPhoto}
              onPhotoClear={handlePhotoClear}
              disabled={isLoading}
            />
          </Animated.View>

          {/* Face validation error */}
          {phase === "face_error" && faceErrorCode && (
            <Animated.View
              entering={FadeIn.duration(200)}
              exiting={FadeOut.duration(150)}
              style={styles.errorCard}
              accessibilityRole="alert"
            >
              <View style={styles.errorHeader}>
                <Ionicons
                  name="alert-circle-outline"
                  size={20}
                  color={THEME.colors.destructive}
                />
                <Text style={styles.errorTitle}>Face Validation Failed</Text>
              </View>
              <Text style={styles.errorGuidance}>
                {getFaceErrorGuidance(faceErrorCode)}
              </Text>
            </Animated.View>
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
            </Animated.View>
          )}

          {/* Loading state with elapsed timer */}
          {isLoading && (
            <Animated.View
              entering={FadeIn.duration(200)}
              style={styles.loadingCard}
              accessibilityLabel={
                phase === "uploading"
                  ? "Uploading photo"
                  : `Generating glow-up, ${elapsedSeconds} seconds elapsed`
              }
              accessibilityRole="progressbar"
            >
              <ActivityIndicator size="large" color={theme.accent} />
              <Text style={styles.loadingTitle}>
                {phase === "uploading" ? "Uploading..." : "Generating glow-up"}
              </Text>
              {phase === "generating" && (
                <Text style={[styles.elapsedText, { color: theme.accent }]}>
                  {formatElapsed(elapsedSeconds)}
                </Text>
              )}
              {phase === "generating" &&
                elapsedSeconds * 1000 > ANALYSIS_POLLING.TIMEOUT_HINT_MS && (
                  <Text style={styles.hintText}>
                    Taking longer than usual. Hang tight...
                  </Text>
                )}
            </Animated.View>
          )}
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

          {phase === "generating" ? (
            <Animated.View style={cancelPressStyle}>
              <Pressable
                onPress={handleCancel}
                onPressIn={() => { cancelScale.value = withSpring(0.97, THEME.animation.press); }}
                onPressOut={() => { cancelScale.value = withSpring(1, THEME.animation.press); }}
                style={styles.cancelButton}
                accessibilityLabel="Cancel generation"
                accessibilityRole="button"
              >
                <Ionicons
                  name="close-circle-outline"
                  size={20}
                  color={THEME.colors.textPrimary}
                />
                <Text style={styles.cancelText}>Cancel</Text>
              </Pressable>
            </Animated.View>
          ) : (
            <Animated.View style={analyzePressStyle}>
              <Pressable
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
              </Pressable>
            </Animated.View>
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
    fontFamily: FONTS.display,
    fontSize: 18,
    color: THEME.colors.textPrimary,
    letterSpacing: THEME.typography.heading.letterSpacing,
  },
  elapsedText: {
    fontFamily: FONTS.display,
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
