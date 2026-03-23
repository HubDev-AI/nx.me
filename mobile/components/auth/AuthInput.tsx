import { useState, useCallback, forwardRef } from "react";
import {
  View,
  Text,
  TextInput,
  StyleSheet,
  Pressable,
  Platform,
  type TextInputProps,
} from "react-native";
import { Ionicons } from "@expo/vector-icons";

import { THEME } from "../../constants/theme";
import { FONTS } from "../../hooks/useFonts";

interface AuthInputProps extends Omit<TextInputProps, "style"> {
  label: string;
  error?: string;
  isPassword?: boolean;
}

const MIN_TOUCH_TARGET = 44;
const INPUT_HEIGHT = 48;
const FONT_SIZE_BODY = 16;

export const AuthInput = forwardRef<TextInput, AuthInputProps>(
  function AuthInput(
    { label, error, isPassword = false, onFocus, onBlur, ...rest },
    ref,
  ) {
    const [isFocused, setIsFocused] = useState(false);
    const [isSecureVisible, setIsSecureVisible] = useState(false);

    const handleFocus = useCallback(
      (e: Parameters<NonNullable<TextInputProps["onFocus"]>>[0]) => {
        setIsFocused(true);
        onFocus?.(e);
      },
      [onFocus],
    );

    const handleBlur = useCallback(
      (e: Parameters<NonNullable<TextInputProps["onBlur"]>>[0]) => {
        setIsFocused(false);
        onBlur?.(e);
      },
      [onBlur],
    );

    const toggleSecureVisibility = useCallback(() => {
      setIsSecureVisible((prev) => !prev);
    }, []);

    const borderColor = error
      ? THEME.colors.destructive
      : isFocused
        ? THEME.colors.borderFocused
        : THEME.colors.glassBorder;

    return (
      <View style={styles.container}>
        <Text style={styles.label} accessibilityRole="text">
          {label}
        </Text>
        <View style={[styles.inputWrapper, { borderColor }]}>
          <TextInput
            ref={ref}
            style={styles.input}
            placeholderTextColor={THEME.colors.textDisabled}
            selectionColor={THEME.colors.textPrimary}
            secureTextEntry={isPassword && !isSecureVisible}
            onFocus={handleFocus}
            onBlur={handleBlur}
            accessibilityLabel={label}
            accessibilityState={{ disabled: rest.editable === false }}
            testID={`input-${label.toLowerCase().replace(/\s+/g, "-")}`}
            {...rest}
          />
          {isPassword && (
            <Pressable
              onPress={toggleSecureVisibility}
              style={styles.eyeButton}
              accessibilityLabel={
                isSecureVisible ? "Hide password" : "Show password"
              }
              accessibilityRole="button"
              hitSlop={8}
            >
              <Ionicons
                name={isSecureVisible ? "eye-off-outline" : "eye-outline"}
                size={20}
                color={THEME.colors.textSecondary}
              />
            </Pressable>
          )}
        </View>
        {error ? (
          <View style={styles.errorRow}>
            <Ionicons
              name="alert-circle-outline"
              size={14}
              color={THEME.colors.destructive}
            />
            <Text style={styles.errorText}>{error}</Text>
          </View>
        ) : null}
      </View>
    );
  },
);

const styles = StyleSheet.create({
  container: {
    marginBottom: THEME.spacing.lg,
  },
  label: {
    fontFamily: FONTS.bodySemiBold,
    fontSize: 11,
    color: THEME.colors.textSecondary,
    marginBottom: THEME.spacing.sm,
    letterSpacing: 1,
    textTransform: "uppercase",
    textShadowColor: "rgba(0, 0, 0, 0.6)",
    textShadowOffset: { width: 0, height: 1 },
    textShadowRadius: 3,
  },
  inputWrapper: {
    flexDirection: "row",
    alignItems: "center",
    backgroundColor: THEME.colors.glass,
    borderWidth: 1,
    borderRadius: THEME.radius.lg,
    minHeight: INPUT_HEIGHT,
  },
  input: {
    flex: 1,
    fontFamily: FONTS.body,
    fontSize: FONT_SIZE_BODY,
    color: THEME.colors.textPrimary,
    paddingHorizontal: THEME.spacing.lg,
    paddingVertical: THEME.spacing.md,
    minHeight: INPUT_HEIGHT,
    ...(Platform.OS === "web" ? { outlineStyle: "none" as any } : {}),
  },
  eyeButton: {
    minWidth: MIN_TOUCH_TARGET,
    minHeight: MIN_TOUCH_TARGET,
    alignItems: "center",
    justifyContent: "center",
    paddingRight: THEME.spacing.md,
  },
  errorRow: {
    flexDirection: "row",
    alignItems: "center",
    marginTop: THEME.spacing.xs,
    gap: THEME.spacing.xs,
  },
  errorText: {
    fontSize: 13,
    color: THEME.colors.destructive,
  },
});
