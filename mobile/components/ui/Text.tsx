/**
 * Typography primitives — single source of truth for text styling.
 *
 * Use these instead of the raw `react-native` Text so every screen gets
 * the theme typography + font family consistently.
 *
 * - <Heading size="md|lg" display> — Instrument Serif by default
 * - <Body weight="regular|medium|semibold|bold"> — Inter
 * - <Caption weight="regular|medium|semibold"> — smaller Inter for secondary text
 * - <Label> — uppercase, letter-spaced 11pt label ("magazine style")
 */
import type { ReactNode } from "react";
import { Text as RNText, type TextProps as RNTextProps, type StyleProp, type TextStyle } from "react-native";
import { THEME } from "../../constants/theme";
import { FONTS } from "../../hooks/useFonts";

type SemanticColor = "primary" | "secondary" | "muted" | "disabled" | "destructive" | "inherit";
type ColorProp = SemanticColor | string;

interface BaseTextProps extends Omit<RNTextProps, "style"> {
  children?: ReactNode;
  color?: ColorProp;
  style?: StyleProp<TextStyle>;
}

function resolveColor(color: ColorProp | undefined): string | undefined {
  if (!color || color === "inherit") return undefined;
  switch (color) {
    case "primary":
      return THEME.colors.textPrimary;
    case "secondary":
      return THEME.colors.textSecondary;
    case "muted":
      return THEME.colors.textMuted;
    case "disabled":
      return THEME.colors.textDisabled;
    case "destructive":
      return THEME.colors.destructive;
    default:
      return color;
  }
}

// ─── Heading ─────────────────────────────────────────────────────────────────

interface HeadingProps extends BaseTextProps {
  size?: "md" | "lg";
  /** Use Instrument Serif display face (default). Set false for Inter semibold. */
  display?: boolean;
}

export function Heading({
  size = "md",
  display = true,
  color = "primary",
  style,
  children,
  ...rest
}: HeadingProps) {
  const typo = size === "lg" ? THEME.typography.headingLg : THEME.typography.heading;
  return (
    <RNText
      accessibilityRole="header"
      {...rest}
      style={[
        {
          ...typo,
          fontFamily: display ? FONTS.display : FONTS.bodySemiBold,
          color: resolveColor(color),
        },
        style,
      ]}
    >
      {children}
    </RNText>
  );
}

// ─── Body ────────────────────────────────────────────────────────────────────

type BodyWeight = "regular" | "medium" | "semibold" | "bold";

const BODY_FONT: Record<BodyWeight, string> = {
  regular: FONTS.body,
  medium: FONTS.bodyMedium,
  semibold: FONTS.bodySemiBold,
  bold: FONTS.bodyBold,
};

interface BodyProps extends BaseTextProps {
  weight?: BodyWeight;
}

export function Body({ weight = "regular", color = "primary", style, children, ...rest }: BodyProps) {
  return (
    <RNText
      {...rest}
      style={[
        {
          ...THEME.typography.body,
          fontFamily: BODY_FONT[weight],
          color: resolveColor(color),
        },
        style,
      ]}
    >
      {children}
    </RNText>
  );
}

// ─── Caption ─────────────────────────────────────────────────────────────────

type CaptionWeight = "regular" | "medium" | "semibold";

const CAPTION_FONT: Record<CaptionWeight, string> = {
  regular: FONTS.body,
  medium: FONTS.bodyMedium,
  semibold: FONTS.bodySemiBold,
};

interface CaptionProps extends BaseTextProps {
  weight?: CaptionWeight;
}

export function Caption({ weight = "regular", color = "secondary", style, children, ...rest }: CaptionProps) {
  return (
    <RNText
      {...rest}
      style={[
        {
          ...THEME.typography.caption,
          fontFamily: CAPTION_FONT[weight],
          color: resolveColor(color),
        },
        style,
      ]}
    >
      {children}
    </RNText>
  );
}

// ─── Label ───────────────────────────────────────────────────────────────────

const LABEL_STYLE = {
  fontFamily: FONTS.bodySemiBold,
  fontSize: 11,
  lineHeight: 14,
  letterSpacing: 1,
  textTransform: "uppercase" as const,
};

export function Label({ color = "secondary", style, children, ...rest }: BaseTextProps) {
  return (
    <RNText
      {...rest}
      style={[
        LABEL_STYLE,
        { color: resolveColor(color) },
        style,
      ]}
    >
      {children}
    </RNText>
  );
}
