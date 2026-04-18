import { useCallback, useEffect, useState } from "react";
import { ScrollView, StyleSheet, View } from "react-native";
import { useRouter } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Ionicons } from "@expo/vector-icons";

import { apiFetch } from "../lib/api";
import { parseApiError } from "../lib/errors";
import { setItem } from "../lib/secure-storage";
import { SECURE_STORE_KEYS } from "../constants/config";
import { THEME } from "../constants/theme";
import { SUCCESS_DARK } from "../constants/colors";
import { PageBackground } from "../components/ui/PageBackground";
import { Button } from "../components/ui/Button";
import { Body, Caption, Heading } from "../components/ui/Text";
import { useTheme } from "../lib/theme-context";

/** Entitlement response shape from GET /v1/entitlement */
interface EntitlementSnapshot {
  tier: string;
  trial_analyses_remaining: number;
  credit_balance: number;
  can_generate: boolean;
}

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

const LOGO_DIAMETER = 72;
const FEATURE_ICON_DIAMETER = 48;
const FEATURE_ROW_MIN_HEIGHT = 48;

export default function OnboardingScreen() {
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const { theme } = useTheme();

  const [trialRemaining, setTrialRemaining] = useState<number | null>(null);
  const [isLoadingEntitlement, setIsLoadingEntitlement] = useState(true);
  const [entitlementError, setEntitlementError] = useState(false);

  useEffect(() => {
    let cancelled = false;

    async function fetchEntitlement() {
      try {
        const data = await apiFetch<EntitlementSnapshot>("/v1/entitlement");
        if (!cancelled) {
          setTrialRemaining(data.trial_analyses_remaining);
        }
      } catch (err) {
        if (!cancelled) {
          // Non-critical: entitlement info is decorative — silently degrade
          void parseApiError(err);
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
    await setItem(SECURE_STORE_KEYS.ONBOARDING_COMPLETE, "true");
    router.replace("/(tabs)/create");
  }, [router]);

  const trialText = isLoadingEntitlement
    ? "Loading..."
    : entitlementError
      ? "Welcome to NXME"
      : trialRemaining !== null && trialRemaining > 0
        ? `You have ${trialRemaining} free ${trialRemaining === 1 ? "analysis" : "analyses"} remaining`
        : "Welcome to NXME";

  return (
    <View style={[styles.container, { paddingTop: insets.top + THEME.spacing.lg }]}>
      <PageBackground overlayOpacity={0.88} />
      <ScrollView
        contentContainerStyle={[
          styles.scrollContent,
          { paddingBottom: insets.bottom + THEME.spacing.xxl },
        ]}
        showsVerticalScrollIndicator={false}
      >
        <View style={styles.header}>
          <View style={styles.logoCircle}>
            <Ionicons name="sparkles" size={32} color={theme.accent} />
          </View>
          <Heading size="lg" color="primary" style={styles.title}>
            Your Glow-Up Starts Here
          </Heading>
          <Body color="secondary" style={styles.subtitle}>
            {trialText}
          </Body>
        </View>

        {!isLoadingEntitlement &&
        !entitlementError &&
        trialRemaining !== null &&
        trialRemaining > 0 ? (
          <View style={styles.trialBadge}>
            <Ionicons name="gift-outline" size={20} color={SUCCESS_DARK} />
            <Body weight="semibold" color={SUCCESS_DARK}>
              {trialRemaining} free {trialRemaining === 1 ? "trial" : "trials"} included
            </Body>
          </View>
        ) : null}

        <View style={styles.featureList}>
          {FEATURES.map((feature) => (
            <View key={feature.title} style={styles.featureRow}>
              <View style={styles.featureIconCircle}>
                <Ionicons name={feature.icon} size={24} color={theme.accent} />
              </View>
              <View style={styles.featureTextContainer}>
                <Body weight="semibold" color="primary">
                  {feature.title}
                </Body>
                <Caption color="secondary">{feature.description}</Caption>
              </View>
            </View>
          ))}
        </View>

        <View style={styles.ctaContainer}>
          <Button
            title="Analyze My Style"
            onPress={handleAnalyzeCTA}
            variant="primary"
            size="lg"
            block
            glow
            disabled={isLoadingEntitlement && !entitlementError}
            isLoading={isLoadingEntitlement && !entitlementError}
            accentColor={theme.accent}
          />
          <Caption color="secondary" style={styles.ctaHint}>
            Upload a photo and let AI do the rest
          </Caption>
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
    paddingHorizontal: THEME.spacing.xxl,
  },
  header: {
    alignItems: "center",
    marginTop: THEME.spacing.xxxl + THEME.spacing.lg,
    marginBottom: THEME.spacing.xxxl,
  },
  logoCircle: {
    width: LOGO_DIAMETER,
    height: LOGO_DIAMETER,
    borderRadius: LOGO_DIAMETER / 2,
    backgroundColor: THEME.colors.glass,
    borderWidth: 1,
    borderColor: THEME.colors.glassBorder,
    alignItems: "center",
    justifyContent: "center",
    marginBottom: THEME.spacing.lg,
  },
  title: {
    textAlign: "center",
    marginBottom: THEME.spacing.sm,
  },
  subtitle: {
    textAlign: "center",
  },
  trialBadge: {
    flexDirection: "row",
    alignItems: "center",
    alignSelf: "center",
    backgroundColor: THEME.colors.glass,
    borderWidth: 1,
    borderColor: THEME.colors.glassBorder,
    borderRadius: THEME.radius.md,
    borderCurve: "continuous",
    paddingVertical: THEME.spacing.md,
    paddingHorizontal: THEME.spacing.lg,
    gap: THEME.spacing.sm,
    marginBottom: THEME.spacing.xxxl,
  },
  featureList: {
    gap: THEME.spacing.lg,
    marginBottom: THEME.spacing.xxxl,
  },
  featureRow: {
    flexDirection: "row",
    alignItems: "center",
    backgroundColor: THEME.colors.glass,
    borderRadius: THEME.radius.md,
    borderCurve: "continuous",
    borderWidth: 1,
    borderColor: THEME.colors.glassBorder,
    padding: THEME.spacing.lg,
    minHeight: FEATURE_ROW_MIN_HEIGHT,
    gap: THEME.spacing.lg,
  },
  featureIconCircle: {
    width: FEATURE_ICON_DIAMETER,
    height: FEATURE_ICON_DIAMETER,
    borderRadius: THEME.radius.pill,
    backgroundColor: THEME.colors.surfaceElevated,
    alignItems: "center",
    justifyContent: "center",
  },
  featureTextContainer: {
    flex: 1,
    gap: THEME.spacing.xs,
  },
  ctaContainer: {
    marginBottom: THEME.spacing.lg,
    gap: THEME.spacing.sm,
  },
  ctaHint: {
    textAlign: "center",
  },
});
