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
  Pressable,
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
import SuggestionPills from "../../components/result/SuggestionPills";
import {
  getJobStatus,
  requestRefund,
  type JobResult,
} from "../../lib/analysis";
import {
  BG_PAGE,
  TEXT_PRIMARY,
  TEXT_SECONDARY,
  TEXT_DISABLED,
  CTA_PRIMARY,
  CTA_PRESSED,
  ERROR_DARK,
  CORAL_TINT,
  COLORS,
} from "../../constants/colors";
import { UNIVERSAL_LINK_ORIGIN } from "../../constants/config";

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export default function ResultScreen() {
  const { jobId } = useLocalSearchParams<{ jobId: string }>();
  const router = useRouter();

  const [result, setResult] = useState<JobResult | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [revealComplete, setRevealComplete] = useState(false);
  const [ctasVisible, setCtasVisible] = useState(false);
  const [refundRequested, setRefundRequested] = useState(false);

  // Fetch job result
  useEffect(() => {
    if (!jobId) return;

    setLoading(true);
    getJobStatus(jobId)
      .then((data) => {
        setResult(data);
        setLoading(false);
      })
      .catch(() => {
        setError("Failed to load results. Please try again.");
        setLoading(false);
      });
  }, [jobId]);

  const handleRevealComplete = useCallback(() => {
    setRevealComplete(true);
    // Stagger CTAs slightly after pills
    const ctaDelay = (result?.suggestions?.length ?? 0) * 80 + 200;
    setTimeout(() => setCtasVisible(true), ctaDelay);
  }, [result?.suggestions?.length]);

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
      if (Platform.OS === "ios") {
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
            headerStyle: { backgroundColor: BG_PAGE },
            headerTintColor: COLORS.neutral.dark[900],
            headerShadowVisible: false,
          }}
        />
        <View style={styles.centeredContainer}>
          <ActivityIndicator size="large" color={CTA_PRIMARY} />
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
            headerStyle: { backgroundColor: BG_PAGE },
            headerTintColor: COLORS.neutral.dark[900],
            headerShadowVisible: false,
          }}
        />
        <View style={styles.centeredContainer}>
          <Ionicons name="alert-circle-outline" size={48} color={ERROR_DARK} />
          <Text style={styles.errorText}>
            {error ?? "No results available."}
          </Text>
          <Pressable
            onPress={handleNewGlowUp}
            style={styles.retryButton}
            accessibilityLabel="Try again"
            accessibilityRole="button"
          >
            <Text style={styles.retryText}>Try Again</Text>
          </Pressable>
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
            headerStyle: { backgroundColor: BG_PAGE },
            headerTintColor: COLORS.neutral.dark[900],
            headerShadowVisible: false,
          }}
        />
        <View style={styles.centeredContainer}>
          <Ionicons
            name={result.status === "cancelled" ? "close-circle-outline" : "alert-circle-outline"}
            size={48}
            color={result.status === "cancelled" ? TEXT_SECONDARY : ERROR_DARK}
          />
          <Text style={styles.errorText}>
            {result.status === "cancelled"
              ? "Generation was cancelled."
              : result.error_message ?? "Generation failed."}
          </Text>
          <Pressable
            onPress={handleNewGlowUp}
            style={styles.retryButton}
            accessibilityLabel="Start a new glow-up"
            accessibilityRole="button"
          >
            <Text style={styles.retryText}>New Glow-Up</Text>
          </Pressable>
        </View>
      </>
    );
  }

  // ---------------------------------------------------------------------------
  // Render: Success — before/after reveal
  // ---------------------------------------------------------------------------

  const hasBothImages = result.before_url && result.after_url;

  return (
    <>
      <Stack.Screen
        options={{
          title: "Your Glow-Up",
          headerStyle: { backgroundColor: BG_PAGE },
          headerTintColor: COLORS.neutral.dark[900],
          headerShadowVisible: false,
        }}
      />
      <SafeAreaView style={styles.safeArea} edges={["bottom"]}>
        <ScrollView
          style={styles.scroll}
          contentContainerStyle={styles.scrollContent}
        >
          {/* Before / After Reveal */}
          {hasBothImages ? (
            <BeforeAfterReveal
              beforeUrl={result.before_url!}
              afterUrl={result.after_url!}
              onRevealComplete={handleRevealComplete}
            />
          ) : (
            <View style={styles.missingImages}>
              <Ionicons
                name="image-outline"
                size={48}
                color={TEXT_DISABLED}
              />
              <Text style={styles.missingText}>
                Images are not available yet.
              </Text>
            </View>
          )}

          {/* Suggestion Pills */}
          <SuggestionPills
            suggestions={result.suggestions ?? []}
            visible={revealComplete}
          />

          {/* CTAs */}
          {ctasVisible && (
            <Animated.View
              entering={FadeIn.duration(250)}
              style={styles.ctaContainer}
            >
              {/* Primary action */}
              <Pressable
                onPress={handleShare}
                style={({ pressed }) => [
                  styles.ctaPrimary,
                  pressed && styles.ctaPrimaryPressed,
                ]}
                accessibilityLabel="Share your glow-up"
                accessibilityRole="button"
              >
                <Ionicons name="share-outline" size={20} color="#FFFFFF" />
                <Text style={styles.ctaPrimaryText}>Share</Text>
              </Pressable>

              {/* Refund action */}
              {!refundRequested ? (
                <Pressable
                  onPress={handleRefund}
                  style={styles.refundButton}
                  accessibilityLabel="Report that this does not look like you"
                  accessibilityRole="button"
                >
                  <Ionicons
                    name="flag-outline"
                    size={16}
                    color={TEXT_SECONDARY}
                  />
                  <Text style={styles.refundText}>
                    This doesn't look like me
                  </Text>
                </Pressable>
              ) : (
                <View style={styles.refundConfirmed}>
                  <Ionicons
                    name="checkmark-circle-outline"
                    size={16}
                    color={COLORS.after[400]}
                  />
                  <Text style={styles.refundConfirmedText}>
                    Refund requested
                  </Text>
                </View>
              )}

              {/* New glow-up */}
              <Pressable
                onPress={handleNewGlowUp}
                style={({ pressed }) => [
                  styles.newGlowUpButton,
                  pressed && styles.newGlowUpButtonPressed,
                ]}
                accessibilityLabel="Start a new glow-up"
                accessibilityRole="button"
              >
                <Ionicons
                  name="sparkles-outline"
                  size={18}
                  color={CTA_PRIMARY}
                />
                <Text style={styles.newGlowUpText}>New Glow-Up</Text>
              </Pressable>
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
    paddingBottom: SPACING * 6,
  },
  // Loading / Error states
  centeredContainer: {
    flex: 1,
    backgroundColor: BG_PAGE,
    alignItems: "center",
    justifyContent: "center",
    padding: SPACING * 4,
    gap: SPACING * 2,
  },
  loadingText: {
    fontSize: 16,
    color: TEXT_SECONDARY,
  },
  errorText: {
    fontSize: 16,
    color: TEXT_SECONDARY,
    textAlign: "center",
    lineHeight: 22,
  },
  retryButton: {
    backgroundColor: CTA_PRIMARY,
    borderRadius: 12,
    paddingHorizontal: SPACING * 4,
    paddingVertical: 12,
    marginTop: SPACING,
  },
  retryText: {
    fontSize: 15,
    fontWeight: "700",
    color: "#FFFFFF",
  },
  // Missing images
  missingImages: {
    alignItems: "center",
    justifyContent: "center",
    padding: SPACING * 6,
    gap: SPACING * 2,
  },
  missingText: {
    fontSize: 14,
    color: TEXT_SECONDARY,
  },
  // CTAs
  ctaContainer: {
    paddingHorizontal: SPACING * 2,
    paddingTop: SPACING * 3,
    gap: SPACING * 2,
  },
  ctaPrimary: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: CTA_PRIMARY,
    borderRadius: 12,
    paddingVertical: 14,
    gap: SPACING,
    minHeight: SPACING * 6,
  },
  ctaPrimaryPressed: {
    backgroundColor: CTA_PRESSED,
  },
  ctaPrimaryText: {
    fontSize: 15,
    fontWeight: "700",
    color: "#FFFFFF",
  },
  // Refund
  refundButton: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    paddingVertical: SPACING * 1.5,
    gap: SPACING,
    minHeight: 44,
  },
  refundText: {
    fontSize: 13,
    color: TEXT_SECONDARY,
    textDecorationLine: "underline",
  },
  refundConfirmed: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    paddingVertical: SPACING * 1.5,
    gap: SPACING,
  },
  refundConfirmedText: {
    fontSize: 13,
    color: COLORS.after[400],
    fontWeight: "600",
  },
  // New glow-up
  newGlowUpButton: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    borderRadius: 12,
    paddingVertical: 12,
    gap: SPACING,
    minHeight: 44,
    borderWidth: 1,
    borderColor: CTA_PRIMARY,
  },
  newGlowUpButtonPressed: {
    backgroundColor: CORAL_TINT,
  },
  newGlowUpText: {
    fontSize: 15,
    fontWeight: "600",
    color: CTA_PRIMARY,
  },
});
