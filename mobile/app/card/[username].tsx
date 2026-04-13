/**
 * Card Detail Screen — deep link target for nxme.ai/{username}.
 *
 * Displays the public glow-up card for a given username:
 * - Before / after images (animated reveal)
 * - Top-5 improvement recommendations
 * - Reaction and comment counts
 *
 * Route: /card/[username]
 * Auth: none required — calls the public cards API
 */
import { useCallback, useEffect, useState } from "react";
import {
  ActivityIndicator,
  ScrollView,
  StyleSheet,
  View,
} from "react-native";
import { Stack, useLocalSearchParams } from "expo-router";
import { SafeAreaView } from "react-native-safe-area-context";
import { Ionicons } from "@expo/vector-icons";

import BeforeAfterSlider from "../../components/result/BeforeAfterSlider";
import SuggestionPills from "../../components/result/SuggestionPills";
import { PageBackground } from "../../components/ui/PageBackground";
import { Body, Caption, Heading } from "../../components/ui/Text";
import { Button } from "../../components/ui/Button";
import { AUTH_VALIDATION, CARD_ENDPOINTS } from "../../constants/config";
import { apiFetch } from "../../lib/api";
import { parseApiError } from "../../lib/errors";
import { THEME } from "../../constants/theme";
import { useTheme } from "../../lib/theme-context";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface PublicCard {
  username: string;
  before_image_url: string;
  after_image_url: string;
  recommendations: string[];
  reaction_count: number;
  comment_count: number;
}

// ---------------------------------------------------------------------------
// Username validation
// ---------------------------------------------------------------------------

/** Use the canonical username pattern from config (starts with letter, alphanumeric + underscores) */
const USERNAME_RE = AUTH_VALIDATION.USERNAME_PATTERN;

// ---------------------------------------------------------------------------
// API helper (no auth — public endpoint)
// ---------------------------------------------------------------------------

async function fetchPublicCard(username: string): Promise<PublicCard> {
  if (!USERNAME_RE.test(username)) {
    throw new Error("Invalid username format");
  }
  return apiFetch<PublicCard>(CARD_ENDPOINTS.PUBLIC(encodeURIComponent(username)));
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export default function CardDetailScreen() {
  const { username } = useLocalSearchParams<{ username: string }>();
  const { theme } = useTheme();

  const [card, setCard] = useState<PublicCard | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [revealComplete, setRevealComplete] = useState(false);

  const load = useCallback(
    (onResult?: (cancelled: () => boolean) => void) => {
      if (!username) return () => {};
      let cancelled = false;

      setLoading(true);
      setError(null);

      fetchPublicCard(username)
        .then((data) => {
          if (cancelled) return;
          setCard(data);
          setLoading(false);
          onResult?.(() => cancelled);
        })
        .catch((err: unknown) => {
          if (cancelled) return;
          const appError = parseApiError(err);
          setError(
            appError.kind === "notFound"
              ? "This card is no longer available."
              : appError.message,
          );
          setLoading(false);
        });

      return () => {
        cancelled = true;
      };
    },
    [username],
  );

  useEffect(() => load(), [load]);

  const handleRevealComplete = useCallback(() => {
    setRevealComplete(true);
  }, []);

  const handleRetry = useCallback(() => {
    load();
  }, [load]);

  const screenOptions = {
    title: username ? `@${username}` : "Card",
    headerStyle: { backgroundColor: THEME.colors.bg },
    headerTintColor: THEME.colors.textPrimary,
    headerShadowVisible: false,
  };

  // ---------------------------------------------------------------------------
  // Render: Loading
  // ---------------------------------------------------------------------------

  if (loading) {
    return (
      <>
        <Stack.Screen options={screenOptions} />
        <View style={styles.centered}>
          <PageBackground overlayOpacity={0.88} />
          <ActivityIndicator size="large" color={theme.accent} />
          <Body color="secondary">Loading card…</Body>
        </View>
      </>
    );
  }

  // ---------------------------------------------------------------------------
  // Render: Error
  // ---------------------------------------------------------------------------

  if (error || !card) {
    return (
      <>
        <Stack.Screen options={screenOptions} />
        <View style={styles.centered}>
          <PageBackground overlayOpacity={0.88} />
          <Ionicons name="alert-circle-outline" size={48} color={THEME.colors.destructive} />
          <Body color="secondary" style={styles.errorText}>
            {error ?? "Card not available."}
          </Body>
          <Button
            title="Try Again"
            onPress={handleRetry}
            variant="primary"
            size="md"
            accentColor={theme.accent}
            accessibilityLabel="Retry loading card"
            style={styles.retryButton}
          />
        </View>
      </>
    );
  }

  // ---------------------------------------------------------------------------
  // Render: Card content
  // ---------------------------------------------------------------------------

  return (
    <>
      <Stack.Screen options={screenOptions} />
      <SafeAreaView style={styles.safeArea} edges={["bottom"]}>
        <PageBackground overlayOpacity={0.88} />
        <ScrollView
          style={styles.scroll}
          contentContainerStyle={styles.scrollContent}
        >
          {/* Username heading */}
          <Heading size="md" color="primary" style={styles.usernameHeading}>
            @{card.username}
          </Heading>

          {/* Before / After reveal */}
          <BeforeAfterSlider
            beforeUrl={card.before_image_url}
            afterUrl={card.after_image_url}
            rightLabel="Glow Up"
            onAccessibilityToggle={handleRevealComplete}
          />

          {/* Stats row */}
          <View style={styles.statsRow}>
            <View style={styles.stat}>
              <Ionicons
                name="heart-outline"
                size={16}
                color={THEME.colors.textSecondary}
                style={styles.statIcon}
              />
              <Caption weight="semibold" color="secondary">
                {card.reaction_count.toLocaleString()}
              </Caption>
            </View>
            <View style={styles.stat}>
              <Ionicons
                name="chatbubble-outline"
                size={16}
                color={THEME.colors.textSecondary}
                style={styles.statIcon}
              />
              <Caption weight="semibold" color="secondary">
                {card.comment_count.toLocaleString()}
              </Caption>
            </View>
          </View>

          {/* Recommendations */}
          <SuggestionPills
            suggestions={card.recommendations}
            visible={revealComplete}
          />
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
  centered: {
    flex: 1,
    backgroundColor: THEME.colors.bg,
    alignItems: "center",
    justifyContent: "center",
    padding: THEME.spacing.xxxl,
    gap: THEME.spacing.lg,
  },
  errorText: {
    textAlign: "center",
  },
  retryButton: {
    marginTop: THEME.spacing.sm,
  },
  usernameHeading: {
    textAlign: "center",
    paddingTop: THEME.spacing.xxl,
    paddingHorizontal: THEME.spacing.lg,
  },
  statsRow: {
    flexDirection: "row",
    justifyContent: "center",
    gap: THEME.spacing.xxxl,
    paddingHorizontal: THEME.spacing.lg,
    paddingTop: THEME.spacing.sm,
    paddingBottom: THEME.spacing.lg,
  },
  stat: {
    flexDirection: "row",
    alignItems: "center",
    gap: THEME.spacing.xs,
    backgroundColor: THEME.colors.glass,
    paddingHorizontal: THEME.spacing.lg,
    paddingVertical: THEME.spacing.sm,
    borderRadius: THEME.radius.pill,
    borderCurve: "continuous",
    borderWidth: 1,
    borderColor: THEME.colors.glassBorder,
  },
  statIcon: {
    marginRight: 2,
  },
});
