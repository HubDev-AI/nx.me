/**
 * Blocked Users screen — displays the list of users the current user has blocked
 * and allows unblocking them.
 *
 * Route: /blocked-users (Stack.Screen)
 * Auth: required
 *
 * Backend:
 *   GET  /v1/users/blocked          -> BlockedListResponse
 *   DELETE /v1/users/{id}/block      -> 204 (unblock)
 */
import { useState, useEffect, useCallback } from "react";
import {
  View,
  Text,
  ScrollView,
  Pressable,
  ActivityIndicator,
  Alert,
  StyleSheet,
} from "react-native";
import { Stack } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Ionicons } from "@expo/vector-icons";
import Animated, { FadeInDown } from "react-native-reanimated";

import { THEME } from "../constants/theme";
import { PageBackground } from "../components/ui/PageBackground";
import { useTheme } from "../lib/theme-context";
import { FONTS } from "../hooks/useFonts";
import { MIN_TOUCH_TARGET } from "../constants/config";
import { apiFetch, ApiError } from "../lib/api";
import { unblockUser } from "../lib/block";

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
  users: Array<{
    id: string;
    blocked_id: string;
    created_at: string;
    /** Backend now resolves display_name for blocked users */
    display_name?: string;
    /** Backend now resolves username for blocked users */
    username?: string;
  }>;
  next_cursor: string | null;
  has_more: boolean;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export default function BlockedUsersScreen() {
  const insets = useSafeAreaInsets();
  const { theme } = useTheme();

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
      setError(
        err instanceof ApiError
          ? `Failed to load blocked users (${err.status})`
          : "Failed to load blocked users",
      );
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    loadBlockedUsers();
  }, [loadBlockedUsers]);

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
              } catch {
                Alert.alert("Error", "Failed to unblock user. Please try again.");
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

  // -------------------------------------------------------------------------
  // Render
  // -------------------------------------------------------------------------
  return (
    <>
      <Stack.Screen
        options={{
          title: "Blocked Users",
          headerStyle: { backgroundColor: THEME.colors.bg },
          headerTintColor: THEME.colors.textPrimary,
          headerShadowVisible: false,
          headerTitleStyle: {
            fontFamily: FONTS.display,
            fontSize: 18,
          },
        }}
      />

      <View style={styles.container}>
        <PageBackground overlayOpacity={0.88} />

        <ScrollView
          style={styles.scroll}
          contentContainerStyle={[
            styles.scrollContent,
            { paddingBottom: insets.bottom + THEME.spacing.xxxl },
          ]}
          showsVerticalScrollIndicator={false}
        >
          {/* Loading state */}
          {isLoading ? (
            <Animated.View
              entering={FadeInDown.duration(400)}
              style={styles.centered}
            >
              <ActivityIndicator color={theme.accent} size="large" />
              <Text style={styles.loadingText}>Loading blocked users...</Text>
            </Animated.View>
          ) : error ? (
            /* Error state */
            <Animated.View
              entering={FadeInDown.duration(400)}
              style={styles.centered}
            >
              <Ionicons
                name="alert-circle-outline"
                size={48}
                color={THEME.colors.textSecondary}
              />
              <Text style={styles.errorText}>{error}</Text>
              <Pressable
                onPress={loadBlockedUsers}
                style={[styles.retryButton, { backgroundColor: theme.accent }]}
                accessibilityLabel="Retry loading blocked users"
                accessibilityRole="button"
              >
                <Ionicons name="refresh-outline" size={18} color={THEME.colors.bg} />
                <Text style={styles.retryButtonText}>Try Again</Text>
              </Pressable>
            </Animated.View>
          ) : blockedUsers.length === 0 ? (
            /* Empty state */
            <Animated.View
              entering={FadeInDown.duration(400)}
              style={styles.centered}
            >
              <View style={styles.emptyIconWrapper}>
                <Ionicons
                  name="shield-checkmark-outline"
                  size={48}
                  color={THEME.colors.textMuted}
                />
              </View>
              <Text style={styles.emptyTitle}>No blocked users</Text>
              <Text style={styles.emptySubtitle}>
                Users you block will appear here
              </Text>
            </Animated.View>
          ) : (
            /* Blocked users list */
            <View style={styles.list}>
              {blockedUsers.map((user, index) => {
                const isUnblocking = unblockingIds.has(user.blocked_id);
                return (
                  <Animated.View
                    key={user.id}
                    entering={FadeInDown.delay(index * 60).duration(400)}
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
                          <Text style={styles.userName} numberOfLines={1}>
                            {user.display_name || "Blocked User"}
                          </Text>
                          <Text style={styles.userMeta} numberOfLines={1}>
                            {user.username
                              ? `@${user.username}`
                              : `ID: ${user.blocked_id.slice(0, 8)}...`}
                          </Text>
                        </View>

                        {/* Unblock button */}
                        <Pressable
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
                            <Text
                              style={[
                                styles.unblockButtonText,
                                { color: theme.accent },
                              ]}
                            >
                              Unblock
                            </Text>
                          )}
                        </Pressable>
                      </View>
                    </View>
                  </Animated.View>
                );
              })}
            </View>
          )}
        </ScrollView>
      </View>
    </>
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
  scroll: {
    flex: 1,
  },
  scrollContent: {
    paddingHorizontal: THEME.spacing.xl,
    paddingTop: THEME.spacing.lg,
    flexGrow: 1,
  },

  // Centered states (loading, error, empty)
  centered: {
    flex: 1,
    alignItems: "center",
    justifyContent: "center",
    paddingTop: 80,
    gap: THEME.spacing.md,
  },
  loadingText: {
    fontFamily: FONTS.body,
    ...THEME.typography.caption,
    color: THEME.colors.textSecondary,
    marginTop: THEME.spacing.sm,
  },
  errorText: {
    fontFamily: FONTS.body,
    ...THEME.typography.caption,
    color: THEME.colors.destructive,
    textAlign: "center",
    marginTop: THEME.spacing.sm,
  },
  retryButton: {
    flexDirection: "row",
    alignItems: "center",
    gap: THEME.spacing.sm,
    marginTop: THEME.spacing.lg,
    paddingHorizontal: THEME.spacing.xxl,
    paddingVertical: THEME.spacing.md,
    borderRadius: THEME.radius.pill,
    minHeight: MIN_TOUCH_TARGET,
  },
  retryButtonText: {
    fontFamily: FONTS.bodyMedium,
    fontSize: 15,
    color: THEME.colors.bg,
  },

  // Empty state
  emptyIconWrapper: {
    width: 80,
    height: 80,
    borderRadius: 40,
    backgroundColor: THEME.colors.glass,
    borderWidth: 1,
    borderColor: THEME.colors.glassBorder,
    alignItems: "center",
    justifyContent: "center",
    marginBottom: THEME.spacing.lg,
  },
  emptyTitle: {
    fontFamily: FONTS.display,
    ...THEME.typography.heading,
    color: THEME.colors.textPrimary,
  },
  emptySubtitle: {
    fontFamily: FONTS.body,
    ...THEME.typography.body,
    color: THEME.colors.textSecondary,
    textAlign: "center",
  },

  // List
  list: {
    gap: THEME.spacing.md,
  },

  // Glass card
  glassCard: {
    backgroundColor: THEME.colors.glass,
    borderRadius: THEME.radius.lg,
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
  userName: {
    fontFamily: FONTS.bodyMedium,
    ...THEME.typography.body,
    color: THEME.colors.textPrimary,
  },
  userMeta: {
    fontFamily: FONTS.body,
    ...THEME.typography.caption,
    color: THEME.colors.textSecondary,
  },

  // Unblock button (pill outline)
  unblockButton: {
    borderRadius: THEME.radius.pill,
    borderWidth: 1,
    alignItems: "center",
    justifyContent: "center",
    minHeight: 36,
    paddingHorizontal: THEME.spacing.lg,
    paddingVertical: THEME.spacing.xs,
  },
  unblockButtonDisabled: {
    opacity: 0.5,
  },
  unblockButtonText: {
    fontFamily: FONTS.bodyMedium,
    fontSize: 14,
  },
});
