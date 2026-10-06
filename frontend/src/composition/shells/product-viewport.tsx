"use client";

import { useSyncExternalStore, type ReactNode } from "react";
import { DesktopNavigationToolbar } from "@/composition/navigation/desktop-navigation-toolbar";
import { getDesktopWindowState, isTauriDesktopRuntime, subscribeDesktopRoute } from "@/lib/desktop/product-window";
import styles from "./product-viewport.module.css";
import { NavigationCapabilitiesContext } from "@/lib/navigation/navigation-capabilities";
import { desktopHistoryAvailability } from "@/lib/desktop/desktop-history";

export function ProductViewport({ children }: { children: ReactNode }) {
  const native = useSyncExternalStore(subscribeDesktopRoute, isTauriDesktopRuntime, () => false);
  const kind = useSyncExternalStore(subscribeDesktopRoute, () => getDesktopWindowState()?.kind ?? "browser", () => "browser");
  const back = useSyncExternalStore(subscribeDesktopRoute, () => native && desktopHistoryAvailability().back, () => false);
  return (
    <NavigationCapabilitiesContext.Provider value={{ home: native, back }}><div className={styles.viewport} data-product-viewport={kind}>
      {native ? <DesktopNavigationToolbar /> : null}
      <div className={styles.body} data-product-viewport-body="true">{children}</div>
    </div></NavigationCapabilitiesContext.Provider>
  );
}
