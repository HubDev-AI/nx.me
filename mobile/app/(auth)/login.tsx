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
import { useEffect } from "react";
import { ActivityIndicator, StyleSheet, View } from "react-native";
import { Stack } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Ionicons } from "@expo/vector-icons";
import Animated from "react-native-reanimated";

import { useEntering } from "../../lib/hooks/use-entering";
import { THEME } from "../../constants/theme";
import { ERROR_BG, TEXT_SHADOW_DARK } from "../../constants/colors";
import { SocialLoginButtons } from "../../components/auth/SocialLoginButtons";
import { useSocialAuth } from "../../hooks/useSocialAuth";
import { useEnabledProviders } from "../../hooks/useEnabledProviders";
import { HeroBackground } from "../../components/ui/HeroBackground";
import { BrandLabel } from "../../components/ui/BrandLabel";
import { Button } from "../../components/ui/Button";
import { Body, Heading } from "../../components/ui/Text";
import { FONTS } from "../../hooks/useFonts";
import { useTheme } from "../../lib/theme-context";

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

/** Shared text-shadow values used on hero headlines (readable over image bg). */
const HERO_TEXT_SHADOW = {
  textShadowColor: TEXT_SHADOW_DARK,
  textShadowOffset: { width: 0, height: 3 },
  textShadowRadius: 12,
} as const;

const SUBTITLE_TEXT_SHADOW = {
  textShadowColor: "rgba(0, 0, 0, 0.7)",
  textShadowOffset: { width: 0, height: 1 },
  textShadowRadius: 4,
} as const;

const HERO_FONT_SIZE = 48;
const HERO_LINE_HEIGHT = 52;
const CONTENT_HORIZONTAL_PADDING = THEME.spacing.xxl;
const TOP_INSET_EXTRA = THEME.spacing.lg;
const BOTTOM_INSET_EXTRA = THEME.spacing.xxl;

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export default function AuthScreen() {
  const insets = useSafeAreaInsets();
  const { theme } = useTheme();
  const { fadeInDown } = useEntering();

  const {
    providers,
    isLoading: isLoadingProviders,
    error: providersError,
    retry: retryProviders,
  } = useEnabledProviders();

  const {
    isSocialLoading,
    socialError,
    handleGoogleLogin,
    handleAppleLogin,
    handleTikTokLogin,
    clearSocialError,
  } = useSocialAuth();

  useEffect(() => {
    return clearSocialError;
  }, [clearSocialError]);

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
              <Ionicons name="cloud-offline-outline" size={32} color={THEME.colors.textPrimary} />
              <Body color="primary" style={styles.providerErrorText}>
                {providersError}
              </Body>
              <Button
                title="Retry"
                onPress={retryProviders}
                variant="primary"
                size="lg"
                glow
                accentColor={theme.accent}
                style={{ alignSelf: "center" }}
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
            paddingTop: insets.top + TOP_INSET_EXTRA,
            paddingBottom: insets.bottom + BOTTOM_INSET_EXTRA,
          },
        ]}
      >
        <BrandLabel />
        <View style={styles.spacer} />

        {/* Hero headline */}
        <Animated.View entering={fadeInDown(0, 300)}>
          <Heading
            color={THEME.colors.white}
            maxFontSizeMultiplier={1.3}
            style={styles.heroTitle}
          >
            {"Your style,\nelevated"}
          </Heading>
          <Heading
            color={theme.accent}
            maxFontSizeMultiplier={1.3}
            style={styles.heroAccent}
          >
            start your glow-up
          </Heading>
        </Animated.View>

        <Animated.View entering={fadeInDown(60, 300)}>
          <Body
            color={THEME.colors.textPrimary}
            maxFontSizeMultiplier={1.4}
            style={styles.subtitle}
          >
            Sign in or create an account to continue
          </Body>
        </Animated.View>

        {/* Social login buttons (config-driven) */}
        {socialProviders.length > 0 && (
          <Animated.View entering={fadeInDown(120, 300)}>
            {socialError ? (
              <View
                style={styles.inlineError}
                accessibilityRole="alert"
                accessibilityLiveRegion="polite"
              >
                <Ionicons
                  name="alert-circle"
                  size={18}
                  color={THEME.colors.destructive}
                />
                <Body
                  color="destructive"
                  maxFontSizeMultiplier={1.4}
                  style={styles.inlineErrorText}
                >
                  {socialError.message}
                </Body>
              </View>
            ) : null}
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

// ---------------------------------------------------------------------------
// Styles
// ---------------------------------------------------------------------------

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
    textAlign: "center",
  },
  content: {
    ...StyleSheet.absoluteFillObject,
    paddingHorizontal: CONTENT_HORIZONTAL_PADDING,
    justifyContent: "flex-end",
  },
  spacer: {
    flex: 1,
    minHeight: 120,
  },
  heroTitle: {
    fontFamily: FONTS.display,
    fontSize: HERO_FONT_SIZE,
    lineHeight: HERO_LINE_HEIGHT,
    letterSpacing: -0.5,
    ...HERO_TEXT_SHADOW,
  },
  heroAccent: {
    fontFamily: FONTS.displayItalic,
    fontSize: HERO_FONT_SIZE,
    lineHeight: HERO_LINE_HEIGHT,
    letterSpacing: -0.5,
    marginBottom: THEME.spacing.md,
    ...HERO_TEXT_SHADOW,
  },
  subtitle: {
    marginBottom: THEME.spacing.xxl,
    ...SUBTITLE_TEXT_SHADOW,
  },
  inlineError: {
    flexDirection: "row",
    alignItems: "center",
    gap: THEME.spacing.sm,
    backgroundColor: ERROR_BG,
    borderRadius: THEME.radius.md,
    borderCurve: "continuous",
    padding: THEME.spacing.md,
    marginBottom: THEME.spacing.md,
  },
  inlineErrorText: {
    flex: 1,
  },
});
