import React from "react";
import { View, Text, Pressable, StyleSheet } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import * as Sentry from "@sentry/react-native";

import { THEME } from "../../constants/theme";
import { FONTS } from "../../hooks/useFonts";

interface Props {
  children: React.ReactNode;
}

interface State {
  hasError: boolean;
  error: Error | null;
}

/**
 * Top-level error boundary that catches unhandled JS errors in the
 * React tree and renders a recovery screen instead of a white/blank page.
 */
export class ErrorBoundary extends React.Component<Props, State> {
  state: State = { hasError: false, error: null };

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, info: React.ErrorInfo) {
    Sentry.captureException(error, {
      contexts: {
        react: { componentStack: info.componentStack ?? undefined },
      },
      tags: { source: "errorBoundary" },
    });
    if (__DEV__) {
      console.error("[ErrorBoundary]", error, info);
    }
  }

  private handleReset = () => {
    this.setState({ hasError: false, error: null });
  };

  render() {
    if (this.state.hasError) {
      return (
        <View style={styles.container} accessibilityRole="alert">
          <View style={styles.iconCircle}>
            <Ionicons
              name="warning-outline"
              size={32}
              color={THEME.colors.textSecondary}
            />
          </View>
          <Text style={styles.title}>Something went wrong</Text>
          <Text style={styles.message} numberOfLines={4}>
            {this.state.error?.message ?? "Something unexpected happened."}
          </Text>
          <Pressable
            style={styles.button}
            onPress={this.handleReset}
            accessibilityLabel="Try again"
            accessibilityRole="button"
          >
            <Ionicons name="refresh-outline" size={18} color={THEME.colors.bg} />
            <Text style={styles.buttonText}>Try again</Text>
          </Pressable>
        </View>
      );
    }

    return this.props.children;
  }
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: THEME.colors.bg,
    alignItems: "center",
    justifyContent: "center",
    paddingHorizontal: THEME.spacing.xxxl,
    gap: THEME.spacing.sm,
  },
  iconCircle: {
    width: 64,
    height: 64,
    borderRadius: 32,
    backgroundColor: THEME.colors.glass,
    borderWidth: 1,
    borderColor: THEME.colors.glassBorder,
    alignItems: "center",
    justifyContent: "center",
    marginBottom: THEME.spacing.md,
  },
  title: {
    fontFamily: FONTS.bodySemiBold,
    fontSize: 22,
    color: THEME.colors.textPrimary,
    letterSpacing: THEME.typography.heading.letterSpacing,
    textAlign: "center",
  },
  message: {
    fontFamily: FONTS.body,
    ...THEME.typography.caption,
    color: THEME.colors.textSecondary,
    textAlign: "center",
    marginTop: THEME.spacing.xs,
  },
  button: {
    flexDirection: "row",
    alignItems: "center",
    gap: THEME.spacing.sm,
    marginTop: THEME.spacing.xl,
    backgroundColor: THEME.colors.textPrimary,
    paddingHorizontal: THEME.spacing.xxl,
    paddingVertical: THEME.spacing.md,
    borderRadius: THEME.radius.pill,
    minHeight: 48,
  },
  buttonText: {
    fontFamily: FONTS.bodySemiBold,
    fontSize: 15,
    color: THEME.colors.bg,
  },
});
