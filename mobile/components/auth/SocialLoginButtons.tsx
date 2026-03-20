import { View, Text, Pressable, StyleSheet, Platform } from "react-native";
import { Ionicons } from "@expo/vector-icons";

import { TEXT_SECONDARY } from "../../constants/colors";
import { FONTS } from "../../hooks/useFonts";

interface SocialLoginButtonsProps {
  onGooglePress: () => void;
  onApplePress: () => void;
  googleDisabled?: boolean;
  appleDisabled?: boolean;
  disabled?: boolean;
}

const BUTTON_HEIGHT = 48;

/**
 * Social login buttons — frosted glass style to match the hero bg overlay.
 */
export function SocialLoginButtons({
  onGooglePress,
  onApplePress,
  googleDisabled = false,
  appleDisabled = false,
  disabled = false,
}: SocialLoginButtonsProps) {
  return (
    <View style={styles.container}>
      {/* Thin accent divider line instead of "or" text */}
      <View style={styles.dividerRow}>
        <View style={styles.dividerLine} />
        <Text style={styles.dividerText}>or</Text>
        <View style={styles.dividerLine} />
      </View>

      <Pressable
        onPress={onGooglePress}
        disabled={disabled || googleDisabled}
        style={({ pressed }) => [
          styles.socialButton,
          styles.googleButton,
          pressed && styles.socialButtonPressed,
          (disabled || googleDisabled) && styles.socialButtonDisabled,
        ]}
        accessibilityLabel="Continue with Google"
        accessibilityRole="button"
        accessibilityState={{ disabled: disabled || googleDisabled }}
      >
        <Ionicons name="logo-google" size={18} color="#4285F4" />
        <Text style={styles.googleText}>Continue with Google</Text>
      </Pressable>

      {Platform.OS === "ios" ? (
        <Pressable
          onPress={onApplePress}
          disabled={disabled || appleDisabled}
          style={({ pressed }) => [
            styles.socialButton,
            styles.appleButton,
            pressed && styles.socialButtonPressed,
            (disabled || appleDisabled) && styles.socialButtonDisabled,
          ]}
          accessibilityLabel="Continue with Apple"
          accessibilityRole="button"
          accessibilityState={{ disabled: disabled || appleDisabled }}
        >
          <Ionicons name="logo-apple" size={18} color="#FFFFFF" />
          <Text style={styles.appleText}>Continue with Apple</Text>
        </Pressable>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    gap: 12,
    marginTop: 8,
  },
  dividerRow: {
    flexDirection: "row",
    alignItems: "center",
    marginVertical: 8,
  },
  dividerLine: {
    flex: 1,
    height: StyleSheet.hairlineWidth,
    backgroundColor: "rgba(255, 255, 255, 0.12)",
  },
  dividerText: {
    fontFamily: FONTS.body,
    fontSize: 13,
    color: TEXT_SECONDARY,
    marginHorizontal: 16,
  },
  socialButton: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    minHeight: BUTTON_HEIGHT,
    borderRadius: 9999,
    borderWidth: 1,
    paddingHorizontal: 16,
    gap: 10,
  },
  socialButtonPressed: {
    opacity: 0.8,
  },
  socialButtonDisabled: {
    opacity: 0.5,
  },
  googleButton: {
    backgroundColor: "rgba(255, 255, 255, 0.95)",
    borderColor: "rgba(255, 255, 255, 0.2)",
  },
  googleText: {
    fontFamily: FONTS.bodyMedium,
    fontSize: 15,
    color: "#1F1F1F",
  },
  appleButton: {
    backgroundColor: "rgba(0, 0, 0, 0.85)",
    borderColor: "rgba(255, 255, 255, 0.12)",
  },
  appleText: {
    fontFamily: FONTS.bodyMedium,
    fontSize: 15,
    color: "#FFFFFF",
  },
});
