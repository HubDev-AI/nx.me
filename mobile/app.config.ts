import "dotenv/config";
import type { ExpoConfig, ConfigContext } from "expo/config";

/**
 * Dynamic Expo config — reads environment-sensitive values from process.env.
 *
 * Env vars are loaded from mobile/.env via dotenv/config.
 * For CI / production, set the env vars directly in the shell environment.
 */

/** Derive the iOS URL scheme from the Google iOS Client ID (reversed domain). */
const googleIosClientId = process.env.GOOGLE_IOS_CLIENT_ID ?? "";
const googleIosUrlScheme = googleIosClientId
  ? `com.googleusercontent.apps.${googleIosClientId.split(".")[0]}`
  : "";

export default ({ config }: ConfigContext): ExpoConfig => ({
  ...config,
  name: "NXME",
  slug: "nxme",
  version: "1.0.0",
  orientation: "portrait",
  icon: "./assets/icon.png",
  userInterfaceStyle: "automatic",
  scheme: "nxme",
  splash: {
    image: "./assets/splash-icon.png",
    resizeMode: "contain",
    backgroundColor: "#080808",
  },
  ios: {
    supportsTablet: false,
    bundleIdentifier: "ai.nxme.app",
    associatedDomains: ["applinks:nxme.ai"],
    infoPlist: {
      NSAppTransportSecurity: {
        NSAllowsArbitraryLoads: true,
        NSAllowsLocalNetworking: true,
      },
    },
  },
  android: {
    package: "ai.nxme.app",
    adaptiveIcon: {
      backgroundColor: "#080808",
      foregroundImage: "./assets/android-icon-foreground.png",
      backgroundImage: "./assets/android-icon-background.png",
      monochromeImage: "./assets/android-icon-monochrome.png",
    },
    // Path filters MUST mirror card-web/src/config/constants.ts APP_LINK_PATHS.
    // Claiming all paths ("/") would capture web-only URLs like /{username}
    // share cards into the app, which has no matching route.
    //
    // Android `pathPrefix` is substring-prefix — `/signup` would also capture
    // `/signups`, `/signup-bot`, etc. — so use an exact `path` for signup.
    // There is no `/signup/...` route in mobile (see `mobile/app/(auth)/`),
    // so we do NOT claim a nested pattern. `/card/` is safe as a prefix
    // because every match starts with the terminating slash, so it cannot
    // swallow a hypothetical `/cardiology`.
    intentFilters: [
      {
        action: "VIEW",
        autoVerify: true,
        data: [
          { scheme: "https", host: "nxme.ai", path: "/signup" },
          { scheme: "https", host: "nxme.ai", pathPrefix: "/card/" },
        ],
        category: ["BROWSABLE", "DEFAULT"],
      },
    ],
  },
  web: {
    bundler: "metro",
    favicon: "./assets/favicon.png",
  },
  experiments: {
    typedRoutes: true,
  },
  plugins: [
    ["expo-router", { origin: "https://nxme.ai" }],
    "expo-secure-store",
    [
      "expo-image-picker",
      {
        photosPermission:
          "NXME needs access to your photo library to select a photo for your glow-up.",
        cameraPermission:
          "NXME needs access to your camera to take a photo for your glow-up.",
      },
    ],
    "expo-web-browser",
    [
      "@stripe/stripe-react-native",
      {
        merchantIdentifier:
          process.env.APPLE_MERCHANT_ID ?? "merchant.ai.nxme.app",
        enableGooglePay: true,
      },
    ],
    [
      "@react-native-google-signin/google-signin",
      { iosUrlScheme: googleIosUrlScheme },
    ],
    "expo-font",
    [
      "react-native-tiktok",
      { tiktokClientKey: process.env.TIKTOK_CLIENT_KEY ?? "" },
    ],
    "./plugins/with-bundle-deployment-target",
  ],
  extra: {
    // Intentionally no default — API_BASE_URL must be set per environment
    // (see mobile/.env / mobile/.env.example). The consuming constants.ts
    // throws at import time if apiBaseUrl is undefined.
    apiBaseUrl: process.env.API_BASE_URL,
    stripePublishableKey: process.env.STRIPE_PUBLISHABLE_KEY ?? "",
    googleClientId: process.env.GOOGLE_IOS_CLIENT_ID ?? "",
    googleWebClientId: process.env.GOOGLE_OAUTH_CLIENT_ID ?? "",
    appleClientId: process.env.APPLE_CLIENT_ID ?? "",
    appleMerchantId:
      process.env.APPLE_MERCHANT_ID ?? "merchant.ai.nxme.app",
    tiktokClientKey: process.env.TIKTOK_CLIENT_KEY ?? "",
    /**
     * Dev only — comma list of feature short names to force-disable on top of
     * the backend `/v1/features` response. e.g. `social,onboarding`.
     */
    devDisableFeatures: process.env.DEV_DISABLE_FEATURES ?? "",
  },
});
