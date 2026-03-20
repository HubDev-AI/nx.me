import { useCallback, useState } from "react";
import {
  View,
  Text,
  Image,
  Pressable,
  Share,
  Platform,
  LayoutAnimation,
  UIManager,
  StyleSheet,
} from "react-native";

// Enable LayoutAnimation on Android
if (Platform.OS === "android" && UIManager.setLayoutAnimationEnabledExperimental) {
  UIManager.setLayoutAnimationEnabledExperimental(true);
}
import { Ionicons } from "@expo/vector-icons";

import { TEXT_SECONDARY } from "../../constants/colors";
import {
  UNIVERSAL_LINK_ORIGIN,
  MIN_TOUCH_TARGET,
} from "../../constants/config";
import { FONTS } from "../../hooks/useFonts";
import { useTheme } from "../../lib/theme-context";
import { formatCount } from "../../lib/format";
import type { UserProfile } from "./types";

const AVATAR_SIZE = 40;

interface ProfileHeaderProps {
  profile: UserProfile;
  onEditProfile: () => void;
}

/**
 * Collapsible profile header.
 *
 * COLLAPSED (default): clean card-like row -- avatar, name + @username stacked,
 * "View profile" tap target on the right. Entire row is tappable.
 *
 * EXPANDED: additional content slides down below the collapsed row --
 * stats row, Edit Profile pill button. Uses Reanimated entering/exiting
 * layout animations (FadeInDown / FadeOutUp) so content is never clipped.
 */
export function ProfileHeader({
  profile,
  onEditProfile,
}: ProfileHeaderProps) {
  const { theme } = useTheme();
  const [expanded, setExpanded] = useState(false);
  const displayName = profile.display_name ?? profile.username;
  const shareUrl = `${UNIVERSAL_LINK_ORIGIN}/${profile.username}`;

  const toggle = useCallback(() => {
    LayoutAnimation.configureNext(LayoutAnimation.Presets.easeInEaseOut);
    setExpanded((prev) => !prev);
  }, []);

  const handleShare = useCallback(() => {
    const sharePayload =
      Platform.OS === "ios"
        ? { url: shareUrl }
        : { message: shareUrl };

    Share.share(sharePayload).catch(() => {
      // User cancelled or share failed -- no action needed
    });
  }, [shareUrl]);

  return (
    <View style={styles.wrapper}>
      {/* ---- Collapsed row -- always visible, tappable to toggle ---- */}
      <Pressable
        onPress={toggle}
        style={({ pressed }) => [
          styles.collapsedRow,
          pressed && styles.collapsedRowPressed,
        ]}
        accessibilityLabel={
          expanded ? "Hide profile details" : "View profile details"
        }
        accessibilityRole="button"
        accessibilityState={{ expanded }}
      >
        {/* Avatar */}
        {profile.avatar_url ? (
          <Image
            source={{ uri: profile.avatar_url }}
            style={styles.avatar}
            accessibilityLabel={`${displayName} avatar`}
          />
        ) : (
          <View style={[styles.avatar, styles.avatarPlaceholder]}>
            <Ionicons name="person" size={18} color={TEXT_SECONDARY} />
          </View>
        )}

        {/* Name + username stacked */}
        <View style={styles.nameColumn}>
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
        </View>

        {/* "View profile" / "Hide" link */}
        <Text style={styles.toggleLabel}>
          {expanded ? "Hide" : "View profile"}
        </Text>
      </Pressable>

      {/* ---- Expanded content -- conditionally rendered with layout animation ---- */}
      {expanded && (
        <View style={styles.expandedContent}>
          {/* Stats row */}
          <View style={styles.statsRow}>
            <StatItem value={profile.post_count} label="Posts" />
            <View style={styles.statsDivider} />
            <StatItem value={profile.total_reactions} label="Reactions" />
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
                color={theme.accent}
              />
            </Pressable>
          </View>
        </View>
      )}
    </View>
  );
}

interface StatItemProps {
  value: number;
  label: string;
}

function StatItem({ value, label }: StatItemProps) {
  return (
    <View
      style={styles.statItem}
      accessibilityLabel={`${formatCount(value)} ${label}`}
    >
      <Text style={styles.statValue}>{formatCount(value)}</Text>
      <Text style={styles.statLabel}>{label}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  wrapper: {
    marginHorizontal: 16,
    marginTop: 8,
    borderWidth: 1,
    borderColor: "rgba(255,255,255,0.06)",
    borderRadius: 16,
    backgroundColor: "#111111",
    paddingHorizontal: 16,
  },

  /* ---- Collapsed row ---- */
  collapsedRow: {
    flexDirection: "row",
    alignItems: "center",
    paddingVertical: 12,
    gap: 12,
    minHeight: 64,
  },
  collapsedRowPressed: {
    opacity: 0.7,
  },

  /* Avatar */
  avatar: {
    width: AVATAR_SIZE,
    height: AVATAR_SIZE,
    borderRadius: AVATAR_SIZE / 2,
  },
  avatarPlaceholder: {
    backgroundColor: "#111111",
    borderWidth: 1,
    borderColor: "rgba(255,255,255,0.06)",
    alignItems: "center",
    justifyContent: "center",
  },

  /* Name column */
  nameColumn: {
    flex: 1,
    justifyContent: "center",
    gap: 2,
  },
  displayName: {
    fontFamily: FONTS.display,
    fontSize: 18,
    color: "#e8e8e8",
    lineHeight: 22,
  },
  username: {
    fontFamily: FONTS.body,
    fontSize: 13,
    color: "#888888",
    lineHeight: 16,
  },

  /* Toggle label */
  toggleLabel: {
    fontFamily: FONTS.bodyMedium,
    fontSize: 13,
    color: "#888888",
    paddingLeft: 8,
  },

  /* ---- Expanded content ---- */
  expandedContent: {
    paddingBottom: 16,
    paddingTop: 4,
  },

  /* Stats row */
  statsRow: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    gap: 24,
    marginBottom: 16,
    paddingVertical: 8,
  },
  statItem: {
    alignItems: "center",
    gap: 2,
  },
  statValue: {
    fontFamily: FONTS.display,
    fontSize: 22,
    color: "#e8e8e8",
  },
  statLabel: {
    fontFamily: FONTS.body,
    fontSize: 11,
    color: "#888888",
    textTransform: "uppercase",
    letterSpacing: 1,
  },
  statsDivider: {
    width: 1,
    height: 28,
    backgroundColor: "rgba(255,255,255,0.06)",
  },

  /* Action buttons */
  buttonsRow: {
    flexDirection: "row",
    gap: 8,
  },
  editButton: {
    flex: 1,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    gap: 6,
    minHeight: MIN_TOUCH_TARGET,
    borderRadius: 9999,
    borderWidth: 1,
    borderColor: "rgba(255,255,255,0.12)",
    paddingVertical: 10,
    paddingHorizontal: 16,
  },
  editButtonPressed: {
    backgroundColor: "rgba(255,255,255,0.04)",
  },
  editButtonText: {
    fontFamily: FONTS.bodyMedium,
    fontSize: 14,
    color: "#e8e8e8",
  },
  shareButton: {
    width: MIN_TOUCH_TARGET,
    height: MIN_TOUCH_TARGET,
    alignItems: "center",
    justifyContent: "center",
    borderRadius: 9999,
    borderWidth: 1,
    borderColor: "rgba(255,255,255,0.12)",
  },
  shareButtonPressed: {
    backgroundColor: "rgba(255,255,255,0.04)",
  },
});
