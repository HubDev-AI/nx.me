/**
 * Native social authentication helpers.
 *
 * Uses platform-native SDKs to obtain id_tokens that the backend can verify
 * via Supabase's `sign_in_with_id_token`.
 *
 * - Google: @react-native-google-signin/google-signin (returns idToken directly)
 * - Apple:  expo-apple-authentication (returns identityToken JWT directly)
 *
 * Both providers return an id_token without requiring a redirect URI or
 * server-side authorization code exchange.
 */
import { Platform } from "react-native";
import * as AppleAuthentication from "expo-apple-authentication";
import * as Crypto from "expo-crypto";
import {
  GoogleSignin,
  statusCodes,
} from "@react-native-google-signin/google-signin";

import { GOOGLE_WEB_CLIENT_ID } from "../constants/config";

/** Result shape returned by both social sign-in helpers. */
export interface SocialAuthResult {
  idToken: string;
  /** Raw nonce sent to the provider (required by Apple for Supabase verification). */
  nonce?: string;
}

// ---------------------------------------------------------------------------
// Google Sign-In
// ---------------------------------------------------------------------------

/** One-time configuration — safe to call multiple times. */
let googleConfigured = false;

function ensureGoogleConfigured(): void {
  if (googleConfigured) return;
  GoogleSignin.configure({
    webClientId: GOOGLE_WEB_CLIENT_ID,
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
 * A cryptographic nonce is generated and passed to Apple so that Supabase can
 * verify the id_token was issued for this specific authentication request.
 *
 * Returns `null` if the user cancels. Throws on unexpected errors.
 */
export async function signInWithApple(): Promise<SocialAuthResult | null> {
  if (Platform.OS !== "ios") {
    throw new Error("Apple Sign-In is only available on iOS.");
  }

  // Generate a cryptographic nonce for replay protection.
  // Supabase expects the raw (unhashed) nonce so it can hash and compare
  // against the nonce claim inside the id_token from Apple.
  const rawNonce = await Crypto.digestStringAsync(
    Crypto.CryptoDigestAlgorithm.SHA256,
    Crypto.getRandomBytes(32).toString(),
  );

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
