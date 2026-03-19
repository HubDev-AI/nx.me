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

import BeforeAfterReveal from "../../components/result/BeforeAfterReveal";
import SuggestionPills from "../../components/result/SuggestionPills";
import { CARD_ENDPOINTS } from "../../constants/config";
import { apiFetch } from "../../lib/api";
import {
  BG_PAGE,
  BG_ELEVATED,
  TEXT_PRIMARY,
  TEXT_SECONDARY,
  CTA_PRIMARY,
  ERROR_DARK,
  COLORS,
} from "../../constants/colors";

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
// Constants
// ---------------------------------------------------------------------------

const SPACING = 8;

// ---------------------------------------------------------------------------
// Username validation
// ---------------------------------------------------------------------------

const _USERNAME_RE = /^[a-zA-Z0-9_]{1,30}$/;

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

  const [card, setCard] = useState<PublicCard | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [revealComplete, setRevealComplete] = useState(false);

  useEffect(() => {
    if (!username) return;

    setLoading(true);
    setError(null);

    fetchPublicCard(username)
      .then((data) => {
        setCard(data);
        setLoading(false);
      })
      .catch(() => {
        setError("Could not load this card. It may no longer be available.");
        setLoading(false);
      });
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
      .catch(() => {
        setError("Could not load this card. It may no longer be available.");
        setLoading(false);
      });
  }, [username]);

  const screenOptions = {
    title: username ? `@${username}` : "Card",
    headerStyle: { backgroundColor: BG_PAGE },
    headerTintColor: COLORS.neutral.dark[900],
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
          <ActivityIndicator size="large" color={CTA_PRIMARY} />
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
          <Ionicons name="alert-circle-outline" size={48} color={ERROR_DARK} />
          <Text style={styles.errorText}>{error ?? "Card not available."}</Text>
          <Pressable
            onPress={handleRetry}
            style={styles.retryButton}
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
        <ScrollView
          style={styles.scroll}
          contentContainerStyle={styles.scrollContent}
        >
          {/* Username heading */}
          <Text style={styles.usernameHeading}>@{card.username}</Text>

          {/* Before / After reveal */}
          <BeforeAfterReveal
            beforeUrl={card.before_image_url}
            afterUrl={card.after_image_url}
            onRevealComplete={handleRevealComplete}
          />

          {/* Stats row */}
          <View style={styles.statsRow}>
            <View style={styles.stat}>
              <Ionicons
                name="heart-outline"
                size={16}
                color={TEXT_SECONDARY}
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
                color={TEXT_SECONDARY}
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
    backgroundColor: BG_PAGE,
  },
  scroll: {
    flex: 1,
  },
  scrollContent: {
    paddingBottom: SPACING * 6,
  },
  centered: {
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
  usernameHeading: {
    fontSize: 22,
    fontWeight: "700",
    color: TEXT_PRIMARY,
    textAlign: "center",
    paddingTop: SPACING * 3,
    paddingHorizontal: SPACING * 2,
  },
  statsRow: {
    flexDirection: "row",
    justifyContent: "center",
    gap: SPACING * 4,
    paddingHorizontal: SPACING * 2,
    paddingTop: SPACING,
    paddingBottom: SPACING * 2,
  },
  stat: {
    flexDirection: "row",
    alignItems: "center",
    gap: SPACING / 2,
    backgroundColor: BG_ELEVATED,
    paddingHorizontal: SPACING * 2,
    paddingVertical: SPACING,
    borderRadius: 20,
  },
  statIcon: {
    marginRight: 2,
  },
  statText: {
    fontSize: 13,
    fontWeight: "600",
    color: TEXT_SECONDARY,
  },
});
