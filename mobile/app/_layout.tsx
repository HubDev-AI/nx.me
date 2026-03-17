import { useEffect, useState, useCallback } from "react";
import { Slot, useRouter, useNavigationContainerRef } from "expo-router";
import * as SplashScreen from "expo-splash-screen";
import { StatusBar } from "expo-status-bar";
import * as Linking from "expo-linking";
import { View } from "react-native";
import { StripeProvider } from "@stripe/stripe-react-native";

import { getOrCreateGuestToken } from "../lib/guest-session";
import { getStoredJwt } from "../lib/auth";
import { registerForPushNotifications } from "../lib/notifications";
import { isAllowedDeepLink } from "../lib/deep-link-guard";
import { BG_PAGE } from "../constants/colors";
import { STRIPE_PUBLISHABLE_KEY, APPLE_MERCHANT_ID } from "../constants/config";

// Keep splash screen visible while we initialize
SplashScreen.preventAutoHideAsync();

export default function RootLayout() {
  const [isReady, setIsReady] = useState(false);
  const router = useRouter();
  const navigationRef = useNavigationContainerRef();

  // Cold start initialization
  useEffect(() => {
    async function initialize() {
      try {
        // 1. Get or create guest session token
        await getOrCreateGuestToken();

        // 2. Register for push notifications (non-blocking)
        registerForPushNotifications().catch(() => {
          // Silently ignore — user may have denied permissions
        });

        // 3. Check for stored JWT (auto-login check)
        const jwt = await getStoredJwt();
        if (jwt) {
          // JWT exists — user is authenticated.
          // Full token validation will happen in later stories.
        }
      } catch (error) {
        console.warn("App initialization error:", error);
      } finally {
        setIsReady(true);
      }
    }

    initialize();
  }, []);

  // Deep link guard: reject custom URI scheme redirects
  useEffect(() => {
    const subscription = Linking.addEventListener("url", (event) => {
      if (!isAllowedDeepLink(event.url)) {
        console.warn("Rejected non-universal deep link:", event.url);
        // Do not navigate — silently drop the redirect
      }
    });

    return () => subscription.remove();
  }, []);

  // Hide splash when ready and navigation is mounted
  const onLayoutReady = useCallback(async () => {
    if (isReady) {
      await SplashScreen.hideAsync();
    }
  }, [isReady]);

  if (!isReady) {
    return null;
  }

  return (
    <StripeProvider
      publishableKey={STRIPE_PUBLISHABLE_KEY}
      urlScheme="nxme"
      merchantIdentifier={APPLE_MERCHANT_ID}
    >
      <View style={{ flex: 1, backgroundColor: BG_PAGE }} onLayout={onLayoutReady}>
        <StatusBar style="light" />
        <Slot />
      </View>
    </StripeProvider>
  );
}
