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

import {
  BG_PAGE,
  TEXT_PRIMARY,
  TEXT_SECONDARY,
  TEXT_DISABLED,
  CTA_PRIMARY,
  ERROR_DARK,
} from "../../constants/colors";
import { MIN_TOUCH_TARGET } from "../../constants/config";
import { getStoredJwt } from "../../lib/auth";
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
  const [isAuthenticated, setIsAuthenticated] = useState<boolean | null>(null);
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

  // Check auth state on mount
  useEffect(() => {
    getStoredJwt().then((jwt) => {
      setIsAuthenticated(jwt !== null);
    });
  }, []);

  // Load profile when authenticated
  useEffect(() => {
    if (isAuthenticated && profile === null) {
      loadProfile("me");
    }
  }, [isAuthenticated, profile, loadProfile]);

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

  const handleSaveProfile = useCallback(
    async (payload: UpdateProfilePayload): Promise<boolean> => {
      if (!profile) return false;
      return updateProfile(profile.username, payload);
    },
    [profile, updateProfile],
  );

  // Auth check loading
  if (isAuthenticated === null) {
    return (
      <View style={[styles.centered, { paddingTop: insets.top }]}>
        <ActivityIndicator size="large" color={CTA_PRIMARY} />
      </View>
    );
  }

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
        <Pressable
          onPress={() => loadProfile("me")}
          style={styles.retryButton}
          accessibilityLabel="Retry loading profile"
          accessibilityRole="button"
        >
          <Text style={styles.retryButtonText}>Retry</Text>
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

  return (
    <View style={[styles.container, { paddingTop: insets.top }]}>
      {/* Single FlatList: profile header + glow-up grid — no nested ScrollView */}
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
    fontSize: 20,
    fontWeight: "700",
    color: TEXT_PRIMARY,
    marginTop: 16,
    marginBottom: 8,
  },
  signInSubtitle: {
    fontSize: 15,
    color: TEXT_SECONDARY,
    textAlign: "center",
  },
  loadingText: {
    fontSize: 14,
    color: TEXT_SECONDARY,
    marginTop: 12,
  },
  errorTitle: {
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
    borderRadius: 10,
    paddingHorizontal: 24,
    paddingVertical: 12,
    minHeight: MIN_TOUCH_TARGET,
    alignItems: "center",
    justifyContent: "center",
  },
  retryButtonText: {
    fontSize: 16,
    fontWeight: "600",
    color: "#FFFFFF",
  },
});
