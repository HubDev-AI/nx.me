import { useState, useCallback, useEffect, useRef } from "react";
import {
  View,
  Text,
  StyleSheet,
  KeyboardAvoidingView,
  ScrollView,
  Platform,
  Pressable,
  Linking,
  TextInput,
} from "react-native";
import { useRouter, useLocalSearchParams, Stack } from "expo-router";
import * as WebBrowser from "expo-web-browser";
import { useAuthRequest, makeRedirectUri } from "expo-auth-session";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Ionicons } from "@expo/vector-icons";

import {
  BG_PAGE,
  BG_CARD,
  TEXT_PRIMARY,
  TEXT_SECONDARY,
  CTA_PRIMARY,
  BORDER_DEFAULT,
} from "../../constants/colors";
import {
  AUTH_ENDPOINTS,
  AUTH_VALIDATION,
  GOOGLE_CLIENT_ID,
  APPLE_CLIENT_ID,
} from "../../constants/config";
import { apiFetch, ApiError } from "../../lib/api";
import { storeJwt } from "../../lib/auth";
import { AuthInput } from "../../components/auth/AuthInput";
import { AuthButton } from "../../components/auth/AuthButton";

WebBrowser.maybeCompleteAuthSession();

const GOOGLE_DISCOVERY = {
  authorizationEndpoint: "https://accounts.google.com/o/oauth2/v2/auth",
  tokenEndpoint: "https://oauth2.googleapis.com/token",
};

const APPLE_DISCOVERY = {
  authorizationEndpoint: "https://appleid.apple.com/auth/authorize",
  tokenEndpoint: "https://appleid.apple.com/auth/token",
};

type ScreenState = "form" | "verification";

interface RegisterResponse {
  message: string;
  email: string;
}

interface LoginResponse {
  access_token: string;
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
  const { card } = useLocalSearchParams<{ card?: string }>();

  const [screenState, setScreenState] = useState<ScreenState>("form");
  const [username, setUsername] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [errors, setErrors] = useState<FieldErrors>({});
  const [isLoading, setIsLoading] = useState(false);
  const [isSocialLoading, setIsSocialLoading] = useState(false);

  const usernameRef = useRef<TextInput>(null);
  const displayNameRef = useRef<TextInput>(null);
  const emailRef = useRef<TextInput>(null);
  const passwordRef = useRef<TextInput>(null);
  const confirmPasswordRef = useRef<TextInput>(null);

  // Social auth setup
  const redirectUri = makeRedirectUri({
    scheme: "https",
    path: "auth/callback",
  });

  const [googleRequest, googleResponse, googlePromptAsync] = useAuthRequest(
    {
      clientId: GOOGLE_CLIENT_ID,
      scopes: ["openid", "email", "profile"],
      redirectUri,
      usePKCE: true,
    },
    GOOGLE_DISCOVERY,
  );

  const [appleRequest, appleResponse, applePromptAsync] = useAuthRequest(
    {
      clientId: APPLE_CLIENT_ID,
      scopes: ["openid", "email", "name"],
      redirectUri,
      usePKCE: true,
    },
    APPLE_DISCOVERY,
  );

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

  const handleSocialAuth = useCallback(
    async (provider: "google" | "apple", code: string) => {
      setIsSocialLoading(true);
      setErrors({});

      try {
        const response = await apiFetch<LoginResponse>(
          AUTH_ENDPOINTS.SOCIAL_LOGIN,
          {
            method: "POST",
            body: JSON.stringify({ provider, code, redirect_uri: redirectUri }),
          },
        );

        await storeJwt(response.access_token);
        router.replace("/(tabs)");
      } catch (err) {
        if (err instanceof ApiError) {
          setErrors({ general: "Social signup failed. Please try again." });
        } else {
          setErrors({
            general: "Unable to connect. Check your internet connection.",
          });
        }
      } finally {
        setIsSocialLoading(false);
      }
    },
    [redirectUri, router],
  );

  // Handle social auth responses
  useEffect(() => {
    if (googleResponse?.type === "success" && googleResponse.params.code) {
      handleSocialAuth("google", googleResponse.params.code);
    }
  }, [googleResponse, handleSocialAuth]);

  useEffect(() => {
    if (appleResponse?.type === "success" && appleResponse.params.code) {
      handleSocialAuth("apple", appleResponse.params.code);
    }
  }, [appleResponse, handleSocialAuth]);

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
      // Silently ignore — verification email may have been sent regardless
    } finally {
      setIsLoading(false);
    }
  }, [username, email, password, displayName]);

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
            <Ionicons name="mail-outline" size={48} color={CTA_PRIMARY} />
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
      <KeyboardAvoidingView
        style={styles.flex}
        behavior={Platform.OS === "ios" ? "padding" : "height"}
        keyboardVerticalOffset={Platform.OS === "ios" ? 0 : 20}
      >
        <ScrollView
          contentContainerStyle={[
            styles.scrollContent,
            {
              paddingTop: insets.top + 48,
              paddingBottom: insets.bottom + 24,
            },
          ]}
          keyboardShouldPersistTaps="handled"
          showsVerticalScrollIndicator={false}
        >
          {/* Logo / Wordmark */}
          <Text style={styles.logo} accessibilityRole="header">
            NXME
          </Text>

          {/* Header */}
          <Text style={styles.title}>Create your account</Text>
          <Text style={styles.subtitle}>
            {card
              ? `Invited via @${card}'s card`
              : "Start your glow-up journey"}
          </Text>

          {/* General error */}
          {errors.general ? (
            <View style={styles.generalError} accessibilityRole="alert">
              <Ionicons name="alert-circle" size={18} color="#F87171" />
              <Text style={styles.generalErrorText}>{errors.general}</Text>
            </View>
          ) : null}

          {/* Form */}
          <View style={styles.form}>
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
            <AuthInput
              ref={passwordRef}
              label="Password"
              value={password}
              onChangeText={setPassword}
              error={errors.password}
              isPassword
              autoCapitalize="none"
              autoComplete="password-new"
              textContentType="newPassword"
              returnKeyType="next"
              onSubmitEditing={() => confirmPasswordRef.current?.focus()}
              editable={!isAnyLoading}
            />
            <AuthInput
              ref={confirmPasswordRef}
              label="Confirm password"
              value={confirmPassword}
              onChangeText={setConfirmPassword}
              error={errors.confirmPassword}
              isPassword
              autoCapitalize="none"
              autoComplete="password-new"
              textContentType="newPassword"
              returnKeyType="done"
              onSubmitEditing={handleSignup}
              editable={!isAnyLoading}
            />
          </View>

          {/* CTA */}
          <AuthButton
            title="Create account"
            onPress={handleSignup}
            isLoading={isLoading}
            disabled={isSocialLoading}
          />

          {/* Social login divider + buttons */}
          <View style={styles.dividerRow}>
            <View style={styles.dividerLine} />
            <Text style={styles.dividerText}>or</Text>
            <View style={styles.dividerLine} />
          </View>

          <Pressable
            onPress={() => googlePromptAsync()}
            disabled={isAnyLoading || !googleRequest}
            style={({ pressed }) => [
              styles.socialButton,
              styles.googleButton,
              pressed && styles.socialButtonPressed,
              (isAnyLoading || !googleRequest) && styles.socialButtonDisabled,
            ]}
            accessibilityLabel="Continue with Google"
            accessibilityRole="button"
          >
            <Ionicons name="logo-google" size={20} color="#4285F4" />
            <Text style={styles.googleText}>Continue with Google</Text>
          </Pressable>

          {Platform.OS === "ios" ? (
            <Pressable
              onPress={() => applePromptAsync()}
              disabled={isAnyLoading || !appleRequest}
              style={({ pressed }) => [
                styles.socialButton,
                styles.appleButton,
                pressed && styles.socialButtonPressed,
                (isAnyLoading || !appleRequest) && styles.socialButtonDisabled,
              ]}
              accessibilityLabel="Continue with Apple"
              accessibilityRole="button"
            >
              <Ionicons name="logo-apple" size={20} color="#FFFFFF" />
              <Text style={styles.appleText}>Continue with Apple</Text>
            </Pressable>
          ) : null}

          {/* Login link */}
          <View style={styles.switchRow}>
            <Text style={styles.switchText}>Already have an account? </Text>
            <Pressable
              onPress={() => router.push("/(auth)/login")}
              disabled={isAnyLoading}
              accessibilityLabel="Log in"
              accessibilityRole="link"
            >
              <Text style={styles.switchLink}>Log in</Text>
            </Pressable>
          </View>
        </ScrollView>
      </KeyboardAvoidingView>
    </>
  );
}

const styles = StyleSheet.create({
  flex: {
    flex: 1,
    backgroundColor: BG_PAGE,
  },
  scrollContent: {
    flexGrow: 1,
    paddingHorizontal: 24,
  },
  logo: {
    fontSize: 28,
    fontWeight: "800",
    color: TEXT_PRIMARY,
    textAlign: "center",
    letterSpacing: 2,
    marginBottom: 32,
  },
  title: {
    fontSize: 24,
    fontWeight: "700",
    color: TEXT_PRIMARY,
    marginBottom: 4,
  },
  subtitle: {
    fontSize: 16,
    color: TEXT_SECONDARY,
    marginBottom: 24,
  },
  generalError: {
    flexDirection: "row",
    alignItems: "center",
    gap: 8,
    backgroundColor: "rgba(248, 113, 113, 0.1)",
    borderRadius: 8,
    padding: 12,
    marginBottom: 16,
  },
  generalErrorText: {
    fontSize: 14,
    color: "#F87171",
    flex: 1,
  },
  form: {
    marginBottom: 8,
  },
  dividerRow: {
    flexDirection: "row",
    alignItems: "center",
    marginVertical: 20,
  },
  dividerLine: {
    flex: 1,
    height: StyleSheet.hairlineWidth,
    backgroundColor: BORDER_DEFAULT,
  },
  dividerText: {
    fontSize: 14,
    color: TEXT_SECONDARY,
    marginHorizontal: 16,
  },
  socialButton: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    minHeight: 48,
    borderRadius: 12,
    borderWidth: 1,
    paddingHorizontal: 16,
    gap: 10,
    marginBottom: 12,
  },
  socialButtonPressed: {
    opacity: 0.8,
  },
  socialButtonDisabled: {
    opacity: 0.5,
  },
  googleButton: {
    backgroundColor: "#FFFFFF",
    borderColor: "#DADCE0",
  },
  googleText: {
    fontSize: 16,
    fontWeight: "600",
    color: "#1F1F1F",
  },
  appleButton: {
    backgroundColor: "#000000",
    borderColor: "#000000",
  },
  appleText: {
    fontSize: 16,
    fontWeight: "600",
    color: "#FFFFFF",
  },
  switchRow: {
    flexDirection: "row",
    justifyContent: "center",
    alignItems: "center",
    marginTop: 16,
    minHeight: 44,
  },
  switchText: {
    fontSize: 16,
    color: TEXT_SECONDARY,
  },
  switchLink: {
    fontSize: 16,
    fontWeight: "600",
    color: CTA_PRIMARY,
  },
  // Verification screen styles
  verificationContainer: {
    flex: 1,
    backgroundColor: BG_PAGE,
    paddingHorizontal: 24,
    alignItems: "center",
  },
  verificationIconWrapper: {
    width: 80,
    height: 80,
    borderRadius: 40,
    backgroundColor: BG_CARD,
    alignItems: "center",
    justifyContent: "center",
    marginBottom: 24,
  },
  verificationTitle: {
    fontSize: 24,
    fontWeight: "700",
    color: TEXT_PRIMARY,
    marginBottom: 8,
    textAlign: "center",
  },
  verificationSubtitle: {
    fontSize: 16,
    color: TEXT_SECONDARY,
    textAlign: "center",
  },
  verificationEmail: {
    fontSize: 16,
    fontWeight: "600",
    color: TEXT_PRIMARY,
    textAlign: "center",
    marginBottom: 32,
  },
  verificationActions: {
    width: "100%",
    gap: 12,
  },
  textButton: {
    minHeight: 44,
    alignItems: "center",
    justifyContent: "center",
  },
  textButtonLabel: {
    fontSize: 16,
    fontWeight: "600",
    color: CTA_PRIMARY,
  },
});
