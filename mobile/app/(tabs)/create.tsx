import { Pressable, ScrollView, StyleSheet, View } from "react-native";
import { useRouter } from "expo-router";
import { Ionicons } from "@expo/vector-icons";
import Animated, {
  useAnimatedStyle,
  useSharedValue,
  withSpring,
} from "react-native-reanimated";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { TAB_BAR_HEIGHT } from "./_layout";

import { THEME } from "../../constants/theme";
import { PageBackground } from "../../components/ui/PageBackground";
import { Body, Caption, Heading, Label } from "../../components/ui/Text";
import { useTheme } from "../../lib/theme-context";
import { useEntering } from "../../lib/hooks/use-entering";

/* ------------------------------------------------------------------ */
/*  Feature definitions                                                */
/* ------------------------------------------------------------------ */

/**
 * Route targets for active features. Expo Router typed-routes require a
 * concrete union here (not a bare `string`) for `router.push` to type-check.
 * Expand as more features ship.
 */
type FeatureRoute = "/upload";

interface Feature {
  key: string;
  icon: keyof typeof Ionicons.glyphMap;
  name: string;
  description: string;
  active: boolean;
  route?: FeatureRoute;
}

const GRID_COLUMN_GAP = THEME.spacing.md;
const INACTIVE_ICON_BG = "rgba(255, 255, 255, 0.04)";

const FEATURES: Feature[] = [
  {
    key: "glow-up",
    icon: "sparkles",
    name: "Glow Up",
    description: "Upload a selfie — get an AI glow-up",
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
          <View
            style={[
              styles.iconWrapper,
              isActive
                ? { backgroundColor: accent + "1A" }
                : { backgroundColor: INACTIVE_ICON_BG },
            ]}
          >
            <Ionicons
              name={feature.icon}
              size={32}
              color={isActive ? accent : THEME.colors.textMuted}
            />
          </View>

          <Body
            weight="semibold"
            color={isActive ? "primary" : "muted"}
            style={styles.featureName}
          >
            {feature.name}
          </Body>

          <Caption
            color={isActive ? "secondary" : "disabled"}
            style={styles.featureDesc}
          >
            {feature.description}
          </Caption>

          {!isActive && (
            <View style={styles.comingSoonBadge}>
              <Label color="muted" style={styles.comingSoonLabel}>
                Coming soon
              </Label>
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
      router.push(feature.route);
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
        <Animated.View entering={fadeInDown(80, THEME.animation.duration.fast)}>
          <Heading size="lg" color="primary" style={styles.title} maxFontSizeMultiplier={1.3}>
            Create
          </Heading>
        </Animated.View>
        <Animated.View entering={fadeInDown(160, THEME.animation.duration.fast)}>
          <Body color="secondary" style={styles.subtitle} maxFontSizeMultiplier={1.3}>
            What would you like to do?
          </Body>
        </Animated.View>

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
    marginBottom: THEME.spacing.xs,
  },
  subtitle: {
    marginBottom: THEME.spacing.lg,
  },

  /* Subtitle divider */
  subtitleDivider: {
    height: 1,
    backgroundColor: THEME.colors.glassBorder,
    marginBottom: THEME.spacing.xl,
  },

  /* Grid — flex-basis + gap instead of negative margin */
  grid: {
    flexDirection: "row",
    flexWrap: "wrap",
    gap: GRID_COLUMN_GAP,
  },
  gridCell: {
    flexBasis: "48%",
    flexGrow: 1,
    flexShrink: 0,
  },

  /* Box shared */
  box: {
    borderWidth: 1,
    borderRadius: THEME.radius.lg,
    borderCurve: "continuous",
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
    borderCurve: "continuous",
    alignItems: "center",
    justifyContent: "center",
    marginBottom: THEME.spacing.md,
  },

  /* Feature text */
  featureName: {
    marginBottom: THEME.spacing.xs,
  },
  featureDesc: {
    lineHeight: 16,
  },

  /* Coming soon badge */
  comingSoonBadge: {
    marginTop: "auto",
    alignSelf: "flex-start",
    backgroundColor: THEME.colors.surfaceElevated,
    borderRadius: THEME.radius.sm,
    borderCurve: "continuous",
    paddingHorizontal: THEME.spacing.sm,
    paddingVertical: THEME.spacing.xs / 2,
  },
  comingSoonLabel: {
    fontSize: 9,
    letterSpacing: 1.2,
  },
});
