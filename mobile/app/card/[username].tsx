/**
 * Card Detail Screen — post detail + deep-link target for nxme.ai/{username}.
 *
 * Displays the public glow-up card for a given username:
 * - Before / after slider reveal
 * - Top improvement recommendations
 * - Reaction and comment counts
 * - Custom header with back button + 3-dots menu
 *
 * Route: /card/[username]
 * Params (from in-app feed, optional for deep-link visitors):
 *   - postId — enables Report / Delete
 *   - userId — enables Block
 *
 * Ownership = authed session username matches the card username.
 */
import { useCallback, useEffect, useMemo, useState } from "react";
import {
  ActivityIndicator,
  Alert,
  Platform,
  Pressable,
  ScrollView,
  Share,
  StyleSheet,
  View,
} from "react-native";
import { Stack, useLocalSearchParams, useRouter } from "expo-router";
import { SafeAreaView, useSafeAreaInsets } from "react-native-safe-area-context";
import { Ionicons } from "@expo/vector-icons";
import { useQueryClient } from "@tanstack/react-query";
import * as Clipboard from "expo-clipboard";
import * as WebBrowser from "expo-web-browser";

import BeforeAfterSlider from "../../components/result/BeforeAfterSlider";
import SuggestionPills from "../../components/result/SuggestionPills";
import { PageBackground } from "../../components/ui/PageBackground";
import { Body, Caption, Heading } from "../../components/ui/Text";
import { Button } from "../../components/ui/Button";
import {
  HeaderBackButton,
} from "../../components/ui/HeaderBackButton";
import { DropdownMenu, type DropdownMenuItem } from "../../components/ui/DropdownMenu";
import {
  AUTH_VALIDATION,
  CARD_ENDPOINTS,
  FEED_ENDPOINTS,
  MIN_TOUCH_TARGET,
  UNIVERSAL_LINK_ORIGIN,
} from "../../constants/config";
import { apiFetch } from "../../lib/api";
import { parseApiError } from "../../lib/errors";
import { THEME } from "../../constants/theme";
import { useTheme } from "../../lib/theme-context";
import { useAuth } from "../../lib/auth-context";
import { hapticLight, hapticError } from "../../lib/haptics";
import { showToast } from "../../lib/toast";
import { blockUser } from "../../lib/block";
import { reportPost } from "../../lib/report";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface RecommendationItem {
  rank: number;
  category: string;
  suggestion: string;
  rationale: string | null;
}

interface PublicCard {
  username: string;
  display_name: string;
  share_hash: string;
  before_image_url: string;
  after_image_url: string;
  recommendations: RecommendationItem[];
  reaction_count: number;
  comment_count: number;
}

// ---------------------------------------------------------------------------
// Username validation
// ---------------------------------------------------------------------------

const USERNAME_RE = AUTH_VALIDATION.USERNAME_PATTERN;

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

/**
 * Post-type label shown in the screen header. Currently all cards are
 * glow-ups; when we ship additional post types (make-up, style, etc.)
 * this will come from the card response and select between labels.
 */
const CARD_TITLE_GLOW_UP = "Glow Up";

/** Feed query key prefix — matches `useFeed()`'s useInfiniteQuery key. */
const FEED_QUERY_KEY_PREFIX = ["feed"] as const;

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
  const { username, postId, userId } = useLocalSearchParams<{
    username: string;
    postId?: string;
    userId?: string;
  }>();
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const { theme } = useTheme();
  const { username: currentUsername } = useAuth();
  const queryClient = useQueryClient();

  const [card, setCard] = useState<PublicCard | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [revealComplete, setRevealComplete] = useState(false);
  const [menuVisible, setMenuVisible] = useState(false);
  const [isDeleting, setIsDeleting] = useState(false);

  const isOwner = useMemo(
    () => !!currentUsername && !!card && currentUsername === card.username,
    [currentUsername, card],
  );

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

  const handleBack = useCallback(() => {
    // Don't pop the screen mid-delete — the DELETE request would be
    // orphaned and a late error toast would fire on a screen the user
    // is no longer on.
    if (isDeleting) return;
    router.back();
  }, [router, isDeleting]);

  const toggleMenu = useCallback(() => setMenuVisible((v) => !v), []);
  const closeMenu = useCallback(() => setMenuVisible(false), []);

  // ─── Menu actions ──────────────────────────────────────────────────────

  // Prefer the deep-link hash URL (`/{username}/glow-up/{share_hash}`) so the
  // link pins this specific published post. Falls back to the latest-card URL
  // while the public card is still loading.
  const shareUrl = card
    ? `${UNIVERSAL_LINK_ORIGIN}/${card.username}/glow-up/${card.share_hash}`
    : username
      ? `${UNIVERSAL_LINK_ORIGIN}/${username}`
      : UNIVERSAL_LINK_ORIGIN;
  const shareMessage = `Check out this glow-up on NXME ${shareUrl}`;

  const handleShare = useCallback(async () => {
    hapticLight();
    try {
      if (Platform.OS === "web") {
        if (typeof navigator !== "undefined" && navigator.share) {
          await navigator.share({ url: shareUrl, text: shareMessage });
        } else if (typeof navigator !== "undefined" && navigator.clipboard) {
          await navigator.clipboard.writeText(shareUrl);
          showToast({ kind: "success", message: "Share link copied to clipboard" });
        }
      } else if (Platform.OS === "ios") {
        await Share.share({ message: shareMessage, url: shareUrl });
      } else {
        await Share.share({ message: shareMessage });
      }
    } catch {
      // User cancelled share sheet
    }
  }, [shareUrl, shareMessage]);

  const handleCopyLink = useCallback(async () => {
    try {
      await Clipboard.setStringAsync(shareUrl);
      hapticLight();
      showToast({ kind: "success", message: "Link copied to clipboard" });
    } catch {
      hapticError();
      showToast({ kind: "error", message: "Couldn't copy link. Try again." });
    }
  }, [shareUrl]);

  const handleOpenInBrowser = useCallback(async () => {
    try {
      hapticLight();
      // Use openBrowserAsync (SFSafariViewController / Chrome Custom Tabs)
      // instead of Linking.openURL — the latter loops back to the app
      // because NXME claims `nxme.ai` as a universal link domain, so
      // `Linking.openURL("https://nxme.ai/…")` re-navigates here.
      await WebBrowser.openBrowserAsync(shareUrl);
    } catch {
      hapticError();
      showToast({ kind: "error", message: "Couldn't open link. Try again." });
    }
  }, [shareUrl]);

  const handleDeletePost = useCallback(() => {
    if (!postId || isDeleting) return;
    Alert.alert(
      "Delete Post",
      "This will permanently remove this post. This action cannot be undone.",
      [
        { text: "Cancel", style: "cancel" },
        {
          text: "Delete",
          style: "destructive",
          onPress: async () => {
            setIsDeleting(true);
            try {
              await apiFetch<void>(FEED_ENDPOINTS.DELETE_POST(postId), {
                method: "DELETE",
              });
              hapticLight();
              // Invalidate every feed sort variant so the feed refetches
              // (and the deleted post disappears) the moment the user pops
              // back to the list. Without this, `staleTime: 30s` in useFeed
              // would leave the deleted card in the UI until manual pull-
              // to-refresh.
              queryClient.invalidateQueries({
                queryKey: FEED_QUERY_KEY_PREFIX.slice(),
              });
              router.back();
            } catch (err) {
              hapticError();
              const appError = parseApiError(err);
              const msg =
                appError.kind === "permission"
                  ? "You can only delete your own posts."
                  : appError.message;
              showToast({ kind: "error", message: msg });
            } finally {
              setIsDeleting(false);
            }
          },
        },
      ],
    );
  }, [postId, isDeleting, router, queryClient]);

  const handleBlockUser = useCallback(() => {
    if (!userId) return;
    const name = card?.display_name || "this user";
    Alert.alert(
      "Block User",
      `Are you sure you want to block ${name}? You won't see their posts anymore.`,
      [
        { text: "Cancel", style: "cancel" },
        {
          text: "Block",
          style: "destructive",
          onPress: async () => {
            try {
              await blockUser(userId);
              hapticLight();
              showToast({ kind: "success", message: `${name} has been blocked.` });
              router.back();
            } catch (err) {
              hapticError();
              const appError = parseApiError(err);
              showToast({ kind: "error", message: appError.message });
            }
          },
        },
      ],
    );
  }, [userId, card?.display_name, router]);

  const handleReportPost = useCallback(() => {
    if (!postId) return;
    Alert.alert(
      "Report Post",
      "Are you sure you want to report this post? Our team will review it.",
      [
        { text: "Cancel", style: "cancel" },
        {
          text: "Report",
          style: "destructive",
          onPress: async () => {
            try {
              await reportPost(postId);
              hapticLight();
              showToast({ kind: "success", message: "Thank you. Our team will review this post." });
            } catch (err) {
              hapticError();
              const appError = parseApiError(err);
              showToast({ kind: "error", message: appError.message });
            }
          },
        },
      ],
    );
  }, [postId]);

  const menuItems = useMemo<DropdownMenuItem[]>(() => {
    const items: DropdownMenuItem[] = [
      { label: "Share", icon: "share-outline", onPress: handleShare },
    ];
    // Copy / Open are only meaningful once the card has loaded — before that
    // we'd fall back to a bare `/{username}` URL that doesn't pin the post.
    if (card) {
      items.push({
        label: "Copy Link",
        icon: "link-outline",
        onPress: handleCopyLink,
      });
      items.push({
        label: "Open in Browser",
        icon: "open-outline",
        onPress: handleOpenInBrowser,
      });
    }
    if (isOwner) {
      if (postId) {
        items.push({
          label: isDeleting ? "Deleting..." : "Delete Post",
          icon: "trash-outline",
          onPress: handleDeletePost,
          destructive: true,
        });
      }
    } else {
      if (userId) {
        items.push({
          label: "Block User",
          icon: "ban-outline",
          onPress: handleBlockUser,
        });
      }
      if (postId) {
        items.push({
          label: "Report Post",
          icon: "flag-outline",
          onPress: handleReportPost,
          destructive: true,
        });
      }
    }
    return items;
  }, [
    card,
    isOwner,
    postId,
    userId,
    isDeleting,
    handleShare,
    handleCopyLink,
    handleOpenInBrowser,
    handleDeletePost,
    handleBlockUser,
    handleReportPost,
  ]);

  // ─── Render ─────────────────────────────────────────────────────────────

  const renderHeader = (title: string) => (
    <View style={[styles.header, { paddingTop: insets.top }]}>
      <HeaderBackButton onPress={handleBack} />
      <Heading
        size="md"
        style={styles.headerTitle}
        numberOfLines={1}
        maxFontSizeMultiplier={1.3}
      >
        {title}
      </Heading>
      {menuItems.length > 0 ? (
        <Pressable
          onPress={toggleMenu}
          style={styles.headerAction}
          accessibilityLabel="More options"
          accessibilityRole="button"
          hitSlop={8}
        >
          <Ionicons
            name="ellipsis-horizontal"
            size={22}
            color={THEME.colors.textPrimary}
          />
        </Pressable>
      ) : (
        <View style={styles.headerAction} />
      )}
    </View>
  );

  if (loading) {
    return (
      <>
        <Stack.Screen options={{ headerShown: false }} />
        <SafeAreaView style={styles.safeArea} edges={["bottom"]}>
          <PageBackground overlayOpacity={0.88} />
          {renderHeader(CARD_TITLE_GLOW_UP)}
          <View style={styles.centered}>
            <ActivityIndicator size="large" color={theme.accent} />
            <Body color="secondary">Loading card…</Body>
          </View>
        </SafeAreaView>
      </>
    );
  }

  if (error || !card) {
    return (
      <>
        <Stack.Screen options={{ headerShown: false }} />
        <SafeAreaView style={styles.safeArea} edges={["bottom"]}>
          <PageBackground overlayOpacity={0.88} />
          {renderHeader(CARD_TITLE_GLOW_UP)}
          <View style={styles.centered}>
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
        </SafeAreaView>
      </>
    );
  }

  return (
    <>
      <Stack.Screen options={{ headerShown: false }} />
      <SafeAreaView style={styles.safeArea} edges={["bottom"]}>
        <PageBackground overlayOpacity={0.88} />
        {renderHeader(CARD_TITLE_GLOW_UP)}
        <ScrollView
          style={styles.scroll}
          contentContainerStyle={styles.scrollContent}
        >
          <Heading size="md" color="primary" style={styles.usernameHeading}>
            {card.display_name}
          </Heading>

          <BeforeAfterSlider
            beforeUrl={card.before_image_url}
            afterUrl={card.after_image_url}
            rightLabel="Glow Up"
            onAccessibilityToggle={handleRevealComplete}
          />

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

          <SuggestionPills
            suggestions={card.recommendations.map((r) => r.suggestion)}
            visible={revealComplete}
          />
        </ScrollView>
      </SafeAreaView>

      <DropdownMenu
        visible={menuVisible}
        onClose={closeMenu}
        items={menuItems}
        anchorPosition={{ top: insets.top + MIN_TOUCH_TARGET, right: THEME.spacing.lg }}
      />

      {isDeleting && (
        <View style={styles.deletingOverlay}>
          <ActivityIndicator size="large" color={THEME.colors.textPrimary} />
          <Body weight="medium" color="primary">Deleting...</Body>
        </View>
      )}
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
  header: {
    flexDirection: "row",
    alignItems: "center",
    paddingHorizontal: THEME.spacing.lg,
    paddingBottom: THEME.spacing.sm,
    gap: THEME.spacing.sm,
  },
  headerTitle: {
    flex: 1,
    textAlign: "center",
  },
  headerAction: {
    width: MIN_TOUCH_TARGET,
    height: MIN_TOUCH_TARGET,
    alignItems: "center",
    justifyContent: "center",
  },
  scroll: {
    flex: 1,
  },
  scrollContent: {
    paddingBottom: THEME.spacing.xxxl + THEME.spacing.lg,
  },
  centered: {
    flex: 1,
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
    paddingTop: THEME.spacing.xl,
    paddingBottom: THEME.spacing.sm,
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
  deletingOverlay: {
    ...StyleSheet.absoluteFillObject,
    backgroundColor: "rgba(0,0,0,0.6)",
    alignItems: "center",
    justifyContent: "center",
    zIndex: 100,
    gap: THEME.spacing.md,
  },
});
