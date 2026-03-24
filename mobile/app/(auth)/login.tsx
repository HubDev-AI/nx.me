/**
 * Auth screen -- social-only login.
 *
 * Login methods are config-driven: the backend GET /auth/providers endpoint
 * returns which providers are enabled. Only enabled providers are shown.
 * When a provider is disabled, its button is hidden from the UI.
 *
 * For social auth (TikTok, Google, Apple), login and signup are the same
 * flow -- the backend handles account creation on first login.
 */
import { useState, useEffect } from "react";
import {
  View,
  Text,
  StyleSheet,
  ActivityIndicator,
} from "react-native";
import { Stack } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Ionicons } from "@expo/vector-icons";
import Animated, { FadeInDown } from "react-native-reanimated";

import { THEME } from "../../constants/theme";
import {
  TEXT_INVERSE,
  TEXT_PRIMARY,
  TEXT_SHADOW_DARK,
  ERROR_BG,
} from "../../constants/colors";
import { SocialLoginButtons } from "../../components/auth/SocialLoginButtons";
import { useSocialAuth } from "../../hooks/useSocialAuth";
import { useEnabledProviders } from "../../hooks/useEnabledProviders";

import { HeroBackground } from "../../components/ui/HeroBackground";
import { BrandLabel } from "../../components/ui/BrandLabel";
import { GlowButton } from "../../components/ui/GlowButton";
import { useTheme } from "../../lib/theme-context";
import { FONTS } from "../../hooks/useFonts";

interface FieldErrors {
  general?: string;
}

export default function AuthScreen() {
  const insets = useSafeAreaInsets();
  const { theme } = useTheme();

  // Fetch enabled providers from backend
  const {
    providers,
    isLoading: isLoadingProviders,
    error: providersError,
    retry: retryProviders,
  } = useEnabledProviders();

  // Social auth
  const {
    isSocialLoading,
    socialError,
    handleGoogleLogin,
    handleAppleLogin,
    handleTikTokLogin,
    clearSocialError,
  } = useSocialAuth();

  const [errors, setErrors] = useState<FieldErrors>({});

  // Surface social auth errors
  useEffect(() => {
    if (socialError) {
      setErrors({ general: socialError });
      clearSocialError();
    }
  }, [socialError, clearSocialError]);

  // ---- Providers loading / error state ----
  if (isLoadingProviders || providersError) {
    return (
      <>
        <Stack.Screen options={{ headerShown: false }} />
        <HeroBackground />
        <View style={styles.loadingContainer}>
          {isLoadingProviders ? (
            <ActivityIndicator size="large" color={theme.accent} />
          ) : (
            <View style={styles.providerErrorContainer}>
              <Ionicons name="cloud-offline-outline" size={32} color={TEXT_PRIMARY} />
              <Text style={styles.providerErrorText}>{providersError}</Text>
              <GlowButton
                title="Retry"
                onPress={retryProviders}
                glowColor={theme.accent}
                size="large"
              />
            </View>
          )}
        </View>
      </>
    );
  }

  const socialProviders = providers.filter((p) => p !== "email");

  return (
    <>
      <Stack.Screen options={{ headerShown: false }} />
      <HeroBackground />

      <View
        style={[
          styles.content,
          {
            paddingTop: insets.top + 16,
            paddingBottom: insets.bottom + 24,
          },
        ]}
      >
        <BrandLabel />
        <View style={styles.spacer} />

        {/* Hero headline */}
        <Animated.View entering={FadeInDown.duration(800).springify().damping(15)}>
          <Text style={styles.heroTitle}>{"Your style,\nelevated"}</Text>
          <Text style={[styles.heroAccent, { color: theme.accent }]}>
            start your glow-up
          </Text>
        </Animated.View>

        <Animated.View entering={FadeInDown.delay(150).duration(800).springify().damping(15)}>
          <Text style={styles.subtitle}>
            Sign in or create an account to continue
          </Text>
        </Animated.View>

        {/* General error */}
        {errors.general ? (
          <View style={styles.generalError} accessibilityRole="alert">
            <Ionicons name="alert-circle" size={18} color={THEME.colors.destructive} />
            <Text style={styles.generalErrorText}>{errors.general}</Text>
          </View>
        ) : null}

        {/* Social login buttons (config-driven) */}
        {socialProviders.length > 0 && (
          <Animated.View entering={FadeInDown.delay(300).duration(800).springify().damping(15)}>
            <SocialLoginButtons
              enabledProviders={providers}
              onGooglePress={handleGoogleLogin}
              onApplePress={handleAppleLogin}
              onTikTokPress={handleTikTokLogin}
              disabled={isSocialLoading}
            />
          </Animated.View>
        )}
      </View>
    </>
  );
}

const styles = StyleSheet.create({
  loadingContainer: {
    ...StyleSheet.absoluteFillObject,
    justifyContent: "center",
    alignItems: "center",
  },
  providerErrorContainer: {
    alignItems: "center",
    gap: THEME.spacing.lg,
    paddingHorizontal: THEME.spacing.xxl,
  },
  providerErrorText: {
    fontFamily: FONTS.body,
    fontSize: 15,
    color: TEXT_PRIMARY,
    textAlign: "center",
  },
  content: {
    ...StyleSheet.absoluteFillObject,
    paddingHorizontal: THEME.spacing.xxl,
    justifyContent: "flex-end",
  },
  spacer: {
    flex: 1,
    minHeight: 120,
  },
  heroTitle: {
    fontFamily: FONTS.display,
    fontSize: 48,
    lineHeight: 52,
    color: TEXT_INVERSE,
    letterSpacing: -0.5,
    textShadowColor: TEXT_SHADOW_DARK,
    textShadowOffset: { width: 0, height: 3 },
    textShadowRadius: 12,
  },
  heroAccent: {
    fontFamily: FONTS.displayItalic,
    fontSize: 48,
    lineHeight: 52,
    letterSpacing: -0.5,
    marginBottom: THEME.spacing.md,
  },
  subtitle: {
    fontFamily: FONTS.body,
    fontSize: 15,
    color: TEXT_PRIMARY,
    marginBottom: THEME.spacing.xxl,
    textShadowColor: "rgba(0, 0, 0, 0.7)",
    textShadowOffset: { width: 0, height: 1 },
    textShadowRadius: 4,
  },
  generalError: {
    flexDirection: "row",
    alignItems: "center",
    gap: THEME.spacing.sm,
    backgroundColor: ERROR_BG,
    borderRadius: THEME.radius.md,
    padding: THEME.spacing.md,
    marginBottom: THEME.spacing.lg,
  },
  generalErrorText: {
    fontSize: 14,
    color: THEME.colors.destructive,
    flex: 1,
  },
});
