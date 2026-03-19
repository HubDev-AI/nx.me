import { useState, useCallback, forwardRef } from "react";
import {
  View,
  Text,
  TextInput,
  StyleSheet,
  Pressable,
  type TextInputProps,
} from "react-native";
import { Ionicons } from "@expo/vector-icons";

import {
  INPUT_FILL,
  BORDER_DEFAULT,
  TEXT_PRIMARY,
  TEXT_SECONDARY,
  TEXT_DISABLED,
  CTA_PRIMARY,
  ERROR_DARK,
} from "../../constants/colors";

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
      ? ERROR_DARK
      : isFocused
        ? CTA_PRIMARY
        : BORDER_DEFAULT;

    return (
      <View style={styles.container}>
        <Text style={styles.label} accessibilityRole="text">
          {label}
        </Text>
        <View style={[styles.inputWrapper, { borderColor }]}>
          <TextInput
            ref={ref}
            style={styles.input}
            placeholderTextColor={TEXT_DISABLED}
            selectionColor={CTA_PRIMARY}
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
                color={TEXT_SECONDARY}
              />
            </Pressable>
          )}
        </View>
        {error ? (
          <View style={styles.errorRow}>
            <Ionicons
              name="alert-circle-outline"
              size={14}
              color={ERROR_DARK}
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
    marginBottom: 16,
  },
  label: {
    fontSize: 14,
    fontWeight: "500",
    color: TEXT_SECONDARY,
    marginBottom: 6,
  },
  inputWrapper: {
    flexDirection: "row",
    alignItems: "center",
    backgroundColor: INPUT_FILL,
    borderWidth: 1,
    borderRadius: 12,
    minHeight: INPUT_HEIGHT,
  },
  input: {
    flex: 1,
    fontSize: FONT_SIZE_BODY,
    color: TEXT_PRIMARY,
    paddingHorizontal: 16,
    paddingVertical: 12,
    minHeight: INPUT_HEIGHT,
  },
  eyeButton: {
    minWidth: MIN_TOUCH_TARGET,
    minHeight: MIN_TOUCH_TARGET,
    alignItems: "center",
    justifyContent: "center",
    paddingRight: 12,
  },
  errorRow: {
    flexDirection: "row",
    alignItems: "center",
    marginTop: 4,
    gap: 4,
  },
  errorText: {
    fontSize: 13,
    color: ERROR_DARK,
  },
});
