/**
 * Settings screen — account info, subscription link, about, danger zone.
 *
 * Route: /settings (Stack.Screen)
 * Auth: required — fetches /v1/auth/me for account details.
 */
import { useState, useEffect, useCallback } from "react";
import {
  View,
  Text,
  ScrollView,
  ActivityIndicator,
  Alert,
  StyleSheet,
} from "react-native";
import { Stack, useRouter } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Ionicons } from "@expo/vector-icons";
import Animated, { FadeInDown } from "react-native-reanimated";
import type ExpoConstants from "expo-constants";

import { THEME } from "../constants/theme";
import { ERROR_BORDER } from "../constants/colors";
import { PageBackground } from "../components/ui/PageBackground";
import { PressableScale } from "../components/ui/PressableScale";
import { useTheme } from "../lib/theme-context";
import { useAuth } from "../lib/auth-context";
import { FONTS } from "../hooks/useFonts";
import { MIN_TOUCH_TARGET } from "../constants/config";
import { apiFetch, ApiError } from "../lib/api";
import { clearAllTokens } from "../lib/auth";

// Safely resolve expo-constants — if unavailable (bare workflow edge case),
// we fall back to a static version string instead of crashing the screen.
let Constants: typeof ExpoConstants | undefined;
try {
  // eslint-disable-next-line @typescript-eslint/no-require-imports -- dynamic require for graceful fallback in bare workflow
  Constants = require("expo-constants") as typeof ExpoConstants;
} catch {
  // expo-constants not available
}

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface MeResponse {
  user_id: string;
  username: string;
  display_name: string;
  email: string;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export default function SettingsScreen() {
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const { theme } = useTheme();
  const { setAuthenticated } = useAuth();

  const [me, setMe] = useState<MeResponse | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [isDeleting, setIsDeleting] = useState(false);

  const appVersion = Constants?.expoConfig?.version ?? "1.0.0";

  // -------------------------------------------------------------------------
  // Fetch /v1/auth/me
  // -------------------------------------------------------------------------
  useEffect(() => {
    let cancelled = false;

    async function load() {
      setIsLoading(true);
      setError(null);
      try {
        const data = await apiFetch<MeResponse>("/v1/auth/me");
        if (!cancelled) setMe(data);
      } catch (err) {
        if (!cancelled) {
          setError(
            err instanceof ApiError
              ? `Failed to load account (${err.status})`
              : "Failed to load account",
          );
        }
      } finally {
        if (!cancelled) setIsLoading(false);
      }
    }

    load();
    return () => {
      cancelled = true;
    };
  }, []);

  // -------------------------------------------------------------------------
  // Delete account
  // -------------------------------------------------------------------------
  const handleDeleteAccount = useCallback(() => {
    Alert.alert(
      "Delete Account",
      "This action is permanent and cannot be undone. All your data will be deleted.",
      [
        { text: "Cancel", style: "cancel" },
        {
          text: "Delete",
          style: "destructive",
          onPress: async () => {
            setIsDeleting(true);
            try {
              await apiFetch<void>("/v1/auth/account", { method: "DELETE" });
              await clearAllTokens();
              setAuthenticated(false);
            } catch (err) {
              Alert.alert(
                "Error",
                err instanceof ApiError
                  ? `Could not delete account (${err.status})`
                  : "Could not delete account. Please try again.",
              );
            } finally {
              setIsDeleting(false);
            }
          },
        },
      ],
    );
  }, [setAuthenticated]);

  // -------------------------------------------------------------------------
  // Render
  // -------------------------------------------------------------------------
  return (
    <>
      <Stack.Screen
        options={{
          title: "Settings",
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
          {/* ─── Account Section ──────────────────────────────────────── */}
          <Animated.View entering={FadeInDown.delay(50).duration(400)}>
            <Text style={styles.sectionLabel}>ACCOUNT</Text>
            <View style={styles.glassCard}>
              {isLoading ? (
                <View style={styles.loadingRow}>
                  <ActivityIndicator color={THEME.colors.textSecondary} />
                  <Text style={styles.loadingText}>Loading account...</Text>
                </View>
              ) : error ? (
                <Text style={styles.errorText}>{error}</Text>
              ) : me ? (
                <>
                  <SettingsRow
                    icon="person-outline"
                    label="Display Name"
                    value={me.display_name}
                  />
                  <View style={styles.divider} />
                  <SettingsRow
                    icon="at-outline"
                    label="Username"
                    value={`@${me.username}`}
                  />
                  <View style={styles.divider} />
                  <SettingsRow
                    icon="mail-outline"
                    label="Email"
                    value={me.email}
                  />
                </>
              ) : null}
            </View>
          </Animated.View>

          {/* ─── Subscription Section ─────────────────────────────────── */}
          <Animated.View entering={FadeInDown.delay(120).duration(400)}>
            <Text style={styles.sectionLabel}>SUBSCRIPTION</Text>
            <PressableScale
              style={styles.glassCard}
              onPress={() => router.push("/subscription")}
              accessibilityLabel="Manage subscription"
              accessibilityRole="button"
            >
              <View style={styles.navRow}>
                <View style={styles.navRowLeft}>
                  <Ionicons
                    name="diamond-outline"
                    size={20}
                    color={theme.accent}
                  />
                  <Text style={styles.navRowLabel}>Manage Subscription</Text>
                </View>
                <Ionicons
                  name="chevron-forward"
                  size={18}
                  color={THEME.colors.textMuted}
                />
              </View>
            </PressableScale>
          </Animated.View>

          {/* ─── Privacy Section ──────────────────────────────────────── */}
          <Animated.View entering={FadeInDown.delay(190).duration(400)}>
            <Text style={styles.sectionLabel}>PRIVACY</Text>
            <PressableScale
              style={styles.glassCard}
              onPress={() => router.push("/blocked-users")}
              accessibilityLabel="Blocked users"
              accessibilityRole="button"
            >
              <View style={styles.navRow}>
                <View style={styles.navRowLeft}>
                  <Ionicons
                    name="shield-outline"
                    size={20}
                    color={theme.accent}
                  />
                  <Text style={styles.navRowLabel}>Blocked Users</Text>
                </View>
                <Ionicons
                  name="chevron-forward"
                  size={18}
                  color={THEME.colors.textMuted}
                />
              </View>
            </PressableScale>
          </Animated.View>

          {/* ─── About Section ────────────────────────────────────────── */}
          <Animated.View entering={FadeInDown.delay(260).duration(400)}>
            <Text style={styles.sectionLabel}>ABOUT</Text>
            <View style={styles.glassCard}>
              <SettingsRow
                icon="information-circle-outline"
                label="App Version"
                value={`v${appVersion}`}
              />
            </View>
          </Animated.View>

          {/* ─── Danger Zone ──────────────────────────────────────────── */}
          <Animated.View entering={FadeInDown.delay(330).duration(400)}>
            <Text style={[styles.sectionLabel, { color: THEME.colors.destructive }]}>
              DANGER ZONE
            </Text>
            <View style={[styles.glassCard, styles.dangerCard]}>
              <Text style={styles.dangerText}>
                Permanently delete your account and all associated data. This
                action cannot be undone.
              </Text>
              <PressableScale
                onPress={handleDeleteAccount}
                disabled={isDeleting}
                style={[
                  styles.deleteButton,
                  isDeleting && styles.deleteButtonDisabled,
                ]}
                accessibilityLabel="Delete account"
                accessibilityRole="button"
              >
                {isDeleting ? (
                  <ActivityIndicator color={THEME.colors.white} size="small" />
                ) : (
                  <>
                    <Ionicons
                      name="trash-outline"
                      size={18}
                      color={THEME.colors.white}
                    />
                    <Text style={styles.deleteButtonText}>Delete Account</Text>
                  </>
                )}
              </PressableScale>
            </View>
          </Animated.View>
        </ScrollView>
      </View>
    </>
  );
}

// ---------------------------------------------------------------------------
// SettingsRow — read-only label + value
// ---------------------------------------------------------------------------

interface SettingsRowProps {
  icon: React.ComponentProps<typeof Ionicons>["name"];
  label: string;
  value: string;
}

function SettingsRow({ icon, label, value }: SettingsRowProps) {
  return (
    <View style={styles.settingsRow}>
      <View style={styles.settingsRowLeft}>
        <Ionicons name={icon} size={18} color={THEME.colors.textSecondary} />
        <Text style={styles.settingsRowLabel}>{label}</Text>
      </View>
      <Text style={styles.settingsRowValue} numberOfLines={1}>
        {value}
      </Text>
    </View>
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
  },

  // Section label
  sectionLabel: {
    fontFamily: FONTS.bodySemiBold,
    fontSize: 11,
    color: THEME.colors.textSecondary,
    letterSpacing: 1,
    textTransform: "uppercase",
    marginTop: THEME.spacing.xxl,
    marginBottom: THEME.spacing.sm,
    marginLeft: THEME.spacing.xs,
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

  // Divider inside card
  divider: {
    height: StyleSheet.hairlineWidth,
    backgroundColor: THEME.colors.border,
    marginVertical: THEME.spacing.md,
  },

  // Settings row
  settingsRow: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    minHeight: 36,
  },
  settingsRowLeft: {
    flexDirection: "row",
    alignItems: "center",
    gap: THEME.spacing.md,
    flexShrink: 0,
  },
  settingsRowLabel: {
    fontFamily: FONTS.bodyMedium,
    ...THEME.typography.body,
    color: THEME.colors.textSecondary,
  },
  settingsRowValue: {
    fontFamily: FONTS.body,
    ...THEME.typography.body,
    color: THEME.colors.textPrimary,
    textAlign: "right",
    flexShrink: 1,
    marginLeft: THEME.spacing.lg,
  },

  // Loading
  loadingRow: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    gap: THEME.spacing.md,
    paddingVertical: THEME.spacing.md,
  },
  loadingText: {
    fontFamily: FONTS.body,
    ...THEME.typography.caption,
    color: THEME.colors.textSecondary,
  },

  // Error
  errorText: {
    fontFamily: FONTS.body,
    ...THEME.typography.caption,
    color: THEME.colors.destructive,
    textAlign: "center",
  },

  // Navigation row (Subscription link)
  navRow: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    minHeight: MIN_TOUCH_TARGET - THEME.spacing.lg * 2,
  },
  navRowLeft: {
    flexDirection: "row",
    alignItems: "center",
    gap: THEME.spacing.md,
  },
  navRowLabel: {
    fontFamily: FONTS.bodyMedium,
    ...THEME.typography.body,
    color: THEME.colors.textPrimary,
  },

  // Danger zone
  dangerCard: {
    borderColor: ERROR_BORDER,
  },
  dangerText: {
    fontFamily: FONTS.body,
    ...THEME.typography.caption,
    color: THEME.colors.textSecondary,
    marginBottom: THEME.spacing.lg,
    lineHeight: 20,
  },
  deleteButton: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    gap: THEME.spacing.sm,
    backgroundColor: THEME.colors.destructive,
    borderRadius: THEME.radius.pill,
    minHeight: MIN_TOUCH_TARGET,
    paddingHorizontal: THEME.spacing.xxl,
  },
  deleteButtonDisabled: {
    opacity: 0.5,
  },
  deleteButtonText: {
    fontFamily: FONTS.bodyMedium,
    fontSize: 15,
    color: THEME.colors.white,
  },
});
