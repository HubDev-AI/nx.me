/**
 * RadialMenuProvider — single app-wide radial menu instance.
 *
 * Any screen can open the menu without threading local visibility state or
 * rendering the component itself:
 *
 * ```tsx
 * const { open } = useRadialMenu();
 * open([
 *   { label: "Edit", icon: "create-outline", onPress: handleEdit },
 *   { label: "Delete", icon: "trash-outline", onPress: handleDelete, destructive: true },
 * ]);
 * ```
 *
 * Mount `<RadialMenuProvider>` once near the root of the tree (above the
 * screens that need it) and the menu renders on demand with whatever items
 * the caller passed.
 */
import { createContext, useCallback, useContext, useMemo, useState } from "react";

import { RadialMenu, type RadialMenuItem } from "../components/ui/RadialMenu";
import { useTheme } from "./theme-context";

interface RadialMenuContextValue {
  /** Open the radial menu with the given items. */
  open: (items: RadialMenuItem[]) => void;
  /** Close the currently-open menu. */
  close: () => void;
}

const RadialMenuContext = createContext<RadialMenuContextValue | null>(null);

export function RadialMenuProvider({ children }: { children: React.ReactNode }) {
  const { theme } = useTheme();
  const [items, setItems] = useState<RadialMenuItem[]>([]);
  const [visible, setVisible] = useState(false);

  const open = useCallback((next: RadialMenuItem[]) => {
    setItems(next);
    setVisible(true);
  }, []);

  const close = useCallback(() => {
    setVisible(false);
  }, []);

  const value = useMemo(() => ({ open, close }), [open, close]);

  return (
    <RadialMenuContext.Provider value={value}>
      {children}
      <RadialMenu
        visible={visible}
        onClose={close}
        items={items}
        accentColor={theme.accent}
      />
    </RadialMenuContext.Provider>
  );
}

export function useRadialMenu(): RadialMenuContextValue {
  const ctx = useContext(RadialMenuContext);
  if (!ctx) {
    throw new Error("useRadialMenu must be used inside a RadialMenuProvider");
  }
  return ctx;
}
