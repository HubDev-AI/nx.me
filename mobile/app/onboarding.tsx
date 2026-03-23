import { useEffect, useState, useCallback } from "react";
import { View, Text, Pressable, StyleSheet, ScrollView } from "react-native";
import { useRouter } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Ionicons } from "@expo/vector-icons";

import { AuthButton } from "../components/auth/AuthButton";
import { apiFetch } from "../lib/api";
import { registerForPushNotifications } from "../lib/notifications";
import { setItem } from "../lib/secure-storage";
import { THEME } from "../constants/theme";

/** Semantic green for success states */
const SUCCESS_GREEN = "#4ADE80";
import { PageBackground } from "../components/ui/PageBackground";
import { useTheme } from "../lib/theme-context";
import { FONTS } from "../hooks/useFonts";

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

export default function OnboardingScreen() {
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const { theme } = useTheme();

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

  const handleAnalyzeCTA = useCallback(async () => {
    await setItem("nxme_onboarding_complete", "true");
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
      <PageBackground overlayOpacity={0.88} />
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
              color={theme.accent}
            />
          </View>
          <Text style={styles.title}>Your Glow-Up Starts Here</Text>
          <Text style={styles.subtitle}>{trialText}</Text>
        </View>

        {/* Trial count badge */}
        {!isLoadingEntitlement && !entitlementError && trialRemaining !== null && trialRemaining > 0 && (
          <View style={styles.trialBadge}>
            <Ionicons name="gift-outline" size={20} color={SUCCESS_GREEN} />
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
                  color={theme.accent}
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
                color={THEME.colors.textPrimary}
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
            disabled={isLoadingEntitlement && !entitlementError}
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
    backgroundColor: THEME.colors.bg,
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
    backgroundColor: THEME.colors.glass,
    borderWidth: 1,
    borderColor: THEME.colors.glassBorder,
    alignItems: "center",
    justifyContent: "center",
    marginBottom: SPACING * 2,
  },
  title: {
    fontFamily: FONTS.display,
    ...THEME.typography.headingLg,
    color: THEME.colors.textPrimary,
    textAlign: "center",
    marginBottom: SPACING,
  },
  subtitle: {
    fontFamily: FONTS.body,
    fontSize: 16,
    color: THEME.colors.textSecondary,
    textAlign: "center",
    letterSpacing: THEME.typography.body.letterSpacing,
  },
  trialBadge: {
    flexDirection: "row",
    alignItems: "center",
    alignSelf: "center",
    backgroundColor: THEME.colors.glass,
    borderWidth: 1,
    borderColor: THEME.colors.glassBorder,
    paddingVertical: SPACING * 1.5,
    paddingHorizontal: SPACING * 2,
    borderRadius: THEME.radius.md,
    gap: SPACING,
    marginBottom: SPACING * 4,
  },
  trialBadgeText: {
    fontFamily: FONTS.bodySemiBold,
    fontSize: 15,
    color: SUCCESS_GREEN,
  },
  featureList: {
    gap: SPACING * 2,
    marginBottom: SPACING * 4,
  },
  featureRow: {
    flexDirection: "row",
    alignItems: "center",
    backgroundColor: THEME.colors.glass,
    borderRadius: THEME.radius.md,
    borderWidth: 1,
    borderColor: THEME.colors.glassBorder,
    padding: SPACING * 2,
    minHeight: 44,
    gap: SPACING * 2,
  },
  featureIconCircle: {
    width: 48,
    height: 48,
    borderRadius: THEME.radius.pill,
    backgroundColor: THEME.colors.surfaceElevated,
    alignItems: "center",
    justifyContent: "center",
  },
  featureTextContainer: {
    flex: 1,
  },
  featureTitle: {
    fontFamily: FONTS.display,
    fontSize: 17,
    color: THEME.colors.textPrimary,
    letterSpacing: THEME.typography.heading.letterSpacing,
    marginBottom: 2,
  },
  featureDescription: {
    fontFamily: FONTS.body,
    fontSize: 14,
    color: THEME.colors.textSecondary,
  },
  pushCard: {
    backgroundColor: THEME.colors.glass,
    borderRadius: THEME.radius.lg,
    borderWidth: 1,
    borderColor: THEME.colors.glassBorder,
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
    fontFamily: FONTS.display,
    fontSize: 18,
    color: THEME.colors.textPrimary,
    letterSpacing: THEME.typography.heading.letterSpacing,
  },
  pushDescription: {
    fontFamily: FONTS.body,
    fontSize: 14,
    color: THEME.colors.textSecondary,
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
    fontFamily: FONTS.displayItalic,
    fontSize: 14,
    color: THEME.colors.textSecondary,
    textAlign: "center",
  },
  ctaContainer: {
    marginBottom: SPACING * 2,
  },
  ctaHint: {
    fontFamily: FONTS.displayItalic,
    fontSize: 14,
    color: THEME.colors.textSecondary,
    textAlign: "center",
    marginTop: SPACING,
  },
});
