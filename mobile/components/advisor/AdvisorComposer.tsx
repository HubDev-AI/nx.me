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
import { useRef, useState } from "react";
import {
  ActivityIndicator,
  Pressable,
  StyleSheet,
  Text as RNText,
  TextInput,
  View,
} from "react-native";
import { Ionicons } from "@expo/vector-icons";

import { THEME } from "../../constants/theme";
import {
  COMPOSER_PREFILL_MICROCOPY,
  MIN_TOUCH_TARGET,
} from "../../constants/config";
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
   * Read-only signal for the "Ada suggested this question — edit or send"
   * microcopy. When non-empty AND the current `value` equals it exactly,
   * the microcopy is shown above the input. The first character-level
   * divergence from `initialText` (keystroke, backspace) dismisses the
   * microcopy for the lifetime of this component — re-typing the exact
   * prefill string does NOT re-activate it (one-shot).
   *
   * The parent owns the text state; the composer never seeds `value`
   * itself. That keeps the composer reusable by the memories add-form
   * without adding implicit state.
   */
  initialText?: string;
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
  initialText,
}: AdvisorComposerProps) {
  const { theme } = useTheme();
  const [isFocused, setIsFocused] = useState(false);

  // -------------------------------------------------------------------------
  // Prefill microcopy — one-shot. Starts `true` iff `initialText` is
  // provided AND matches `value` on mount; flips `false` on the first
  // divergence and never flips back for this composer's lifetime.
  // -------------------------------------------------------------------------
  const initialTextRef = useRef(initialText ?? "");
  const [prefillActive, setPrefillActive] = useState<boolean>(
    () =>
      (initialText ?? "").length > 0 && (initialText ?? "") === value,
  );

  const canSubmit = value.trim().length > 0 && !disabled;
  const iconName = submitIcon === "add" ? "add" : "send";
  const iconSize = submitIcon === "add" ? ADD_ICON_SIZE : SEND_ICON_SIZE;
  const showPrefillMicrocopy =
    prefillActive && value === initialTextRef.current;

  return (
    <View
      style={[
        styles.wrapper,
        bottomPadding !== undefined && { paddingBottom: bottomPadding },
      ]}
    >
      {showPrefillMicrocopy && (
        <RNText
          style={styles.prefillMicrocopy}
          accessibilityLabel={COMPOSER_PREFILL_MICROCOPY}
        >
          {COMPOSER_PREFILL_MICROCOPY}
        </RNText>
      )}
      <View style={styles.bar}>
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
              // Submitting consumes the prefill — matches the
              // button-tap path so microcopy doesn't survive into
              // subsequent messages on hardware-keyboard submits.
              if (prefillActive) setPrefillActive(false);
              onSubmit();
            }
            return;
          }
          // Any divergence from the prefilled string dismisses the
          // microcopy for this composer's lifetime. One-shot — re-typing
          // the exact prefill text does not re-activate it.
          if (prefillActive && next !== initialTextRef.current) {
            setPrefillActive(false);
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
        onPress={() => onSubmit()}
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
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  wrapper: {
    backgroundColor: "transparent",
  },
  prefillMicrocopy: {
    fontFamily: FONTS.body,
    fontSize: THEME.typography.caption.fontSize,
    lineHeight: THEME.typography.caption.lineHeight,
    letterSpacing: THEME.typography.caption.letterSpacing,
    color: THEME.colors.textSecondary,
    paddingHorizontal: THEME.spacing.lg,
    paddingBottom: THEME.spacing.xs,
  },
  bar: {
    flexDirection: "row",
    alignItems: "flex-end",
    paddingHorizontal: THEME.spacing.md,
    paddingVertical: THEME.spacing.sm,
    gap: THEME.spacing.sm,
    backgroundColor: "transparent",
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
