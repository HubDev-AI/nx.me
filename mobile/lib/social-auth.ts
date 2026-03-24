/**
 * Native social authentication helpers.
 *
 * - Google: @react-native-google-signin/google-signin (returns idToken directly)
 * - Apple:  expo-apple-authentication (returns identityToken JWT directly)
 * - TikTok: expo-web-browser OAuth2 PKCE flow (returns authorization code)
 *
 * Google & Apple return id_tokens verified by Supabase GoTrue.
 * TikTok returns an authorization code exchanged server-side.
 */
import { Platform } from "react-native";
import * as AppleAuthentication from "expo-apple-authentication";
import * as Crypto from "expo-crypto";

import { GOOGLE_CLIENT_ID, GOOGLE_WEB_CLIENT_ID, UNIVERSAL_LINK_ORIGIN } from "../constants/config";

// Lazy-load Google Sign-In to avoid crashing in Expo Go where
// the native module (RNGoogleSignin) is not available.
let _GoogleSignin: typeof import("@react-native-google-signin/google-signin").GoogleSignin | null = null;
let _statusCodes: typeof import("@react-native-google-signin/google-signin").statusCodes | null = null;

function getGoogleSignin() {
  if (!_GoogleSignin) {
    try {
      // eslint-disable-next-line @typescript-eslint/no-var-requires
      const mod = require("@react-native-google-signin/google-signin");
      _GoogleSignin = mod.GoogleSignin;
      _statusCodes = mod.statusCodes;
    } catch {
      throw new Error(
        "Google Sign-In is not available. Use a development build instead of Expo Go.",
      );
    }
  }
  return { GoogleSignin: _GoogleSignin!, statusCodes: _statusCodes! };
}

/** Result shape returned by Google & Apple sign-in helpers. */
export interface SocialAuthResult {
  idToken: string;
  /** Raw nonce sent to the provider (required by Apple for Supabase verification). */
  nonce?: string;
}

/** Result shape returned by TikTok native SDK sign-in. */
export interface TikTokAuthResult {
  /** Authorization code to exchange server-side for an access token. */
  authCode: string;
  /** PKCE code verifier (Android only — needed for server-side token exchange). */
  codeVerifier?: string;
}

// ---------------------------------------------------------------------------
// Google Sign-In
// ---------------------------------------------------------------------------

/** One-time configuration — safe to call multiple times. */
let googleConfigured = false;

function ensureGoogleConfigured(): void {
  if (googleConfigured) return;
  const { GoogleSignin } = getGoogleSignin();
  GoogleSignin.configure({
    webClientId: GOOGLE_WEB_CLIENT_ID,
    iosClientId: GOOGLE_CLIENT_ID,
    offlineAccess: false,
  });
  googleConfigured = true;
}

/**
 * Prompt the user to sign in with Google and return the id_token.
 *
 * Returns `null` if the user cancels. Throws on unexpected errors.
 */
export async function signInWithGoogle(): Promise<SocialAuthResult | null> {
  ensureGoogleConfigured();
  const { GoogleSignin, statusCodes } = getGoogleSignin();

  try {
    await GoogleSignin.hasPlayServices({ showPlayServicesUpdateDialog: true });
    const response = await GoogleSignin.signIn();

    // The signIn response shape includes data.idToken in v13+
    const idToken =
      (response as { data?: { idToken?: string | null } }).data?.idToken ??
      (response as { idToken?: string | null }).idToken;

    if (!idToken) {
      throw new Error("Google Sign-In succeeded but no id_token was returned.");
    }

    return { idToken };
  } catch (error: unknown) {
    const err = error as { code?: string };
    if (
      err.code === statusCodes.SIGN_IN_CANCELLED ||
      err.code === statusCodes.IN_PROGRESS
    ) {
      // User cancelled or sign-in already in progress — not an error
      return null;
    }
    throw error;
  }
}

// ---------------------------------------------------------------------------
// Apple Sign-In
// ---------------------------------------------------------------------------

/**
 * Prompt the user to sign in with Apple and return the id_token + raw nonce.
 *
 * Apple Sign-In is only available on iOS. On other platforms this function
 * throws immediately.
 *
 * Returns `null` if the user cancels. Throws on unexpected errors.
 */
export async function signInWithApple(): Promise<SocialAuthResult | null> {
  if (Platform.OS !== "ios") {
    throw new Error("Apple Sign-In is only available on iOS.");
  }

  // Generate a cryptographic nonce for replay protection.
  const rawNonce = Array.from(Crypto.getRandomBytes(32))
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");

  try {
    const credential = await AppleAuthentication.signInAsync({
      requestedScopes: [
        AppleAuthentication.AppleAuthenticationScope.FULL_NAME,
        AppleAuthentication.AppleAuthenticationScope.EMAIL,
      ],
      nonce: rawNonce,
    });

    if (!credential.identityToken) {
      throw new Error(
        "Apple Sign-In succeeded but no identity token was returned.",
      );
    }

    return {
      idToken: credential.identityToken,
      nonce: rawNonce,
    };
  } catch (error: unknown) {
    const err = error as { code?: string };
    if (err.code === "ERR_REQUEST_CANCELED") {
      return null;
    }
    throw error;
  }
}

// ---------------------------------------------------------------------------
// TikTok Sign-In (native SDK via react-native-tiktok)
// ---------------------------------------------------------------------------

/**
 * Trigger TikTok native login via the TikTok app (or webview fallback).
 *
 * Uses react-native-tiktok which wraps the official TikTok OpenSDK.
 * The SDK handles redirect URI / deep link plumbing natively.
 * Requires a dev build — not available in Expo Go or on web.
 *
 * Returns `null` if the user cancels. Throws on errors.
 */
export async function signInWithTikTok(): Promise<TikTokAuthResult | null> {
  if (Platform.OS === "web") {
    throw new Error("TikTok login is not supported on web. Use a mobile device.");
  }

  let authorize: typeof import("react-native-tiktok").authorize;
  let Scopes: typeof import("react-native-tiktok").Scopes;
  try {
    // eslint-disable-next-line @typescript-eslint/no-var-requires
    const mod = require("react-native-tiktok");
    authorize = mod.authorize;
    Scopes = mod.Scopes;
  } catch {
    throw new Error(
      "TikTok SDK is not available. Use a development build (npx expo run:ios/android).",
    );
  }

  return new Promise((resolve, reject) => {
    try {
      authorize({
        redirectURI: `${UNIVERSAL_LINK_ORIGIN}/auth/callback`,
        scopes: [Scopes.user.info.basic],
        callback: (authCode: string, codeVerifier?: string) => {
          if (!authCode) {
            resolve(null);
            return;
          }
          resolve({ authCode, codeVerifier });
        },
      });
    } catch (err) {
      reject(err);
    }
  });
}
