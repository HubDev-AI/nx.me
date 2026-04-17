import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import {
  ActivityIndicator,
  Alert,
  Pressable,
  StyleSheet,
  View,
} from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useNavigation, useRouter } from "expo-router";

import { THEME } from "../../constants/theme";
import { TAB_BAR_HEIGHT } from "./_layout";
import { PageBackground } from "../../components/ui/PageBackground";
import { EmptyState } from "../../components/ui/EmptyState";
import { Caption } from "../../components/ui/Text";
import {
  AUTH_ENDPOINTS,
  DISMISS_ERRORED_JOB_BODY,
  DISMISS_ERRORED_JOB_CANCEL_LABEL,
  DISMISS_ERRORED_JOB_REMOVE_LABEL,
  DISMISS_ERRORED_JOB_TITLE,
} from "../../constants/config";
import { clearAllTokens } from "../../lib/auth";
import { apiFetch } from "../../lib/api";
import { useTheme } from "../../lib/theme-context";
import { useAuth } from "../../lib/auth-context";
import { ProfileHeader } from "../../components/profile/ProfileHeader";
import { GlowUpGrid } from "../../components/profile/GlowUpGrid";
import { EditProfileSheet } from "../../components/profile/EditProfileSheet";
import { useProfile } from "../../components/profile/useProfile";
import { buildProfileMenu } from "../../components/profile/menu";
import { useRadialMenu } from "../../lib/radial-menu-context";
import { useCapabilities } from "../../lib/capabilities";
import type { GlowUpItem, UpdateProfilePayload } from "../../components/profile/types";

/** Status values that surface as a dismissable errored cell on the grid. */
const ERRORED_STATUSES = new Set<string>(["failed", "cancelled"]);

/**
 * Profile screen: shows user avatar, stats, glow-up history grid,
 * and edit profile sheet.
 */
export default function ProfileScreen() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const navigation = useNavigation();
  const toggleMenuRef = useRef<() => void>(() => {});
  const { username: authUsername, setSessionMode, setUsername: setAuthUsername } = useAuth();
  const caps = useCapabilities();
  const { theme } = useTheme();
  const radialMenu = useRadialMenu();
  const [editSheetVisible, setEditSheetVisible] = useState(false);

  const {
    profile,
    glowUps,
    isLoading,
    isRefreshing,
    isLoadingMore,
    hasMoreGlowUps,
    error,
    isUpdating,
    updateError,
    loadProfile,
    refresh,
    loadMoreGlowUps,
    updateProfile,
    dismissErroredItem,
    reconcileWithJob,
  } = useProfile();

  // Load profile once the session can view its own profile and the username
  // is known. Gated on canViewOwnProfile (not isUser) so guests with a valid
  // guest token in `auth_required=false` mode also fetch their data.
  useEffect(() => {
    if (caps.canViewOwnProfile && authUsername && profile === null) {
      loadProfile(authUsername);
    }
  }, [caps.canViewOwnProfile, authUsername, profile, loadProfile]);

  const handleRefresh = useCallback(() => {
    if (profile) {
      refresh(profile.username);
    }
  }, [profile, refresh]);

  const handleLoadMoreGlowUps = useCallback(() => {
    if (profile) {
      loadMoreGlowUps(profile.username);
    }
  }, [profile, loadMoreGlowUps]);

  const handleEditProfile = useCallback(() => {
    setEditSheetVisible(true);
  }, []);

  const handleCloseEditSheet = useCallback(() => {
    setEditSheetVisible(false);
  }, []);

  const handleLogout = useCallback(async () => {
    // Best-effort server-side logout — always clear local tokens even on failure
    try {
      await apiFetch<void>(AUTH_ENDPOINTS.LOGOUT, { method: "POST" });
    } catch {
      // Network error or server unreachable — proceed with local logout
    }
    await clearAllTokens();
    setSessionMode("anon");
  }, [setSessionMode]);

  const handleSaveProfile = useCallback(
    async (payload: UpdateProfilePayload): Promise<boolean> => {
      if (!profile) return false;
      const success = await updateProfile(profile.username, payload);
      // Propagate username change to auth context so all subsequent
      // API calls and navigation use the new username.
      if (success && payload.new_username) {
        setAuthUsername(payload.new_username);
      }
      return success;
    },
    [profile, updateProfile, setAuthUsername],
  );

  const handleSignIn = useCallback(() => {
    router.push("/(auth)/login");
  }, [router]);

  // Tap a glow-up cell → /result/[jobId]. The result screen renders the
  // right branch based on status (waiting / success / terminal-failure)
  // so a single destination covers pending, completed, and errored.
  const handleItemPress = useCallback(
    (item: GlowUpItem) => {
      if (!item.job_id) return; // Legacy row with no job — non-tappable.
      router.push(`/result/${item.job_id}`);
    },
    [router],
  );

  // Long-press a failed/cancelled cell → confirm + dismiss. Completed
  // and pending cells ignore long-press; the prompt only fires for
  // dismissable rows.
  const handleItemLongPress = useCallback(
    (item: GlowUpItem) => {
      if (!item.job_id) return;
      if (!ERRORED_STATUSES.has(item.status)) return;
      const dismissedJobId = item.job_id;
      Alert.alert(
        DISMISS_ERRORED_JOB_TITLE,
        DISMISS_ERRORED_JOB_BODY,
        [
          { text: DISMISS_ERRORED_JOB_CANCEL_LABEL, style: "cancel" },
          {
            text: DISMISS_ERRORED_JOB_REMOVE_LABEL,
            style: "destructive",
            onPress: () => dismissErroredItem(dismissedJobId),
          },
        ],
      );
    },
    [dismissErroredItem],
  );

  // Menu items derive from capabilities — single source of truth keeps this
  // screen and any future profile actions in sync with the (features × session)
  // matrix in mobile/lib/capabilities.ts.
  const menuItems = buildProfileMenu(caps, {
    onEditProfile: handleEditProfile,
    onOpenSubscription: () => router.push("/subscription"),
    onOpenSettings: () => router.push("/settings"),
    onLogout: handleLogout,
    onSignIn: handleSignIn,
  });

  // Keep ref in sync so headerRight button can call it
  toggleMenuRef.current = () => radialMenu.open(menuItems);

  // Put 3-dot button in the actual navigation header
  useLayoutEffect(() => {
    navigation.setOptions({
      headerRight: () => (
        <Pressable
          onPress={() => toggleMenuRef.current?.()}
          style={{ padding: THEME.spacing.sm, marginRight: THEME.spacing.sm }}
          accessibilityLabel="More options"
          accessibilityRole="button"
          hitSlop={8}
        >
          <Ionicons name="ellipsis-horizontal" size={20} color={THEME.colors.textSecondary} />
        </Pressable>
      ),
    });
  }, [navigation]);

  // No profile to show (anon, or impossible-state guest with auth_required=true)
  // — render a centered sign-in CTA. The RadialMenu is mounted globally via
  // RadialMenuProvider, so we only call `open(menuItems)` from the 3-dot
  // button; no local rendering needed.
  if (!caps.canViewOwnProfile) {
    const title = "Sign in to see your profile";
    const subtitle = "Track your glow-ups and reactions";
    return (
      <View style={styles.emptyStateScreen}>
        <PageBackground overlayOpacity={0.85} />
        <EmptyState
          icon="person-circle-outline"
          title={title}
          description={subtitle}
          action={
            caps.canSignIn
              ? {
                  label: "Sign In",
                  onPress: handleSignIn,
                  accessibilityLabel: "Sign in",
                }
              : undefined
          }
        />
      </View>
    );
  }

  // Authenticated but username not yet resolved — surface Log out as the
  // primary recovery action so the button matches the rest of the app's
  // design (same primary-button shape as "Try Again" on error states).
  if (!authUsername) {
    return (
      <View style={styles.emptyStateScreen}>
        <EmptyState
          icon="person-circle-outline"
          title="Complete your profile"
          description="We couldn't determine your username. Please log out and sign in again, or register a new account."
          action={
            caps.canSignOut
              ? {
                  label: "Log out",
                  onPress: handleLogout,
                  accessibilityLabel: "Log out",
                }
              : undefined
          }
        />
      </View>
    );
  }

  // Loading profile
  if (isLoading && !profile) {
    return (
      <View style={styles.emptyStateLoading}>
        <ActivityIndicator size="large" color={theme.accent} />
        <Caption color="secondary" style={styles.loadingText}>
          Loading profile...
        </Caption>
      </View>
    );
  }

  // Error state — prefer Retry if we have a username to retry with,
  // otherwise fall back to Log out (both actions rendered as the standard
  // primary button via EmptyState's action prop).
  if (error && !profile) {
    const errorAction = authUsername
      ? {
          label: "Retry",
          onPress: () => loadProfile(authUsername),
          accessibilityLabel: "Retry loading profile",
        }
      : caps.canSignOut
        ? {
            label: "Log out",
            onPress: handleLogout,
            accessibilityLabel: "Log out",
          }
        : undefined;
    return (
      <View style={styles.emptyStateScreen}>
        <EmptyState
          icon="alert-circle-outline"
          title="Something went wrong"
          description={error}
          action={errorAction}
        />
      </View>
    );
  }

  if (!profile) return null;

  const profileHeader = (
    <ProfileHeader
      profile={profile}
      onEditProfile={handleEditProfile}
      showStats={caps.canSeeFeed}
    />
  );

  return (
    <View style={[styles.container, { paddingTop: insets.top }]}>
      <PageBackground overlayOpacity={0.85} />
      {/* Radial menu — button is in headerRight, menu renders here */}
      {/* Single FlatList: profile header + glow-up grid -- no nested ScrollView */}
      <GlowUpGrid
        items={glowUps}
        isLoadingMore={isLoadingMore}
        hasMore={hasMoreGlowUps}
        onLoadMore={handleLoadMoreGlowUps}
        onItemPress={handleItemPress}
        onItemLongPress={handleItemLongPress}
        onJobResolved={reconcileWithJob}
        ListHeaderComponent={profileHeader}
        refreshing={isRefreshing}
        onRefresh={handleRefresh}
      />

      {/* Edit Profile sheet */}
      <EditProfileSheet
        visible={editSheetVisible}
        profile={profile}
        isUpdating={isUpdating}
        updateError={updateError}
        onSave={handleSaveProfile}
        onClose={handleCloseEditSheet}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: THEME.colors.bg,
  },
  /* Shared wrapper for every non-populated Profile state (signed-out,
     username-missing, error). EmptyState (center={true}) does the
     centering; the wrapper just bounds the empty region to the screen
     minus the floating tab bar, matching the Feed / Advisor rhythm. */
  emptyStateScreen: {
    flex: 1,
    backgroundColor: THEME.colors.bg,
    paddingBottom: TAB_BAR_HEIGHT,
  },
  /* Loading variant renders an ActivityIndicator + caption pair instead
     of EmptyState, so it does its own centering here. */
  emptyStateLoading: {
    flex: 1,
    backgroundColor: THEME.colors.bg,
    alignItems: "center",
    justifyContent: "center",
    paddingBottom: TAB_BAR_HEIGHT,
  },
  loadingText: {
    marginTop: THEME.spacing.md,
  },
});
