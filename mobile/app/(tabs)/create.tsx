import { View, Text, Pressable, ScrollView, StyleSheet } from "react-native";
import { useRouter } from "expo-router";
import { Ionicons } from "@expo/vector-icons";
import Animated, {
  useSharedValue,
  useAnimatedStyle,
  withSpring,
} from "react-native-reanimated";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { TAB_BAR_HEIGHT } from "./_layout";

import { THEME } from "../../constants/theme";
import { PageBackground } from "../../components/ui/PageBackground";
import { useTheme } from "../../lib/theme-context";
import { useEntering } from "../../lib/hooks/use-entering";
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
/*  Feature card with spring press scale                               */
/* ------------------------------------------------------------------ */

function FeatureCard({
  feature,
  index,
  onPress,
  accent,
}: {
  feature: Feature;
  index: number;
  onPress: (f: Feature) => void;
  accent: string;
}) {
  const isActive = feature.active;
  const scale = useSharedValue(1);
  const pressStyle = useAnimatedStyle(() => ({
    transform: [{ scale: scale.value }],
  }));
  const { fadeInDown } = useEntering();

  return (
    <Animated.View
      key={feature.key}
      entering={fadeInDown(240 + index * 50, THEME.animation.duration.normal)}
      style={styles.gridCell}
    >
      <Animated.View style={pressStyle}>
        <Pressable
          onPress={() => onPress(feature)}
          onPressIn={() => {
            if (isActive) scale.value = withSpring(0.97, THEME.animation.press);
          }}
          onPressOut={() => {
            scale.value = withSpring(1, THEME.animation.press);
          }}
          disabled={!isActive}
          style={[
            styles.box,
            isActive
              ? [
                  {
                    borderColor: accent + "4D",
                    backgroundColor: accent + "0F",
                  },
                  THEME.shadow.glow(accent),
                ]
              : styles.boxInactive,
          ]}
          accessibilityRole="button"
          accessibilityLabel={
            isActive
              ? feature.name
              : `${feature.name} - coming soon`
          }
          accessibilityState={{ disabled: !isActive }}
        >
          {/* Icon wrapper with accent tint background for active */}
          <View style={[
            styles.iconWrapper,
            isActive
              ? { backgroundColor: accent + "1A" }
              : { backgroundColor: THEME.colors.surfaceElevated },
          ]}>
            <Ionicons
              name={feature.icon}
              size={32}
              color={isActive ? accent : THEME.colors.textMuted}
            />
          </View>

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
            <View style={styles.comingSoonBadge}>
              <Text style={styles.comingSoon}>COMING SOON</Text>
            </View>
          )}
        </Pressable>
      </Animated.View>
    </Animated.View>
  );
}

/* ------------------------------------------------------------------ */
/*  Screen                                                             */
/* ------------------------------------------------------------------ */

export default function CreateScreen() {
  const router = useRouter();
  const { theme } = useTheme();
  const insets = useSafeAreaInsets();
  const { fadeInDown } = useEntering();

  const handleFeaturePress = (feature: Feature) => {
    if (feature.active && feature.route) {
      router.push(feature.route as `/${string}`);
    }
  };

  return (
    <View style={styles.container}>
      <PageBackground overlayOpacity={0.85} />
      <ScrollView
        contentContainerStyle={[
          styles.scrollContent,
          { paddingTop: insets.top + THEME.spacing.xxl, paddingBottom: TAB_BAR_HEIGHT },
        ]}
        showsVerticalScrollIndicator={false}
      >
        {/* Header */}
        <Animated.Text
          entering={fadeInDown(80, THEME.animation.duration.fast)}
          style={styles.title}
          maxFontSizeMultiplier={1.3}
        >
          Create
        </Animated.Text>
        <Animated.Text
          entering={fadeInDown(160, THEME.animation.duration.fast)}
          style={styles.subtitle}
          maxFontSizeMultiplier={1.3}
        >
          What would you like to do?
        </Animated.Text>

        {/* Divider below subtitle */}
        <Animated.View
          entering={fadeInDown(200, THEME.animation.duration.fast)}
          style={styles.subtitleDivider}
        />

        {/* 2-column grid */}
        <View style={styles.grid}>
          {FEATURES.map((feature, index) => (
            <FeatureCard
              key={feature.key}
              feature={feature}
              index={index}
              onPress={handleFeaturePress}
              accent={theme.accent}
            />
          ))}
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
    backgroundColor: THEME.colors.bg,
  },
  scrollContent: {
    paddingHorizontal: THEME.spacing.xl,
  },

  /* Header */
  title: {
    fontFamily: FONTS.display,
    fontSize: 32,
    color: THEME.colors.textPrimary,
    letterSpacing: THEME.typography.headingLg.letterSpacing,
    marginBottom: THEME.spacing.xs,
  },
  subtitle: {
    fontFamily: FONTS.body,
    fontSize: 15,
    color: THEME.colors.textSecondary,
    letterSpacing: THEME.typography.body.letterSpacing,
    marginBottom: THEME.spacing.lg,
  },

  /* Subtitle divider */
  subtitleDivider: {
    height: 1,
    backgroundColor: THEME.colors.glassBorder,
    marginBottom: THEME.spacing.xl,
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
    marginBottom: THEME.spacing.md,
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

  /* Icon wrapper — circular background behind icon */
  iconWrapper: {
    width: 48,
    height: 48,
    borderRadius: THEME.radius.md,
    alignItems: "center",
    justifyContent: "center",
    marginBottom: THEME.spacing.md,
  },

  /* Feature text */
  featureName: {
    fontFamily: FONTS.bodySemiBold,
    fontSize: 15,
    color: THEME.colors.textPrimary,
    letterSpacing: THEME.typography.heading.letterSpacing,
    marginBottom: THEME.spacing.xs,
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

  /* Coming soon badge */
  comingSoonBadge: {
    marginTop: "auto",
    alignSelf: "flex-start",
    backgroundColor: THEME.colors.surfaceElevated,
    borderRadius: THEME.radius.sm,
    paddingHorizontal: THEME.spacing.sm,
    paddingVertical: THEME.spacing.xs / 2,
  },
  comingSoon: {
    fontFamily: FONTS.bodySemiBold,
    fontSize: 9,
    color: THEME.colors.textMuted,
    letterSpacing: 1.2,
  },
});
