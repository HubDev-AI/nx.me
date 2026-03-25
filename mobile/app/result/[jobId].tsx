/**
 * Result Screen — displays before/after reveal animation with suggestions and CTAs.
 *
 * Route: /result/[jobId]
 *
 * Flow:
 * 1. Fetch job result from GET /v1/jobs/{jobId}
 * 2. Before image slides in, after wipes from right with glow ring
 * 3. Suggestion pills stagger up after reveal completes
 * 4. CTAs fade in: "Share", "Save", "This doesn't look like me"
 * 5. "This doesn't look like me" triggers refund + re-generation offer
 */
import { useState, useEffect, useCallback } from "react";
import {
  View,
  Text,
  ScrollView,
  StyleSheet,
  ActivityIndicator,
  Alert,
  Share,
  Platform,
} from "react-native";
import { useLocalSearchParams, useRouter, Stack } from "expo-router";
import { SafeAreaView } from "react-native-safe-area-context";
import Animated, { FadeIn } from "react-native-reanimated";
import { Ionicons } from "@expo/vector-icons";

import BeforeAfterReveal from "../../components/result/BeforeAfterReveal";
import {
  getJobStatus,
  requestRefund,
  type JobResult,
} from "../../lib/analysis";
import { THEME } from "../../constants/theme";
import { PageBackground } from "../../components/ui/PageBackground";
import { PressableScale } from "../../components/ui/PressableScale";
import { useTheme } from "../../lib/theme-context";
import { FONTS } from "../../hooks/useFonts";
import { UNIVERSAL_LINK_ORIGIN } from "../../constants/config";

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export default function ResultScreen() {
  const { jobId } = useLocalSearchParams<{ jobId: string }>();
  const router = useRouter();
  const { theme } = useTheme();

  const [result, setResult] = useState<JobResult | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [revealComplete, setRevealComplete] = useState(false);
  const [ctasVisible, setCtasVisible] = useState(false);
  const [refundRequested, setRefundRequested] = useState(false);

  // Fetch job result
  useEffect(() => {
    if (!jobId) return;
    let cancelled = false;

    setLoading(true);
    getJobStatus(jobId)
      .then((data) => {
        if (!cancelled) {
          setResult(data);
          setLoading(false);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setError("Failed to load results. Please try again.");
          setLoading(false);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [jobId]);

  const handleRevealComplete = useCallback(() => {
    setRevealComplete(true);
    // Show CTAs shortly after reveal completes
    setTimeout(() => setCtasVisible(true), 200);
  }, []);

  const handleRefund = useCallback(() => {
    if (!jobId) return;

    Alert.alert(
      "Report issue",
      "This will request a refund for this generation. Would you also like to try again?",
      [
        {
          text: "Cancel",
          style: "cancel",
        },
        {
          text: "Refund only",
          onPress: async () => {
            try {
              await requestRefund(jobId);
              setRefundRequested(true);
            } catch {
              setRefundRequested(false);
              Alert.alert("Error", "Failed to process refund. Please try again.");
            }
          },
        },
        {
          text: "Refund & retry",
          style: "destructive",
          onPress: async () => {
            try {
              await requestRefund(jobId);
              setRefundRequested(true);
              router.replace("/upload");
            } catch {
              setRefundRequested(false);
              Alert.alert("Error", "Failed to process refund. Please try again.");
            }
          },
        },
      ],
    );
  }, [jobId, router]);

  const handleShare = useCallback(async () => {
    const shareUrl = `${UNIVERSAL_LINK_ORIGIN}/result/${jobId}`;
    try {
      if (Platform.OS === "web") {
        if (typeof navigator !== "undefined" && navigator.share) {
          await navigator.share({ url: shareUrl });
        } else if (typeof navigator !== "undefined" && navigator.clipboard) {
          await navigator.clipboard.writeText(shareUrl);
          Alert.alert("Link copied", "Share link copied to clipboard");
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
  // Render: Loading
  // ---------------------------------------------------------------------------

  if (loading) {
    return (
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
          <ActivityIndicator size="large" color={theme.accent} />
          <Text style={styles.loadingText}>Loading results...</Text>
        </View>
      </>
    );
  }

  // ---------------------------------------------------------------------------
  // Render: Error
  // ---------------------------------------------------------------------------

  if (error || !result) {
    return (
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
          <Ionicons name="alert-circle-outline" size={48} color={THEME.colors.destructive} />
          <Text style={styles.errorText}>
            {error ?? "No results available."}
          </Text>
          <PressableScale
            onPress={handleNewGlowUp}
            style={[styles.retryButton, { backgroundColor: theme.accent }]}
            accessibilityLabel="Try again"
            accessibilityRole="button"
          >
            <Text style={styles.retryText}>Try Again</Text>
          </PressableScale>
        </View>
      </>
    );
  }

  // ---------------------------------------------------------------------------
  // Render: Job failed/cancelled
  // ---------------------------------------------------------------------------

  if (result.status === "failed" || result.status === "cancelled") {
    return (
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
    );
  }

  // ---------------------------------------------------------------------------
  // Render: Success — before/after reveal
  // ---------------------------------------------------------------------------

  const hasBothImages = result.before_image_url && result.after_image_url;

  return (
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
          {hasBothImages && result.before_image_url && result.after_image_url ? (
            <BeforeAfterReveal
              beforeUrl={result.before_image_url}
              afterUrl={result.after_image_url}
              onRevealComplete={handleRevealComplete}
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
          {result.user_guidance && revealComplete && (
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
              {/* Primary action */}
              <PressableScale
                onPress={handleShare}
                style={styles.ctaPrimary}
                accessibilityLabel="Share your glow-up"
                accessibilityRole="button"
              >
                <Ionicons name="share-outline" size={20} color={THEME.colors.bg} />
                <Text style={styles.ctaPrimaryText}>Share</Text>
              </PressableScale>

              {/* Refund action */}
              {!refundRequested ? (
                <PressableScale
                  scale={0.97}
                  onPress={handleRefund}
                  style={styles.refundButton}
                  accessibilityLabel="Report that this does not look like you"
                  accessibilityRole="button"
                >
                  <Ionicons
                    name="flag-outline"
                    size={16}
                    color={THEME.colors.textSecondary}
                  />
                  <Text style={styles.refundText}>
                    This doesn&apos;t look like me
                  </Text>
                </PressableScale>
              ) : (
                <View style={styles.refundConfirmed}>
                  <Ionicons
                    name="checkmark-circle-outline"
                    size={16}
                    color={theme.accent}
                  />
                  <Text style={styles.refundConfirmedText}>
                    Refund requested
                  </Text>
                </View>
              )}

              {/* New glow-up */}
              <PressableScale
                onPress={handleNewGlowUp}
                style={[
                  styles.newGlowUpButton,
                  { borderColor: theme.accent },
                ]}
                accessibilityLabel="Start a new glow-up"
                accessibilityRole="button"
              >
                <Ionicons
                  name="sparkles-outline"
                  size={18}
                  color={theme.accent}
                />
                <Text style={[styles.newGlowUpText, { color: theme.accent }]}>New Glow-Up</Text>
              </PressableScale>
            </Animated.View>
          )}
        </ScrollView>
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
    paddingBottom: THEME.spacing.xxxl + THEME.spacing.lg,
  },
  // Loading / Error states
  centeredContainer: {
    flex: 1,
    backgroundColor: THEME.colors.bg,
    alignItems: "center",
    justifyContent: "center",
    padding: THEME.spacing.xxxl,
    gap: THEME.spacing.lg,
  },
  loadingText: {
    fontFamily: FONTS.body,
    ...THEME.typography.body,
    color: THEME.colors.textSecondary,
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
    paddingHorizontal: THEME.spacing.lg,
    paddingTop: THEME.spacing.xxl,
    gap: THEME.spacing.lg,
  },
  ctaPrimary: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: THEME.colors.glass,
    borderRadius: THEME.radius.pill,
    borderWidth: 1,
    borderColor: THEME.colors.glassBorder,
    paddingVertical: THEME.spacing.lg - 2,
    gap: THEME.spacing.sm,
    minHeight: 48,
  },
  ctaPrimaryText: {
    fontFamily: FONTS.bodySemiBold,
    fontSize: 15,
    color: THEME.colors.textPrimary,
  },
  // Refund
  refundButton: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    paddingVertical: THEME.spacing.md,
    gap: THEME.spacing.sm,
    minHeight: 44,
  },
  refundText: {
    fontFamily: FONTS.body,
    ...THEME.typography.caption,
    color: THEME.colors.textSecondary,
    textDecorationLine: "underline",
  },
  refundConfirmed: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    paddingVertical: THEME.spacing.md,
    gap: THEME.spacing.sm,
  },
  refundConfirmedText: {
    fontFamily: FONTS.bodyMedium,
    ...THEME.typography.caption,
    color: THEME.colors.textSecondary,
  },
  // New glow-up
  newGlowUpButton: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    borderRadius: THEME.radius.pill,
    paddingVertical: THEME.spacing.md,
    gap: THEME.spacing.sm,
    minHeight: 44,
    borderWidth: 1,
  },
  newGlowUpText: {
    fontFamily: FONTS.bodyMedium,
    fontSize: 15,
  },
});
