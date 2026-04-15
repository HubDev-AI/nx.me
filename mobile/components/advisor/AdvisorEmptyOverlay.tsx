/**
 * AdvisorEmptyOverlay — fixed-center zero-state for the advisor tabs.
 *
 * Renders EmptyState inside an absolute-positioned overlay so the copy
 * lands at the same on-screen position on every tab (Chat, Nudges,
 * Memories), regardless of whether the tab has a composer, form, or
 * other chrome siblings. `pointerEvents="none"` keeps the overlay from
 * stealing taps from the composer or list beneath it.
 *
 * Call sites gate mounting on `!isLoading && !error && items.length === 0`
 * — that way the overlay never competes with skeletons or the error
 * variant of EmptyState.
 */
import { StyleSheet, View } from "react-native";
import { Ionicons } from "@expo/vector-icons";

import { EmptyState } from "../ui/EmptyState";

interface AdvisorEmptyOverlayProps {
  icon: React.ComponentProps<typeof Ionicons>["name"];
  title: string;
  description?: string;
}

export function AdvisorEmptyOverlay({
  icon,
  title,
  description,
}: AdvisorEmptyOverlayProps) {
  return (
    <View
      style={StyleSheet.absoluteFill}
      pointerEvents="none"
      accessibilityRole="text"
    >
      <View style={styles.center}>
        <EmptyState
          icon={icon}
          title={title}
          description={description}
          center={false}
        />
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  center: {
    flex: 1,
    alignItems: "center",
    justifyContent: "center",
  },
});
