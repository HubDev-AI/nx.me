import { useState } from "react";
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
import { useCapabilities } from "../../lib/capabilities";
import { useFeatures } from "../../lib/features-context";
import { PaywallModal } from "../../components/paywall/PaywallModal";

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
  /** True when feature is active but requires a Pro upgrade to use. */
  locked?: boolean;
  route?: FeatureRoute;
}

const GRID_COLUMN_GAP = THEME.spacing.md;
const INACTIVE_ICON_BG = "rgba(255, 255, 255, 0.04)";

/**
 * Feature-card entry animation timing. Cards staggered from
 * ``CARD_ENTRY_BASE_DELAY_MS`` upward so the grid "cascades" in rather
 * than appearing as one slab.
 */
const CARD_ENTRY_BASE_DELAY_MS = 240;
const CARD_STAGGER_INCREMENT_MS = 50;

const STATIC_COMING_SOON: Feature[] = [
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
  const isLocked = feature.locked ?? false;
  const pressable = isActive || isLocked;
  const scale = useSharedValue(1);
  const pressStyle = useAnimatedStyle(() => ({
    transform: [{ scale: scale.value }],
  }));
  const { fadeInDown } = useEntering();

  return (
    <Animated.View
      key={feature.key}
      entering={fadeInDown(
        CARD_ENTRY_BASE_DELAY_MS + index * CARD_STAGGER_INCREMENT_MS,
        THEME.animation.duration.normal,
      )}
      style={styles.gridCell}
    >
      <Animated.View style={pressStyle}>
        <Pressable
          onPress={() => onPress(feature)}
          onPressIn={() => {
            if (pressable) scale.value = withSpring(0.97, THEME.animation.press);
          }}
          onPressOut={() => {
            scale.value = withSpring(1, THEME.animation.press);
          }}
          disabled={!pressable}
          style={[
            styles.box,
            isActive || isLocked
              ? [
                  {
                    borderColor: accent + THEME.alpha.strong,
                    backgroundColor: accent + THEME.alpha.faint,
                  },
                  THEME.shadow.glow(accent),
                ]
              : styles.boxInactive,
          ]}
          accessibilityRole="button"
          accessibilityLabel={
            isActive && !isLocked
              ? feature.name
              : isLocked
                ? `${feature.name} - Pro`
                : `${feature.name} - coming soon`
          }
          accessibilityState={{ disabled: !pressable }}
        >
          {/* Icon wrapper with accent tint background for active/locked */}
          <View
            style={[
              styles.iconWrapper,
              isActive || isLocked
                ? { backgroundColor: accent + THEME.alpha.soft }
                : { backgroundColor: INACTIVE_ICON_BG },
            ]}
          >
            <Ionicons
              name={feature.icon}
              size={32}
              color={isActive || isLocked ? accent : THEME.colors.textMuted}
            />
          </View>

          <Body
            weight="semibold"
            color={isActive || isLocked ? "primary" : "muted"}
            style={styles.featureName}
          >
            {feature.name}
          </Body>

          <Caption
            color={isActive || isLocked ? "secondary" : "disabled"}
            style={styles.featureDesc}
          >
            {feature.description}
          </Caption>

          {!isActive && !isLocked && (
            <View style={styles.comingSoonBadge}>
              <Label color="muted" style={styles.comingSoonLabel}>
                Coming soon
              </Label>
            </View>
          )}

          {isLocked && (
            <View style={styles.proBadge}>
              <Ionicons name="lock-closed" size={9} color={accent} />
              <Label style={[styles.proBadgeLabel, { color: accent }]}>
                Pro
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
  const { canUseMakeup } = useCapabilities();
  const { features } = useFeatures();
  const [paywallVisible, setPaywallVisible] = useState(false);

  const glowUpFeature: Feature = {
    key: "glow-up",
    icon: "sparkles",
    name: "Glow Up",
    description: "Upload a selfie — get an AI glow-up",
    active: true,
    route: "/upload",
  };

  const makeupFeature: Feature | null = features.makeup_enabled
    ? {
        key: "makeup",
        icon: "color-palette-outline",
        name: "AI Makeup",
        description: "See how makeup looks on you",
        active: canUseMakeup,
        locked: !canUseMakeup,
        route: "/upload",
      }
    : null;

  const allFeatures: Feature[] = [
    glowUpFeature,
    ...(makeupFeature ? [makeupFeature] : []),
    ...STATIC_COMING_SOON,
  ];

  const handleFeaturePress = (feature: Feature) => {
    if (feature.locked) {
      setPaywallVisible(true);
      return;
    }
    if (feature.active && feature.route) {
      if (feature.key === "makeup") {
        router.push({ pathname: "/upload", params: { action: "makeup" } });
      } else {
        router.push(feature.route);
      }
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
          {allFeatures.map((feature, index) => (
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

      <PaywallModal
        visible={paywallVisible}
        onClose={() => setPaywallVisible(false)}
        action="makeup"
      />
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

  /* Pro lock badge */
  proBadge: {
    marginTop: "auto",
    alignSelf: "flex-start",
    flexDirection: "row",
    alignItems: "center",
    gap: THEME.spacing.xs / 2,
    backgroundColor: THEME.colors.surfaceElevated,
    borderRadius: THEME.radius.sm,
    borderCurve: "continuous",
    paddingHorizontal: THEME.spacing.sm,
    paddingVertical: THEME.spacing.xs / 2,
  },
  proBadgeLabel: {
    fontSize: 9,
    letterSpacing: 1.2,
  },
});
