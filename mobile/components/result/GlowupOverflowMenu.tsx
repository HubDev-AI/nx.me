/**
 * GlowupOverflowMenu — bottom-sheet overflow menu for the result screen's
 * header ellipsis.
 *
 * Single row today: Delete. Scales naturally to additional rows (Report,
 * Copy link, Edit caption) without structural change. The animation +
 * header shape mirror EditProfileSheet / (ported) ShareDialog so the
 * glow-up modals share one aesthetic.
 *
 * State ownership:
 *   - `visible` is parent-owned.
 *   - Tapping the Delete row fires `onDelete` synchronously; the parent is
 *     responsible for closing the menu and deferring any follow-up modal
 *     (e.g., Alert.alert destructive confirm) until the exit animation
 *     completes — iOS races Modal + Alert stacking otherwise.
 *
 * The menu container advertises `accessibilityRole="menu"` and each row
 * advertises `"menuitem"` so VoiceOver reads it as a menu, matching the
 * existing `RadialMenu` parity pattern.
 */
import { useCallback, useEffect, useRef, useState } from "react";
import {
  Animated,
  Modal,
  Pressable,
  StyleSheet,
  View,
} from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { THEME } from "../../constants/theme";
import { MIN_TOUCH_TARGET } from "../../constants/config";
import { hapticLight } from "../../lib/haptics";
import { Body } from "../ui/Text";

// ---------------------------------------------------------------------------
// Animation constants — match EditProfileSheet / ShareDialog exactly.
// ---------------------------------------------------------------------------

const ENTER_DURATION_MS = 300;
/** Exit duration exported so callers can schedule after-exit work. */
export const OVERFLOW_MENU_EXIT_DURATION_MS = 200;

const SCRIM_TARGET_OPACITY = 0.5;
const SHEET_OFFSCREEN_Y = 400;
const ROW_ICON_SIZE = 22;
const HEADER_SLOT_MIN_WIDTH = 60;

// ---------------------------------------------------------------------------
// Copy
// ---------------------------------------------------------------------------

const CANCEL_LABEL = "Cancel";
const DELETE_ROW_LABEL = "Delete glow-up";

// ---------------------------------------------------------------------------
// Row sub-component — local duplicate of ShareDialog's DialogRow shape,
// kept separate per plan so the two menus can drift independently.
// ---------------------------------------------------------------------------

interface OverflowMenuRowProps {
  iconName: React.ComponentProps<typeof Ionicons>["name"];
  title: string;
  onPress: () => void;
  destructive?: boolean;
  accessibilityLabel: string;
  testID?: string;
}

function OverflowMenuRow({
  iconName,
  title,
  onPress,
  destructive = false,
  accessibilityLabel,
  testID,
}: OverflowMenuRowProps) {
  const handlePress = useCallback(() => {
    hapticLight();
    onPress();
  }, [onPress]);

  const tintColor = destructive
    ? THEME.colors.destructive
    : THEME.colors.textPrimary;

  return (
    <Pressable
      onPress={handlePress}
      style={({ pressed }) => [styles.row, pressed && styles.rowPressed]}
      accessibilityRole="menuitem"
      accessibilityLabel={accessibilityLabel}
      testID={testID}
    >
      <View style={styles.rowIcon}>
        <Ionicons name={iconName} size={ROW_ICON_SIZE} color={tintColor} />
      </View>
      <View style={styles.rowText}>
        <Body
          color={destructive ? "destructive" : "primary"}
          weight="medium"
        >
          {title}
        </Body>
      </View>
    </Pressable>
  );
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export interface GlowupOverflowMenuProps {
  visible: boolean;
  onClose: () => void;
  onDelete: () => void;
}

export function GlowupOverflowMenu({
  visible,
  onClose,
  onDelete,
}: GlowupOverflowMenuProps) {
  const insets = useSafeAreaInsets();

  const [mounted, setMounted] = useState(visible);
  const isClosingRef = useRef(false);

  const slideAnim = useRef(new Animated.Value(0)).current;
  const scrimAnim = useRef(new Animated.Value(0)).current;

  const handleExitComplete = useCallback(
    ({ finished }: { finished: boolean }) => {
      if (!finished) return;
      if (!isClosingRef.current) return;
      isClosingRef.current = false;
      setMounted(false);
    },
    [],
  );

  useEffect(() => {
    if (visible) {
      isClosingRef.current = false;
      setMounted(true);
      Animated.parallel([
        Animated.timing(slideAnim, {
          toValue: 1,
          duration: ENTER_DURATION_MS,
          useNativeDriver: true,
        }),
        Animated.timing(scrimAnim, {
          toValue: 1,
          duration: ENTER_DURATION_MS,
          useNativeDriver: true,
        }),
      ]).start();
    } else {
      isClosingRef.current = true;
      Animated.parallel([
        Animated.timing(slideAnim, {
          toValue: 0,
          duration: OVERFLOW_MENU_EXIT_DURATION_MS,
          useNativeDriver: true,
        }),
        Animated.timing(scrimAnim, {
          toValue: 0,
          duration: OVERFLOW_MENU_EXIT_DURATION_MS,
          useNativeDriver: true,
        }),
      ]).start(handleExitComplete);
    }
    // Stop in-flight animations on unmount so the legacy `Animated.timing`
    // completion callback can't fire `setMounted` on a dead tree.
    // `stopAnimation` invokes the callback with `finished: false`; the
    // `handleExitComplete`'s `if (!finished) return` guard traps it.
    return () => {
      slideAnim.stopAnimation();
      scrimAnim.stopAnimation();
    };
  }, [visible, slideAnim, scrimAnim, handleExitComplete]);

  const handleClose = useCallback(() => {
    hapticLight();
    onClose();
  }, [onClose]);

  const translateY = slideAnim.interpolate({
    inputRange: [0, 1],
    outputRange: [SHEET_OFFSCREEN_Y, 0],
  });

  const scrimOpacity = scrimAnim.interpolate({
    inputRange: [0, 1],
    outputRange: [0, SCRIM_TARGET_OPACITY],
  });

  return (
    <Modal
      visible={mounted}
      transparent
      animationType="none"
      onRequestClose={handleClose}
    >
      <View style={styles.modalContainer}>
        <Animated.View style={[styles.scrim, { opacity: scrimOpacity }]}>
          <Pressable
            style={StyleSheet.absoluteFill}
            onPress={handleClose}
            accessibilityLabel="Close menu"
            accessibilityRole="button"
          />
        </Animated.View>

        <Animated.View
          style={[
            styles.sheet,
            {
              transform: [{ translateY }],
              paddingBottom: Math.max(insets.bottom, THEME.spacing.xl),
            },
          ]}
          accessibilityRole="menu"
        >
          <View style={styles.sheetTopBorder} />
          <View style={styles.handleBar} />

          <View style={styles.header}>
            <Pressable
              onPress={handleClose}
              style={styles.headerSlotLeft}
              accessibilityLabel={CANCEL_LABEL}
              accessibilityRole="button"
              testID="glowup-overflow-cancel"
            >
              <Body color="secondary">{CANCEL_LABEL}</Body>
            </Pressable>

            <View style={styles.headerSlotCenter} />

            <View style={styles.headerSlotRight} />
          </View>

          <View style={styles.content}>
            <OverflowMenuRow
              iconName="trash-outline"
              title={DELETE_ROW_LABEL}
              onPress={onDelete}
              destructive
              accessibilityLabel={DELETE_ROW_LABEL}
              testID="glowup-overflow-row-delete"
            />
          </View>
        </Animated.View>
      </View>
    </Modal>
  );
}

// ---------------------------------------------------------------------------
// Styles
// ---------------------------------------------------------------------------

const styles = StyleSheet.create({
  modalContainer: {
    flex: 1,
    justifyContent: "flex-end",
  },
  scrim: {
    ...StyleSheet.absoluteFillObject,
    backgroundColor: THEME.colors.backdrop,
  },
  sheet: {
    backgroundColor: THEME.colors.glass,
    borderTopLeftRadius: THEME.radius.xl,
    borderTopRightRadius: THEME.radius.xl,
    overflow: "hidden",
  },
  sheetTopBorder: {
    position: "absolute",
    top: 0,
    left: 0,
    right: 0,
    height: StyleSheet.hairlineWidth,
    backgroundColor: THEME.colors.sheetTopBorder,
  },
  handleBar: {
    width: 36,
    height: 4,
    borderRadius: THEME.radius.pill,
    backgroundColor: THEME.colors.borderFocused,
    alignSelf: "center",
    marginTop: THEME.spacing.sm,
    marginBottom: THEME.spacing.sm,
  },
  header: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    paddingHorizontal: THEME.spacing.lg,
    paddingVertical: THEME.spacing.sm,
    minHeight: MIN_TOUCH_TARGET,
  },
  headerSlotLeft: {
    minWidth: HEADER_SLOT_MIN_WIDTH,
    minHeight: MIN_TOUCH_TARGET,
    justifyContent: "center",
    alignItems: "flex-start",
  },
  headerSlotCenter: {
    flex: 1,
  },
  headerSlotRight: {
    minWidth: HEADER_SLOT_MIN_WIDTH,
    minHeight: MIN_TOUCH_TARGET,
  },
  content: {
    paddingHorizontal: THEME.spacing.xl,
    paddingTop: THEME.spacing.sm,
    paddingBottom: THEME.spacing.sm,
  },
  row: {
    flexDirection: "row",
    alignItems: "center",
    gap: THEME.spacing.md,
    paddingVertical: THEME.spacing.md,
    minHeight: MIN_TOUCH_TARGET,
  },
  rowPressed: {
    opacity: 0.6,
  },
  rowIcon: {
    width: MIN_TOUCH_TARGET,
    height: MIN_TOUCH_TARGET,
    borderRadius: THEME.radius.pill,
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: THEME.colors.surface,
  },
  rowText: {
    flex: 1,
  },
});
