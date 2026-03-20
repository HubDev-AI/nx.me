import { useState, useCallback, useRef, useEffect } from "react";
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  Platform,
  Pressable,
  Linking,
  TextInput,
} from "react-native";
import { useRouter, useLocalSearchParams, Stack } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Ionicons } from "@expo/vector-icons";
import Animated, { FadeInDown } from "react-native-reanimated";

// Error feedback colors from THEME
import { THEME } from "../../constants/theme";
import { AUTH_ENDPOINTS, AUTH_VALIDATION, SECURE_STORE_KEYS } from "../../constants/config";
import { setItem } from "../../lib/secure-storage";
import { apiFetch, ApiError } from "../../lib/api";
import { AuthInput } from "../../components/auth/AuthInput";
import { AuthButton } from "../../components/auth/AuthButton";
import { SocialLoginButtons } from "../../components/auth/SocialLoginButtons";
import { useSocialAuth } from "../../hooks/useSocialAuth";
import { useAuth } from "../../lib/auth-context";

// Futuristic UI components
import { HeroBackground } from "../../components/ui/HeroBackground";
import { BrandLabel } from "../../components/ui/BrandLabel";
import { GlowButton } from "../../components/ui/GlowButton";
import { useTheme } from "../../lib/theme-context";
import { FONTS } from "../../hooks/useFonts";

type ScreenState = "form" | "verification";

interface RegisterResponse {
  message: string;
  email: string;
}

interface FieldErrors {
  username?: string;
  displayName?: string;
  email?: string;
  password?: string;
  confirmPassword?: string;
  general?: string;
}

export default function SignupScreen() {
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const { setUsername: setAuthUsername } = useAuth();
  const { card: rawCard } = useLocalSearchParams<{ card?: string }>();
  // Validate card param against username pattern before rendering (M-15)
  const card = rawCard && AUTH_VALIDATION.USERNAME_PATTERN.test(rawCard) ? rawCard : undefined;

  const [screenState, setScreenState] = useState<ScreenState>("form");
  const [username, setUsername] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [errors, setErrors] = useState<FieldErrors>({});
  const [isLoading, setIsLoading] = useState(false);

  const {
    isSocialLoading,
    socialError,
    handleGoogleLogin: handleGoogleSignup,
    handleAppleLogin: handleAppleSignup,
    clearSocialError,
  } = useSocialAuth();

  // Surface social auth errors into the general error field
  useEffect(() => {
    if (socialError) {
      setErrors({ general: socialError });
      clearSocialError();
    }
  }, [socialError, clearSocialError]);

  const usernameRef = useRef<TextInput>(null);
  const displayNameRef = useRef<TextInput>(null);
  const emailRef = useRef<TextInput>(null);
  const passwordRef = useRef<TextInput>(null);
  const confirmPasswordRef = useRef<TextInput>(null);

  const validate = useCallback((): boolean => {
    const fieldErrors: FieldErrors = {};

    // Username
    if (!username.trim()) {
      fieldErrors.username = "Username is required";
    } else if (username.trim().length < AUTH_VALIDATION.USERNAME_MIN_LENGTH) {
      fieldErrors.username = `Username must be at least ${AUTH_VALIDATION.USERNAME_MIN_LENGTH} characters`;
    } else if (username.trim().length > AUTH_VALIDATION.USERNAME_MAX_LENGTH) {
      fieldErrors.username = `Username must be at most ${AUTH_VALIDATION.USERNAME_MAX_LENGTH} characters`;
    } else if (!AUTH_VALIDATION.USERNAME_PATTERN.test(username.trim())) {
      fieldErrors.username =
        "Username must start with a letter and contain only letters, numbers, and underscores";
    }

    // Display name
    if (!displayName.trim()) {
      fieldErrors.displayName = "Display name is required";
    }

    // Email
    if (!email.trim()) {
      fieldErrors.email = "Email is required";
    } else if (!AUTH_VALIDATION.EMAIL_PATTERN.test(email.trim())) {
      fieldErrors.email = "Enter a valid email address";
    }

    // Password
    if (!password) {
      fieldErrors.password = "Password is required";
    } else if (password.length < AUTH_VALIDATION.PASSWORD_MIN_LENGTH) {
      fieldErrors.password = `Password must be at least ${AUTH_VALIDATION.PASSWORD_MIN_LENGTH} characters`;
    }

    // Confirm password
    if (!confirmPassword) {
      fieldErrors.confirmPassword = "Please confirm your password";
    } else if (password !== confirmPassword) {
      fieldErrors.confirmPassword = "Passwords do not match";
    }

    setErrors(fieldErrors);

    // Focus first invalid field
    if (fieldErrors.username) {
      usernameRef.current?.focus();
    } else if (fieldErrors.displayName) {
      displayNameRef.current?.focus();
    } else if (fieldErrors.email) {
      emailRef.current?.focus();
    } else if (fieldErrors.password) {
      passwordRef.current?.focus();
    } else if (fieldErrors.confirmPassword) {
      confirmPasswordRef.current?.focus();
    }

    return Object.keys(fieldErrors).length === 0;
  }, [username, displayName, email, password, confirmPassword]);

  const handleSignup = useCallback(async () => {
    if (!validate()) return;

    setIsLoading(true);
    setErrors({});

    try {
      await apiFetch<RegisterResponse>(AUTH_ENDPOINTS.REGISTER, {
        method: "POST",
        body: JSON.stringify({
          username: username.trim(),
          email: email.trim(),
          password,
          display_name: displayName.trim(),
        }),
      });

      // Persist the username so login can resolve it later
      setAuthUsername(username.trim());

      // Mark email verification as pending so the feed shows a reminder banner
      setItem(SECURE_STORE_KEYS.PENDING_EMAIL_VERIFICATION, "1").catch(() => {});

      setScreenState("verification");
    } catch (err) {
      if (err instanceof ApiError) {
        if (err.status === 409) {
          // Try to parse body for specific conflict field
          try {
            const body = JSON.parse(err.body);
            if (body.detail?.includes("email")) {
              setErrors({ email: "An account with this email already exists" });
              emailRef.current?.focus();
            } else if (body.detail?.includes("username")) {
              setErrors({ username: "This username is already taken" });
              usernameRef.current?.focus();
            } else {
              setErrors({ general: "An account with these details already exists" });
            }
          } catch {
            setErrors({ general: "An account with these details already exists" });
          }
        } else if (err.status === 422) {
          setErrors({ general: "Please check your input and try again" });
        } else {
          setErrors({ general: "Something went wrong. Please try again." });
        }
      } else {
        setErrors({
          general: "Unable to connect. Check your internet connection.",
        });
      }
    } finally {
      setIsLoading(false);
    }
  }, [username, displayName, email, password, validate]);

  const handleOpenEmailApp = useCallback(async () => {
    // On iOS, opens mail app; on Android, opens chooser
    if (Platform.OS === "ios") {
      await Linking.openURL("message://");
    } else {
      await Linking.openURL("mailto:");
    }
  }, []);

  const handleVerified = useCallback(() => {
    // Navigate to login so user can sign in with verified account
    router.replace("/(auth)/login");
  }, [router]);

  const handleResendEmail = useCallback(async () => {
    // Re-submit registration to trigger another verification email
    setIsLoading(true);
    try {
      await apiFetch(AUTH_ENDPOINTS.REGISTER, {
        method: "POST",
        body: JSON.stringify({
          username: username.trim(),
          email: email.trim(),
          password,
          display_name: displayName.trim(),
        }),
      });
    } catch {
      // Silently ignore -- verification email may have been sent regardless
    } finally {
      setIsLoading(false);
    }
  }, [username, email, password, displayName]);

  const { theme } = useTheme();
  const isAnyLoading = isLoading || isSocialLoading;

  // Email verification prompt screen
  if (screenState === "verification") {
    return (
      <>
        <Stack.Screen options={{ headerShown: false }} />
        <View
          style={[
            styles.verificationContainer,
            {
              paddingTop: insets.top + 80,
              paddingBottom: insets.bottom + 24,
            },
          ]}
        >
          <View style={styles.verificationIconWrapper}>
            <Ionicons name="mail-outline" size={48} color={theme.accent} />
          </View>

          <Text style={styles.verificationTitle}>Check your email</Text>
          <Text style={styles.verificationSubtitle}>
            We sent a verification link to
          </Text>
          <Text style={styles.verificationEmail}>{email.trim()}</Text>

          <View style={styles.verificationActions}>
            <AuthButton
              title="Open email app"
              onPress={handleOpenEmailApp}
              isLoading={false}
            />

            <Pressable
              onPress={handleResendEmail}
              disabled={isLoading}
              style={styles.textButton}
              accessibilityLabel="Resend verification email"
              accessibilityRole="button"
            >
              <Text style={styles.textButtonLabel}>Resend email</Text>
            </Pressable>

            <Pressable
              onPress={handleVerified}
              style={styles.textButton}
              accessibilityLabel="I have verified my email"
              accessibilityRole="button"
            >
              <Text style={styles.textButtonLabel}>
                I've verified my email
              </Text>
            </Pressable>
          </View>
        </View>
      </>
    );
  }

  // Signup form screen
  return (
    <>
      <Stack.Screen options={{ headerShown: false }} />
      <View style={styles.flex}>
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
          keyboardDismissMode="interactive"
          showsVerticalScrollIndicator={false}
          automaticallyAdjustKeyboardInsets
        >
          {/* Tiny brand label -- top-left like card-web fashion label */}
          <BrandLabel />

          {/* Spacer pushes all content to the bottom half of the viewport */}
          <View style={styles.spacer} />

          {/* Hero headline -- matches card-web layout: large serif + italic accent */}
          <Animated.View entering={FadeInDown.duration(800).springify().damping(15)}>
            <Text style={styles.heroTitle}>{"Create your\naccount,"}</Text>
            <Text style={[styles.heroAccent, { color: theme.accent }]}>
              {card ? `invited by @${card}` : "start your glow-up"}
            </Text>
          </Animated.View>

          {/* Subtitle */}
          <Animated.View entering={FadeInDown.delay(150).duration(800).springify().damping(15)}>
            <Text style={styles.subtitle}>
              {card
                ? `Join via @${card}\u2019s card`
                : "AI-powered style recommendations, just for you"}
            </Text>
          </Animated.View>

          {/* General error */}
          {errors.general ? (
            <View style={styles.generalError} accessibilityRole="alert">
              <Ionicons name="alert-circle" size={18} color={THEME.colors.destructive} />
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
                ref={usernameRef}
                label="Username"
                value={username}
                onChangeText={setUsername}
                error={errors.username}
                autoCapitalize="none"
                autoComplete="username-new"
                textContentType="username"
                returnKeyType="next"
                onSubmitEditing={() => displayNameRef.current?.focus()}
                editable={!isAnyLoading}
              />
            </View>
            <View style={styles.inputCard}>
              <AuthInput
                ref={displayNameRef}
                label="Display name"
                value={displayName}
                onChangeText={setDisplayName}
                error={errors.displayName}
                autoCapitalize="words"
                autoComplete="name"
                textContentType="name"
                returnKeyType="next"
                onSubmitEditing={() => emailRef.current?.focus()}
                editable={!isAnyLoading}
              />
            </View>
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
                autoComplete="off"
                textContentType="oneTimeCode"
                returnKeyType="next"
                onSubmitEditing={() => confirmPasswordRef.current?.focus()}
                editable={!isAnyLoading}
              />
            </View>
            <View style={styles.inputCard}>
              <AuthInput
                ref={confirmPasswordRef}
                label="Confirm password"
                value={confirmPassword}
                onChangeText={setConfirmPassword}
                error={errors.confirmPassword}
                isPassword
                autoCapitalize="none"
                autoComplete="off"
                textContentType="oneTimeCode"
                returnKeyType="done"
                onSubmitEditing={handleSignup}
                editable={!isAnyLoading}
              />
            </View>
          </Animated.View>

          {/* Full-width pill CTA -- accent follows session theme */}
          <Animated.View entering={FadeInDown.delay(450).duration(800).springify().damping(15)}>
            <View style={styles.ctaWrapper}>
              <GlowButton
                title="Create account"
                onPress={handleSignup}
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
              onGooglePress={handleGoogleSignup}
              onApplePress={handleAppleSignup}
              disabled={isAnyLoading}
            />

            {/* Login link */}
            <View style={styles.switchRow}>
              <Text style={styles.switchText}>Already have an account? </Text>
              <Pressable
                onPress={() => router.push("/(auth)/login")}
                disabled={isAnyLoading}
                accessibilityLabel="Log in"
                accessibilityRole="link"
              >
                <Text
                  style={[
                    styles.switchLink,
                    { color: theme.accent, textDecorationColor: theme.accent + "80" },
                  ]}
                >
                  Log in
                </Text>
              </Pressable>
            </View>
          </Animated.View>
        </ScrollView>
      </View>
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
    paddingHorizontal: THEME.spacing.xxl,
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
    minHeight: 120,
  },
  /* ---- Hero headline -- Instrument Serif 48px, left-aligned ---- */
  heroTitle: {
    fontFamily: FONTS.display,
    fontSize: 48,
    lineHeight: 52,
    color: "#ffffff",
    letterSpacing: -0.5,
    textShadowColor: "rgba(0, 0, 0, 0.4)",
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
  /* ---- Subtitle -- small Inter, muted ---- */
  subtitle: {
    fontFamily: FONTS.body,
    fontSize: 15,
    color: "#e8e8e8",
    marginBottom: THEME.spacing.xxl,
    textShadowColor: "rgba(0, 0, 0, 0.7)",
    textShadowOffset: { width: 0, height: 1 },
    textShadowRadius: 4,
  },
  /* ---- Error banner ---- */
  generalError: {
    flexDirection: "row",
    alignItems: "center",
    gap: THEME.spacing.sm,
    backgroundColor: "rgba(239, 68, 68, 0.1)",
    borderRadius: THEME.radius.md,
    padding: THEME.spacing.md,
    marginBottom: THEME.spacing.lg,
  },
  generalErrorText: {
    fontSize: 14,
    color: THEME.colors.destructive,
    flex: 1,
  },
  /* ---- Form area ---- */
  form: {
    marginBottom: THEME.spacing.lg,
  },
  inputCard: {
    backgroundColor: "rgba(8, 8, 8, 0.78)",
    borderRadius: THEME.radius.xl,
    paddingHorizontal: THEME.spacing.lg,
    paddingTop: THEME.spacing.md,
    paddingBottom: 0,
    marginBottom: THEME.spacing.lg,
    borderWidth: 1,
    borderColor: THEME.colors.border,
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: "rgba(255, 255, 255, 0.08)",
  },
  /* ---- CTA wrapper ---- */
  ctaWrapper: {
    marginTop: THEME.spacing.sm,
    marginBottom: THEME.spacing.xs,
    borderRadius: THEME.radius.pill,
    overflow: "hidden",
  },
  /* ---- Switch row -- login/signup toggle ---- */
  switchRow: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    marginTop: THEME.spacing.lg,
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
  /* ---- Verification screen styles (unchanged) ---- */
  verificationContainer: {
    flex: 1,
    backgroundColor: THEME.colors.bg,
    paddingHorizontal: THEME.spacing.xxl,
    alignItems: "center",
  },
  verificationIconWrapper: {
    width: 80,
    height: 80,
    borderRadius: 40,
    backgroundColor: THEME.colors.glass,
    borderWidth: 1,
    borderColor: THEME.colors.glassBorder,
    alignItems: "center",
    justifyContent: "center",
    marginBottom: THEME.spacing.xxl,
  },
  verificationTitle: {
    fontFamily: FONTS.display,
    ...THEME.typography.headingLg,
    color: THEME.colors.textPrimary,
    marginBottom: THEME.spacing.sm,
    textAlign: "center",
  },
  verificationSubtitle: {
    fontFamily: FONTS.body,
    ...THEME.typography.body,
    color: THEME.colors.textSecondary,
    textAlign: "center",
  },
  verificationEmail: {
    fontFamily: FONTS.bodySemiBold,
    ...THEME.typography.body,
    color: THEME.colors.textPrimary,
    textAlign: "center",
    marginBottom: THEME.spacing.xxxl,
  },
  verificationActions: {
    width: "100%",
    gap: THEME.spacing.md,
  },
  textButton: {
    minHeight: 44,
    alignItems: "center",
    justifyContent: "center",
  },
  textButtonLabel: {
    fontFamily: FONTS.bodySemiBold,
    fontSize: 16,
    color: THEME.colors.textSecondary,
  },
});
