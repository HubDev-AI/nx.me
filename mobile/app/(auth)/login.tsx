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

import {
  BG_PAGE,
  TEXT_PRIMARY,
  TEXT_SECONDARY,
  CTA_PRIMARY,
  ERROR_DARK,
  ERROR_BG,
} from "../../constants/colors";
import { AUTH_ENDPOINTS, AUTH_VALIDATION } from "../../constants/config";
import { apiFetch, ApiError } from "../../lib/api";
import { storeJwt, storeRefreshToken } from "../../lib/auth";
import { useAuth } from "../../lib/auth-context";
import { AuthInput } from "../../components/auth/AuthInput";
import { AuthButton } from "../../components/auth/AuthButton";
import { SocialLoginButtons } from "../../components/auth/SocialLoginButtons";
import { useSocialAuth } from "../../hooks/useSocialAuth";
import type { LoginResponse } from "../../components/auth/types";

interface FieldErrors {
  email?: string;
  password?: string;
  general?: string;
}

export default function LoginScreen() {
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const { setAuthenticated } = useAuth();

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
  }, [email, password, validate, router]);

  const isAnyLoading = isLoading || isSocialLoading;

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
          <Text style={styles.title}>Welcome back</Text>
          <Text style={styles.subtitle}>Log in to your account</Text>

          {/* General error */}
          {errors.general ? (
            <View style={styles.generalError} accessibilityRole="alert">
              <Ionicons name="alert-circle" size={18} color={ERROR_DARK} />
              <Text style={styles.generalErrorText}>{errors.general}</Text>
            </View>
          ) : null}

          {/* Form */}
          <View style={styles.form}>
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
              autoComplete="password"
              textContentType="password"
              returnKeyType="done"
              onSubmitEditing={handleLogin}
              editable={!isAnyLoading}
            />
          </View>

          {/* CTA */}
          <AuthButton
            title="Log in"
            onPress={handleLogin}
            isLoading={isLoading}
            disabled={isSocialLoading}
          />

          {/* Social login divider + buttons */}
          <SocialLoginButtons
            onGooglePress={handleGoogleLogin}
            onApplePress={handleAppleLogin}
            disabled={isAnyLoading}
          />

          {/* Signup link */}
          <View style={styles.switchRow}>
            <Text style={styles.switchText}>Don't have an account? </Text>
            <Pressable
              onPress={() => router.push("/(auth)/signup")}
              disabled={isAnyLoading}
              accessibilityLabel="Sign up"
              accessibilityRole="link"
            >
              <Text style={styles.switchLink}>Sign up</Text>
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
    backgroundColor: ERROR_BG,
    borderRadius: 8,
    padding: 12,
    marginBottom: 16,
  },
  generalErrorText: {
    fontSize: 14,
    color: ERROR_DARK,
    flex: 1,
  },
  form: {
    marginBottom: 8,
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
});
