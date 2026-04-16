/**
 * Settings screen — account info, subscription link, about, danger zone.
 *
 * Route: /settings (custom header)
 * Auth: required — fetches /v1/auth/me for account details.
 */
import { useCallback, useEffect, useState } from "react";
import {
  Alert,
  ScrollView,
  StyleSheet,
  View,
} from "react-native";
import { useRouter } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Ionicons } from "@expo/vector-icons";
import Animated from "react-native-reanimated";

import { LoadingSkeleton } from "../components/ui/LoadingSkeleton";
import { useEntering } from "../lib/hooks/use-entering";
import type ExpoConstants from "expo-constants";

import { THEME } from "../constants/theme";
import { ERROR_BORDER } from "../constants/colors";
import { PageBackground } from "../components/ui/PageBackground";
import { PressableScale } from "../components/ui/PressableScale";
import { Button } from "../components/ui/Button";
import {
  HeaderBackButton,
  HeaderBackButtonSpacer,
} from "../components/ui/HeaderBackButton";
import { Body, Caption, Heading, Label } from "../components/ui/Text";
import { useTheme } from "../lib/theme-context";
import { useAuth } from "../lib/auth-context";
import { useCapabilities } from "../lib/capabilities";
import { AUTH_ENDPOINTS, MIN_TOUCH_TARGET } from "../constants/config";
import { apiFetch } from "../lib/api";
import { parseApiError } from "../lib/errors";
import { showToast } from "../lib/toast";
import { clearAllTokens } from "../lib/auth";

/** Header title font size — matches subscription + upload screens. */
const HEADER_TITLE_FONT_SIZE = 20;

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
  const { setSessionMode } = useAuth();
  const caps = useCapabilities();
  const { fadeInDown } = useEntering();

  const [me, setMe] = useState<MeResponse | null>(null);
  const [isLoading, setIsLoading] = useState(caps.canViewAccountDetails);
  const [error, setError] = useState<string | null>(null);
  const [isDeleting, setIsDeleting] = useState(false);
  const [isLoggingOut, setIsLoggingOut] = useState(false);

  const appVersion = Constants?.expoConfig?.version ?? "1.0.0";

  // -------------------------------------------------------------------------
  // Fetch /v1/auth/me — only for real users; guests have no account record.
  // -------------------------------------------------------------------------
  useEffect(() => {
    if (!caps.canViewAccountDetails) return;

    let cancelled = false;

    async function load() {
      setIsLoading(true);
      setError(null);
      try {
        const data = await apiFetch<MeResponse>("/v1/auth/me");
        if (!cancelled) setMe(data);
      } catch (err) {
        if (!cancelled) {
          const appError = parseApiError(err);
          setError(appError.message);
        }
      } finally {
        if (!cancelled) setIsLoading(false);
      }
    }

    load();
    return () => {
      cancelled = true;
    };
  }, [caps.canViewAccountDetails]);

  // -------------------------------------------------------------------------
  // Logout (best-effort server logout — always clear local tokens)
  // -------------------------------------------------------------------------
  const handleLogout = useCallback(() => {
    Alert.alert(
      "Log Out",
      "You'll need to sign in again to access your account.",
      [
        { text: "Cancel", style: "cancel" },
        {
          text: "Log Out",
          style: "destructive",
          onPress: async () => {
            setIsLoggingOut(true);
            try {
              await apiFetch<void>(AUTH_ENDPOINTS.LOGOUT, { method: "POST" });
            } catch {
              // Network or 401 — proceed with local logout anyway.
            }
            await clearAllTokens();
            setSessionMode("anon");
          },
        },
      ],
    );
  }, [setSessionMode]);

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
              setSessionMode("anon");
            } catch (err) {
              const appError = parseApiError(err);
              showToast({ kind: 'error', message: appError.message });
            } finally {
              setIsDeleting(false);
            }
          },
        },
      ],
    );
  }, [setSessionMode]);

  // -------------------------------------------------------------------------
  // Render
  // -------------------------------------------------------------------------
  return (
    <View style={styles.container}>
      <PageBackground overlayOpacity={0.88} />

      {/* Custom header — matches subscription + upload screens. */}
      <View style={[styles.header, { paddingTop: insets.top }]}>
        <HeaderBackButton onPress={() => router.back()} />
        <Heading
          size="md"
          style={styles.headerTitle}
          maxFontSizeMultiplier={1.3}
        >
          Settings
        </Heading>
        <HeaderBackButtonSpacer />
      </View>

      <ScrollView
          style={styles.scroll}
          contentContainerStyle={[
            styles.scrollContent,
            { paddingBottom: insets.bottom + THEME.spacing.xxxl },
          ]}
          showsVerticalScrollIndicator={false}
        >
          {/* ─── Account Section ──────────────────────────────────────── */}
          <Animated.View entering={fadeInDown(0, 240)}>
            <Label color="secondary" style={styles.sectionLabel} maxFontSizeMultiplier={1.3}>
              ACCOUNT
            </Label>
            <View style={styles.glassCard}>
              {!caps.canViewAccountDetails ? (
                <Body color="secondary" style={styles.guestText}>
                  You&apos;re using NXME as a guest. Your glow-ups are saved on
                  this device only and won&apos;t sync across installs. Sign in
                  from the profile menu to keep them tied to an account.
                </Body>
              ) : isLoading ? (
                <View style={styles.accountSkeleton}>
                  <LoadingSkeleton height={18} width="40%" />
                  <LoadingSkeleton height={18} width="60%" />
                  <LoadingSkeleton height={18} width="70%" />
                </View>
              ) : error ? (
                <Caption color="destructive" style={styles.errorText}>{error}</Caption>
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
          <Animated.View entering={fadeInDown(40, 240)}>
            <Label color="secondary" style={styles.sectionLabel} maxFontSizeMultiplier={1.3}>
              SUBSCRIPTION
            </Label>
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
                  <Body weight="medium" color="primary">Manage Subscription</Body>
                </View>
                <Ionicons
                  name="chevron-forward"
                  size={18}
                  color={THEME.colors.textMuted}
                />
              </View>
            </PressableScale>
          </Animated.View>

          {/* ─── Privacy Section — auth + social both required ────────── */}
          {caps.canViewBlockedUsers && (
            <Animated.View entering={fadeInDown(80, 240)}>
              <Label color="secondary" style={styles.sectionLabel} maxFontSizeMultiplier={1.3}>
                PRIVACY
              </Label>
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
                    <Body weight="medium" color="primary">Blocked Users</Body>
                  </View>
                  <Ionicons
                    name="chevron-forward"
                    size={18}
                    color={THEME.colors.textMuted}
                  />
                </View>
              </PressableScale>
            </Animated.View>
          )}

          {/* ─── About Section ────────────────────────────────────────── */}
          <Animated.View entering={fadeInDown(120, 240)}>
            <Label color="secondary" style={styles.sectionLabel} maxFontSizeMultiplier={1.3}>
              ABOUT
            </Label>
            <View style={styles.glassCard}>
              <SettingsRow
                icon="information-circle-outline"
                label="App Version"
                value={`v${appVersion}`}
              />
            </View>
          </Animated.View>

          {/* ─── Session — only when auth is enabled for this user ────── */}
          {caps.canSignOut && (
            <Animated.View entering={fadeInDown(160, 240)}>
              <Label color="secondary" style={styles.sectionLabel} maxFontSizeMultiplier={1.3}>
                SESSION
              </Label>
              <View style={styles.glassCard}>
                <Button
                  title="Log Out"
                  onPress={handleLogout}
                  variant="secondary"
                  size="md"
                  block
                  isLoading={isLoggingOut}
                  leftIcon={
                    <Ionicons
                      name="log-out-outline"
                      size={18}
                      color={theme.accent}
                    />
                  }
                  accessibilityLabel="Log out of your account"
                />
              </View>
            </Animated.View>
          )}

          {/* ─── Danger Zone — only for signed-in users ──────────────── */}
          {caps.canDeleteAccount && (
            <Animated.View entering={fadeInDown(200, 240)}>
              <Label color="destructive" style={styles.sectionLabel} maxFontSizeMultiplier={1.3}>
                DANGER ZONE
              </Label>
              <View style={[styles.glassCard, styles.dangerCard]}>
                <Body color="secondary" style={styles.dangerText}>
                  Permanently delete your account and all associated data. This
                  action cannot be undone.
                </Body>
                <Button
                  title="Delete Account"
                  onPress={handleDeleteAccount}
                  variant="destructive"
                  size="md"
                  block
                  isLoading={isDeleting}
                  leftIcon={
                    <Ionicons
                      name="trash-outline"
                      size={18}
                      color={THEME.colors.white}
                    />
                  }
                  accessibilityLabel="Delete account"
                />
              </View>
            </Animated.View>
          )}
      </ScrollView>
    </View>
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
        <Body weight="medium" color="secondary">{label}</Body>
      </View>
      <Body color="primary" numberOfLines={1} style={styles.settingsRowValue}>
        {value}
      </Body>
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
  header: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    paddingHorizontal: THEME.spacing.sm,
    paddingBottom: THEME.spacing.sm,
  },
  headerTitle: {
    fontSize: HEADER_TITLE_FONT_SIZE,
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
    marginTop: THEME.spacing.xxl,
    marginBottom: THEME.spacing.sm,
    marginLeft: THEME.spacing.xs,
  },

  // Glass card
  glassCard: {
    backgroundColor: THEME.colors.glass,
    borderRadius: THEME.radius.lg,
    borderCurve: "continuous",
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
    minHeight: MIN_TOUCH_TARGET,
  },
  settingsRowLeft: {
    flexDirection: "row",
    alignItems: "center",
    gap: THEME.spacing.md,
    flexShrink: 0,
  },
  settingsRowValue: {
    textAlign: "right",
    flexShrink: 1,
    marginLeft: THEME.spacing.lg,
  },

  // Loading
  accountSkeleton: {
    paddingVertical: THEME.spacing.md,
    paddingHorizontal: THEME.spacing.lg,
    gap: THEME.spacing.md,
  },

  // Error
  errorText: {
    textAlign: "center",
  },

  // Guest explainer
  guestText: {
    lineHeight: 20,
  },

  // Navigation row (Subscription link)
  navRow: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    minHeight: MIN_TOUCH_TARGET,
  },
  navRowLeft: {
    flexDirection: "row",
    alignItems: "center",
    gap: THEME.spacing.md,
  },

  // Danger zone
  dangerCard: {
    borderColor: ERROR_BORDER,
  },
  dangerText: {
    marginBottom: THEME.spacing.lg,
    lineHeight: 20,
  },
});
