/**
 * Blocked Users screen — displays the list of users the current user has blocked
 * and allows unblocking them.
 *
 * Route: /blocked-users (custom header)
 * Auth: required
 *
 * Backend:
 *   GET  /v1/users/blocked          -> BlockedListResponse
 *   DELETE /v1/users/{id}/block      -> 204 (unblock)
 */
import { useCallback, useEffect, useState } from "react";
import {
  ActivityIndicator,
  Alert,
  ScrollView,
  StyleSheet,
  View,
} from "react-native";
import { Redirect, useRouter } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Ionicons } from "@expo/vector-icons";
import Animated, { FadeInDown } from "react-native-reanimated";

import { THEME } from "../constants/theme";
import { PageBackground } from "../components/ui/PageBackground";
import { PressableScale } from "../components/ui/PressableScale";
import { EmptyState } from "../components/ui/EmptyState";
import {
  HeaderBackButton,
  HeaderBackButtonSpacer,
} from "../components/ui/HeaderBackButton";
import { Body, Caption, Heading } from "../components/ui/Text";
import { useTheme } from "../lib/theme-context";
import { useCapabilities } from "../lib/capabilities";
import { useEntering } from "../lib/hooks/use-entering";
import { MIN_TOUCH_TARGET } from "../constants/config";
import { apiFetch } from "../lib/api";
import { parseApiError } from "../lib/errors";
import { showToast } from "../lib/toast";
import { unblockUser } from "../lib/block";

/** Header title font size — matches subscription + settings screens. */
const HEADER_TITLE_FONT_SIZE = 20;
/** Header chrome height (button row + bottom padding) — below insets.top. */
const HEADER_CHROME_HEIGHT = MIN_TOUCH_TARGET + THEME.spacing.sm;

// ---------------------------------------------------------------------------
// Types (mirrors backend BlockedListResponse / BlockedUserResponse)
// ---------------------------------------------------------------------------

interface BlockedUser {
  id: string;
  blocked_id: string;
  created_at: string;
  /** Resolved via profile fetch — may be null if profile unavailable */
  username?: string;
  display_name?: string;
  avatar_url?: string | null;
}

interface BlockedListResponse {
  users: {
    id: string;
    blocked_id: string;
    created_at: string;
    /** Backend now resolves display_name for blocked users */
    display_name?: string;
    /** Backend now resolves username for blocked users */
    username?: string;
  }[];
  next_cursor: string | null;
  has_more: boolean;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export default function BlockedUsersScreen() {
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const { theme } = useTheme();
  const caps = useCapabilities();
  const { fadeInDown } = useEntering();

  const [blockedUsers, setBlockedUsers] = useState<BlockedUser[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [unblockingIds, setUnblockingIds] = useState<Set<string>>(new Set());

  // -------------------------------------------------------------------------
  // Fetch blocked list, then resolve display names via profiles
  // -------------------------------------------------------------------------
  const loadBlockedUsers = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const data = await apiFetch<BlockedListResponse>("/v1/users/blocked");
      // Backend now returns display_name and username directly
      const enriched: BlockedUser[] = data.users.map((entry) => ({
        ...entry,
        display_name: entry.display_name,
        username: entry.username,
        avatar_url: null,
      }));
      setBlockedUsers(enriched);
    } catch (err) {
      const appError = parseApiError(err);
      setError(appError.message);
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    if (!caps.canViewBlockedUsers) return;
    loadBlockedUsers();
  }, [caps.canViewBlockedUsers, loadBlockedUsers]);

  // -------------------------------------------------------------------------
  // Unblock handler
  // -------------------------------------------------------------------------
  const handleUnblock = useCallback(
    (user: BlockedUser) => {
      const name = user.display_name || user.username || "this user";
      Alert.alert(
        `Unblock ${name}?`,
        "They will be able to see your posts and interact with you again.",
        [
          { text: "Cancel", style: "cancel" },
          {
            text: "Unblock",
            onPress: async () => {
              setUnblockingIds((prev) => new Set(prev).add(user.blocked_id));
              try {
                await unblockUser(user.blocked_id);
                setBlockedUsers((prev) =>
                  prev.filter((u) => u.blocked_id !== user.blocked_id),
                );
              } catch (err) {
                const appError = parseApiError(err);
                showToast({ kind: 'error', message: appError.message });
              } finally {
                setUnblockingIds((prev) => {
                  const next = new Set(prev);
                  next.delete(user.blocked_id);
                  return next;
                });
              }
            },
          },
        ],
      );
    },
    [],
  );

  // Deep-link defense: with auth or social disabled there is no concept of
  // blocking users. Redirect back to settings so the route matches the
  // capability-gated entry point in settings.tsx.
  if (!caps.canViewBlockedUsers) {
    return <Redirect href="/settings" />;
  }

  // Loading / error / empty states don't need a scroll region — render a
  // plain flex:1 view and let EmptyState (center={true}) do the centering.
  // Matches the canonical "the bounding view IS the empty region" rule.
  const showEmptyScreen = isLoading || error !== null || blockedUsers.length === 0;

  // -------------------------------------------------------------------------
  // Render
  // -------------------------------------------------------------------------
  return (
    <View style={styles.container}>
      <PageBackground overlayOpacity={0.88} />

      {showEmptyScreen ? (
        <Animated.View
          entering={FadeInDown.duration(400)}
          style={styles.fillCentered}
        >
          {isLoading ? (
            <>
              <ActivityIndicator color={theme.accent} size="large" />
              <Caption color="secondary" style={styles.loadingText}>
                Loading blocked users…
              </Caption>
            </>
          ) : error ? (
            <EmptyState
              icon="alert-circle-outline"
              title="Could not load blocked users"
              description={error}
              action={{
                label: "Try Again",
                onPress: loadBlockedUsers,
                accessibilityLabel: "Retry loading blocked users",
              }}
            />
          ) : (
            <EmptyState
              icon="shield-checkmark-outline"
              title="No blocked users"
              description="Users you block will appear here"
            />
          )}
        </Animated.View>
      ) : (
        <ScrollView
          style={styles.scroll}
          contentContainerStyle={[
            styles.scrollContent,
            {
              paddingTop:
                insets.top + HEADER_CHROME_HEIGHT + THEME.spacing.lg,
              paddingBottom: insets.bottom + THEME.spacing.xxxl,
            },
          ]}
          showsVerticalScrollIndicator={false}
        >
          {/* Blocked users list */}
          <View style={styles.list}>
            {blockedUsers.map((user, index) => {
              const isUnblocking = unblockingIds.has(user.blocked_id);
              return (
                <Animated.View
                  key={user.id}
                  entering={fadeInDown(Math.min(index, 8) * 40, 240)}
                >
                  <View style={styles.glassCard}>
                    <View style={styles.userRow}>
                      {/* Avatar placeholder */}
                      <View
                        style={[
                          styles.avatar,
                          { borderColor: theme.accent + "40" },
                        ]}
                      >
                        <Ionicons
                          name="person"
                          size={20}
                          color={THEME.colors.textMuted}
                        />
                      </View>

                      {/* User info */}
                      <View style={styles.userInfo}>
                        <Body weight="medium" color="primary" numberOfLines={1}>
                          {user.display_name || "Blocked User"}
                        </Body>
                        <Caption color="secondary" numberOfLines={1}>
                          {user.username
                            ? `@${user.username}`
                            : `ID: ${user.blocked_id.slice(0, 8)}…`}
                        </Caption>
                      </View>

                      {/* Unblock button */}
                      <PressableScale
                        onPress={() => handleUnblock(user)}
                        disabled={isUnblocking}
                        style={[
                          styles.unblockButton,
                          { borderColor: theme.accent },
                          isUnblocking && styles.unblockButtonDisabled,
                        ]}
                        accessibilityLabel={`Unblock ${user.display_name || "user"}`}
                        accessibilityRole="button"
                      >
                        {isUnblocking ? (
                          <ActivityIndicator
                            color={theme.accent}
                            size="small"
                          />
                        ) : (
                          <Caption weight="medium" color={theme.accent}>
                            Unblock
                          </Caption>
                        )}
                      </PressableScale>
                    </View>
                  </View>
                </Animated.View>
              );
            })}
          </View>
        </ScrollView>
      )}

      {/* Custom header — absolute overlay so the centered empty state stays
          at the true vertical center of the screen (does not shift down). */}
      <View style={[styles.header, { paddingTop: insets.top }]}>
        <HeaderBackButton onPress={() => router.back()} />
        <Heading
          size="md"
          style={styles.headerTitle}
          maxFontSizeMultiplier={1.3}
        >
          Blocked Users
        </Heading>
        <HeaderBackButtonSpacer />
      </View>
    </View>
  );
}

// ---------------------------------------------------------------------------
// Styles
// ---------------------------------------------------------------------------

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: THEME.colors.bg,
  },

  // Absolute header — overlays content so centered empty state stays
  // at the true vertical center of the screen. Matches settings +
  // subscription chrome spacing.
  header: {
    position: "absolute",
    top: 0,
    left: 0,
    right: 0,
    zIndex: 10,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    paddingHorizontal: THEME.spacing.sm,
    paddingBottom: THEME.spacing.sm,
  },
  headerTitle: {
    fontSize: HEADER_TITLE_FONT_SIZE,
  },

  scroll: {
    flex: 1,
  },
  scrollContent: {
    paddingHorizontal: THEME.spacing.xl,
    paddingTop: THEME.spacing.lg,
    flexGrow: 1,
  },

  // Fill-centered wrapper for loading / error / empty states. flex:1
  // bounds the empty region to the entire screen below the header, which
  // lets EmptyState's built-in centering (center={true}) do the work.
  fillCentered: {
    flex: 1,
    alignItems: "center",
    justifyContent: "center",
    gap: THEME.spacing.md,
  },
  loadingText: {
    marginTop: THEME.spacing.sm,
  },

  // List
  list: {
    gap: THEME.spacing.md,
  },

  // Glass card
  glassCard: {
    backgroundColor: THEME.colors.glass,
    borderRadius: THEME.radius.lg,
    borderCurve: "continuous",
    borderWidth: 1,
    borderColor: THEME.colors.glassBorder,
    padding: THEME.spacing.lg,
    ...THEME.shadow.glass,
  },

  // User row
  userRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: THEME.spacing.md,
  },

  // Avatar
  avatar: {
    width: 44,
    height: 44,
    borderRadius: 22,
    backgroundColor: THEME.colors.surfaceElevated,
    borderWidth: 1,
    alignItems: "center",
    justifyContent: "center",
  },

  // User info
  userInfo: {
    flex: 1,
    gap: 2,
  },

  // Unblock button (pill outline)
  unblockButton: {
    borderRadius: THEME.radius.pill,
    borderCurve: "continuous",
    borderWidth: 1,
    alignItems: "center",
    justifyContent: "center",
    minHeight: MIN_TOUCH_TARGET,
    paddingHorizontal: THEME.spacing.lg,
    paddingVertical: THEME.spacing.xs,
  },
  unblockButtonDisabled: {
    opacity: 0.5,
  },
});
