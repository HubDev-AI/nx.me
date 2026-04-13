import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import {
  ActivityIndicator,
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
import { Button } from "../../components/ui/Button";
import { Body, Caption, Heading } from "../../components/ui/Text";
import { AUTH_ENDPOINTS } from "../../constants/config";
import { clearAllTokens } from "../../lib/auth";
import { apiFetch } from "../../lib/api";
import { useTheme } from "../../lib/theme-context";
import { useAuth } from "../../lib/auth-context";
import { ProfileHeader } from "../../components/profile/ProfileHeader";
import { GlowUpGrid } from "../../components/profile/GlowUpGrid";
import { EditProfileSheet } from "../../components/profile/EditProfileSheet";
import { useProfile } from "../../components/profile/useProfile";
import { RadialMenu, type RadialMenuItem } from "../../components/ui/RadialMenu";
import type { UpdateProfilePayload } from "../../components/profile/types";

/**
 * Profile screen: shows user avatar, stats, glow-up history grid,
 * and edit profile sheet.
 */
export default function ProfileScreen() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const navigation = useNavigation();
  const toggleMenuRef = useRef<() => void>(() => {});
  const { isAuthenticated, username: authUsername, setAuthenticated: setGlobalAuth, setUsername: setAuthUsername } = useAuth();
  const { theme } = useTheme();
  const [editSheetVisible, setEditSheetVisible] = useState(false);
  const [menuVisible, setMenuVisible] = useState(false);

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
  } = useProfile();

  // Load profile when authenticated and username is known
  useEffect(() => {
    if (isAuthenticated && authUsername && profile === null) {
      loadProfile(authUsername);
    }
  }, [isAuthenticated, authUsername, profile, loadProfile]);

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
    setGlobalAuth(false);
  }, [setGlobalAuth]);

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

  const toggleMenu = useCallback(() => {
    setMenuVisible((prev) => !prev);
  }, []);

  const closeMenu = useCallback(() => {
    setMenuVisible(false);
  }, []);

  const menuItems: RadialMenuItem[] = [
    { label: "Edit Profile", icon: "create-outline", onPress: handleEditProfile },
    { label: "Subscription", icon: "diamond-outline", onPress: () => router.push("/subscription") },
    { label: "Settings", icon: "settings-outline", onPress: () => router.push("/settings") },
    { label: "Log Out", icon: "log-out-outline", onPress: handleLogout, destructive: true },
  ];

  // Keep ref in sync so headerRight button can call it
  toggleMenuRef.current = toggleMenu;

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

  // Not signed in
  if (!isAuthenticated) {
    return (
      <View style={[styles.centered, { paddingTop: insets.top }]}>
        <Ionicons
          name="person-circle-outline"
          size={64}
          color={THEME.colors.textMuted}
        />
        <Heading size="md" color="primary" style={styles.signInTitle}>
          Sign in to see your profile
        </Heading>
        <Body color="secondary" style={styles.signInSubtitle}>
          Track your glow-ups and reactions
        </Body>
        <Button
          title="Sign In"
          onPress={() => router.push("/(auth)/login")}
          variant="primary"
          size="md"
          accentColor={theme.accent}
          accessibilityLabel="Sign in"
          style={styles.signInButton}
        />
      </View>
    );
  }

  // Authenticated but username not yet resolved
  if (!authUsername) {
    return (
      <View style={[styles.centered, { paddingTop: insets.top }]}>
        <Ionicons
          name="person-circle-outline"
          size={64}
          color={THEME.colors.textMuted}
        />
        <Heading size="md" color="primary" style={styles.signInTitle}>
          Complete your profile
        </Heading>
        <Body color="secondary" style={styles.signInSubtitle}>
          We couldn&apos;t determine your username. Please log out and sign in again,
          or register a new account.
        </Body>
        <Button
          title="Log out"
          onPress={handleLogout}
          variant="ghost"
          size="md"
          haptic="light"
          testID="logout-button"
          leftIcon={
            <Ionicons
              name="log-out-outline"
              size={20}
              color={THEME.colors.textSecondary}
            />
          }
          style={styles.fallbackLogoutButton}
        />
      </View>
    );
  }

  // Loading profile
  if (isLoading && !profile) {
    return (
      <View style={[styles.centered, { paddingTop: insets.top }]}>
        <ActivityIndicator size="large" color={theme.accent} />
        <Caption color="secondary" style={styles.loadingText}>
          Loading profile...
        </Caption>
      </View>
    );
  }

  // Error state
  if (error && !profile) {
    return (
      <View style={[styles.centered, { paddingTop: insets.top }]}>
        <View style={styles.errorCard}>
          <Ionicons
            name="alert-circle-outline"
            size={48}
            color={THEME.colors.destructive}
          />
          <Heading size="md" display={false} color="primary" style={styles.errorTitle}>
            Something went wrong
          </Heading>
          <Caption color="secondary" style={styles.errorMessage}>
            {error}
          </Caption>
          {authUsername ? (
            <Button
              title="Retry"
              onPress={() => loadProfile(authUsername)}
              variant="primary"
              size="md"
              accentColor={theme.accent}
              accessibilityLabel="Retry loading profile"
            />
          ) : null}
        </View>
        <Button
          title="Log out"
          onPress={handleLogout}
          variant="ghost"
          size="md"
          haptic="light"
          testID="logout-button"
          leftIcon={
            <Ionicons
              name="log-out-outline"
              size={20}
              color={THEME.colors.textSecondary}
            />
          }
          style={styles.fallbackLogoutButton}
        />
      </View>
    );
  }

  if (!profile) return null;

  const profileHeader = (
    <ProfileHeader
      profile={profile}
      onEditProfile={handleEditProfile}
    />
  );

  return (
    <View style={[styles.container, { paddingTop: insets.top }]}>
      <PageBackground overlayOpacity={0.85} />
      {/* Radial menu — button is in headerRight, menu renders here */}
      <RadialMenu
        visible={menuVisible}
        onClose={closeMenu}
        items={menuItems}
        accentColor={theme.accent}
      />

      {/* Single FlatList: profile header + glow-up grid -- no nested ScrollView */}
      <GlowUpGrid
        items={glowUps}
        isLoadingMore={isLoadingMore}
        hasMore={hasMoreGlowUps}
        onLoadMore={handleLoadMoreGlowUps}
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
  centered: {
    flex: 1,
    backgroundColor: THEME.colors.bg,
    alignItems: "center",
    justifyContent: "center",
    padding: THEME.spacing.xxl,
    paddingBottom: TAB_BAR_HEIGHT,
  },
  signInTitle: {
    marginTop: THEME.spacing.lg,
    marginBottom: THEME.spacing.sm,
    textAlign: "center",
  },
  signInSubtitle: {
    textAlign: "center",
  },
  signInButton: {
    marginTop: THEME.spacing.xl,
  },
  loadingText: {
    marginTop: THEME.spacing.md,
  },
  errorCard: {
    backgroundColor: THEME.colors.glass,
    borderRadius: THEME.radius.lg,
    borderCurve: "continuous",
    borderWidth: 1,
    borderColor: THEME.colors.glassBorder,
    padding: THEME.spacing.xxl,
    alignItems: "center",
    gap: THEME.spacing.sm,
  },
  errorTitle: {
    marginTop: THEME.spacing.md,
    textAlign: "center",
  },
  errorMessage: {
    textAlign: "center",
    marginBottom: THEME.spacing.lg,
  },

  /* Fallback logout for edge-case screens (no username, error state) */
  fallbackLogoutButton: {
    marginTop: THEME.spacing.xxxl,
    marginBottom: THEME.spacing.xxxl + THEME.spacing.sm,
  },
});
