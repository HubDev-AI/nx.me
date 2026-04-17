/**
 * AdvisorComposer — shared pill input + round accent action button used by
 * the advisor chat (send) and the memories add-form (add). Keeps visual
 * parity between the two input surfaces and gives callers a minimal prop
 * contract so future reuse is cheap.
 *
 * Callers own keyboard handling and surrounding layout; this component
 * just renders the row. Chat wraps itself in KeyboardAvoidingView and
 * passes `bottomPadding` for the floating tab-bar offset; memories does
 * neither because the form sits above the list.
 */
import { useState } from "react";
import {
  ActivityIndicator,
  Pressable,
  StyleSheet,
  TextInput,
} from "react-native";
import { KeyboardStickyView } from "react-native-keyboard-controller";
import { Ionicons } from "@expo/vector-icons";

import { THEME } from "../../constants/theme";
import { MIN_TOUCH_TARGET } from "../../constants/config";
import { FONTS } from "../../hooks/useFonts";
import { useTheme } from "../../lib/theme-context";

/** Max visible height before the multi-line input starts scrolling internally. */
const TEXTINPUT_MAX_HEIGHT = 120;
/** Size of the icon rendered inside the round submit button. */
const SEND_ICON_SIZE = 20;
const ADD_ICON_SIZE = 24;

export interface AdvisorComposerProps {
  value: string;
  onChangeText: (text: string) => void;
  onSubmit: () => void;
  placeholder: string;
  /** True while a submit is in flight — disables the button and shows a spinner. */
  disabled?: boolean;
  /** Which glyph to render inside the submit button. */
  submitIcon?: "send" | "add";
  /** Character cap forwarded to the underlying TextInput. */
  maxLength?: number;
  /** Accessibility label for the TextInput. */
  accessibilityLabel: string;
  /** Accessibility label for the submit button. */
  submitAccessibilityLabel: string;
  /**
   * Extra bottom padding applied to the bar itself. Used by chat to clear
   * the floating tab bar; memories passes nothing.
   */
  bottomPadding?: number;
  /**
   * When true, the bar renders with a top hairline border and glass
   * backdrop so scrolled content fades behind it. Chat wants this
   * (messages scroll under it); memories doesn't (form sits above the
   * list with no scrolling content above the composer).
   */
  separator?: boolean;
}

export function AdvisorComposer({
  value,
  onChangeText,
  onSubmit,
  placeholder,
  disabled = false,
  submitIcon = "send",
  maxLength,
  accessibilityLabel,
  submitAccessibilityLabel,
  bottomPadding,
  separator = false,
}: AdvisorComposerProps) {
  const { theme } = useTheme();
  const [isFocused, setIsFocused] = useState(false);

  const canSubmit = value.trim().length > 0 && !disabled;
  const iconName = submitIcon === "add" ? "add" : "send";
  const iconSize = submitIcon === "add" ? ADD_ICON_SIZE : SEND_ICON_SIZE;

  return (
    // KeyboardStickyView translates the composer by the native keyboard
    // height (via KeyboardProvider's frame callbacks) so the input sits
    // flush above the keyboard on every device. Immune to chrome above
    // the composer (nav header, sub-tab rows) — no `keyboardVerticalOffset`
    // to guess at. See docs/notes/keyboard-composer-investigation.md.
    <KeyboardStickyView
      offset={{ closed: 0, opened: 0 }}
      style={[
        styles.bar,
        separator && styles.barSeparator,
        bottomPadding !== undefined && { paddingBottom: bottomPadding },
      ]}
    >
      <TextInput
        style={[styles.input, isFocused && { borderColor: theme.accent }]}
        value={value}
        onChangeText={(next) => {
          // Enter in multiline inserts a trailing "\n". Treat the single
          // trailing newline as submit — or suppress it entirely when the
          // input is empty — instead of letting it enter state. Length-delta
          // guard avoids hijacking paste of multi-line text ending in a newline.
          const isEnterKey =
            next.length === value.length + 1 && next.endsWith("\n");
          if (isEnterKey) {
            if (canSubmit) {
              onSubmit();
            }
            return;
          }
          onChangeText(next);
        }}
        onFocus={() => setIsFocused(true)}
        onBlur={() => setIsFocused(false)}
        placeholder={placeholder}
        placeholderTextColor={THEME.colors.textDisabled}
        multiline
        maxLength={maxLength}
        returnKeyType="send"
        blurOnSubmit={false}
        accessibilityLabel={accessibilityLabel}
      />
      <Pressable
        onPress={onSubmit}
        disabled={!canSubmit}
        style={({ pressed }) => [
          styles.button,
          canSubmit && [
            styles.buttonActive,
            {
              backgroundColor: theme.accent,
              ...THEME.shadow.glow(theme.accent),
            },
          ],
          pressed && canSubmit && styles.buttonPressed,
        ]}
        accessibilityLabel={submitAccessibilityLabel}
        accessibilityRole="button"
      >
        {disabled ? (
          <ActivityIndicator size="small" color={THEME.colors.bg} />
        ) : (
          <Ionicons
            name={iconName}
            size={iconSize}
            color={canSubmit ? THEME.colors.bg : THEME.colors.textDisabled}
          />
        )}
      </Pressable>
    </KeyboardStickyView>
  );
}

const styles = StyleSheet.create({
  bar: {
    flexDirection: "row",
    alignItems: "flex-end",
    paddingHorizontal: THEME.spacing.md,
    paddingVertical: THEME.spacing.sm,
    gap: THEME.spacing.sm,
    backgroundColor: "transparent",
  },
  barSeparator: {
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: THEME.colors.glassBorder,
    backgroundColor: THEME.colors.glass,
  },
  input: {
    flex: 1,
    fontFamily: FONTS.body,
    backgroundColor: THEME.colors.glass,
    borderRadius: THEME.radius.xl,
    borderCurve: "continuous",
    borderWidth: 1,
    borderColor: THEME.colors.glassBorder,
    paddingHorizontal: THEME.spacing.lg,
    paddingTop: THEME.spacing.md - 2,
    paddingBottom: THEME.spacing.md - 2,
    ...THEME.typography.body,
    color: THEME.colors.textPrimary,
    maxHeight: TEXTINPUT_MAX_HEIGHT,
    minHeight: MIN_TOUCH_TARGET,
    ...THEME.shadow.glass,
  },
  button: {
    width: MIN_TOUCH_TARGET,
    height: MIN_TOUCH_TARGET,
    borderRadius: MIN_TOUCH_TARGET / 2,
    borderCurve: "continuous",
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: THEME.colors.glass,
    borderWidth: 1,
    borderColor: THEME.colors.glassBorder,
    ...THEME.shadow.glass,
  },
  buttonActive: {
    borderWidth: 0,
  },
  buttonPressed: {
    opacity: 0.85,
  },
});
