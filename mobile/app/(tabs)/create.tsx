import { View, Text, Pressable, ScrollView, StyleSheet } from "react-native";
import { useRouter } from "expo-router";
import { Ionicons } from "@expo/vector-icons";
import Animated, { FadeInDown } from "react-native-reanimated";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { BG_PAGE } from "../../constants/colors";
import { THEME } from "../../constants/theme";
import { PageBackground } from "../../components/ui/PageBackground";
import { useTheme } from "../../lib/theme-context";
import { FONTS } from "../../hooks/useFonts";

/* ------------------------------------------------------------------ */
/*  Feature definitions                                                */
/* ------------------------------------------------------------------ */

interface Feature {
  key: string;
  icon: keyof typeof Ionicons.glyphMap;
  name: string;
  description: string;
  active: boolean;
  route?: string;
}

const FEATURES: Feature[] = [
  {
    key: "glow-up",
    icon: "sparkles",
    name: "Glow Up",
    description: "AI-powered style transformation",
    active: true,
    route: "/upload",
  },
  {
    key: "style-check",
    icon: "shirt-outline",
    name: "Style Check",
    description: "Get feedback on your outfit",
    active: false,
  },
  {
    key: "skin-care",
    icon: "water-outline",
    name: "Skin Care",
    description: "Personalized skincare routine",
    active: false,
  },
  {
    key: "hair-style",
    icon: "cut-outline",
    name: "Hair Style",
    description: "Find your perfect hairstyle",
    active: false,
  },
];

/* ------------------------------------------------------------------ */
/*  Screen                                                             */
/* ------------------------------------------------------------------ */

export default function CreateScreen() {
  const router = useRouter();
  const { theme } = useTheme();
  const insets = useSafeAreaInsets();

  const handleFeaturePress = (feature: Feature) => {
    if (feature.active && feature.route) {
      router.push(feature.route as any);
    }
  };

  return (
    <View style={styles.container}>
      <PageBackground overlayOpacity={0.85} />
      <ScrollView
        contentContainerStyle={[
          styles.scrollContent,
          { paddingTop: insets.top + 24, paddingBottom: 80 },
        ]}
        showsVerticalScrollIndicator={false}
      >
        {/* Header */}
        <Animated.Text
          entering={FadeInDown.duration(500).delay(80)}
          style={styles.title}
        >
          Create
        </Animated.Text>
        <Animated.Text
          entering={FadeInDown.duration(500).delay(160)}
          style={styles.subtitle}
        >
          What would you like to do?
        </Animated.Text>

        {/* 2-column grid */}
        <View style={styles.grid}>
          {FEATURES.map((feature, index) => {
            const isActive = feature.active;

            return (
              <Animated.View
                key={feature.key}
                entering={FadeInDown.duration(500).delay(240 + index * 80)}
                style={styles.gridCell}
              >
                <Pressable
                  onPress={() => handleFeaturePress(feature)}
                  disabled={!isActive}
                  style={({ pressed }) => [
                    styles.box,
                    isActive
                      ? {
                          borderColor: theme.accent,
                          backgroundColor: theme.accent + "1A",
                        }
                      : styles.boxInactive,
                    isActive && pressed && styles.boxPressed,
                  ]}
                  accessibilityRole="button"
                  accessibilityLabel={
                    isActive
                      ? feature.name
                      : `${feature.name} - coming soon`
                  }
                  accessibilityState={{ disabled: !isActive }}
                >
                  <Ionicons
                    name={feature.icon}
                    size={28}
                    color={isActive ? theme.accent : THEME.colors.textMuted}
                    style={styles.icon}
                  />

                  <Text
                    style={[
                      styles.featureName,
                      !isActive && styles.featureNameInactive,
                    ]}
                  >
                    {feature.name}
                  </Text>

                  <Text
                    style={[
                      styles.featureDesc,
                      !isActive && styles.featureDescInactive,
                    ]}
                  >
                    {feature.description}
                  </Text>

                  {!isActive && (
                    <Text style={styles.comingSoon}>COMING SOON</Text>
                  )}
                </Pressable>
              </Animated.View>
            );
          })}
        </View>
      </ScrollView>
    </View>
  );
}

/* ------------------------------------------------------------------ */
/*  Styles                                                             */
/* ------------------------------------------------------------------ */

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: BG_PAGE,
  },
  scrollContent: {
    paddingHorizontal: 20,
  },

  /* Header */
  title: {
    fontFamily: FONTS.display,
    fontSize: 32,
    color: THEME.colors.textPrimary,
    marginBottom: 4,
  },
  subtitle: {
    fontFamily: FONTS.body,
    fontSize: 15,
    color: THEME.colors.textSecondary,
    marginBottom: 24,
  },

  /* Grid */
  grid: {
    flexDirection: "row",
    flexWrap: "wrap",
    marginHorizontal: -6,
  },
  gridCell: {
    width: "50%",
    paddingHorizontal: 6,
    marginBottom: 12,
  },

  /* Box shared */
  box: {
    borderWidth: 1,
    borderRadius: THEME.radius.lg,
    padding: THEME.spacing.lg,
    aspectRatio: 1,
    justifyContent: "flex-start",
  },
  boxInactive: {
    backgroundColor: THEME.colors.surface,
    borderColor: THEME.colors.border,
  },
  boxPressed: {
    opacity: 0.8,
  },

  /* Icon */
  icon: {
    marginBottom: 12,
  },

  /* Feature text */
  featureName: {
    fontFamily: FONTS.bodyMedium,
    fontSize: 15,
    color: THEME.colors.textPrimary,
    marginBottom: 4,
  },
  featureNameInactive: {
    color: THEME.colors.textMuted,
  },
  featureDesc: {
    fontFamily: FONTS.body,
    fontSize: 12,
    color: THEME.colors.textSecondary,
    lineHeight: 16,
  },
  featureDescInactive: {
    color: THEME.colors.textDisabled,
  },

  /* Coming soon label */
  comingSoon: {
    fontFamily: FONTS.bodyMedium,
    fontSize: 10,
    color: THEME.colors.textMuted,
    letterSpacing: 1,
    marginTop: "auto",
  },
});
