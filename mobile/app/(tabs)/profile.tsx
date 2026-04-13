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
  const { session, username: authUsername, setSessionMode, setUsername: setAuthUsername } = useAuth();
  const isAuthenticated = session.isUser;
  const isGuest = session.isGuest;
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

  const toggleMenu = useCallback(() => {
    setMenuVisible((prev) => !prev);
  }, []);

  const closeMenu = useCallback(() => {
    setMenuVisible(false);
  }, []);

  const handleSignIn = useCallback(() => {
    router.push("/(auth)/login");
  }, [router]);

  // Menu items depend on session state. Guests get a reduced set (no account
  // actions, since those require a real JWT) but still see Subscription and a
  // secondary Sign In entry point. Anons see only Sign In.
  const menuItems: RadialMenuItem[] = isAuthenticated
    ? [
        { label: "Edit Profile", icon: "create-outline", onPress: handleEditProfile },
        { label: "Subscription", icon: "diamond-outline", onPress: () => router.push("/subscription") },
        { label: "Settings", icon: "settings-outline", onPress: () => router.push("/settings") },
        { label: "Log Out", icon: "log-out-outline", onPress: handleLogout, destructive: true },
      ]
    : isGuest
      ? [
          { label: "Sign In", icon: "log-in-outline", onPress: handleSignIn },
          { label: "Subscription", icon: "diamond-outline", onPress: () => router.push("/subscription") },
        ]
      : [{ label: "Sign In", icon: "log-in-outline", onPress: handleSignIn }];

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

  // Not a real user (guest or anon) — render a centered sign-in CTA.
  // The tab header already owns the top safe-area inset, so we only reserve
  // room for the floating tab bar at the bottom. Flex centering in the
  // remaining space keeps the CTA anchored both axes.
  //
  // IMPORTANT: RadialMenu is rendered here too so the headerRight 3-dot
  // button (installed unconditionally via useLayoutEffect below) stays wired.
  if (!isAuthenticated) {
    const title = isGuest
      ? "Sign in to save your glow-ups"
      : "Sign in to see your profile";
    const subtitle = isGuest
      ? "Keep your history, reactions, and streaks across devices."
      : "Track your glow-ups and reactions";
    return (
      <View style={styles.emptyStateScreen}>
        <PageBackground overlayOpacity={0.85} />
        <RadialMenu
          visible={menuVisible}
          onClose={closeMenu}
          items={menuItems}
          accentColor={theme.accent}
        />
        <View style={styles.emptyStateContent}>
          <Ionicons
            name="person-circle-outline"
            size={96}
            color={THEME.colors.textMuted}
          />
          <Heading size="md" color="primary" style={styles.signInTitle}>
            {title}
          </Heading>
          <Body color="secondary" style={styles.signInSubtitle}>
            {subtitle}
          </Body>
          <Button
            title="Sign In"
            onPress={handleSignIn}
            variant="primary"
            size="md"
            accentColor={theme.accent}
            accessibilityLabel="Sign in"
            style={styles.signInButton}
          />
        </View>
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
  /* Guest/anon empty-state — tab header owns top safe area; we just reserve
     room for the floating tab bar and center content in what's left. */
  emptyStateScreen: {
    flex: 1,
    backgroundColor: THEME.colors.bg,
  },
  emptyStateContent: {
    flex: 1,
    alignItems: "center",
    justifyContent: "center",
    paddingHorizontal: THEME.spacing.xxl,
    paddingBottom: TAB_BAR_HEIGHT,
    gap: THEME.spacing.md,
  },
  signInTitle: {
    marginTop: THEME.spacing.lg,
    marginBottom: THEME.spacing.xs,
    textAlign: "center",
  },
  signInSubtitle: {
    textAlign: "center",
    maxWidth: 320,
  },
  signInButton: {
    marginTop: THEME.spacing.xl,
    minWidth: 200,
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
