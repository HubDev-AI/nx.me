import { useCallback } from "react";
import {
  View,
  Text,
  Image,
  Pressable,
  Share,
  Platform,
  StyleSheet,
} from "react-native";
import { Ionicons } from "@expo/vector-icons";

import {
  BG_CARD,
  BG_ELEVATED,
  TEXT_PRIMARY,
  TEXT_SECONDARY,
  CTA_PRIMARY,
  CTA_PRESSED,
  COLORS,
} from "../../constants/colors";
import {
  UNIVERSAL_LINK_ORIGIN,
  MIN_TOUCH_TARGET,
} from "../../constants/config";
import type { UserProfile } from "./types";

const AVATAR_SIZE = 80;
const STAT_ICON_SIZE = 16;

interface ProfileHeaderProps {
  profile: UserProfile;
  onEditProfile: () => void;
}

/**
 * Profile header: avatar, display name, username, stats row,
 * Edit Profile and Share buttons.
 */
export function ProfileHeader({
  profile,
  onEditProfile,
}: ProfileHeaderProps) {
  const displayName = profile.display_name ?? profile.username;
  const shareUrl = `${UNIVERSAL_LINK_ORIGIN}/${profile.username}`;

  const handleShare = useCallback(() => {
    const sharePayload =
      Platform.OS === "ios"
        ? { url: shareUrl }
        : { message: shareUrl };

    Share.share(sharePayload).catch(() => {
      // User cancelled or share failed — no action needed
    });
  }, [shareUrl]);

  return (
    <View style={styles.container}>
      {/* Avatar */}
      <View style={styles.avatarContainer}>
        {profile.avatar_url ? (
          <Image
            source={{ uri: profile.avatar_url }}
            style={styles.avatar}
            accessibilityLabel={`${displayName} avatar`}
          />
        ) : (
          <View style={[styles.avatar, styles.avatarPlaceholder]}>
            <Ionicons
              name="person"
              size={36}
              color={TEXT_SECONDARY}
            />
          </View>
        )}
      </View>

      {/* Name + username */}
      <Text
        style={styles.displayName}
        numberOfLines={1}
        accessibilityRole="header"
      >
        {displayName}
      </Text>
      <Text style={styles.username} numberOfLines={1}>
        @{profile.username}
      </Text>

      {/* Stats row */}
      <View style={styles.statsRow}>
        <StatItem
          icon="image-outline"
          value={profile.post_count}
          label="Posts"
        />
        <View style={styles.statDivider} />
        <StatItem
          icon="heart-outline"
          value={profile.reaction_count}
          label="Reactions"
        />
        <View style={styles.statDivider} />
        <StatItem
          icon="flame-outline"
          value={profile.streak_days}
          label="Streak"
        />
      </View>

      {/* Action buttons */}
      <View style={styles.buttonsRow}>
        <Pressable
          onPress={onEditProfile}
          style={({ pressed }) => [
            styles.editButton,
            pressed && styles.editButtonPressed,
          ]}
          accessibilityLabel="Edit Profile"
          accessibilityRole="button"
        >
          <Ionicons name="create-outline" size={18} color={TEXT_PRIMARY} />
          <Text style={styles.editButtonText}>Edit Profile</Text>
        </Pressable>

        <Pressable
          onPress={handleShare}
          style={({ pressed }) => [
            styles.shareButton,
            pressed && styles.shareButtonPressed,
          ]}
          accessibilityLabel="Share profile"
          accessibilityRole="button"
        >
          <Ionicons
            name="share-outline"
            size={18}
            color={CTA_PRIMARY}
          />
        </Pressable>
      </View>
    </View>
  );
}

interface StatItemProps {
  icon: React.ComponentProps<typeof Ionicons>["name"];
  value: number;
  label: string;
}

function StatItem({ icon, value, label }: StatItemProps) {
  return (
    <View
      style={styles.statItem}
      accessibilityLabel={`${formatStatValue(value)} ${label}`}
    >
      <Ionicons name={icon} size={STAT_ICON_SIZE} color={TEXT_SECONDARY} />
      <Text style={styles.statValue}>{formatStatValue(value)}</Text>
      <Text style={styles.statLabel}>{label}</Text>
    </View>
  );
}

/** Format large numbers compactly: 1200 -> 1.2k */
function formatStatValue(count: number): string {
  if (count >= 1_000_000) {
    return `${(count / 1_000_000).toFixed(1)}m`;
  }
  if (count >= 1_000) {
    return `${(count / 1_000).toFixed(1)}k`;
  }
  return String(count);
}

const styles = StyleSheet.create({
  container: {
    alignItems: "center",
    paddingTop: 24,
    paddingBottom: 16,
    paddingHorizontal: 16,
  },
  avatarContainer: {
    marginBottom: 12,
  },
  avatar: {
    width: AVATAR_SIZE,
    height: AVATAR_SIZE,
    borderRadius: AVATAR_SIZE / 2,
  },
  avatarPlaceholder: {
    backgroundColor: BG_ELEVATED,
    alignItems: "center",
    justifyContent: "center",
  },
  displayName: {
    fontSize: 22,
    fontWeight: "700",
    color: TEXT_PRIMARY,
    marginBottom: 2,
  },
  username: {
    fontSize: 14,
    color: TEXT_SECONDARY,
    marginBottom: 16,
  },
  statsRow: {
    flexDirection: "row",
    alignItems: "center",
    backgroundColor: BG_CARD,
    borderRadius: 12,
    paddingVertical: 12,
    paddingHorizontal: 16,
    marginBottom: 16,
    width: "100%",
  },
  statItem: {
    flex: 1,
    alignItems: "center",
    gap: 4,
  },
  statDivider: {
    width: 1,
    height: 32,
    backgroundColor: COLORS.neutral.dark[400],
  },
  statValue: {
    fontSize: 18,
    fontWeight: "700",
    color: TEXT_PRIMARY,
  },
  statLabel: {
    fontSize: 12,
    color: TEXT_SECONDARY,
  },
  buttonsRow: {
    flexDirection: "row",
    gap: 8,
    width: "100%",
  },
  editButton: {
    flex: 1,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    gap: 6,
    minHeight: MIN_TOUCH_TARGET,
    backgroundColor: BG_ELEVATED,
    borderRadius: 10,
    paddingVertical: 10,
    paddingHorizontal: 16,
  },
  editButtonPressed: {
    backgroundColor: COLORS.neutral.dark[300],
  },
  editButtonText: {
    fontSize: 14,
    fontWeight: "600",
    color: TEXT_PRIMARY,
  },
  shareButton: {
    width: MIN_TOUCH_TARGET,
    height: MIN_TOUCH_TARGET,
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: BG_ELEVATED,
    borderRadius: 10,
  },
  shareButtonPressed: {
    backgroundColor: COLORS.neutral.dark[300],
  },
});
