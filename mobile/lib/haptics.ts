import { Platform } from "react-native";

/** Fire-and-forget haptic feedback. No-op on web. */
export async function hapticLight() {
  if (Platform.OS === "web") return;
  const Haptics = require("expo-haptics");
  Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
}

export async function hapticMedium() {
  if (Platform.OS === "web") return;
  const Haptics = require("expo-haptics");
  Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium);
}

export async function hapticError() {
  if (Platform.OS === "web") return;
  const Haptics = require("expo-haptics");
  Haptics.notificationAsync(Haptics.NotificationFeedbackType.Error);
}
