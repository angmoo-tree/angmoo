"use client";

import { useCallback, useEffect, useState } from "react";
import { useAuthRuntimeIdentity } from "@/hooks/use-auth-runtime-identity";
import { useAuth } from "@/hooks/use-auth";
import { useUserEnvironment } from "@/hooks/use-user-environment";
import { DeviceHome } from "@/features/device-home/components/device-home";
import { ensureDefaultSpace } from "@/features/worlds/api/worlds";
import { getProductRuntimeState } from "@/features/runtime-status/api/runtime-status-client";
import { RuntimeStatusSummary } from "@/features/runtime-status/components/runtime-status-summary";
import type { ProductRuntimeState } from "@/features/runtime-status/types/runtime-status";
import { DeviceHomeShell } from "@/composition/screens/device-home-shell";
import { useWorldUnreadCounts } from "@/features/social/hooks/use-world-unread-counts";
import { CountBadge } from "@/components/ui/count-badge";
import { useUiText } from "@/hooks/use-ui-text";
import { LocalOwnerClient } from "@/features/identity/components/local-owner-client";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/button";
import { InlineError } from "@/components/ui/feedback";

export function DeviceHomeScreen() {
  const identity = useAuthRuntimeIdentity("device-home");
  return <ScopedDeviceHomeScreen key={identity} />;
}

function ScopedDeviceHomeScreen() {
  const text = useUiText("social");
  const { t } = useTranslation("identity");
  const [worldIds, setWorldIds] = useState<string[]>([]);
  const onVisibleWorldIds = useCallback((ids: string[]) => setWorldIds(previous => JSON.stringify(previous) === JSON.stringify(ids) ? previous : ids), []);
  const counts = useWorldUnreadCounts(worldIds);
  const { status: authStatus } = useAuth();
  const { ready, errorCode, retry } = useUserEnvironment();
  const status = authStatus === "authenticated" && !ready ? "checking" : authStatus;
  const [runtimeState, setRuntimeState] = useState<ProductRuntimeState>("stale_state");
  useEffect(() => {
    if (status !== "authenticated") return;
    const controller = new AbortController();
    getProductRuntimeState({ signal: controller.signal })
      .then(state => { if (!controller.signal.aborted) setRuntimeState(state); })
      .catch((reason: unknown) => {
        if (controller.signal.aborted) return;
        if (reason instanceof DOMException && reason.name === "AbortError") return;
        setRuntimeState("stale_state");
      });
    return () => controller.abort();
  }, [status]);
  return (
    <DeviceHomeShell status={<RuntimeStatusSummary state={runtimeState} />}>
      {errorCode && <InlineError>{t("detectionFailed")}<Button onClick={retry} variant="secondary">{t("retry")}</Button></InlineError>}
      <DeviceHome authStatus={authStatus} initialPreparationReady={ready} ensureDefaultSpace={ensureDefaultSpace} onVisibleWorldIds={onVisibleWorldIds}
        authenticationFallback={<LocalOwnerClient embedded />}
        renderWorldBadge={id => <CountBadge count={counts.records[id]?.unread_count ?? null} stale={counts.stale} />}
        worldNotificationDescription={(id, name) => {
          const count = counts.records[id]?.unread_count;
          return count === null || count === undefined ? text("{{name}} World 피드 열기. 알림 수를 확인하지 못했어요.", { name }) :
            text(counts.stale ? "{{name}} World 피드 열기. 이전에 확인한 읽지 않은 알림 {{count}}개." : "{{name}} World 피드 열기. 읽지 않은 알림 {{count}}개.", { name, count });
        }} />
    </DeviceHomeShell>
  );
}
