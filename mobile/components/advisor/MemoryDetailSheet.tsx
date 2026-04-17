/**
 * MemoryDetailSheet — bottom sheet showing a single memory's full content.
 *
 * The list row truncates body copy at three lines (`numberOfLines={3}`);
 * tapping a row opens this sheet so the user can read the whole note or
 * goal without surrounding chrome. Mirrors NudgeDetailSheet's passive
 * read-only pattern — only a close affordance, no edit/delete here
 * (delete is the swipe action on the row).
 */
import { useCallback } from "react";
import { Modal, Pressable, ScrollView, StyleSheet, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { Ionicons } from "@expo/vector-icons";

import { THEME } from "../../constants/theme";
import { useTheme } from "../../lib/theme-context";
import { Body, Caption, Heading } from "../ui/Text";
import { MIN_TOUCH_TARGET } from "../../constants/config";
import type { UserMemory } from "../../lib/advisor";
import {
  memoryContentText,
  memoryTypeIcon,
  memoryTypeLabel,
} from "./memory-helpers";

interface MemoryDetailSheetProps {
  memory: UserMemory | null;
  onClose: () => void;
}

export function MemoryDetailSheet({ memory, onClose }: MemoryDetailSheetProps) {
  const { theme } = useTheme();
  const handleBackdropPress = useCallback(() => onClose(), [onClose]);

  const dateStr = memory
    ? new Date(memory.created_at).toLocaleDateString(undefined, {
        month: "short",
        day: "numeric",
        year: "numeric",
      })
    : "";

  return (
    <Modal
      visible={memory !== null}
      animationType="fade"
      transparent
      onRequestClose={onClose}
      statusBarTranslucent
    >
      <Pressable
        style={styles.backdrop}
        onPress={handleBackdropPress}
        accessibilityLabel="Dismiss memory"
        accessibilityRole="button"
      />
      <SafeAreaView
        style={styles.sheetContainer}
        edges={["bottom"]}
        pointerEvents="box-none"
      >
        <View style={styles.sheet}>
          <View style={styles.header}>
            <View
              style={[
                styles.iconContainer,
                { backgroundColor: theme.accentMuted },
              ]}
            >
              <Ionicons
                name={memory ? memoryTypeIcon(memory.type) : "bookmark-outline"}
                size={22}
                color={theme.accent}
              />
            </View>
            <View style={styles.titleColumn}>
              <Heading size="md" display={false}>
                {memory ? memoryTypeLabel(memory.type) : ""}
              </Heading>
              {memory && <Caption color="muted">{dateStr}</Caption>}
            </View>
            <Pressable
              onPress={onClose}
              style={styles.closeButton}
              accessibilityLabel="Close"
              accessibilityRole="button"
              hitSlop={8}
            >
              <Ionicons
                name="close"
                size={22}
                color={THEME.colors.textSecondary}
              />
            </Pressable>
          </View>

          <ScrollView
            style={styles.body}
            contentContainerStyle={styles.bodyContent}
            showsVerticalScrollIndicator={false}
          >
            <Body color="primary" style={styles.bodyText}>
              {memory ? memoryContentText(memory.content) : ""}
            </Body>
          </ScrollView>
        </View>
      </SafeAreaView>
    </Modal>
  );
}

const styles = StyleSheet.create({
  backdrop: {
    ...StyleSheet.absoluteFillObject,
    backgroundColor: "rgba(0, 0, 0, 0.65)",
  },
  sheetContainer: {
    flex: 1,
    justifyContent: "flex-end",
  },
  sheet: {
    backgroundColor: THEME.colors.bg,
    borderTopLeftRadius: THEME.radius.xl,
    borderTopRightRadius: THEME.radius.xl,
    borderCurve: "continuous",
    paddingTop: THEME.spacing.lg,
    paddingHorizontal: THEME.spacing.lg,
    paddingBottom: THEME.spacing.lg,
    maxHeight: "80%",
    borderTopWidth: StyleSheet.hairlineWidth,
    borderLeftWidth: StyleSheet.hairlineWidth,
    borderRightWidth: StyleSheet.hairlineWidth,
    borderColor: THEME.colors.glassBorder,
  },
  header: {
    flexDirection: "row",
    alignItems: "center",
    gap: THEME.spacing.md,
    marginBottom: THEME.spacing.md,
  },
  iconContainer: {
    width: 40,
    height: 40,
    borderRadius: 20,
    alignItems: "center",
    justifyContent: "center",
  },
  titleColumn: {
    flex: 1,
    gap: THEME.spacing.xs / 2,
  },
  closeButton: {
    width: MIN_TOUCH_TARGET,
    height: MIN_TOUCH_TARGET,
    alignItems: "center",
    justifyContent: "center",
  },
  body: {
    flexGrow: 0,
  },
  bodyContent: {
    paddingVertical: THEME.spacing.sm,
  },
  bodyText: {
    lineHeight: 22,
  },
});
