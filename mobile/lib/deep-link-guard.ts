/**
 * Deep link security: reject custom URI scheme redirects.
 * Only Universal Links (https://nxme.ai) and App Links are allowed.
 */

const ALLOWED_SCHEMES = ["https"] as const;
const ALLOWED_HOST = "nxme.ai";

/**
 * Returns true if the URL is a valid NXME universal/app link.
 * Rejects custom URI schemes (e.g., nxme://) to prevent redirect attacks.
 */
export function isAllowedDeepLink(url: string): boolean {
  try {
    const parsed = new URL(url);
    const scheme = parsed.protocol.replace(":", "");
    return (
      (ALLOWED_SCHEMES as readonly string[]).includes(scheme) &&
      parsed.hostname === ALLOWED_HOST
    );
  } catch {
    return false;
  }
}

/**
 * Parse deep link parameters from a signup URL.
 * Expected format: https://nxme.ai/signup?card={username}
 */
export function parseSignupCardParam(url: string): string | null {
  try {
    const parsed = new URL(url);
    return parsed.searchParams.get("card");
  } catch {
    return null;
  }
}
