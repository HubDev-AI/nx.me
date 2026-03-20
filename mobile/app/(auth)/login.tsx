import { useState, useCallback, useRef, useEffect } from "react";
import {
  View,
  Text,
  StyleSheet,
  KeyboardAvoidingView,
  ScrollView,
  Platform,
  Pressable,
  TextInput,
} from "react-native";
import { useRouter, Stack } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Ionicons } from "@expo/vector-icons";
import Animated, { FadeInDown } from "react-native-reanimated";

import {
  BG_PAGE,
  TEXT_PRIMARY,
  TEXT_SECONDARY,
  ERROR_DARK,
  ERROR_BG,
} from "../../constants/colors";
import { AUTH_ENDPOINTS, AUTH_VALIDATION } from "../../constants/config";
import { apiFetch, ApiError } from "../../lib/api";
import { storeJwt, storeRefreshToken } from "../../lib/auth";
import { useAuth } from "../../lib/auth-context";
import { AuthInput } from "../../components/auth/AuthInput";
import { SocialLoginButtons } from "../../components/auth/SocialLoginButtons";
import { useSocialAuth } from "../../hooks/useSocialAuth";
import type { LoginResponse } from "../../components/auth/types";

// Futuristic UI components
import { HeroBackground } from "../../components/ui/HeroBackground";
import { BrandLabel } from "../../components/ui/BrandLabel";
import { GlowButton } from "../../components/ui/GlowButton";
import { useTheme } from "../../lib/theme-context";
import { FONTS } from "../../hooks/useFonts";

interface FieldErrors {
  email?: string;
  password?: string;
  general?: string;
}

export default function LoginScreen() {
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const { setAuthenticated, setUsername } = useAuth();
  const { theme } = useTheme();

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [errors, setErrors] = useState<FieldErrors>({});
  const [isLoading, setIsLoading] = useState(false);

  const {
    isSocialLoading,
    socialError,
    handleGoogleLogin,
    handleAppleLogin,
    clearSocialError,
  } = useSocialAuth();

  // Surface social auth errors into the general error field
  useEffect(() => {
    if (socialError) {
      setErrors({ general: socialError });
      clearSocialError();
    }
  }, [socialError, clearSocialError]);

  const emailRef = useRef<TextInput>(null);
  const passwordRef = useRef<TextInput>(null);

  const validate = useCallback((): boolean => {
    const fieldErrors: FieldErrors = {};

    if (!email.trim()) {
      fieldErrors.email = "Email is required";
    } else if (!AUTH_VALIDATION.EMAIL_PATTERN.test(email.trim())) {
      fieldErrors.email = "Enter a valid email address";
    }

    if (!password) {
      fieldErrors.password = "Password is required";
    }

    setErrors(fieldErrors);

    if (fieldErrors.email) {
      emailRef.current?.focus();
    } else if (fieldErrors.password) {
      passwordRef.current?.focus();
    }

    return Object.keys(fieldErrors).length === 0;
  }, [email, password]);

  /**
   * After storing the JWT, fetch the user's profile via GET /v1/auth/me.
   */
  const resolveUsername = useCallback(async () => {
    try {
      const me = await apiFetch<{ username: string }>("/v1/auth/me");
      if (me?.username) {
        setUsername(me.username);
      }
    } catch {
      // /me failed — username stays null, profile screen will handle it
    }
  }, [setUsername]);

  const handleLogin = useCallback(async () => {
    if (!validate()) return;

    setIsLoading(true);
    setErrors({});

    try {
      const response = await apiFetch<LoginResponse>(AUTH_ENDPOINTS.EMAIL_LOGIN, {
        method: "POST",
        body: JSON.stringify({
          email: email.trim(),
          password,
        }),
      });

      await storeJwt(response.access_token);
      if (response.refresh_token) {
        await storeRefreshToken(response.refresh_token);
      }

      // Resolve username before marking authenticated so profile can load immediately
      await resolveUsername();

      setAuthenticated(true);
    } catch (err) {
      if (err instanceof ApiError) {
        if (err.status === 401) {
          setErrors({ general: "Invalid email or password" });
        } else if (err.status === 422) {
          setErrors({ general: "Please check your input and try again" });
        } else {
          setErrors({ general: "Something went wrong. Please try again." });
        }
      } else {
        setErrors({ general: "Unable to connect. Check your internet connection." });
      }
    } finally {
      setIsLoading(false);
    }
  }, [email, password, validate, resolveUsername, setAuthenticated]);

  const isAnyLoading = isLoading || isSocialLoading;

  return (
    <>
      <Stack.Screen options={{ headerShown: false }} />
      <KeyboardAvoidingView
        style={styles.flex}
        behavior={Platform.OS === "ios" ? "padding" : "height"}
        keyboardVerticalOffset={Platform.OS === "ios" ? 0 : 20}
      >
        {/* Full-bleed hero portrait -- the face IS the visual, no particles needed */}
        <HeroBackground />

        <ScrollView
          contentContainerStyle={[
            styles.scrollContent,
            {
              paddingTop: insets.top + 16,
              paddingBottom: insets.bottom + 24,
            },
          ]}
          keyboardShouldPersistTaps="handled"
          showsVerticalScrollIndicator={false}
        >
          {/* Tiny brand label -- top-left like card-web fashion label */}
          <BrandLabel />

          {/* Spacer pushes all content to the bottom half of the viewport */}
          <View style={styles.spacer} />

          {/* Hero headline -- matches card-web "Your style, elevated." layout */}
          <Animated.View entering={FadeInDown.duration(800).springify().damping(15)}>
            <Text style={styles.heroTitle}>{"Welcome\nback,"}</Text>
            <Text style={[styles.heroAccent, { color: theme.accent }]}>
              to your glow-up
            </Text>
          </Animated.View>

          {/* Subtitle */}
          <Animated.View entering={FadeInDown.delay(150).duration(800).springify().damping(15)}>
            <Text style={styles.subtitle}>Log in to your account</Text>
          </Animated.View>

          {/* General error */}
          {errors.general ? (
            <View style={styles.generalError} accessibilityRole="alert">
              <Ionicons name="alert-circle" size={18} color={ERROR_DARK} />
              <Text style={styles.generalErrorText}>{errors.general}</Text>
            </View>
          ) : null}

          {/* Frosted form inputs */}
          <Animated.View
            entering={FadeInDown.delay(300).duration(800).springify().damping(15)}
            style={styles.form}
          >
            <View style={styles.inputCard}>
              <AuthInput
                ref={emailRef}
                label="Email"
                value={email}
                onChangeText={setEmail}
                error={errors.email}
                keyboardType="email-address"
                autoCapitalize="none"
                autoComplete="email"
                textContentType="emailAddress"
                returnKeyType="next"
                onSubmitEditing={() => passwordRef.current?.focus()}
                editable={!isAnyLoading}
              />
            </View>
            <View style={styles.inputCard}>
              <AuthInput
                ref={passwordRef}
                label="Password"
                value={password}
                onChangeText={setPassword}
                error={errors.password}
                isPassword
                autoCapitalize="none"
                autoComplete="password"
                textContentType="password"
                returnKeyType="done"
                onSubmitEditing={handleLogin}
                editable={!isAnyLoading}
              />
            </View>
          </Animated.View>

          {/* Full-width pill CTA -- accent follows session theme */}
          <Animated.View entering={FadeInDown.delay(450).duration(800).springify().damping(15)}>
            <View style={styles.ctaWrapper}>
              <GlowButton
                title="Log in"
                onPress={handleLogin}
                isLoading={isLoading}
                disabled={isSocialLoading}
                glowColor={theme.accent}
                size="large"
              />
            </View>
          </Animated.View>

          {/* Social login + switch link */}
          <Animated.View entering={FadeInDown.delay(600).duration(800).springify().damping(15)}>
            <SocialLoginButtons
              onGooglePress={handleGoogleLogin}
              onApplePress={handleAppleLogin}
              disabled={isAnyLoading}
            />

            {/* Signup link */}
            <View style={styles.switchRow}>
              <Text style={styles.switchText}>{"Don\u2019t have an account? "}</Text>
              <Pressable
                onPress={() => router.push("/(auth)/signup")}
                disabled={isAnyLoading}
                accessibilityLabel="Sign up"
                accessibilityRole="link"
              >
                <Text
                  style={[
                    styles.switchLink,
                    { color: theme.accent, textDecorationColor: theme.accent + "4D" },
                  ]}
                >
                  Sign up
                </Text>
              </Pressable>
            </View>
          </Animated.View>
        </ScrollView>
      </KeyboardAvoidingView>
    </>
  );
}

const styles = StyleSheet.create({
  flex: {
    flex: 1,
    backgroundColor: "transparent",
  },
  scrollContent: {
    flexGrow: 1,
    paddingHorizontal: 24,
    justifyContent: "flex-end" as const,
  },
  /* ---- Tiny brand label -- top-left like card-web ---- */
  brandLabel: {
    fontFamily: FONTS.bodyMedium,
    fontSize: 11,
    letterSpacing: 4,
    color: "rgba(255, 255, 255, 0.7)",
    textTransform: "uppercase" as const,
  },
  /* ---- Spacer pushes content to the bottom half ---- */
  spacer: {
    flex: 1,
    minHeight: 200,
  },
  /* ---- Hero headline -- Instrument Serif 48px, left-aligned ---- */
  heroTitle: {
    fontFamily: FONTS.display,
    fontSize: 48,
    lineHeight: 52,
    color: "#ffffff",
    letterSpacing: -0.5,
    textShadowColor: "rgba(0, 0, 0, 0.5)",
    textShadowOffset: { width: 0, height: 2 },
    textShadowRadius: 8,
  },
  heroAccent: {
    fontFamily: FONTS.displayItalic,
    fontSize: 48,
    lineHeight: 52,
    letterSpacing: -0.5,
    marginBottom: 12,
  },
  /* ---- Subtitle -- readable on any background ---- */
  subtitle: {
    fontFamily: FONTS.body,
    fontSize: 15,
    color: "#e8e8e8",
    marginBottom: 24,
    textShadowColor: "rgba(0, 0, 0, 0.7)",
    textShadowOffset: { width: 0, height: 1 },
    textShadowRadius: 4,
  },
  /* ---- Error banner ---- */
  generalError: {
    flexDirection: "row",
    alignItems: "center",
    gap: 8,
    backgroundColor: ERROR_BG,
    borderRadius: 12,
    padding: 12,
    marginBottom: 16,
  },
  generalErrorText: {
    fontSize: 14,
    color: ERROR_DARK,
    flex: 1,
  },
  /* ---- Form area ---- */
  form: {
    marginBottom: 16,
  },
  inputCard: {
    backgroundColor: "rgba(8, 8, 8, 0.78)",
    borderRadius: 16,
    paddingHorizontal: 16,
    paddingTop: 12,
    paddingBottom: 0,
    marginBottom: 12,
    borderWidth: 1,
    borderColor: "rgba(255, 255, 255, 0.06)",
  },
  /* ---- CTA wrapper ---- */
  ctaWrapper: {
    marginTop: 8,
    marginBottom: 4,
    borderRadius: 9999,
    overflow: "hidden",
  },
  /* ---- Switch row -- login/signup toggle ---- */
  switchRow: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    marginTop: 16,
    minHeight: 44,
  },
  switchText: {
    fontFamily: FONTS.body,
    fontSize: 15,
    color: "#e8e8e8",
    textShadowColor: "rgba(0, 0, 0, 0.7)",
    textShadowOffset: { width: 0, height: 1 },
    textShadowRadius: 4,
  },
  switchLink: {
    fontFamily: FONTS.bodySemiBold,
    fontSize: 15,
    textDecorationLine: "underline" as const,
  },
});
