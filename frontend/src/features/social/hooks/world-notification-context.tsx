"use client";
import { createContext, useContext, useEffect, useMemo, useSyncExternalStore, type ReactNode } from "react";
import { useAuth } from "@/hooks/use-auth";
import { PRODUCT_LINK_ADMITTED_EVENT } from "@/lib/navigation/product-link-admission";
import { createWorldNotificationController, EMPTY_NOTIFICATION_STATE, sameNotificationScope, type NotificationMode, type WorldNotificationController } from "./world-notification-controller";
import type { NotificationScope } from "../types/world-notifications";

const ControllerContext = createContext<WorldNotificationController | null>(null);
const ScopeContext = createContext<NotificationScope | null>(null);

export function WorldNotificationProvider({ children }: { children: ReactNode }) {
  const { user, status, sessionRevision } = useAuth();
  const userId = user?.id;
  const controller = useMemo(() => status === "authenticated" && userId ? createWorldNotificationController(userId, sessionRevision ?? 0) : null, [status, userId, sessionRevision]);
  useEffect(() => {
    if (!controller) return;
    const admitted = (event: Event) => {
      const anchor = (event as CustomEvent<HTMLAnchorElement>).detail;
      const scope = controller.getSnapshot().scope;
      if (scope && anchor.dataset.notificationWorld === scope.world_id && anchor.dataset.notificationProfile === scope.recipient_world_character_id) {
        const id = Number(anchor.dataset.notificationId);
        if (Number.isSafeInteger(id) && id > 0) void controller.read(id);
      }
    };
    window.addEventListener(PRODUCT_LINK_ADMITTED_EVENT, admitted);
    return () => { window.removeEventListener(PRODUCT_LINK_ADMITTED_EVENT, admitted); controller.dispose(); };
  }, [controller]);
  return <ControllerContext.Provider value={controller}>{children}</ControllerContext.Provider>;
}

export function WorldNotificationScope({ scope, mode, children }: { scope: NotificationScope | null; mode: NotificationMode; children: ReactNode }) {
  const controller = useContext(ControllerContext);
  const worldId = scope?.world_id, profileId = scope?.recipient_world_character_id;
  useEffect(() => {
    if (!controller || !worldId || !profileId) return;
    controller.activate({ world_id: worldId, recipient_world_character_id: profileId }, mode);
    return () => controller.deactivate();
  }, [controller, worldId, profileId, mode]);
  return <ScopeContext.Provider value={scope}>{children}</ScopeContext.Provider>;
}

const noopSubscribe = () => () => {};
const empty = () => EMPTY_NOTIFICATION_STATE;
export function useWorldNotificationView() {
  const controller = useContext(ControllerContext), scope = useContext(ScopeContext);
  const snapshot = useSyncExternalStore(controller?.subscribe ?? noopSubscribe, controller?.getSnapshot ?? empty, empty);
  return { state: sameNotificationScope(snapshot.scope, scope) ? snapshot : EMPTY_NOTIFICATION_STATE, controller, scope };
}
