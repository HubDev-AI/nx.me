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
import Animated, { FadeIn, FadeOut } from "react-native-reanimated";
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
import {
  BG_PAGE,
  BG_CARD,
  BG_ELEVATED,
  TEXT_PRIMARY,
  TEXT_SECONDARY,
  TEXT_DISABLED,
  CTA_PRIMARY,
  CTA_PRESSED,
  ERROR_DARK,
  COLORS,
} from "../constants/colors";
import { ANALYSIS_POLLING } from "../constants/config";

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
          headerStyle: { backgroundColor: BG_PAGE },
          headerTintColor: COLORS.neutral.dark[900],
          headerShadowVisible: false,
        }}
      />
      <SafeAreaView style={styles.safeArea} edges={["bottom"]}>
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
                color={COLORS.after[400]}
              />
              <Text style={styles.trialText}>
                {entitlement.remaining_trials} / {entitlement.total_trials}{" "}
                trials remaining
              </Text>
            </Animated.View>
          )}

          {/* Photo picker */}
          <View style={styles.pickerSection}>
            <PhotoPicker
              photo={photo}
              onPhotoSelected={setPhoto}
              onPhotoClear={handlePhotoClear}
              disabled={isLoading}
            />
          </View>

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
                  color={ERROR_DARK}
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
                  color={ERROR_DARK}
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
              <ActivityIndicator size="large" color={CTA_PRIMARY} />
              <Text style={styles.loadingTitle}>
                {phase === "uploading" ? "Uploading..." : "Generating glow-up"}
              </Text>
              {phase === "generating" && (
                <Text style={styles.elapsedText}>
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

        {/* Bottom action area */}
        <View style={styles.bottomBar}>
          {phase === "generating" ? (
            <Pressable
              onPress={handleCancel}
              style={({ pressed }) => [
                styles.cancelButton,
                pressed && styles.cancelButtonPressed,
              ]}
              accessibilityLabel="Cancel generation"
              accessibilityRole="button"
            >
              <Ionicons
                name="close-circle-outline"
                size={20}
                color={TEXT_PRIMARY}
              />
              <Text style={styles.cancelText}>Cancel</Text>
            </Pressable>
          ) : (
            <Pressable
              onPress={handleAnalyze}
              disabled={isAnalyzeDisabled}
              style={({ pressed }) => [
                styles.analyzeButton,
                pressed && !isAnalyzeDisabled && styles.analyzeButtonPressed,
                isAnalyzeDisabled && styles.analyzeButtonDisabled,
              ]}
              accessibilityLabel="Analyze photo"
              accessibilityRole="button"
              accessibilityState={{ disabled: isAnalyzeDisabled }}
            >
              <Ionicons
                name="sparkles"
                size={20}
                color={isAnalyzeDisabled ? TEXT_DISABLED : "#FFFFFF"}
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

const SPACING = 8;

const styles = StyleSheet.create({
  safeArea: {
    flex: 1,
    backgroundColor: BG_PAGE,
  },
  scroll: {
    flex: 1,
  },
  scrollContent: {
    padding: SPACING * 2,
    paddingBottom: SPACING * 4,
  },
  // Trial badge
  trialBadge: {
    flexDirection: "row",
    alignItems: "center",
    alignSelf: "center",
    backgroundColor: BG_ELEVATED,
    borderRadius: 20,
    paddingHorizontal: SPACING * 2,
    paddingVertical: SPACING,
    marginBottom: SPACING * 2,
    gap: SPACING,
  },
  trialText: {
    fontSize: 13,
    fontWeight: "600",
    color: TEXT_SECONDARY,
  },
  // Photo picker section
  pickerSection: {
    alignItems: "center",
    marginBottom: SPACING * 3,
  },
  // Error card
  errorCard: {
    backgroundColor: "rgba(248, 113, 113, 0.1)",
    borderRadius: 12,
    padding: SPACING * 2,
    marginBottom: SPACING * 2,
    borderWidth: 1,
    borderColor: "rgba(248, 113, 113, 0.2)",
  },
  errorHeader: {
    flexDirection: "row",
    alignItems: "center",
    gap: SPACING,
    marginBottom: SPACING,
  },
  errorTitle: {
    fontSize: 15,
    fontWeight: "700",
    color: ERROR_DARK,
  },
  errorGuidance: {
    fontSize: 14,
    lineHeight: 20,
    color: TEXT_SECONDARY,
  },
  // Loading card
  loadingCard: {
    alignItems: "center",
    backgroundColor: BG_CARD,
    borderRadius: 16,
    padding: SPACING * 4,
    gap: SPACING * 1.5,
  },
  loadingTitle: {
    fontSize: 16,
    fontWeight: "600",
    color: TEXT_PRIMARY,
  },
  elapsedText: {
    fontSize: 24,
    fontWeight: "700",
    color: CTA_PRIMARY,
    fontVariant: ["tabular-nums"],
  },
  hintText: {
    fontSize: 13,
    color: TEXT_SECONDARY,
    textAlign: "center",
  },
  // Bottom bar
  bottomBar: {
    paddingHorizontal: SPACING * 2,
    paddingVertical: SPACING * 1.5,
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: COLORS.neutral.dark[400],
    backgroundColor: BG_PAGE,
  },
  analyzeButton: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: CTA_PRIMARY,
    borderRadius: 12,
    paddingVertical: 14,
    gap: SPACING,
    minHeight: 48,
  },
  analyzeButtonPressed: {
    backgroundColor: CTA_PRESSED,
  },
  analyzeButtonDisabled: {
    backgroundColor: COLORS.neutral.dark[300],
  },
  analyzeText: {
    fontSize: 16,
    fontWeight: "700",
    color: "#FFFFFF",
  },
  analyzeTextDisabled: {
    color: TEXT_DISABLED,
  },
  cancelButton: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: BG_ELEVATED,
    borderRadius: 12,
    paddingVertical: 14,
    gap: SPACING,
    minHeight: 48,
    borderWidth: 1,
    borderColor: COLORS.neutral.dark[400],
  },
  cancelButtonPressed: {
    backgroundColor: COLORS.neutral.dark[300],
  },
  cancelText: {
    fontSize: 16,
    fontWeight: "600",
    color: TEXT_PRIMARY,
  },
});
