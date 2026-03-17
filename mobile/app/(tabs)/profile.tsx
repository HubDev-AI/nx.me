import { useEffect, useState, useCallback } from "react";
import {
  View,
  Text,
  ScrollView,
  RefreshControl,
  Pressable,
  ActivityIndicator,
  StyleSheet,
} from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import {
  BG_PAGE,
  BG_CARD,
  BG_ELEVATED,
  TEXT_PRIMARY,
  TEXT_SECONDARY,
  TEXT_DISABLED,
  CTA_PRIMARY,
  COLORS,
  ERROR_DARK,
} from "../../constants/colors";
import { MIN_TOUCH_TARGET } from "../../constants/config";
import { getStoredJwt } from "../../lib/auth";
import { ProfileHeader } from "../../components/profile/ProfileHeader";
import { GlowUpGrid } from "../../components/profile/GlowUpGrid";
import { ReactionsTab } from "../../components/profile/ReactionsTab";
import { EditProfileSheet } from "../../components/profile/EditProfileSheet";
import { useProfile } from "../../components/profile/useProfile";
import type { ProfileTab, UpdateProfilePayload } from "../../components/profile/types";

const TAB_INDICATOR_HEIGHT = 2;

/**
 * Profile screen: shows user avatar, stats, glow-up grid, reactions tab,
 * and edit profile sheet.
 */
export default function ProfileScreen() {
  const insets = useSafeAreaInsets();
  const [isAuthenticated, setIsAuthenticated] = useState<boolean | null>(null);
  const [editSheetVisible, setEditSheetVisible] = useState(false);

  const {
    profile,
    glowUps,
    reactedPosts,
    isLoading,
    isRefreshing,
    isLoadingMore,
    hasMoreGlowUps,
    hasMoreReactions,
    error,
    activeTab,
    isUpdating,
    updateError,
    loadProfile,
    refresh,
    loadMoreGlowUps,
    loadMoreReactions,
    changeTab,
    updateProfile,
  } = useProfile();

  // Check auth state on mount
  useEffect(() => {
    getStoredJwt().then((jwt) => {
      setIsAuthenticated(jwt !== null);
    });
  }, []);

  // Load profile when authenticated
  // TODO: Get username from auth context once available
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

  const handleLoadMoreReactions = useCallback(() => {
    if (profile) {
      loadMoreReactions(profile.username);
    }
  }, [profile, loadMoreReactions]);

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
          Track your glow-ups, reactions, and streak
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

  return (
    <View style={[styles.container, { paddingTop: insets.top }]}>
      <ScrollView
        style={styles.scrollView}
        contentContainerStyle={styles.scrollContent}
        showsVerticalScrollIndicator={false}
        refreshControl={
          <RefreshControl
            refreshing={isRefreshing}
            onRefresh={handleRefresh}
            tintColor={CTA_PRIMARY}
            colors={[CTA_PRIMARY]}
          />
        }
      >
        {/* Profile header */}
        <ProfileHeader
          profile={profile}
          onEditProfile={handleEditProfile}
        />

        {/* Tab segments */}
        <View style={styles.tabBar}>
          <TabSegment
            label="All Glow-Ups"
            icon="images-outline"
            isActive={activeTab === "glowups"}
            onPress={() => changeTab("glowups")}
          />
          <TabSegment
            label="Reactions"
            icon="heart-outline"
            isActive={activeTab === "reactions"}
            onPress={() => changeTab("reactions")}
          />
        </View>

        {/* Tab content */}
        {activeTab === "glowups" ? (
          <GlowUpGrid
            items={glowUps}
            isLoadingMore={isLoadingMore}
            hasMore={hasMoreGlowUps}
            onLoadMore={handleLoadMoreGlowUps}
          />
        ) : (
          <ReactionsTab
            items={reactedPosts}
            isLoadingMore={isLoadingMore}
            hasMore={hasMoreReactions}
            onLoadMore={handleLoadMoreReactions}
          />
        )}
      </ScrollView>

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

interface TabSegmentProps {
  label: string;
  icon: React.ComponentProps<typeof Ionicons>["name"];
  isActive: boolean;
  onPress: () => void;
}

function TabSegment({ label, icon, isActive, onPress }: TabSegmentProps) {
  return (
    <Pressable
      onPress={onPress}
      style={styles.tabSegment}
      accessibilityLabel={label}
      accessibilityRole="tab"
      accessibilityState={{ selected: isActive }}
    >
      <View style={styles.tabSegmentContent}>
        <Ionicons
          name={icon}
          size={18}
          color={isActive ? CTA_PRIMARY : TEXT_SECONDARY}
        />
        <Text
          style={[
            styles.tabSegmentLabel,
            isActive && styles.tabSegmentLabelActive,
          ]}
        >
          {label}
        </Text>
      </View>
      <View
        style={[
          styles.tabIndicator,
          {
            backgroundColor: isActive ? CTA_PRIMARY : "transparent",
          },
        ]}
      />
    </Pressable>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: BG_PAGE,
  },
  scrollView: {
    flex: 1,
  },
  scrollContent: {
    paddingBottom: 24,
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
  tabBar: {
    flexDirection: "row",
    marginHorizontal: 16,
    backgroundColor: BG_CARD,
    borderRadius: 10,
    marginBottom: 8,
    overflow: "hidden",
  },
  tabSegment: {
    flex: 1,
    alignItems: "center",
    minHeight: MIN_TOUCH_TARGET,
  },
  tabSegmentContent: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    gap: 6,
    paddingVertical: 12,
    flex: 1,
  },
  tabSegmentLabel: {
    fontSize: 14,
    fontWeight: "600",
    color: TEXT_SECONDARY,
  },
  tabSegmentLabelActive: {
    color: CTA_PRIMARY,
  },
  tabIndicator: {
    height: TAB_INDICATOR_HEIGHT,
    width: "100%",
    borderRadius: TAB_INDICATOR_HEIGHT / 2,
  },
});
