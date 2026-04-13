/**
 * Shared hook for social login (Google / Apple / TikTok) used by the auth screen.
 *
 * Handles:
 * - Calling the native social SDK
 * - Sending the id_token (Google/Apple) or auth code (TikTok) to the backend
 * - Storing the JWT + refresh token
 * - Setting authenticated state
 */
import { useState, useCallback } from "react";

import { apiFetch } from "../lib/api";
import { parseApiError, type AppError } from "../lib/errors";
import { storeJwt, storeRefreshToken } from "../lib/auth";
import { useAuth } from "../lib/auth-context";
import { signInWithGoogle, signInWithApple, signInWithTikTok } from "../lib/social-auth";
import { AUTH_ENDPOINTS } from "../constants/config";
import type { LoginResponse } from "../components/auth/types";

interface UseSocialAuthReturn {
  isSocialLoading: boolean;
  socialError: AppError | null;
  handleGoogleLogin: () => Promise<void>;
  handleAppleLogin: () => Promise<void>;
  handleTikTokLogin: () => Promise<void>;
  clearSocialError: () => void;
}

export function useSocialAuth(): UseSocialAuthReturn {
  const { setSessionMode, setUsername } = useAuth();
  const [isSocialLoading, setIsSocialLoading] = useState(false);
  const [socialError, setSocialError] = useState<AppError | null>(null);

  /**
   * Generic handler for Google/Apple — sends id_token to POST /auth/login.
   */
  const handleIdTokenLogin = useCallback(
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
        setUsername(response.username);
        setSessionMode("user");
      } catch (err) {
        setSocialError(parseApiError(err));
      } finally {
        setIsSocialLoading(false);
      }
    },
    [setSessionMode, setUsername],
  );

  const handleGoogleLogin = useCallback(async () => {
    try {
      const result = await signInWithGoogle();
      if (result) {
        await handleIdTokenLogin("google", result.idToken);
      }
    } catch (err) {
      setSocialError(parseApiError(err));
    }
  }, [handleIdTokenLogin]);

  const handleAppleLogin = useCallback(async () => {
    try {
      const result = await signInWithApple();
      if (result) {
        await handleIdTokenLogin("apple", result.idToken, result.nonce);
      }
    } catch (err) {
      setSocialError(parseApiError(err));
    }
  }, [handleIdTokenLogin]);

  /**
   * TikTok uses the native SDK (expo-tiktok-opensdk) which returns an
   * authCode directly. The backend exchanges it for an access token
   * via POST /auth/tiktok-login.
   */
  const handleTikTokLogin = useCallback(async () => {
    setIsSocialLoading(true);
    setSocialError(null);

    try {
      const result = await signInWithTikTok();
      if (!result) {
        // User cancelled
        setIsSocialLoading(false);
        return;
      }

      const response = await apiFetch<LoginResponse>(
        AUTH_ENDPOINTS.TIKTOK_LOGIN,
        {
          method: "POST",
          body: JSON.stringify({
            auth_code: result.authCode,
            ...(result.codeVerifier ? { code_verifier: result.codeVerifier } : {}),
          }),
        },
      );

      await storeJwt(response.access_token);
      if (response.refresh_token) {
        await storeRefreshToken(response.refresh_token);
      }
      setUsername(response.username);
      setSessionMode("user");
    } catch (err) {
      setSocialError(parseApiError(err));
    } finally {
      setIsSocialLoading(false);
    }
  }, [setSessionMode, setUsername]);

  const clearSocialError = useCallback(() => {
    setSocialError(null);
  }, []);

  return {
    isSocialLoading,
    socialError,
    handleGoogleLogin,
    handleAppleLogin,
    handleTikTokLogin,
    clearSocialError,
  };
}
