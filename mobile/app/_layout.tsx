import { useEffect, useState, useCallback, useRef } from "react";
import { Slot, useRouter, useSegments } from "expo-router";
import * as SplashScreen from "expo-splash-screen";
import { StatusBar } from "expo-status-bar";
import * as Linking from "expo-linking";
import { View, Text } from "react-native";
import { StripeProvider } from "../lib/stripe-web-shim";
import { QueryClientProvider } from "@tanstack/react-query";
import NetInfo from "@react-native-community/netinfo";
import * as Sentry from "@sentry/react-native";
import { KeyboardProvider } from "react-native-keyboard-controller";

import { deleteItem, getItem } from "../lib/secure-storage";

import { getOrCreateGuestToken } from "../lib/guest-session";
import { fetchMe } from "../lib/me";
import { getStoredJwt } from "../lib/auth";
import { restoreStoredSession } from "../lib/api";
import { AuthProvider, useAuth } from "../lib/auth-context";
import type { SessionMode } from "../lib/session";
import { FeaturesProvider, useFeatures } from "../lib/features-context";
import { useCapabilities } from "../lib/capabilities";
import { ConsentProvider, useConsent } from "../lib/consent-context";
import { RadialMenuProvider } from "../lib/radial-menu-context";
import { isAllowedDeepLink } from "../lib/deep-link-guard";
import { THEME } from "../constants/theme";
import {
  STRIPE_PUBLISHABLE_KEY,
  APPLE_MERCHANT_ID,
  SECURE_STORE_KEYS,
  GUEST_ME_TIMEOUT_MS,
} from "../constants/config";
import { ThemeProvider } from "../lib/theme-context";
import { useAppFonts } from "../hooks/useFonts";
import { ErrorBoundary } from "../components/ui/ErrorBoundary";
import { OfflineBanner } from "../components/ui/OfflineBanner";
import { queryClient } from "../lib/query-client";
import { initSentry } from "../lib/sentry";
import { mutationQueue } from "../lib/offline-queue";
import { lookupReplayableMutation } from "../lib/mutation-registry";
import { parseApiError, shouldRetry } from "../lib/errors";

/** Upper bound on replay attempts before we drop a poisonous queue entry. */
const MAX_REPLAY_ATTEMPTS = 5;

// Initialize Sentry once at module import — before any component renders.
initSentry();

// Keep splash screen visible while we initialize
SplashScreen.preventAutoHideAsync();

function AuthGuard() {
  const { session, setSessionMode, setUsername, markSessionReady } = useAuth();
  const { isLoading: featuresLoading } = useFeatures();
  const caps = useCapabilities();
  const { markConsentGranted } = useConsent();
  const router = useRouter();
  const segments = useSegments();
  const guestInitRef = useRef(false);

  // Provision the backend guest token once for non-user sessions and
  // promote to "guest" so downstream UI can talk to guest-friendly endpoints
  // (entitlement, uploads, advisor reads). Real-user sessions skip this.
  useEffect(() => {
    if (featuresLoading) return;
    if (session.isUser) {
      markSessionReady();
      return;
    }
    if (guestInitRef.current) return;
    guestInitRef.current = true;
    getOrCreateGuestToken()
      .then(async () => {
        // Promote to "guest" first so apiFetch picks the X-Guest-Token branch
        // for the /me call (it reads the token from SecureStore, not from
        // session mode, but ordering keeps state coherent for any other
        // listeners that may fire on the mode transition).
        setSessionMode("guest");
        try {
          // Bound the /me wait so a stalled network can't block the splash
          // screen indefinitely. On timeout the screen mounts without an
          // authUsername; the profile load effect stays inert until the user
          // backgrounds/foregrounds and the AuthGuard re-runs.
          const me = await Promise.race([
            fetchMe(),
            new Promise<never>((_, reject) =>
              setTimeout(
                () => reject(new Error("Guest /me timed out")),
                GUEST_ME_TIMEOUT_MS,
              ),
            ),
          ]);
          setUsername(me.username);
          // Hydrate ConsentProvider from the server's source of truth so
          // subsequent Analyze taps trust the server state rather than
          // whatever hasConsent happened to be cached on this device.
          // Without this, a DB reset (pre-launch this happens often)
          // leaves the client believing consent is granted while the
          // server 428s the analyze call.
          markConsentGranted(me.face_mod_consent_at !== null);
        } catch (err) {
          // Non-fatal — profile screens fall back to the "complete your
          // profile" stub when authUsername is null. Log so dev can debug.
          if (__DEV__) console.warn("Guest /me lookup failed:", err);
        } finally {
          // Always release the splash, even on /me timeout or failure.
          markSessionReady();
        }
      })
      .catch((err) => {
        if (__DEV__) console.warn("Guest session init failed:", err);
        // Leave session as anon; allow retry on the next connectivity recovery.
        guestInitRef.current = false;
        markSessionReady();
      });
  }, [
    featuresLoading,
    session.isUser,
    setSessionMode,
    setUsername,
    markSessionReady,
    markConsentGranted,
  ]);

  useEffect(() => {
    if (featuresLoading) return;
    const inAuthGroup = segments[0] === "(auth)";

    // Guest sessions reach the app; the auth screens are only for anon.
    if (session.isGuest) {
      if (inAuthGroup) router.replace("/(tabs)");
      return;
    }

    if (!session.isUser) {
      if (!inAuthGroup) router.replace("/(auth)/login");
      return;
    }

    if (!inAuthGroup) return;

    if (!caps.canSeeOnboarding) {
      router.replace("/(tabs)");
      return;
    }

    getItem(SECURE_STORE_KEYS.ONBOARDING_COMPLETE).then((value) => {
      router.replace(value ? "/(tabs)" : "/onboarding");
    });
  }, [
    featuresLoading,
    caps.canSeeOnboarding,
    session.isUser,
    session.isGuest,
    segments,
    router,
  ]);

  return <Slot />;
}

export default function RootLayout() {
  const [isReady, setIsReady] = useState(false);
  const [initError, setInitError] = useState<Error | null>(null);
  const [initialMode, setInitialMode] = useState<SessionMode>("anon");
  const { fontsLoaded, fontError } = useAppFonts();
  // Mutex guarding the offline-replay drain. NetInfo can fire back-to-back
  // during a network flap; without this, we'd double-execute queued mutations.
  const replayingRef = useRef(false);

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
        // Corrupted JWT — clear it and fall back to refresh-token restore
        try { await deleteItem(SECURE_STORE_KEYS.JWT); } catch {}
      }

      // 2. If the access token is missing/expired, attempt a silent restore
      //    from the persisted refresh token before treating the user as logged out.
      if (!authed) {
        authed = Boolean(await restoreStoredSession());
      }

      // Guest token provisioning happens inside AuthGuard once feature flags
      // resolve, so we avoid hitting POST /auth/guest when auth is required.
      setInitialMode(authed ? "user" : "anon");
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

  // Replay queued offline mutations whenever connectivity is restored.
  useEffect(() => {
    const unsubscribe = NetInfo.addEventListener(async (state) => {
      if (!state.isConnected) return;
      if (replayingRef.current) return;
      replayingRef.current = true;
      try {
        const pending = mutationQueue.list();
        for (const queued of pending) {
          const fn = lookupReplayableMutation(queued.mutationKey);
          if (!fn) {
            Sentry.captureMessage("Unhandled replayable mutation", {
              tags: { source: "replay" },
              extra: { mutationKey: queued.mutationKey },
            });
            mutationQueue.dequeue(queued.id);
            continue;
          }
          try {
            await fn(queued.variables);
            mutationQueue.dequeue(queued.id);
          } catch (err) {
            const appError = parseApiError(err);
            const attempts = queued.replayAttempts + 1;
            if (!shouldRetry(appError) || attempts >= MAX_REPLAY_ATTEMPTS) {
              Sentry.captureException(err, {
                tags: { source: "replay", kind: appError.kind },
                extra: { mutationKey: queued.mutationKey, attempts },
              });
              mutationQueue.dequeue(queued.id);
            } else {
              mutationQueue.dequeue(queued.id);
              mutationQueue.enqueue({ ...queued, replayAttempts: attempts });
            }
          }
        }
      } finally {
        replayingRef.current = false;
      }
    });
    return unsubscribe;
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
      <OfflineBanner />
    </View>
  );

  return (
    <ErrorBoundary>
      <KeyboardProvider>
        <QueryClientProvider client={queryClient}>
          <ThemeProvider>
            <FeaturesProvider>
              <AuthProvider initialMode={initialMode}>
                <ConsentProvider>
                  <RadialMenuProvider>
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
                  </RadialMenuProvider>
                </ConsentProvider>
              </AuthProvider>
            </FeaturesProvider>
          </ThemeProvider>
        </QueryClientProvider>
      </KeyboardProvider>
    </ErrorBoundary>
  );
}
