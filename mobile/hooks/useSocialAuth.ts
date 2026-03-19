/**
 * Shared hook for social login (Google / Apple) used by both login and signup screens.
 *
 * Handles:
 * - Calling the native social SDK
 * - Sending the id_token to the backend
 * - Storing the JWT + refresh token
 * - Navigating to the main tabs on success
 */
import { useState, useCallback } from "react";
import { useRouter } from "expo-router";

import { apiFetch, ApiError } from "../lib/api";
import { storeJwt, storeRefreshToken } from "../lib/auth";
import { signInWithGoogle, signInWithApple } from "../lib/social-auth";
import { AUTH_ENDPOINTS } from "../constants/config";
import type { LoginResponse } from "../components/auth/types";

interface UseSocialAuthReturn {
  isSocialLoading: boolean;
  socialError: string | null;
  handleGoogleLogin: () => Promise<void>;
  handleAppleLogin: () => Promise<void>;
  clearSocialError: () => void;
}

export function useSocialAuth(): UseSocialAuthReturn {
  const router = useRouter();
  const [isSocialLoading, setIsSocialLoading] = useState(false);
  const [socialError, setSocialError] = useState<string | null>(null);

  const handleSocialLogin = useCallback(
    async (provider: "google" | "apple", idToken: string, nonce?: string) => {
      setIsSocialLoading(true);
      setSocialError(null);

      try {
        const body: Record<string, string> = { provider, id_token: idToken };
        if (nonce) {
          body.nonce = nonce;
        }

        const response = await apiFetch<LoginResponse>(
          AUTH_ENDPOINTS.SOCIAL_LOGIN,
          {
            method: "POST",
            body: JSON.stringify(body),
          },
        );

        await storeJwt(response.access_token);
        if (response.refresh_token) {
          await storeRefreshToken(response.refresh_token);
        }
        router.replace("/(tabs)");
      } catch (err) {
        if (err instanceof ApiError) {
          setSocialError("Social login failed. Please try again.");
        } else {
          setSocialError("Unable to connect. Check your internet connection.");
        }
      } finally {
        setIsSocialLoading(false);
      }
    },
    [router],
  );

  const handleGoogleLogin = useCallback(async () => {
    try {
      const result = await signInWithGoogle();
      if (result) {
        await handleSocialLogin("google", result.idToken);
      }
    } catch {
      setSocialError("Google sign-in failed. Please try again.");
    }
  }, [handleSocialLogin]);

  const handleAppleLogin = useCallback(async () => {
    try {
      const result = await signInWithApple();
      if (result) {
        await handleSocialLogin("apple", result.idToken, result.nonce);
      }
    } catch {
      setSocialError("Apple sign-in failed. Please try again.");
    }
  }, [handleSocialLogin]);

  const clearSocialError = useCallback(() => {
    setSocialError(null);
  }, []);

  return {
    isSocialLoading,
    socialError,
    handleGoogleLogin,
    handleAppleLogin,
    clearSocialError,
  };
}
