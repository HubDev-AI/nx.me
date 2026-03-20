import { useEffect, useState, useCallback } from "react";
import { Slot, useRouter, useSegments } from "expo-router";
import * as SplashScreen from "expo-splash-screen";
import { StatusBar } from "expo-status-bar";
import * as Linking from "expo-linking";
import { View, Platform } from "react-native";
import { StripeProvider } from "../lib/stripe-web-shim";

import * as SecureStore from "expo-secure-store";

import { getOrCreateGuestToken } from "../lib/guest-session";
import { getStoredJwt } from "../lib/auth";
import { AuthProvider, useAuth } from "../lib/auth-context";
import { registerForPushNotifications } from "../lib/notifications";
import { isAllowedDeepLink } from "../lib/deep-link-guard";
import { BG_PAGE } from "../constants/colors";
import { STRIPE_PUBLISHABLE_KEY, APPLE_MERCHANT_ID, SECURE_STORE_KEYS } from "../constants/config";
import { ThemeProvider } from "../lib/theme-context";
import { useAppFonts } from "../hooks/useFonts";

// Keep splash screen visible while we initialize
SplashScreen.preventAutoHideAsync();

function AuthGuard() {
  const { isAuthenticated } = useAuth();
  const router = useRouter();
  const segments = useSegments();

  useEffect(() => {
    const inAuthGroup = segments[0] === "(auth)";

    if (!isAuthenticated && !inAuthGroup) {
      router.replace("/(auth)/login");
    } else if (isAuthenticated && inAuthGroup) {
      router.replace("/(tabs)");
    }
  }, [isAuthenticated, segments]);

  return <Slot />;
}

export default function RootLayout() {
  const [isReady, setIsReady] = useState(false);
  const [initialAuth, setInitialAuth] = useState(false);
  const fontsLoaded = useAppFonts();

  // Cold start initialization
  useEffect(() => {
    async function initialize() {
      let authed = false;
      try {
        await getOrCreateGuestToken();

        registerForPushNotifications().catch(() => {});

        const jwt = await getStoredJwt();
        if (jwt) {
          try {
            const parts = jwt.split(".");
            if (!parts[1]) throw new Error("malformed JWT");
            const payload = JSON.parse(atob(parts[1]));
            if (payload.exp && payload.exp * 1000 < Date.now()) {
              await SecureStore.deleteItemAsync(SECURE_STORE_KEYS.JWT);
            } else {
              authed = true;
            }
          } catch {
            await SecureStore.deleteItemAsync(SECURE_STORE_KEYS.JWT);
          }
        }
      } catch (error) {
        console.warn("App initialization failed");
      } finally {
        setInitialAuth(authed);
        setIsReady(true);
      }
    }

    initialize();
  }, []);

  // Deep link guard
  useEffect(() => {
    const subscription = Linking.addEventListener("url", (event) => {
      if (!isAllowedDeepLink(event.url)) {
        console.warn("Rejected non-universal deep link");
      }
    });
    return () => subscription.remove();
  }, []);

  const onLayoutReady = useCallback(async () => {
    if (isReady && fontsLoaded) {
      await SplashScreen.hideAsync();
    }
  }, [isReady, fontsLoaded]);

  if (!isReady || !fontsLoaded) {
    return null;
  }

  const inner = (
    <View style={{ flex: 1, backgroundColor: BG_PAGE }} onLayout={onLayoutReady}>
      <StatusBar style="light" />
      <AuthGuard />
    </View>
  );

  return (
    <ThemeProvider>
      <AuthProvider initialAuth={initialAuth}>
        {StripeProvider ? (
          <StripeProvider
            publishableKey={STRIPE_PUBLISHABLE_KEY}
            urlScheme="https"
            merchantIdentifier={APPLE_MERCHANT_ID}
          >
            {inner}
          </StripeProvider>
        ) : (
          inner
        )}
      </AuthProvider>
    </ThemeProvider>
  );
}
