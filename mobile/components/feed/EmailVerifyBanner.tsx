/**
 * EmailVerifyBanner — subtle glass banner shown at the top of the feed
 * when the user has not yet verified their email.
 *
 * The banner auto-dismisses when:
 * - The user taps "Dismiss" (persists dismissal)
 * - Entitlement shows trial_analyses_remaining > 0 (implies verified)
 *
 * Relies on the PENDING_EMAIL_VERIFICATION SecureStore flag set during signup.
 */
import { useEffect, useState, useCallback } from "react";
import { View, Text, Pressable, StyleSheet, Linking, Platform } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import Animated, { FadeInDown, FadeOutUp } from "react-native-reanimated";

import { THEME } from "../../constants/theme";
import { FONTS } from "../../hooks/useFonts";
import { useTheme } from "../../lib/theme-context";
import { useAuth } from "../../lib/auth-context";
import { getItem, deleteItem } from "../../lib/secure-storage";
import { SECURE_STORE_KEYS } from "../../constants/config";
import { fetchEntitlement } from "../../lib/entitlement";

export function EmailVerifyBanner() {
  const { isAuthenticated } = useAuth();
  const { theme } = useTheme();
  const [showBanner, setShowBanner] = useState(false);

  useEffect(() => {
    if (!isAuthenticated) {
      setShowBanner(false);
      return;
    }

    let cancelled = false;

    async function check() {
      try {
        const pending = await getItem(SECURE_STORE_KEYS.PENDING_EMAIL_VERIFICATION);
        if (!pending || cancelled) return;

        // Double-check: if entitlement shows trials > 0, user has verified
        try {
          const ent = await fetchEntitlement();
          if (ent.trial_analyses_remaining > 0) {
            // Already verified -- clear the flag
            await deleteItem(SECURE_STORE_KEYS.PENDING_EMAIL_VERIFICATION);
            return;
          }
        } catch {
          // Can't reach entitlement -- show banner to be safe
        }

        if (!cancelled) setShowBanner(true);
      } catch {
        // SecureStore read failed -- don't show banner
      }
    }

    check();
    return () => {
      cancelled = true;
    };
  }, [isAuthenticated]);

  const handleDismiss = useCallback(() => {
    setShowBanner(false);
    deleteItem(SECURE_STORE_KEYS.PENDING_EMAIL_VERIFICATION).catch(() => {});
  }, []);

  const handleOpenEmail = useCallback(async () => {
    try {
      if (Platform.OS === "ios") {
        await Linking.openURL("message://");
      } else {
        await Linking.openURL("mailto:");
      }
    } catch {
      // Can't open email app -- no-op
    }
  }, []);

  if (!showBanner) return null;

  return (
    <Animated.View
      entering={FadeInDown.duration(400)}
      exiting={FadeOutUp.duration(300)}
      style={styles.outerWrapper}
    >
      <View style={[styles.banner, { borderColor: theme.accent + "40" }]}>
        <View style={styles.content}>
          <Ionicons name="mail-outline" size={18} color={theme.accent} />
          <Text style={styles.text}>
            Verify your email to unlock free trials
          </Text>
        </View>
        <View style={styles.actions}>
          <Pressable
            onPress={handleOpenEmail}
            style={[styles.actionButton, { backgroundColor: theme.accent + "1A" }]}
            accessibilityLabel="Open email app to verify"
            accessibilityRole="button"
          >
            <Text style={[styles.actionText, { color: theme.accent }]}>
              Open Email
            </Text>
          </Pressable>
          <Pressable
            onPress={handleDismiss}
            style={styles.dismissButton}
            accessibilityLabel="Dismiss verification banner"
            accessibilityRole="button"
          >
            <Ionicons
              name="close"
              size={18}
              color={THEME.colors.textMuted}
            />
          </Pressable>
        </View>
      </View>
    </Animated.View>
  );
}

const styles = StyleSheet.create({
  outerWrapper: {
    paddingHorizontal: THEME.spacing.xl,
    paddingTop: THEME.spacing.sm,
  },
  banner: {
    backgroundColor: THEME.colors.glass,
    borderRadius: THEME.radius.lg,
    borderWidth: 1,
    padding: THEME.spacing.md,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    ...THEME.shadow.glass,
  },
  content: {
    flexDirection: "row",
    alignItems: "center",
    gap: THEME.spacing.sm,
    flex: 1,
    marginRight: THEME.spacing.sm,
  },
  text: {
    fontFamily: FONTS.bodyMedium,
    ...THEME.typography.caption,
    color: THEME.colors.textPrimary,
    flex: 1,
  },
  actions: {
    flexDirection: "row",
    alignItems: "center",
    gap: THEME.spacing.xs,
  },
  actionButton: {
    borderRadius: THEME.radius.pill,
    paddingHorizontal: THEME.spacing.md,
    paddingVertical: THEME.spacing.xs,
    minHeight: 32,
    alignItems: "center",
    justifyContent: "center",
  },
  actionText: {
    fontFamily: FONTS.bodySemiBold,
    fontSize: 12,
  },
  dismissButton: {
    width: 32,
    height: 32,
    alignItems: "center",
    justifyContent: "center",
    borderRadius: THEME.radius.pill,
  },
});
