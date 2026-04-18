import { useCallback, useEffect, useState } from "react";
import {
  View,
  Text,
  Image,
  Pressable,
  Share,
  Platform,
  StyleSheet,
} from "react-native";
import Animated, {
  useSharedValue,
  useAnimatedStyle,
  withSpring,
  withTiming,
  interpolateColor,
  Easing,
  FadeOutUp,
} from "react-native-reanimated";
import { Ionicons } from "@expo/vector-icons";

import { THEME } from "../../constants/theme";
import {
  UNIVERSAL_LINK_ORIGIN,
  MIN_TOUCH_TARGET,
} from "../../constants/config";
import { hapticLight } from "../../lib/haptics";
import { FONTS } from "../../hooks/useFonts";
import { useTheme } from "../../lib/theme-context";
import { useEntering } from "../../lib/hooks/use-entering";
import { formatCount } from "../../lib/format";
import { showToast } from "../../lib/toast";
import type { UserProfile } from "./types";

const AVATAR_SIZE = 40;

interface ProfileHeaderProps {
  profile: UserProfile;
  onEditProfile: () => void;
  showStats: boolean;
  /**
   * Share-profile button visible. Keyed to `canShareProfile` in
   * capabilities — the public card-web surface only matters when
   * social is on.
   */
  showShareProfile: boolean;
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
  showStats,
  showShareProfile,
}: ProfileHeaderProps) {
  const { theme } = useTheme();
  const { fadeInDown, reduced } = useEntering();
  const [expanded, setExpanded] = useState(false);
  const displayName = profile.display_name ?? profile.username;
  const shareUrl = `${UNIVERSAL_LINK_ORIGIN}/${profile.username}`;

  // Chevron rotation: 0 = collapsed (▼), 180 = expanded (▲)
  const chevronRotation = useSharedValue(0);

  // Wrapper border: 0 = collapsed border, 1 = expanded border
  const borderProgress = useSharedValue(0);

  // Press scale animations
  const toggleScale = useSharedValue(1);
  const editScale = useSharedValue(1);
  const shareScale = useSharedValue(1);
  const togglePressStyle = useAnimatedStyle(() => ({
    transform: [{ scale: toggleScale.value }],
  }));
  const editPressStyle = useAnimatedStyle(() => ({
    transform: [{ scale: editScale.value }],
  }));
  const sharePressStyle = useAnimatedStyle(() => ({
    transform: [{ scale: shareScale.value }],
  }));

  const chevronStyle = useAnimatedStyle(() => ({
    transform: [{ rotate: `${chevronRotation.value}deg` }],
  }));

  const wrapperAnimatedStyle = useAnimatedStyle(() => ({
    borderColor: interpolateColor(
      borderProgress.value,
      [0, 1],
      [THEME.colors.border, THEME.colors.glassBorder],
    ),
  }));

  const toggle = useCallback(() => {
    hapticLight();
    setExpanded((prev) => !prev);
  }, []);

  // Drive chevron + border animations off the `expanded` state. Writing to
  // shared values inside the setState updater above would fire during
  // React's render phase (strict mode runs updaters twice) and trip
  // Reanimated's "writing to .value during render" warning.
  useEffect(() => {
    const duration = expanded ? 250 : 200;
    chevronRotation.value = withTiming(expanded ? 180 : 0, {
      duration: 200,
      easing: Easing.out(Easing.cubic),
    });
    borderProgress.value = withTiming(expanded ? 1 : 0, {
      duration,
      easing: Easing.out(Easing.cubic),
    });
  }, [expanded, borderProgress, chevronRotation]);

  const handleShare = useCallback(async () => {
    try {
      if (Platform.OS === "web") {
        if (typeof navigator !== "undefined" && navigator.share) {
          await navigator.share({ url: shareUrl });
        } else if (typeof navigator !== "undefined" && navigator.clipboard) {
          await navigator.clipboard.writeText(shareUrl);
          showToast({ kind: 'success', message: "Share link copied to clipboard" });
        }
      } else if (Platform.OS === "ios") {
        await Share.share({ url: shareUrl });
      } else {
        await Share.share({ message: shareUrl });
      }
    } catch {
      // User cancelled or share failed -- no action needed
    }
  }, [shareUrl]);

  return (
    <Animated.View style={[styles.wrapper, wrapperAnimatedStyle]}>
      {/* ---- Collapsed row -- always visible, tappable to toggle ---- */}
      <Animated.View style={togglePressStyle}>
      <Pressable
        onPress={toggle}
        onPressIn={() => { toggleScale.value = withSpring(0.98, THEME.animation.press); }}
        onPressOut={() => { toggleScale.value = withSpring(1, THEME.animation.press); }}
        style={styles.collapsedRow}
        accessibilityLabel={
          expanded ? "Hide profile details" : "View profile details"
        }
        accessibilityRole="button"
        accessibilityState={{ expanded }}
      >
        {/* Avatar with accent ring */}
        <View style={[styles.avatarRing, { borderColor: theme.accent + "66" }]}>
          {profile.avatar_url ? (
            <Image
              source={{ uri: profile.avatar_url }}
              style={styles.avatar}
              accessibilityLabel={`${displayName} avatar`}
            />
          ) : (
            <View style={[styles.avatar, styles.avatarPlaceholder]}>
              <Ionicons name="person" size={18} color={THEME.colors.textSecondary} />
            </View>
          )}
        </View>

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

        {/* Chevron indicator — rotates 180deg when expanded */}
        <Animated.View style={[styles.chevronWrapper, chevronStyle]}>
          <Ionicons name="chevron-down" size={16} color={theme.accent} />
        </Animated.View>
      </Pressable>
      </Animated.View>

      {/* ---- Expanded content ----
          Conditionally mounted so the wrapper shrinks to the collapsed
          row when closed. FadeInDown/FadeOutUp handle the transition,
          so we no longer clip with overflow:hidden + maxHeight — that
          hack was eating expandedInner's paddingBottom and making the
          bottom of the Edit Profile button look sliced off. */}
      {expanded ? (
        <Animated.View
          entering={fadeInDown(0, reduced ? 120 : 220)}
          exiting={reduced ? undefined : FadeOutUp.duration(160)}
          style={styles.expandedInner}
        >
          {/* Separator between collapsed row and expanded content */}
          <View style={styles.expandSeparator} />

          {/* Stats row — gated on social feature (posts + reactions only exist with social on) */}
          {showStats ? (
            <View style={styles.statsRow}>
              <StatItem value={profile.post_count} label="Posts" accent={theme.accent} />
              <View style={styles.statsDivider} />
              <StatItem value={profile.total_reactions} label="Reactions" accent={theme.accent} />
            </View>
          ) : null}

          {/* Action buttons */}
          <View style={styles.buttonsRow}>
            <Animated.View style={[{ flex: 1 }, editPressStyle]}>
              <Pressable
                onPress={onEditProfile}
                onPressIn={() => { editScale.value = withSpring(0.97, THEME.animation.press); }}
                onPressOut={() => { editScale.value = withSpring(1, THEME.animation.press); }}
                style={[
                  styles.editButton,
                  { borderColor: theme.accent + "4D" },
                ]}
                accessibilityLabel="Edit Profile"
                accessibilityRole="button"
              >
                <Ionicons name="create-outline" size={16} color={theme.accent} />
                <Text style={[styles.editButtonText, { color: theme.accent }]}>
                  Edit Profile
                </Text>
              </Pressable>
            </Animated.View>

            {showShareProfile ? (
              <Animated.View style={sharePressStyle}>
                <Pressable
                  onPress={handleShare}
                  onPressIn={() => { shareScale.value = withSpring(0.97, THEME.animation.press); }}
                  onPressOut={() => { shareScale.value = withSpring(1, THEME.animation.press); }}
                  style={[
                    styles.shareButton,
                    { borderColor: theme.accent + "4D" },
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
              </Animated.View>
            ) : null}
          </View>
        </Animated.View>
      ) : null}
    </Animated.View>
  );
}

interface StatItemProps {
  value: number;
  label: string;
  accent: string;
}

function StatItem({ value, label, accent }: StatItemProps) {
  return (
    <View
      style={styles.statItem}
      accessibilityLabel={`${formatCount(value)} ${label}`}
    >
      <Text style={[styles.statValue, { color: accent }]}>
        {formatCount(value)}
      </Text>
      <Text style={styles.statLabel}>{label}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  wrapper: {
    marginHorizontal: THEME.spacing.lg,
    marginTop: THEME.spacing.sm,
    borderWidth: 1,
    borderColor: THEME.colors.border,
    borderRadius: THEME.radius.lg,
    backgroundColor: THEME.colors.glass,
    paddingHorizontal: THEME.spacing.lg,
    ...THEME.shadow.glass,
  },

  /* ---- Collapsed row ---- */
  collapsedRow: {
    flexDirection: "row",
    alignItems: "center",
    paddingVertical: THEME.spacing.md,
    gap: THEME.spacing.md,
    minHeight: 64,
  },

  /* Avatar with accent ring */
  avatarRing: {
    width: AVATAR_SIZE + 4,
    height: AVATAR_SIZE + 4,
    borderRadius: (AVATAR_SIZE + 4) / 2,
    borderWidth: 2,
    alignItems: "center",
    justifyContent: "center",
  },
  avatar: {
    width: AVATAR_SIZE,
    height: AVATAR_SIZE,
    borderRadius: AVATAR_SIZE / 2,
  },
  avatarPlaceholder: {
    backgroundColor: THEME.colors.surfaceElevated,
    borderWidth: 1,
    borderColor: THEME.colors.border,
    alignItems: "center",
    justifyContent: "center",
  },

  /* Name column */
  nameColumn: {
    flex: 1,
    justifyContent: "center",
    gap: THEME.spacing.xs / 2,
  },
  displayName: {
    fontFamily: FONTS.display,
    fontSize: 20,
    color: THEME.colors.textPrimary,
    lineHeight: 24,
  },
  username: {
    fontFamily: FONTS.body,
    ...THEME.typography.caption,
    color: THEME.colors.textSecondary,
  },

  /* Chevron toggle indicator */
  chevronWrapper: {
    paddingLeft: THEME.spacing.sm,
    alignItems: "center",
    justifyContent: "center",
  },

  /* Separator between collapsed row and expanded content */
  expandSeparator: {
    height: 1,
    backgroundColor: THEME.colors.glassBorder,
    marginBottom: THEME.spacing.md,
  },

  /* ---- Expanded content ----
     Conditionally mounted (see render). No overflow:hidden needed now
     that FadeInDown/FadeOutUp drive the transition — the prior
     maxHeight hack was clipping paddingBottom, trimming the bottom of
     the Edit Profile button. */
  expandedInner: {
    paddingTop: THEME.spacing.xs,
    paddingBottom: THEME.spacing.lg,
  },

  /* Stats row */
  statsRow: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    gap: THEME.spacing.xxl,
    marginBottom: THEME.spacing.lg,
    paddingVertical: THEME.spacing.sm,
  },
  statItem: {
    alignItems: "center",
    gap: THEME.spacing.xs,
  },
  statValue: {
    fontFamily: FONTS.bodyBold,
    fontSize: 22,
    lineHeight: 28,
    letterSpacing: 0,
    color: THEME.colors.textPrimary,
  },
  statLabel: {
    fontFamily: FONTS.bodySemiBold,
    fontSize: 11,
    color: THEME.colors.textSecondary,
    textTransform: "uppercase",
    letterSpacing: THEME.typography.caption.letterSpacing,
  },
  statsDivider: {
    width: 1,
    height: 32,
    backgroundColor: THEME.colors.glassBorder,
  },

  /* Action buttons */
  buttonsRow: {
    flexDirection: "row",
    gap: THEME.spacing.sm,
  },
  editButton: {
    flex: 1,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    gap: THEME.spacing.sm,
    minHeight: MIN_TOUCH_TARGET,
    borderRadius: THEME.radius.pill,
    borderWidth: 1,
    paddingVertical: THEME.spacing.md - 2,
    paddingHorizontal: THEME.spacing.lg,
  },
  editButtonText: {
    fontFamily: FONTS.bodyMedium,
    fontSize: 14,
  },
  shareButton: {
    width: MIN_TOUCH_TARGET,
    height: MIN_TOUCH_TARGET,
    alignItems: "center",
    justifyContent: "center",
    borderRadius: THEME.radius.pill,
    borderWidth: 1,
  },
});
