import { View, Text, Pressable, StyleSheet } from "react-native";
import { useRouter } from "expo-router";
import { Ionicons } from "@expo/vector-icons";

import {
  BG_PAGE,
  TEXT_PRIMARY,
  TEXT_SECONDARY,
  CTA_PRIMARY,
  CTA_PRESSED,
  COLORS,
} from "../../constants/colors";

/**
 * Create tab — navigates to the upload screen.
 * Shows a quick CTA; tapping the tab or the button routes to /upload.
 */
export default function CreateScreen() {
  const router = useRouter();

  const handlePress = () => {
    router.push("/upload");
  };

  return (
    <View style={styles.container}>
      <View style={styles.iconCircle}>
        <Ionicons name="sparkles" size={28} color="#FFFFFF" />
      </View>
      <Text style={styles.title}>Create your glow-up</Text>
      <Text style={styles.subtitle}>
        Upload a photo and get AI-powered style suggestions
      </Text>
      <Pressable
        onPress={handlePress}
        style={({ pressed }) => [
          styles.ctaButton,
          pressed && styles.ctaButtonPressed,
        ]}
        accessibilityLabel="Upload a photo for glow-up"
        accessibilityRole="button"
      >
        <Ionicons name="camera-outline" size={20} color="#FFFFFF" />
        <Text style={styles.ctaText}>Upload Photo</Text>
      </Pressable>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: BG_PAGE,
    alignItems: "center",
    justifyContent: "center",
    padding: 24,
  },
  iconCircle: {
    width: 64,
    height: 64,
    borderRadius: 32,
    backgroundColor: COLORS.after[500],
    alignItems: "center",
    justifyContent: "center",
    marginBottom: 16,
  },
  title: {
    fontSize: 24,
    fontWeight: "700",
    color: TEXT_PRIMARY,
    marginBottom: 8,
  },
  subtitle: {
    fontSize: 16,
    color: TEXT_SECONDARY,
    textAlign: "center",
    marginBottom: 24,
    lineHeight: 22,
  },
  ctaButton: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: CTA_PRIMARY,
    borderRadius: 12,
    paddingVertical: 14,
    paddingHorizontal: 32,
    gap: 8,
    minHeight: 48,
  },
  ctaButtonPressed: {
    backgroundColor: CTA_PRESSED,
  },
  ctaText: {
    fontSize: 16,
    fontWeight: "700",
    color: "#FFFFFF",
  },
});
