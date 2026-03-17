import { useEffect, useState, useCallback } from "react";
import { View, Text, Pressable, StyleSheet, ScrollView, Alert } from "react-native";
import { useRouter } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Ionicons } from "@expo/vector-icons";

import { AuthButton } from "../components/auth/AuthButton";
import { apiFetch } from "../lib/api";
import { registerForPushNotifications } from "../lib/notifications";
import {
  BG_PAGE,
  BG_CARD,
  BG_ELEVATED,
  TEXT_PRIMARY,
  TEXT_SECONDARY,
  COLORS,
  SUCCESS_DARK,
} from "../constants/colors";

/** Entitlement response shape from GET /v1/entitlement */
interface EntitlementSnapshot {
  tier: string;
  trial_analyses_remaining: number;
  credit_balance: number;
  can_generate: boolean;
}

/** Spacing unit (8dp grid) */
const SPACING = 8;

/** Feature list items shown to new users */
const FEATURES = [
  {
    icon: "camera-outline" as const,
    title: "Upload Your Photo",
    description: "Take or choose a photo to get started",
  },
  {
    icon: "sparkles-outline" as const,
    title: "AI-Powered Styling",
    description: "Get personalized style transformations",
  },
  {
    icon: "shield-checkmark-outline" as const,
    title: "Your Identity, Preserved",
    description: "We style, never alter who you are",
  },
] as const;

type FeatureIconName = (typeof FEATURES)[number]["icon"];

export default function OnboardingScreen() {
  const router = useRouter();
  const insets = useSafeAreaInsets();

  const [trialRemaining, setTrialRemaining] = useState<number | null>(null);
  const [isLoadingEntitlement, setIsLoadingEntitlement] = useState(true);
  const [entitlementError, setEntitlementError] = useState(false);
  const [isRequestingPush, setIsRequestingPush] = useState(false);
  const [pushCompleted, setPushCompleted] = useState(false);

  // Fetch entitlement on mount
  useEffect(() => {
    let cancelled = false;

    async function fetchEntitlement() {
      try {
        const data = await apiFetch<EntitlementSnapshot>("/v1/entitlement");
        if (!cancelled) {
          setTrialRemaining(data.trial_analyses_remaining);
        }
      } catch {
        if (!cancelled) {
          setEntitlementError(true);
        }
      } finally {
        if (!cancelled) {
          setIsLoadingEntitlement(false);
        }
      }
    }

    fetchEntitlement();
    return () => {
      cancelled = true;
    };
  }, []);

  const handleAnalyzeCTA = useCallback(() => {
    router.replace("/(tabs)/create");
  }, [router]);

  const handleEnablePush = useCallback(async () => {
    setIsRequestingPush(true);
    try {
      const token = await registerForPushNotifications();
      setPushCompleted(true);
      if (token) {
        // Token stored by registerForPushNotifications
      }
      // Whether granted or declined, don't block the user
    } catch {
      // Non-blocking — push is optional
      setPushCompleted(true);
    } finally {
      setIsRequestingPush(false);
    }
  }, []);

  const trialText = isLoadingEntitlement
    ? "Loading..."
    : entitlementError
      ? "Welcome to NXME"
      : trialRemaining !== null && trialRemaining > 0
        ? `You have ${trialRemaining} free ${trialRemaining === 1 ? "analysis" : "analyses"} remaining`
        : "Welcome to NXME";

  return (
    <View style={[styles.container, { paddingTop: insets.top }]}>
      <ScrollView
        contentContainerStyle={[
          styles.scrollContent,
          { paddingBottom: insets.bottom + SPACING * 3 },
        ]}
        showsVerticalScrollIndicator={false}
      >
        {/* Header */}
        <View style={styles.header}>
          <View style={styles.logoCircle}>
            <Ionicons
              name="sparkles"
              size={32}
              color={COLORS.after[500]}
            />
          </View>
          <Text style={styles.title}>Your Glow-Up Starts Here</Text>
          <Text style={styles.subtitle}>{trialText}</Text>
        </View>

        {/* Trial count badge */}
        {!isLoadingEntitlement && !entitlementError && trialRemaining !== null && trialRemaining > 0 && (
          <View style={styles.trialBadge}>
            <Ionicons name="gift-outline" size={20} color={SUCCESS_DARK} />
            <Text style={styles.trialBadgeText}>
              {trialRemaining} free {trialRemaining === 1 ? "trial" : "trials"} included
            </Text>
          </View>
        )}

        {/* Feature list */}
        <View style={styles.featureList}>
          {FEATURES.map((feature) => (
            <View key={feature.title} style={styles.featureRow}>
              <View style={styles.featureIconCircle}>
                <Ionicons
                  name={feature.icon}
                  size={24}
                  color={COLORS.after[500]}
                />
              </View>
              <View style={styles.featureTextContainer}>
                <Text style={styles.featureTitle}>{feature.title}</Text>
                <Text style={styles.featureDescription}>
                  {feature.description}
                </Text>
              </View>
            </View>
          ))}
        </View>

        {/* Push notification opt-in */}
        {!pushCompleted && (
          <View style={styles.pushCard}>
            <View style={styles.pushHeader}>
              <Ionicons
                name="notifications-outline"
                size={24}
                color={TEXT_PRIMARY}
              />
              <Text style={styles.pushTitle}>Stay in the Loop</Text>
            </View>
            <Text style={styles.pushDescription}>
              Get notified when your glow-up is ready and discover new styles.
            </Text>
            <AuthButton
              title="Enable Notifications"
              onPress={handleEnablePush}
              isLoading={isRequestingPush}
            />
            <Pressable
              onPress={() => setPushCompleted(true)}
              accessibilityLabel="Skip push notifications"
              accessibilityRole="button"
              style={styles.skipButton}
            >
              <Text style={styles.skipText}>Not now</Text>
            </Pressable>
          </View>
        )}

        {/* Primary CTA */}
        <View style={styles.ctaContainer}>
          <AuthButton
            title="Analyze My Style"
            onPress={handleAnalyzeCTA}
            disabled={isLoadingEntitlement}
          />
          <Text style={styles.ctaHint}>
            Upload a photo and let AI do the rest
          </Text>
        </View>
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: BG_PAGE,
  },
  scrollContent: {
    paddingHorizontal: SPACING * 3,
  },
  header: {
    alignItems: "center",
    marginTop: SPACING * 6,
    marginBottom: SPACING * 4,
  },
  logoCircle: {
    width: 72,
    height: 72,
    borderRadius: 36,
    backgroundColor: BG_ELEVATED,
    alignItems: "center",
    justifyContent: "center",
    marginBottom: SPACING * 2,
  },
  title: {
    fontSize: 28,
    fontWeight: "700",
    color: TEXT_PRIMARY,
    textAlign: "center",
    marginBottom: SPACING,
  },
  subtitle: {
    fontSize: 16,
    color: TEXT_SECONDARY,
    textAlign: "center",
  },
  trialBadge: {
    flexDirection: "row",
    alignItems: "center",
    alignSelf: "center",
    backgroundColor: BG_ELEVATED,
    paddingVertical: SPACING * 1.5,
    paddingHorizontal: SPACING * 2,
    borderRadius: 12,
    gap: SPACING,
    marginBottom: SPACING * 4,
  },
  trialBadgeText: {
    fontSize: 15,
    fontWeight: "600",
    color: SUCCESS_DARK,
  },
  featureList: {
    gap: SPACING * 2,
    marginBottom: SPACING * 4,
  },
  featureRow: {
    flexDirection: "row",
    alignItems: "center",
    backgroundColor: BG_CARD,
    borderRadius: 12,
    padding: SPACING * 2,
    minHeight: 44,
    gap: SPACING * 2,
  },
  featureIconCircle: {
    width: 48,
    height: 48,
    borderRadius: 24,
    backgroundColor: BG_ELEVATED,
    alignItems: "center",
    justifyContent: "center",
  },
  featureTextContainer: {
    flex: 1,
  },
  featureTitle: {
    fontSize: 16,
    fontWeight: "600",
    color: TEXT_PRIMARY,
    marginBottom: 2,
  },
  featureDescription: {
    fontSize: 14,
    color: TEXT_SECONDARY,
  },
  pushCard: {
    backgroundColor: BG_CARD,
    borderRadius: 16,
    padding: SPACING * 3,
    marginBottom: SPACING * 4,
  },
  pushHeader: {
    flexDirection: "row",
    alignItems: "center",
    gap: SPACING,
    marginBottom: SPACING,
  },
  pushTitle: {
    fontSize: 18,
    fontWeight: "600",
    color: TEXT_PRIMARY,
  },
  pushDescription: {
    fontSize: 14,
    color: TEXT_SECONDARY,
    marginBottom: SPACING * 2,
    lineHeight: 20,
  },
  skipButton: {
    marginTop: SPACING * 1.5,
    paddingVertical: SPACING,
    minHeight: 44,
    alignItems: "center",
    justifyContent: "center",
  },
  skipText: {
    fontSize: 14,
    color: TEXT_SECONDARY,
    textAlign: "center",
  },
  ctaContainer: {
    marginBottom: SPACING * 2,
  },
  ctaHint: {
    fontSize: 13,
    color: TEXT_SECONDARY,
    textAlign: "center",
    marginTop: SPACING,
  },
});
