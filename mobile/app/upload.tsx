/**
 * Upload Screen — photo selection, progressive auto-upload, and Glow Up flow.
 *
 * Tier-3 two-step flow (R7 progressive auto-upload):
 * 1. Photo picked → immediately call POST /v1/uploads (auto-trigger)
 * 2. Phase `uploading` → ProcessingHUD; on success → phase `uploaded`, store uploadId
 * 3. "Analyze" button is disabled during `uploading`; enabled when `uploaded`
 * 4. Tap Analyze → check consent → call POST /v1/uploads/{id}/glowup/analyze
 * 5. On analyze success → call POST /v1/uploads/{id}/glowup/generate
 * 6. On generate success → navigate to result/[jobId]
 * 7. On 428 FACE_MOD_CONSENT_REQUIRED → show consent modal (via ConsentContext)
 * 8. On FACE_NOT_DETECTED → show FaceErrorCard
 * 9. Cancel aborts in-flight requests
 */
import { useCallback, useEffect, useRef, useState } from "react";
import { ScrollView, StyleSheet, View } from "react-native";
import { Stack, useRouter } from "expo-router";
import { SafeAreaView } from "react-native-safe-area-context";
import Animated, { FadeIn, FadeInDown, FadeOut } from "react-native-reanimated";
import { Ionicons } from "@expo/vector-icons";
import * as Crypto from "expo-crypto";

import PhotoPicker, { type SelectedPhoto } from "../components/upload/PhotoPicker";
import ProcessingHUD, {
  type ProcessingPhase,
} from "../components/upload/ProcessingHUD";
import {
  analyzeGlowup,
  cancelJob,
  createUpload,
  generateGlowup,
  getEntitlement,
  type EntitlementInfo,
} from "../lib/analysis";
import { ApiError } from "../lib/api";
import {
  HTTP_FACE_MOD_CONSENT_REQUIRED,
  RETENTION_DISCLOSURE,
} from "../constants/config";
import { THEME } from "../constants/theme";
import { Button } from "../components/ui/Button";
import { FaceErrorCard } from "../components/ui/FaceErrorCard";
import { HeaderBackButton } from "../components/ui/HeaderBackButton";
import { PageBackground } from "../components/ui/PageBackground";
import { Body, Caption, Label } from "../components/ui/Text";
import { hapticError, hapticMedium } from "../lib/haptics";
import { useTheme } from "../lib/theme-context";
import { ConsentDismissedError, useConsent } from "../lib/consent-context";

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

const PROCESSING_PHASES: ReadonlySet<UploadPhase> = new Set([
  "uploading",
  "analyzing",
  "generating",
]);

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export default function UploadScreen() {
  const router = useRouter();
  const { theme } = useTheme();
  const { requestConsentIfNeeded } = useConsent();

  const [photo, setPhoto] = useState<SelectedPhoto | null>(null);
  const [phase, setPhase] = useState<UploadPhase>("idle");
  const [uploadId, setUploadId] = useState<string | null>(null);
  const [currentJobId, setCurrentJobId] = useState<string | null>(null);
  const [entitlement, setEntitlement] = useState<EntitlementInfo | null>(null);
  const [elapsedSeconds, setElapsedSeconds] = useState(0);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [isFaceError, setIsFaceError] = useState(false);

  const abortControllerRef = useRef<AbortController | null>(null);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const isActivelyProcessing = PROCESSING_PHASES.has(phase);

  const handleBack = useCallback(() => {
    if (router.canGoBack()) {
      router.back();
    } else {
      router.replace("/(tabs)/create");
    }
  }, [router]);

  // Fetch entitlement on mount
  useEffect(() => {
    getEntitlement()
      .then(setEntitlement)
      .catch(() => {
        // Silently fail — user can still attempt upload
      });
  }, []);

  // Elapsed timer during any active processing phase
  useEffect(() => {
    if (isActivelyProcessing) {
      setElapsedSeconds(0);
      timerRef.current = setInterval(() => {
        setElapsedSeconds((prev) => prev + 1);
      }, 1000);
    } else if (timerRef.current) {
      clearInterval(timerRef.current);
      timerRef.current = null;
    }
    return () => {
      if (timerRef.current) clearInterval(timerRef.current);
    };
  }, [isActivelyProcessing]);

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
        hapticError();
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
    if (!uploadId || phase !== "uploaded") return;

    try {
      await requestConsentIfNeeded();
    } catch (err) {
      if (err instanceof ConsentDismissedError) return;
      throw err;
    }

    hapticMedium();

    const controller = new AbortController();
    abortControllerRef.current = controller;
    setPhase("analyzing");
    setErrorMessage(null);
    setIsFaceError(false);

    try {
      await analyzeGlowup(uploadId);
      if (controller.signal.aborted) return;

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
          // Defensive — consent was granted above, but tolerate races.
          setPhase("uploaded");
          return;
        }
        try {
          const body = JSON.parse(err.body) as { error?: { code?: string } };
          if (body?.error?.code === "face_not_detected") {
            hapticError();
            setIsFaceError(true);
            setPhase("face_error");
            return;
          }
        } catch {
          // Ignore parse failures — fall through to generic handling
        }
        hapticError();
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

      hapticError();
      setErrorMessage("Something unexpected happened. Give it another try.");
      setPhase("error");
    }
  }, [uploadId, phase, requestConsentIfNeeded, router]);

  const handleCancel = useCallback(() => {
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

  const isAnalyzeDisabled = phase !== "uploaded";

  return (
    <>
      <Stack.Screen
        options={{
          title: "Upload",
          headerStyle: { backgroundColor: THEME.colors.bg },
          headerTintColor: THEME.colors.textPrimary,
          headerShadowVisible: false,
          headerBackVisible: false,
          headerLeft: () => <HeaderBackButton onPress={handleBack} />,
        }}
      />
      <SafeAreaView style={styles.safeArea} edges={["bottom"]}>
        <PageBackground overlayOpacity={0.88} />

        <ScrollView
          style={styles.scroll}
          contentContainerStyle={styles.scrollContent}
          contentInsetAdjustmentBehavior="automatic"
          keyboardShouldPersistTaps="handled"
          showsVerticalScrollIndicator={false}
        >
          {entitlement ? (
            <Animated.View
              entering={FadeIn.duration(200)}
              style={styles.trialBadge}
              accessibilityLabel={`${entitlement.remaining_trials} of ${entitlement.total_trials} free trials remaining`}
            >
              <Ionicons name="flash-outline" size={16} color={theme.accent} />
              <Caption weight="semibold" color="secondary">
                {entitlement.remaining_trials} / {entitlement.total_trials} trials remaining
              </Caption>
            </Animated.View>
          ) : null}

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

          {phase === "face_error" && isFaceError ? (
            <FaceErrorCard
              error={{
                kind: "faceAnalysis",
                message:
                  "No face detected. Please upload a clear, front-facing selfie.",
                errorCode: "face_not_detected",
              }}
              onTryAgain={handleRetry}
            />
          ) : null}

          {phase === "error" && errorMessage ? (
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
                <Label color="destructive">Something went wrong</Label>
              </View>
              <Body color="secondary">{errorMessage}</Body>
              <View style={styles.errorActions}>
                <Button
                  title="Try again"
                  onPress={handleRetry}
                  variant="secondary"
                  size="sm"
                />
              </View>
            </Animated.View>
          ) : null}

          {isActivelyProcessing ? (
            <ProcessingHUD
              phase={phase as ProcessingPhase}
              elapsedSeconds={elapsedSeconds}
            />
          ) : null}

          <Caption color="muted" style={styles.retentionDisclosure}>
            {RETENTION_DISCLOSURE}
          </Caption>
        </ScrollView>

        {/* Sticky bottom action */}
        <View style={styles.bottomBar}>
          {isActivelyProcessing ? (
            <Button
              title="Cancel"
              onPress={handleCancel}
              variant="outline"
              size="md"
              block
              leftIcon={
                <Ionicons
                  name="close-circle-outline"
                  size={20}
                  color={THEME.colors.textPrimary}
                />
              }
              accessibilityLabel="Cancel"
            />
          ) : (
            <Button
              title="Analyze"
              onPress={handleAnalyze}
              variant="primary"
              size="lg"
              block
              glow={!isAnalyzeDisabled}
              haptic="none"
              disabled={isAnalyzeDisabled}
              accentColor={theme.accent}
              leftIcon={
                <Ionicons
                  name="sparkles"
                  size={20}
                  color={
                    isAnalyzeDisabled
                      ? THEME.colors.textDisabled
                      : THEME.colors.bg
                  }
                />
              }
              accessibilityLabel="Analyze photo"
            />
          )}
        </View>
      </SafeAreaView>
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
    padding: THEME.spacing.xl,
    paddingBottom: THEME.spacing.xxxl,
    gap: THEME.spacing.lg,
  },
  // Trial badge
  trialBadge: {
    flexDirection: "row",
    alignItems: "center",
    alignSelf: "center",
    backgroundColor: THEME.colors.glass,
    borderRadius: THEME.radius.pill,
    borderCurve: "continuous",
    borderWidth: 1,
    borderColor: THEME.colors.glassBorder,
    paddingHorizontal: THEME.spacing.lg,
    paddingVertical: THEME.spacing.sm,
    gap: THEME.spacing.sm,
  },
  // Photo picker section
  pickerSection: {
    alignItems: "center",
  },
  // Error card
  errorCard: {
    backgroundColor: THEME.colors.glass,
    borderRadius: THEME.radius.md,
    borderCurve: "continuous",
    padding: THEME.spacing.lg,
    borderWidth: 1,
    borderColor: THEME.colors.glassBorder,
    gap: THEME.spacing.md,
  },
  errorHeader: {
    flexDirection: "row",
    alignItems: "center",
    gap: THEME.spacing.sm,
  },
  errorActions: {
    flexDirection: "row",
  },
  // Retention disclosure
  retentionDisclosure: {
    textAlign: "center",
    marginTop: THEME.spacing.md,
    opacity: 0.7,
  },
  // Bottom bar — sticky footer with hairline top border
  bottomBar: {
    paddingHorizontal: THEME.spacing.xl,
    paddingVertical: THEME.spacing.md,
    backgroundColor: THEME.colors.glass,
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: THEME.colors.glassBorder,
  },
});
