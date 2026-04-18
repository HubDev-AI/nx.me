/**
 * Full-screen overlay shown while the delete-account server request is in
 * flight. Pairs with a navigation-remove listener in settings.tsx so the
 * user cannot navigate away mid-operation. A client-side timeout in the
 * caller (DELETE_ACCOUNT_TIMEOUT_MS) ensures the overlay cannot trap the
 * user forever.
 */
import { ActivityIndicator, StyleSheet, View } from "react-native";

import { THEME } from "../../constants/theme";
import { Body, Heading } from "../ui/Text";

export function DeleteAccountOverlay() {
  return (
    <View
      style={styles.overlay}
      accessibilityRole="progressbar"
      accessibilityLabel="Deleting your account"
      accessibilityViewIsModal
    >
      <ActivityIndicator size="large" color={THEME.colors.textPrimary} />
      <Heading
        size="md"
        style={styles.title}
        maxFontSizeMultiplier={1.3}
      >
        Deleting your account…
      </Heading>
      <Body
        color="secondary"
        style={styles.subtitle}
        maxFontSizeMultiplier={1.4}
      >
        This can take up to a minute while we remove your photos and data. Keep the app open.
      </Body>
    </View>
  );
}

const styles = StyleSheet.create({
  overlay: {
    ...StyleSheet.absoluteFillObject,
    backgroundColor: "rgba(0, 0, 0, 0.85)",
    alignItems: "center",
    justifyContent: "center",
    gap: THEME.spacing.lg,
    paddingHorizontal: THEME.spacing.xxl,
  },
  title: { textAlign: "center" },
  subtitle: { textAlign: "center" },
});
