import * as Sentry from "@sentry/react-native";
import Constants from "expo-constants";
import { SENTRY_DSN } from "../constants/config";

let initialized = false;

export function initSentry(): void {
  if (initialized) return;
  if (!SENTRY_DSN) {
    if (__DEV__) {
      console.warn("[Sentry] SENTRY_DSN missing — crash reporting disabled.");
    }
    return;
  }
  Sentry.init({
    dsn: SENTRY_DSN,
    environment:
      (Constants.expoConfig?.extra?.environment as string | undefined) ??
      "development",
    tracesSampleRate: 0.1,
    enableAutoSessionTracking: true,
    enableNative: true,
  });
  initialized = true;
}

export function addBreadcrumb(
  category: string,
  message: string,
  data?: Record<string, unknown>,
): void {
  Sentry.addBreadcrumb({ category, message, data, level: "info" });
}
