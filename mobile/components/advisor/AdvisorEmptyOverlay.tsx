/**
 * AdvisorEmptyOverlay — fixed-center zero-state / error-state for the
 * advisor tabs.
 *
 * Renders EmptyState inside an absolute-positioned overlay so the copy
 * lands at the same on-screen position on every tab (Chat, Nudges,
 * Memories), regardless of whether the tab has a composer, form, or
 * other chrome siblings.
 *
 * `pointerEvents="box-none"` lets the wrapper ignore taps while still
 * forwarding them to children — the optional retry button stays
 * tappable, and non-interactive empty states still leave the composer
 * or list beneath fully usable.
 *
 * Call sites gate mounting on `!isLoading && items.length === 0` and
 * pass the action only when `error !== null`.
 */
import { StyleSheet, View } from "react-native";
import { Ionicons } from "@expo/vector-icons";

import { EmptyState, type EmptyStateAction } from "../ui/EmptyState";

interface AdvisorEmptyOverlayProps {
  icon: React.ComponentProps<typeof Ionicons>["name"];
  title: string;
  description?: string;
  action?: EmptyStateAction;
}

export function AdvisorEmptyOverlay({
  icon,
  title,
  description,
  action,
}: AdvisorEmptyOverlayProps) {
  return (
    <View style={StyleSheet.absoluteFill} pointerEvents="box-none">
      <View style={styles.center} pointerEvents="box-none">
        <EmptyState
          icon={icon}
          title={title}
          description={description}
          action={action}
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
