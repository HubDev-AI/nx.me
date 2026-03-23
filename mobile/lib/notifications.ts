import { Platform } from "react-native";
import * as Notifications from "expo-notifications";
import * as SecureStore from "expo-secure-store";
import Constants from "expo-constants";

import { SECURE_STORE_KEYS } from "../constants/config";
// import { apiFetch } from "./api"; // Uncomment when backend adds POST /v1/devices

/**
 * Send the push token to the backend for server-initiated push delivery.
 *
 * The backend does not currently expose a push token registration endpoint.
 * When one is added (e.g. POST /v1/devices), this function will send the
 * token and platform. Until then, it silently succeeds so callers don't
 * need to change.
 *
 * TODO: Wire to real endpoint when backend adds POST /v1/devices
 */
export async function sendPushTokenToBackend(token: string): Promise<void> {
  // Backend endpoint not yet available — no-op for now.
  // When the endpoint exists, uncomment the code below:
  //
  // await apiFetch("/v1/devices", {
  //   method: "POST",
  //   body: JSON.stringify({
  //     push_token: token,
  //     platform: Platform.OS,
  //   }),
  // });
  //
  if (__DEV__) {
    console.log("[notifications] Push token ready for backend:", token.slice(0, 20) + "...");
  }
}

/**
 * Request notification permissions and register the Expo push token.
 * Returns the token string if granted, null otherwise.
 *
 * After obtaining the token, attempts to send it to the backend.
 * Only runs on native platforms — web is a no-op.
 */
export async function registerForPushNotifications(): Promise<string | null> {
  if (Platform.OS === "web") {
    return null;
  }

  const { status: existingStatus } =
    await Notifications.getPermissionsAsync();

  let finalStatus = existingStatus;
  if (existingStatus !== "granted") {
    const { status } = await Notifications.requestPermissionsAsync();
    finalStatus = status;
  }

  if (finalStatus !== "granted") {
    return null;
  }

  const tokenData = await Notifications.getExpoPushTokenAsync({
    projectId: Constants.expoConfig?.extra?.eas?.projectId,
  });
  const token = tokenData.data;

  // Persist locally so we can send to backend later
  await SecureStore.setItemAsync(SECURE_STORE_KEYS.PUSH_TOKEN, token);

  // Attempt to register the token with the backend (best-effort)
  sendPushTokenToBackend(token).catch(() => {});

  // Configure notification handling while app is foregrounded
  Notifications.setNotificationHandler({
    handleNotification: async () => ({
      shouldShowAlert: true,
      shouldPlaySound: false,
      shouldSetBadge: true,
      shouldShowBanner: true,
      shouldShowList: true,
    }),
  });

  return token;
}
