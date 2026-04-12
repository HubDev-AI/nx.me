/**
 * Result Screen — displays before/after reveal animation with suggestions and CTAs.
 *
 * Route: /result/[jobId]
 *
 * Flow:
 * 1. Poll job result from GET /v1/jobs/{jobId} every 2s until terminal status
 * 2. Before image slides in, after wipes from right with glow ring
 * 3. Suggestion pills stagger up after reveal completes
 * 4. CTAs fade in: "Share", "New Glow-Up", "This doesn't look like me"
 * 5. "This doesn't look like me" triggers refund mutation
 */
import { useState, useCallback } from "react";
import {
  View,
  Text,
  ScrollView,
  StyleSheet,
  Alert,
  Share,
  Platform,
} from "react-native";
import { useLocalSearchParams, useRouter, Stack } from "expo-router";
import { SafeAreaView } from "react-native-safe-area-context";
import Animated, { FadeIn } from "react-native-reanimated";
import { Ionicons } from "@expo/vector-icons";

// Phase 3: BeforeAfterReveal replaced by BeforeAfterSlider.
// Phase 4 will update the full usage (rightLabel, Save/Share CTAs, consent).
import BeforeAfterSlider from "../../components/result/BeforeAfterSlider";
import {
  getJobStatus,
  requestRefund,
  type JobResult,
} from "../../lib/analysis";
import { THEME } from "../../constants/theme";
import { PageBackground } from "../../components/ui/PageBackground";
import { PressableScale } from "../../components/ui/PressableScale";
import { QueryStateView } from "../../components/ui/QueryStateView";
import { useTheme } from "../../lib/theme-context";
import { FONTS } from "../../hooks/useFonts";
import { UNIVERSAL_LINK_ORIGIN } from "../../constants/config";
import { useAppQuery } from "../../lib/hooks/use-app-query";
import { useAppMutation } from "../../lib/hooks/use-app-mutation";
import { showToast } from "../../lib/toast";
import { useFeatures } from "../../lib/features-context";

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
  const { features } = useFeatures();
  // When Share is hidden, New Glow-Up takes over the primary slot.
  const newGlowUpIsPrimary = !features.share_enabled;

  const [revealComplete, setRevealComplete] = useState(false);
  const [ctasVisible, setCtasVisible] = useState(false);
  const [refundRequested, setRefundRequested] = useState(false);

  // Poll job until terminal status
  const jobQuery = useAppQuery<JobResult>({
    queryKey: ["job", jobId],
    queryFn: () => getJobStatus(jobId as string),
    enabled: !!jobId,
    refetchInterval: (query) => {
      const data = query.state.data;
      if (!data) return 2000;
      if (TERMINAL_STATUSES.has(data.status)) return false;
      return 2000;
    },
  });

  const result = jobQuery.data;

  // Refund mutation
  const refundMutation = useAppMutation<void, void>({
    mutationKey: ["refund", jobId],
    mutationFn: () => requestRefund(jobId as string),
    onSuccess: () => {
      showToast({
        kind: "success",
        message: "Refund requested. Credits will be restored shortly.",
      });
      setRefundRequested(true);
    },
  });

  const handleRevealComplete = useCallback(() => {
    setRevealComplete(true);
    // Show CTAs shortly after reveal completes
    setTimeout(() => setCtasVisible(true), 200);
  }, []);

  const handleRefund = useCallback(() => {
    if (!jobId) return;

    Alert.alert(
      "Report issue",
      "We'll refund your credits. Continue?",
      [
        { text: "Cancel", style: "cancel" },
        { text: "Refund", onPress: () => refundMutation.mutate() },
      ],
    );
  }, [jobId, refundMutation]);

  const handleShare = useCallback(async () => {
    const shareUrl = `${UNIVERSAL_LINK_ORIGIN}/result/${jobId}`;
    try {
      if (Platform.OS === "web") {
        if (typeof navigator !== "undefined" && navigator.share) {
          await navigator.share({ url: shareUrl });
        } else if (typeof navigator !== "undefined" && navigator.clipboard) {
          await navigator.clipboard.writeText(shareUrl);
          showToast({ kind: "success", message: "Share link copied to clipboard." });
        }
      } else if (Platform.OS === "ios") {
        await Share.share({ url: shareUrl });
      } else {
        await Share.share({ message: shareUrl });
      }
    } catch {
      // User cancelled share sheet — not an error
    }
  }, [jobId]);

  const handleNewGlowUp = useCallback(() => {
    router.replace("/upload");
  }, [router]);

  // ---------------------------------------------------------------------------
  // Render
  // ---------------------------------------------------------------------------

  return (
    <QueryStateView
      isLoading={jobQuery.isLoading}
      error={jobQuery.appError}
      onRetry={() => jobQuery.refetch()}
    >
      {/* Job failed/cancelled — content-level failure inside a successful response */}
      {result && (result.status === "failed" || result.status === "cancelled") ? (
        <>
          <Stack.Screen
            options={{
              title: "Result",
              headerStyle: { backgroundColor: THEME.colors.bg },
              headerTintColor: THEME.colors.textPrimary,
              headerShadowVisible: false,
            }}
          />
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
              onPress={handleNewGlowUp}
              style={[styles.retryButton, { backgroundColor: theme.accent }]}
              accessibilityLabel="Start a new glow-up"
              accessibilityRole="button"
            >
              <Text style={styles.retryText}>New Glow-Up</Text>
            </PressableScale>
          </View>
        </>
      ) : (
        /* Success — before/after reveal */
        <>
          <Stack.Screen
            options={{
              title: "Your Glow-Up",
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
            >
              {/* Before / After Reveal */}
              {result?.before_image_url && result.after_image_url ? (
                <BeforeAfterSlider
                  beforeUrl={result.before_image_url}
                  afterUrl={result.after_image_url}
                  rightLabel="Glow Up"
                  onAccessibilityToggle={handleRevealComplete}
                />
              ) : (
                <View style={styles.missingImages}>
                  <Ionicons
                    name="image-outline"
                    size={48}
                    color={THEME.colors.textDisabled}
                  />
                  <Text style={styles.missingText}>
                    Images are not available yet.
                  </Text>
                </View>
              )}

              {/* User Guidance */}
              {result?.user_guidance && revealComplete && (
                <View style={styles.guidanceContainer}>
                  <Text style={styles.guidanceText}>{result.user_guidance}</Text>
                </View>
              )}

              {/* CTAs */}
              {ctasVisible && (
                <Animated.View
                  entering={FadeIn.duration(250)}
                  style={styles.ctaContainer}
                >
                  {/* Primary: Share (hidden when SHARE_ENABLED=false) */}
                  {features.share_enabled && (
                    <PressableScale
                      onPress={handleShare}
                      style={[styles.ctaButton, { backgroundColor: theme.accent }]}
                      accessibilityLabel="Share your glow-up"
                      accessibilityRole="button"
                    >
                      <View style={styles.ctaRow}>
                        <Ionicons name="share-outline" size={18} color={THEME.colors.white} />
                        <Text style={styles.ctaButtonText}>Share</Text>
                      </View>
                    </PressableScale>
                  )}

                  {/* New Glow-Up — promotes to primary styling when Share is hidden. */}
                  <PressableScale
                    onPress={handleNewGlowUp}
                    style={[
                      styles.ctaButton,
                      newGlowUpIsPrimary
                        ? { backgroundColor: theme.accent }
                        : styles.ctaSecondary,
                    ]}
                    accessibilityLabel="Start a new glow-up"
                    accessibilityRole="button"
                  >
                    <View style={styles.ctaRow}>
                      <Ionicons
                        name="sparkles-outline"
                        size={18}
                        color={newGlowUpIsPrimary ? THEME.colors.white : theme.accent}
                      />
                      <Text
                        style={
                          newGlowUpIsPrimary
                            ? styles.ctaButtonText
                            : [styles.ctaSecondaryText, { color: theme.accent }]
                        }
                      >
                        New Glow-Up
                      </Text>
                    </View>
                  </PressableScale>

                  {/* Tertiary: Refund */}
                  {!refundRequested ? (
                    <PressableScale
                      scale={0.97}
                      onPress={handleRefund}
                      style={styles.ctaTertiary}
                      accessibilityLabel="Report that this does not look like you"
                      accessibilityRole="button"
                    >
                      <View style={styles.ctaRow}>
                        <Ionicons name="flag-outline" size={14} color={THEME.colors.textMuted} />
                        <Text style={styles.ctaTertiaryText}>
                          This doesn&apos;t look like me
                        </Text>
                      </View>
                    </PressableScale>
                  ) : (
                    <View style={styles.ctaTertiary}>
                      <View style={styles.ctaRow}>
                        <Ionicons name="checkmark-circle-outline" size={14} color={theme.accent} />
                        <Text style={[styles.ctaTertiaryText, { color: theme.accent }]}>
                          Refund requested
                        </Text>
                      </View>
                    </View>
                  )}
                </Animated.View>
              )}
            </ScrollView>
          </SafeAreaView>
        </>
      )}
    </QueryStateView>
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
    paddingBottom: THEME.spacing.xxxl * 3,
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
  // User guidance
  guidanceContainer: {
    paddingHorizontal: THEME.spacing.lg,
    paddingTop: THEME.spacing.lg,
  },
  guidanceText: {
    fontFamily: FONTS.body,
    ...THEME.typography.body,
    color: THEME.colors.textSecondary,
    textAlign: "center",
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
  // CTAs
  ctaContainer: {
    paddingHorizontal: THEME.spacing.xl,
    paddingTop: THEME.spacing.xxl,
    gap: THEME.spacing.md,
  },
  ctaRow: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    gap: THEME.spacing.md,
  },
  ctaButton: {
    alignItems: "center",
    justifyContent: "center",
    borderRadius: THEME.radius.pill,
    paddingVertical: THEME.spacing.lg,
    minHeight: 52,
  },
  ctaButtonText: {
    fontFamily: FONTS.bodySemiBold,
    fontSize: 16,
    color: THEME.colors.white,
  },
  ctaSecondary: {
    backgroundColor: THEME.colors.glass,
    borderWidth: 1,
    borderColor: THEME.colors.glassBorder,
  },
  ctaSecondaryText: {
    fontFamily: FONTS.bodyMedium,
    fontSize: 15,
  },
  ctaTertiary: {
    alignItems: "center",
    justifyContent: "center",
    paddingVertical: THEME.spacing.md,
    minHeight: 40,
  },
  ctaTertiaryText: {
    fontFamily: FONTS.body,
    fontSize: 13,
    color: THEME.colors.textMuted,
  },
});
