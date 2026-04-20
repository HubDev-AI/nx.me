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
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
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
import { Stack, useLocalSearchParams } from "expo-router";
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
import { ZoomableImageModal } from "../../components/ui/ZoomableImageModal";
import { CommentsSheet } from "../../components/comments/CommentsSheet";
import { useBackToActiveTab } from "../../lib/last-tab";
import {
  AUTH_VALIDATION,
  CARD_ENDPOINTS,
  FEED_ENDPOINTS,
  MIN_TOUCH_TARGET,
  UNIVERSAL_LINK_ORIGIN,
} from "../../constants/config";
import type { ReactionResponse } from "../../components/feed/types";
import { apiFetch } from "../../lib/api";
import { parseApiError } from "../../lib/errors";
import { THEME } from "../../constants/theme";
import { useTheme } from "../../lib/theme-context";
import { useAuth } from "../../lib/auth-context";
import { hapticLight, hapticMedium, hapticError } from "../../lib/haptics";
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

  // Per-user reaction + comment state. The public /cards/{username} endpoint
  // is cacheable and doesn't carry `has_reacted`, so when we have a postId
  // we seed these from /posts/{postId}/reactions/me. Local counts let the
  // UI update optimistically without re-fetching the card.
  const [hasReacted, setHasReacted] = useState(false);
  const [reactionCount, setReactionCount] = useState<number | null>(null);
  const [commentCount, setCommentCount] = useState<number | null>(null);
  const [commentsVisible, setCommentsVisible] = useState(false);
  const [zoomTarget, setZoomTarget] = useState<"before" | "after" | null>(null);
  const reactingRef = useRef(false);

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

  // Seed local counters from the card payload on first load, then let the
  // per-user state fetch and optimistic updates take over.
  useEffect(() => {
    if (card) {
      setReactionCount((prev) => (prev === null ? card.reaction_count : prev));
      setCommentCount((prev) => (prev === null ? card.comment_count : prev));
    }
  }, [card]);

  // Fetch the authed user's reaction state when we have a postId. Deep-link
  // visitors (no postId) can't toggle a reaction anyway — fall back to the
  // public counter shown on the card.
  useEffect(() => {
    if (!postId) return;
    let cancelled = false;
    apiFetch<ReactionResponse>(FEED_ENDPOINTS.REACTION_STATE(postId))
      .then((state) => {
        if (cancelled) return;
        setHasReacted(state.has_reacted);
        setReactionCount(state.reaction_count);
      })
      .catch(() => {
        // Non-fatal — heart stays outline, count stays from card payload.
      });
    return () => {
      cancelled = true;
    };
  }, [postId]);

  const handleRevealComplete = useCallback(() => {
    setRevealComplete(true);
  }, []);

  const handleZoomBefore = useCallback(() => {
    if (card?.before_image_url) setZoomTarget("before");
  }, [card?.before_image_url]);

  const handleZoomAfter = useCallback(() => {
    if (card?.after_image_url) setZoomTarget("after");
  }, [card?.after_image_url]);

  const handleCloseZoom = useCallback(() => setZoomTarget(null), []);

  const handleRetry = useCallback(() => {
    load();
  }, [load]);

  // Back navigation that works across any tab. Pops the native stack
  // when we have one (preserves tab state on in-app pushes); on deep-
  // link entries with no stack, replaces to whichever tab is active in
  // the mounted tabs navigator — so a user tapping a share link while
  // on /profile lands back on profile, not on the default feed tab.
  const navigateBackToOrigin = useBackToActiveTab();

  const handleBack = useCallback(() => {
    // Don't pop the screen mid-delete — the DELETE request would be
    // orphaned and a late error toast would fire on a screen the user
    // is no longer on.
    if (isDeleting) return;
    navigateBackToOrigin();
  }, [isDeleting, navigateBackToOrigin]);

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
              navigateBackToOrigin();
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
  }, [postId, isDeleting, navigateBackToOrigin, queryClient]);

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
              navigateBackToOrigin();
            } catch (err) {
              hapticError();
              const appError = parseApiError(err);
              showToast({ kind: "error", message: appError.message });
            }
          },
        },
      ],
    );
  }, [userId, card?.display_name, navigateBackToOrigin]);

  // ─── Reaction toggle ────────────────────────────────────────────────────

  const handleToggleReaction = useCallback(async () => {
    if (!postId || reactingRef.current || reactionCount === null) return;
    reactingRef.current = true;

    const previousHasReacted = hasReacted;
    const previousCount = reactionCount;
    const nextHasReacted = !previousHasReacted;
    const delta = nextHasReacted ? 1 : -1;

    // Optimistic update
    hapticMedium();
    setHasReacted(nextHasReacted);
    setReactionCount(Math.max(0, previousCount + delta));

    try {
      const response = await apiFetch<ReactionResponse>(
        FEED_ENDPOINTS.REACT(postId),
        { method: "POST" },
      );
      setHasReacted(response.has_reacted);
      setReactionCount(response.reaction_count);
      // Keep the feed list in sync so when the user pops back, the heart
      // and count match the detail screen without waiting for staleTime.
      queryClient.invalidateQueries({
        queryKey: FEED_QUERY_KEY_PREFIX.slice(),
      });
    } catch (err) {
      hapticError();
      setHasReacted(previousHasReacted);
      setReactionCount(previousCount);
      const appError = parseApiError(err);
      const message =
        appError.kind === "rateLimit"
          ? "Too many reactions. Please slow down."
          : "Couldn't save that reaction. Try again.";
      showToast({ kind: "error", message });
    } finally {
      reactingRef.current = false;
    }
  }, [postId, hasReacted, reactionCount, queryClient]);

  // ─── Comments sheet ─────────────────────────────────────────────────────

  const handleOpenComments = useCallback(() => {
    if (!postId) return;
    hapticLight();
    setCommentsVisible(true);
  }, [postId]);

  const handleCloseComments = useCallback(() => {
    setCommentsVisible(false);
  }, []);

  const handleCommentPosted = useCallback(() => {
    setCommentCount((c) => (c === null ? 1 : c + 1));
    queryClient.invalidateQueries({
      queryKey: FEED_QUERY_KEY_PREFIX.slice(),
    });
  }, [queryClient]);

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
            onPressBeforeImage={handleZoomBefore}
            onPressAfterImage={handleZoomAfter}
          />

          <View style={styles.statsRow}>
            <Pressable
              onPress={handleToggleReaction}
              disabled={!postId || reactingRef.current}
              style={({ pressed }) => [
                styles.stat,
                pressed && styles.statPressed,
              ]}
              accessibilityRole="button"
              accessibilityLabel={
                hasReacted
                  ? `Liked, ${reactionCount ?? card.reaction_count} reactions`
                  : `Like, ${reactionCount ?? card.reaction_count} reactions`
              }
              accessibilityState={{ selected: hasReacted }}
              hitSlop={8}
            >
              <Ionicons
                name={hasReacted ? "heart" : "heart-outline"}
                size={16}
                color={hasReacted ? theme.accent : THEME.colors.textSecondary}
                style={styles.statIcon}
              />
              <Caption
                weight="semibold"
                color={hasReacted ? "primary" : "secondary"}
                style={hasReacted ? { color: theme.accent } : undefined}
              >
                {(reactionCount ?? card.reaction_count).toLocaleString()}
              </Caption>
            </Pressable>
            <Pressable
              onPress={handleOpenComments}
              disabled={!postId}
              style={({ pressed }) => [
                styles.stat,
                pressed && styles.statPressed,
              ]}
              accessibilityRole="button"
              accessibilityLabel={`${commentCount ?? card.comment_count} comments, tap to view`}
              hitSlop={8}
            >
              <Ionicons
                name="chatbubble-outline"
                size={16}
                color={THEME.colors.textSecondary}
                style={styles.statIcon}
              />
              <Caption weight="semibold" color="secondary">
                {(commentCount ?? card.comment_count).toLocaleString()}
              </Caption>
            </Pressable>
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

      <CommentsSheet
        visible={commentsVisible}
        postId={postId ?? ""}
        onClose={handleCloseComments}
        onCommentPosted={handleCommentPosted}
      />

      <ZoomableImageModal
        visible={zoomTarget !== null}
        sourceUri={
          zoomTarget === "before"
            ? card.before_image_url
            : zoomTarget === "after"
              ? card.after_image_url
              : null
        }
        altText={zoomTarget === "before" ? "Before photo" : "Glow-up photo"}
        onClose={handleCloseZoom}
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
    minHeight: MIN_TOUCH_TARGET,
  },
  statPressed: {
    opacity: 0.6,
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
