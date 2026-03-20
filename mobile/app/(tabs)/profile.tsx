import { useEffect, useState, useCallback } from "react";
import {
  View,
  Text,
  Pressable,
  ActivityIndicator,
  StyleSheet,
} from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useRouter } from "expo-router";

import {
  BG_PAGE,
  TEXT_PRIMARY,
  TEXT_SECONDARY,
  TEXT_DISABLED,
  CTA_PRIMARY,
  ERROR_DARK,
} from "../../constants/colors";
import { MIN_TOUCH_TARGET } from "../../constants/config";
import { clearAllTokens } from "../../lib/auth";
import { HeroBackground } from "../../components/ui/HeroBackground";
import { FloatingParticles } from "../../components/ui/FloatingParticles";
import { useTheme } from "../../lib/theme-context";
import { FONTS } from "../../hooks/useFonts";
import { useAuth } from "../../lib/auth-context";
import { ProfileHeader } from "../../components/profile/ProfileHeader";
import { GlowUpGrid } from "../../components/profile/GlowUpGrid";
import { EditProfileSheet } from "../../components/profile/EditProfileSheet";
import { useProfile } from "../../components/profile/useProfile";
import type { UpdateProfilePayload } from "../../components/profile/types";

/**
 * Profile screen: shows user avatar, stats, glow-up history grid,
 * and edit profile sheet.
 */
export default function ProfileScreen() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const { isAuthenticated, username: authUsername, setAuthenticated: setGlobalAuth } = useAuth();
  const { theme } = useTheme();
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
    await clearAllTokens();
    setGlobalAuth(false);
  }, [setGlobalAuth]);

  const handleSaveProfile = useCallback(
    async (payload: UpdateProfilePayload): Promise<boolean> => {
      if (!profile) return false;
      return updateProfile(profile.username, payload);
    },
    [profile, updateProfile],
  );

  // Not signed in
  if (!isAuthenticated) {
    return (
      <View style={[styles.centered, { paddingTop: insets.top }]}>
        <Ionicons
          name="person-circle-outline"
          size={64}
          color={TEXT_DISABLED}
        />
        <Text style={styles.signInTitle}>Sign in to see your profile</Text>
        <Text style={styles.signInSubtitle}>
          Track your glow-ups and reactions
        </Text>
        <Pressable
          onPress={() => router.push("/(auth)/login")}
          style={styles.signInButton}
          accessibilityLabel="Sign in"
          accessibilityRole="button"
        >
          <Text style={styles.signInButtonText}>Sign In</Text>
        </Pressable>
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
          color={TEXT_DISABLED}
        />
        <Text style={styles.signInTitle}>Complete your profile</Text>
        <Text style={styles.signInSubtitle}>
          We couldn't determine your username. Please log out and sign in again,
          or register a new account.
        </Text>
        <Pressable
          onPress={handleLogout}
          style={styles.logoutButton}
          accessibilityLabel="Log out"
          accessibilityRole="button"
          testID="logout-button"
        >
          <Ionicons name="log-out-outline" size={20} color={ERROR_DARK} />
          <Text style={styles.logoutText}>Log out</Text>
        </Pressable>
      </View>
    );
  }

  // Loading profile
  if (isLoading && !profile) {
    return (
      <View style={[styles.centered, { paddingTop: insets.top }]}>
        <ActivityIndicator size="large" color={CTA_PRIMARY} />
        <Text style={styles.loadingText}>Loading profile...</Text>
      </View>
    );
  }

  // Error state
  if (error && !profile) {
    return (
      <View style={[styles.centered, { paddingTop: insets.top }]}>
        <Ionicons
          name="alert-circle-outline"
          size={48}
          color={ERROR_DARK}
        />
        <Text style={styles.errorTitle}>Something went wrong</Text>
        <Text style={styles.errorMessage}>{error}</Text>
        {authUsername ? (
          <Pressable
            onPress={() => loadProfile(authUsername)}
            style={styles.retryButton}
            accessibilityLabel="Retry loading profile"
            accessibilityRole="button"
          >
            <Text style={styles.retryButtonText}>Retry</Text>
          </Pressable>
        ) : null}
        <Pressable
          onPress={handleLogout}
          style={styles.logoutButton}
          accessibilityLabel="Log out"
          accessibilityRole="button"
          testID="logout-button"
        >
          <Ionicons name="log-out-outline" size={20} color={ERROR_DARK} />
          <Text style={styles.logoutText}>Log out</Text>
        </Pressable>
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

  const profileHeaderWithLogout = (
    <View>
      {profileHeader}
      <Pressable
        onPress={handleLogout}
        style={styles.logoutButton}
        accessibilityLabel="Log out"
        accessibilityRole="button"
        testID="logout-button"
      >
        <Ionicons name="log-out-outline" size={20} color={ERROR_DARK} />
        <Text style={styles.logoutText}>Log out</Text>
      </Pressable>
    </View>
  );

  return (
    <View style={[styles.container, { paddingTop: insets.top }]}>
      {/* Single FlatList: profile header + glow-up grid — no nested ScrollView */}
      <GlowUpGrid
        items={glowUps}
        isLoadingMore={isLoadingMore}
        hasMore={hasMoreGlowUps}
        onLoadMore={handleLoadMoreGlowUps}
        ListHeaderComponent={profileHeaderWithLogout}
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
    backgroundColor: BG_PAGE,
  },
  centered: {
    flex: 1,
    backgroundColor: BG_PAGE,
    alignItems: "center",
    justifyContent: "center",
    padding: 24,
  },
  signInTitle: {
    fontFamily: FONTS.display,
    fontSize: 24,
    color: TEXT_PRIMARY,
    marginTop: 16,
    marginBottom: 8,
  },
  signInSubtitle: {
    fontFamily: FONTS.body,
    fontSize: 15,
    color: TEXT_SECONDARY,
    textAlign: "center",
  },
  signInButton: {
    marginTop: 20,
    backgroundColor: CTA_PRIMARY,
    borderRadius: 9999,
    paddingHorizontal: 32,
    paddingVertical: 12,
    minHeight: MIN_TOUCH_TARGET,
    alignItems: "center",
    justifyContent: "center",
  },
  signInButtonText: {
    fontFamily: FONTS.bodyMedium,
    fontSize: 16,
    color: "#0a0a0a",
  },
  loadingText: {
    fontFamily: FONTS.body,
    fontSize: 14,
    color: TEXT_SECONDARY,
    marginTop: 12,
  },
  errorTitle: {
    fontFamily: FONTS.display,
    fontSize: 18,
    fontWeight: "700",
    color: TEXT_PRIMARY,
    marginTop: 12,
    marginBottom: 4,
  },
  errorMessage: {
    fontSize: 14,
    color: TEXT_SECONDARY,
    textAlign: "center",
    marginBottom: 16,
  },
  retryButton: {
    backgroundColor: CTA_PRIMARY,
    borderRadius: 9999,
    paddingHorizontal: 24,
    paddingVertical: 12,
    minHeight: MIN_TOUCH_TARGET,
    alignItems: "center",
    justifyContent: "center",
  },
  retryButtonText: {
    fontFamily: FONTS.bodyMedium,
    fontSize: 16,
    color: "#0a0a0a",
  },
  logoutButton: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    gap: 8,
    marginTop: 32,
    marginBottom: 40,
    paddingVertical: 14,
    minHeight: MIN_TOUCH_TARGET,
  },
  logoutText: {
    fontSize: 16,
    fontWeight: "600",
    color: ERROR_DARK,
  },
});
