/**
 * Screen — page-level layout wrapper.
 *
 * Wraps children in SafeAreaView + optional ScrollView with
 * `contentInsetAdjustmentBehavior="automatic"` so iOS handles the large-title
 * header and safe-area insets correctly (per expo Router + building-native-ui
 * guidance).
 *
 * Defaults:
 *   scroll = true
 *   edges = ["bottom"]  (Stack header handles top; override for modal screens)
 */
import type { ReactNode } from "react";
import {
  ScrollView,
  StyleSheet,
  View,
  type ScrollViewProps,
  type StyleProp,
  type ViewStyle,
} from "react-native";
import { SafeAreaView, type Edge } from "react-native-safe-area-context";
import { THEME } from "../../constants/theme";

interface ScreenProps {
  children: ReactNode;
  /** Wrap in ScrollView with `contentInsetAdjustmentBehavior="automatic"`. */
  scroll?: boolean;
  /** Safe-area edges to pad. Default ["bottom"] — Stack handles top. */
  edges?: Edge[];
  /** Background color override. Defaults to THEME.colors.bg. */
  backgroundColor?: string;
  /** Style for outer SafeAreaView. */
  style?: StyleProp<ViewStyle>;
  /** Style applied to the content container (scroll mode only). */
  contentContainerStyle?: StyleProp<ViewStyle>;
  /** Forwarded to the inner ScrollView. */
  keyboardShouldPersistTaps?: ScrollViewProps["keyboardShouldPersistTaps"];
  /** Forwarded to the inner ScrollView. */
  showsVerticalScrollIndicator?: boolean;
  /** Hide SafeAreaView padding entirely (for full-bleed screens). */
  edgeless?: boolean;
}

export function Screen({
  children,
  scroll = true,
  edges = ["bottom"],
  backgroundColor = THEME.colors.bg,
  style,
  contentContainerStyle,
  keyboardShouldPersistTaps = "handled",
  showsVerticalScrollIndicator = false,
  edgeless = false,
}: ScreenProps) {
  const Outer = edgeless ? View : SafeAreaView;
  const outerProps = edgeless ? {} : { edges };

  if (scroll) {
    return (
      <Outer {...outerProps} style={[styles.flex, { backgroundColor }, style]}>
        <ScrollView
          style={styles.flex}
          contentContainerStyle={[styles.content, contentContainerStyle]}
          contentInsetAdjustmentBehavior="automatic"
          keyboardShouldPersistTaps={keyboardShouldPersistTaps}
          showsVerticalScrollIndicator={showsVerticalScrollIndicator}
        >
          {children}
        </ScrollView>
      </Outer>
    );
  }

  return (
    <Outer {...outerProps} style={[styles.flex, { backgroundColor }, style]}>
      {children}
    </Outer>
  );
}

const styles = StyleSheet.create({
  flex: { flex: 1 },
  content: {
    padding: THEME.spacing.lg,
    gap: THEME.spacing.lg,
  },
});
