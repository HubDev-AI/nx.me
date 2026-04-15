/**
 * Profile radial-menu derivation.
 *
 * Pure `(capabilities, handlers) → items[]` so it can be unit-tested without
 * mounting `<ProfileScreen>`. The set of items shown is fully determined by
 * the capability flags — no inline conditionals in `profile.tsx`.
 */
import type { Ionicons } from "@expo/vector-icons";

import type { RadialMenuItem } from "../ui/RadialMenu";
import type { Capabilities } from "../../lib/capabilities";

export interface ProfileMenuHandlers {
  onEditProfile: () => void;
  onOpenSubscription: () => void;
  onOpenSettings: () => void;
  onLogout: () => void;
  onSignIn: () => void;
}

const ICONS = {
  edit: "create-outline",
  subscription: "diamond-outline",
  settings: "settings-outline",
  logOut: "log-out-outline",
  signIn: "log-in-outline",
} satisfies Record<string, keyof typeof Ionicons.glyphMap>;

export function buildProfileMenu(
  caps: Capabilities,
  handlers: ProfileMenuHandlers,
): RadialMenuItem[] {
  const items: RadialMenuItem[] = [];

  if (caps.canEditProfile) {
    items.push({
      label: "Edit Profile",
      icon: ICONS.edit,
      onPress: handlers.onEditProfile,
    });
  }
  if (caps.canSubscribe) {
    items.push({
      label: "Subscription",
      icon: ICONS.subscription,
      onPress: handlers.onOpenSubscription,
    });
  }
  // Settings is always shown (no capability gate today).
  items.push({
    label: "Settings",
    icon: ICONS.settings,
    onPress: handlers.onOpenSettings,
  });
  if (caps.canSignOut) {
    items.push({
      label: "Log Out",
      icon: ICONS.logOut,
      onPress: handlers.onLogout,
      destructive: true,
    });
  }
  if (caps.canSignIn) {
    items.push({
      label: "Sign In",
      icon: ICONS.signIn,
      onPress: handlers.onSignIn,
    });
  }
  return items;
}
