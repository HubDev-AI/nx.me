import { View, Text, StyleSheet } from "react-native";
import { FontAwesome6, Ionicons } from "@expo/vector-icons";

import { THEME } from "../../constants/theme";
import { FONTS } from "../../hooks/useFonts";
import { SOCIAL_GOOGLE_BLUE, SOCIAL_GOOGLE_TEXT } from "../../constants/colors";
import { PressableScale } from "../ui/PressableScale";
import type { AuthProvider } from "../../constants/config";

interface SocialLoginButtonsProps {
  enabledProviders: AuthProvider[];
  onGooglePress: () => void;
  onApplePress: () => void;
  onTikTokPress: () => void;
  disabled?: boolean;
}

const BUTTON_HEIGHT = 54;

/**
 * Config-driven social login buttons.
 * Only renders buttons for providers in the enabledProviders list.
 */
export function SocialLoginButtons({
  enabledProviders,
  onGooglePress,
  onApplePress,
  onTikTokPress,
  disabled = false,
}: SocialLoginButtonsProps) {
  const showTikTok = enabledProviders.includes("tiktok");
  const showGoogle = enabledProviders.includes("google");
  const showApple = enabledProviders.includes("apple");

  if (!showTikTok && !showGoogle && !showApple) {
    return null;
  }

  return (
    <View style={styles.container}>
      {/* TikTok — dark bg with TikTok brand colors */}
      {showTikTok && (
        <PressableScale
          onPress={onTikTokPress}
          disabled={disabled}
          accessibilityLabel="Continue with TikTok"
          accessibilityRole="button"
          accessibilityState={{ disabled }}
          style={disabled ? styles.disabledWrapper : undefined}
        >
          <View style={styles.tiktokButton}>
            <TikTokIcon />
            <Text style={styles.tiktokText}>Continue with TikTok</Text>
          </View>
        </PressableScale>
      )}

      {/* Google — white bg, dark text for brand compliance */}
      {showGoogle && (
        <PressableScale
          onPress={onGooglePress}
          disabled={disabled}
          accessibilityLabel="Continue with Google"
          accessibilityRole="button"
          accessibilityState={{ disabled }}
          style={disabled ? styles.disabledWrapper : undefined}
        >
          <View style={styles.googleButton}>
            <Ionicons name="logo-google" size={20} color={SOCIAL_GOOGLE_BLUE} />
            <Text style={styles.googleText}>Continue with Google</Text>
          </View>
        </PressableScale>
      )}

      {/* Apple — always dark */}
      {showApple && (
        <PressableScale
          onPress={onApplePress}
          disabled={disabled}
          accessibilityLabel="Continue with Apple"
          accessibilityRole="button"
          accessibilityState={{ disabled }}
          style={disabled ? styles.disabledWrapper : undefined}
        >
          <View style={styles.appleButton}>
            <Ionicons name="logo-apple" size={20} color="#FFFFFF" />
            <Text style={styles.appleText}>Continue with Apple</Text>
          </View>
        </PressableScale>
      )}
    </View>
  );
}

/** TikTok brand icon via FontAwesome6. */
function TikTokIcon() {
  return <FontAwesome6 name="tiktok" size={18} color="#FFFFFF" />;
}

const styles = StyleSheet.create({
  container: {
    gap: THEME.spacing.md,
  },
  disabledWrapper: {
    opacity: 0.5,
  },
  tiktokButton: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    minHeight: BUTTON_HEIGHT,
    borderRadius: THEME.radius.pill,
    borderWidth: 1,
    borderColor: "rgba(255, 255, 255, 0.2)",
    backgroundColor: "#000000",
    paddingHorizontal: THEME.spacing.lg,
    gap: THEME.spacing.sm + 2,
  },
  tiktokText: {
    fontFamily: FONTS.bodyMedium,
    fontSize: 16,
    color: "#FFFFFF",
  },
  googleButton: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    minHeight: BUTTON_HEIGHT,
    borderRadius: THEME.radius.pill,
    borderWidth: 1,
    borderColor: "rgba(255, 255, 255, 0.12)",
    backgroundColor: "rgba(255, 255, 255, 0.92)",
    paddingHorizontal: THEME.spacing.lg,
    gap: THEME.spacing.sm + 2,
  },
  googleText: {
    fontFamily: FONTS.bodyMedium,
    fontSize: 16,
    color: SOCIAL_GOOGLE_TEXT,
  },
  appleButton: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    minHeight: BUTTON_HEIGHT,
    borderRadius: THEME.radius.pill,
    borderWidth: 1,
    borderColor: "rgba(255, 255, 255, 0.2)",
    backgroundColor: "rgba(0, 0, 0, 0.65)",
    paddingHorizontal: THEME.spacing.lg,
    gap: THEME.spacing.sm + 2,
  },
  appleText: {
    fontFamily: FONTS.bodyMedium,
    fontSize: 16,
    color: "#FFFFFF",
  },
});
