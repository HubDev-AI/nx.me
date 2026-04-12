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
import { useState, useEffect, useCallback } from "react";
import {
  View,
  Text,
  ScrollView,
  Pressable,
  ActivityIndicator,
  StyleSheet,
} from "react-native";
import { useLocalSearchParams, Stack } from "expo-router";
import { SafeAreaView } from "react-native-safe-area-context";
import { Ionicons } from "@expo/vector-icons";

// Phase 3: BeforeAfterReveal replaced by BeforeAfterSlider.
// Phase 4 will update the full card wiring. card/[username] is an additional
// importer beyond result/[jobId] — flagged for Phase 4 attention.
import BeforeAfterSlider from "../../components/result/BeforeAfterSlider";
import SuggestionPills from "../../components/result/SuggestionPills";
import { PageBackground } from "../../components/ui/PageBackground";
import { AUTH_VALIDATION, CARD_ENDPOINTS } from "../../constants/config";
import { apiFetch } from "../../lib/api";
import { parseApiError } from "../../lib/errors";
import { THEME } from "../../constants/theme";
import { FONTS } from "../../hooks/useFonts";
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
const _USERNAME_RE = AUTH_VALIDATION.USERNAME_PATTERN;

// ---------------------------------------------------------------------------
// API helper (no auth — public endpoint)
// ---------------------------------------------------------------------------

async function fetchPublicCard(username: string): Promise<PublicCard> {
  if (!_USERNAME_RE.test(username)) {
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

  useEffect(() => {
    if (!username) return;
    let cancelled = false;

    setLoading(true);
    setError(null);

    fetchPublicCard(username)
      .then((data) => {
        if (!cancelled) {
          setCard(data);
          setLoading(false);
        }
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          const appError = parseApiError(err);
          setError(appError.kind === 'notFound'
            ? "This card is no longer available."
            : appError.message);
          setLoading(false);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [username]);

  const handleRevealComplete = useCallback(() => {
    setRevealComplete(true);
  }, []);

  const handleRetry = useCallback(() => {
    if (!username) return;

    setLoading(true);
    setError(null);

    fetchPublicCard(username)
      .then((data) => {
        setCard(data);
        setLoading(false);
      })
      .catch((err: unknown) => {
        const appError = parseApiError(err);
        setError(appError.kind === 'notFound'
          ? "This card is no longer available."
          : appError.message);
        setLoading(false);
      });
  }, [username]);

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
          <Text style={styles.loadingText}>Loading card...</Text>
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
          <Text style={styles.errorText}>{error ?? "Card not available."}</Text>
          <Pressable
            onPress={handleRetry}
            style={[styles.retryButton, { backgroundColor: theme.accent }]}
            accessibilityLabel="Retry loading card"
            accessibilityRole="button"
          >
            <Text style={styles.retryText}>Try Again</Text>
          </Pressable>
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
          <Text style={styles.usernameHeading}>@{card.username}</Text>

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
              <Text style={styles.statText}>
                {card.reaction_count.toLocaleString()}
              </Text>
            </View>
            <View style={styles.stat}>
              <Ionicons
                name="chatbubble-outline"
                size={16}
                color={THEME.colors.textSecondary}
                style={styles.statIcon}
              />
              <Text style={styles.statText}>
                {card.comment_count.toLocaleString()}
              </Text>
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
    lineHeight: 22,
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
  usernameHeading: {
    fontFamily: FONTS.display,
    ...THEME.typography.heading,
    color: THEME.colors.textPrimary,
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
    borderWidth: 1,
    borderColor: THEME.colors.glassBorder,
  },
  statIcon: {
    marginRight: 2,
  },
  statText: {
    fontFamily: FONTS.bodySemiBold,
    ...THEME.typography.caption,
    color: THEME.colors.textSecondary,
  },
});
