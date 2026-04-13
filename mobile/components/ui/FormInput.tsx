/**
 * FormInput — themed TextInput wrapper with label, error state, focus ring.
 * Prefer over raw react-native TextInput everywhere.
 */
import type { ReactNode } from "react";
import { forwardRef, useCallback, useState } from "react";
import {
  StyleSheet,
  TextInput,
  View,
  type StyleProp,
  type TextInputProps,
  type TextStyle,
  type ViewStyle,
} from "react-native";
import { ERROR_BORDER, INPUT_FILL } from "../../constants/colors";
import { THEME } from "../../constants/theme";
import { FONTS } from "../../hooks/useFonts";
import { useTheme } from "../../lib/theme-context";
import { Body, Caption } from "./Text";

interface FormInputProps extends Omit<TextInputProps, "style"> {
  label?: string;
  error?: string;
  helpText?: string;
  leftIcon?: ReactNode;
  rightIcon?: ReactNode;
  containerStyle?: StyleProp<ViewStyle>;
  inputStyle?: StyleProp<TextStyle>;
}

export const FormInput = forwardRef<TextInput, FormInputProps>(function FormInput(
  {
    label,
    error,
    helpText,
    leftIcon,
    rightIcon,
    containerStyle,
    inputStyle,
    onFocus,
    onBlur,
    editable = true,
    ...rest
  },
  ref,
) {
  const { theme } = useTheme();
  const [focused, setFocused] = useState(false);

  const handleFocus = useCallback<NonNullable<TextInputProps["onFocus"]>>(
    (e) => {
      setFocused(true);
      onFocus?.(e);
    },
    [onFocus],
  );

  const handleBlur = useCallback<NonNullable<TextInputProps["onBlur"]>>(
    (e) => {
      setFocused(false);
      onBlur?.(e);
    },
    [onBlur],
  );

  const borderColor = error
    ? ERROR_BORDER
    : focused
      ? theme.accent
      : THEME.colors.border;

  return (
    <View style={[styles.container, !editable && styles.disabled, containerStyle]}>
      {label ? (
        <Body weight="medium" color="secondary" style={styles.label}>
          {label}
        </Body>
      ) : null}

      <View style={[styles.fieldRow, { borderColor }]}>
        {leftIcon ? <View style={styles.icon}>{leftIcon}</View> : null}
        <TextInput
          ref={ref}
          editable={editable}
          placeholderTextColor={THEME.colors.textMuted}
          selectionColor={theme.accent}
          onFocus={handleFocus}
          onBlur={handleBlur}
          style={[styles.input, inputStyle]}
          {...rest}
        />
        {rightIcon ? <View style={styles.icon}>{rightIcon}</View> : null}
      </View>

      {error ? (
        <Caption color="destructive" style={styles.help}>
          {error}
        </Caption>
      ) : helpText ? (
        <Caption color="muted" style={styles.help}>
          {helpText}
        </Caption>
      ) : null}
    </View>
  );
});

const styles = StyleSheet.create({
  container: {
    gap: THEME.spacing.xs,
  },
  disabled: {
    opacity: 0.6,
  },
  label: {
    marginBottom: THEME.spacing.xs,
  },
  fieldRow: {
    flexDirection: "row",
    alignItems: "center",
    backgroundColor: INPUT_FILL,
    borderRadius: THEME.radius.md,
    borderCurve: "continuous",
    borderWidth: 1,
    paddingHorizontal: THEME.spacing.lg,
    minHeight: 48,
    gap: THEME.spacing.sm,
  },
  input: {
    flex: 1,
    fontFamily: FONTS.body,
    fontSize: 15,
    color: THEME.colors.textPrimary,
    paddingVertical: THEME.spacing.md,
  },
  icon: {
    alignItems: "center",
    justifyContent: "center",
  },
  help: {
    marginTop: THEME.spacing.xs,
  },
});
