import { useEffect, useState, useCallback } from "react";
import { Slot, useRouter, useSegments } from "expo-router";
import * as SplashScreen from "expo-splash-screen";
import { StatusBar } from "expo-status-bar";
import * as Linking from "expo-linking";
import { View, Text } from "react-native";
import { StripeProvider } from "../lib/stripe-web-shim";

import { deleteItem, getItem } from "../lib/secure-storage";
import { useEnabledProviders } from "../hooks/useEnabledProviders";

import { getOrCreateGuestToken } from "../lib/guest-session";
import { getStoredJwt } from "../lib/auth";
import { AuthProvider, useAuth } from "../lib/auth-context";
import { registerForPushNotifications } from "../lib/notifications";
import { isAllowedDeepLink } from "../lib/deep-link-guard";
import { THEME } from "../constants/theme";
import { STRIPE_PUBLISHABLE_KEY, APPLE_MERCHANT_ID, SECURE_STORE_KEYS } from "../constants/config";
import { ThemeProvider } from "../lib/theme-context";
import { useAppFonts } from "../hooks/useFonts";
import { ErrorBoundary } from "../components/ui/ErrorBoundary";

// Keep splash screen visible while we initialize
SplashScreen.preventAutoHideAsync();

function AuthGuard() {
  const { isAuthenticated } = useAuth();
  const router = useRouter();
  const segments = useSegments();
  const { features } = useEnabledProviders();

  useEffect(() => {
    const inAuthGroup = segments[0] === "(auth)";

    if (!isAuthenticated && !inAuthGroup) {
      router.replace("/(auth)/login");
    } else if (isAuthenticated && inAuthGroup) {
      if (features.onboarding_enabled) {
        // Check if onboarding was already completed
        getItem("nxme_onboarding_complete").then((value) => {
          if (!value) {
            router.replace("/onboarding");
          } else {
            router.replace("/(tabs)");
          }
        });
      } else {
        router.replace("/(tabs)");
      }
    }
  }, [isAuthenticated, segments, features.onboarding_enabled, router]);

  return <Slot />;
}

export default function RootLayout() {
  const [isReady, setIsReady] = useState(false);
  const [initError, setInitError] = useState<Error | null>(null);
  const [initialAuth, setInitialAuth] = useState(false);
  const { fontsLoaded, fontError } = useAppFonts();

  // Cold start initialization
  useEffect(() => {
    async function initialize() {
      let authed = false;

      // 1. Check stored JWT first — this determines auth state
      try {
        const jwt = await getStoredJwt();
        if (jwt) {
          const parts = jwt.split(".");
          if (!parts[1]) throw new Error("malformed JWT");
          const payload = JSON.parse(atob(parts[1]));
          if (payload.exp && payload.exp * 1000 < Date.now()) {
            await deleteItem(SECURE_STORE_KEYS.JWT);
          } else {
            authed = true;
          }
        }
      } catch {
        // Corrupted JWT — clear it, user will re-login
        try { await deleteItem(SECURE_STORE_KEYS.JWT); } catch {}
      }

      // 2. Non-critical init — never blocks auth
      getOrCreateGuestToken().catch((err) => { if (__DEV__) console.warn("Guest token init failed:", err); });
      registerForPushNotifications().catch((err) => { if (__DEV__) console.warn("Push notification registration failed:", err); });

      setInitialAuth(authed);
    }

    initialize()
      .then(() => setIsReady(true))
      .catch((e) => {
        setInitError(e instanceof Error ? e : new Error(String(e)));
        setIsReady(true); // Still set ready so splash hides
      });
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
    if (isReady && (fontsLoaded || fontError)) {
      await SplashScreen.hideAsync();
    }
  }, [isReady, fontsLoaded, fontError]);

  if (!isReady || (!fontsLoaded && !fontError)) {
    return null;
  }

  if (fontError || initError) {
    return (
      <View style={{ flex: 1, backgroundColor: '#0a0a0a', justifyContent: 'center', alignItems: 'center', padding: 24 }}>
        <Text style={{ color: '#e8e8e8', fontSize: 16, textAlign: 'center', marginBottom: 16 }}>
          Something went wrong. Please restart the app.
        </Text>
      </View>
    );
  }

  const inner = (
    <View style={{ flex: 1, backgroundColor: THEME.colors.bg }} onLayout={onLayoutReady}>
      <StatusBar style="light" />
      <AuthGuard />
    </View>
  );

  return (
    <ErrorBoundary>
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
    </ErrorBoundary>
  );
}
