"use client";

import { useEffect, useState } from "react";
import { useAuth } from "@/hooks/use-auth";
import { useUiText } from "@/hooks/use-ui-text";
import { Button } from "@/components/ui/button";
import { AUTH_CHANGED_EVENT, getStoredUser } from "@/lib/auth/browser-session";
import { DESKTOP_RUNTIME_CONFIG_CHANGED_EVENT } from "@/lib/runtime/runtime-config";
import { listWorldCharacterProfiles } from "@/features/characters/api/world-character-profile-client";
import { getLocalWorldSurface } from "@/features/device-home/api/device-home-client";
import { MemoryWorkspace, type MemoryWorkspaceProps } from "@/features/memory/components/memory-workspace";
import type { MemoryScopeLoaders } from "@/features/memory/types/scope-options";
import {readWorldLiveness} from "@/features/worlds/hooks/use-world-deletion-watch";

export function MemoryWorkspaceScreen(props: Omit<MemoryWorkspaceProps, keyof MemoryScopeLoaders>) {
  const { status, user, sessionRevision, refresh } = useAuth();
  const text = useUiText("memory");
  const [runtimeRevision, setRuntimeRevision] = useState(0);
  useEffect(() => {
    const changed = () => setRuntimeRevision(value => value + 1);
    const authChanged = () => { if (getStoredUser()?.id !== user?.id) changed(); };
    window.addEventListener(DESKTOP_RUNTIME_CONFIG_CHANGED_EVENT, changed);
    window.addEventListener(AUTH_CHANGED_EVENT, authChanged);
    return () => {
      window.removeEventListener(DESKTOP_RUNTIME_CONFIG_CHANGED_EVENT, changed);
      window.removeEventListener(AUTH_CHANGED_EVENT, authChanged);
    };
  }, [user?.id]);
  if (status !== "authenticated" || !user || getStoredUser()?.id !== user.id) {
    return <main data-main-landmark-owner="memory" data-product-shell="memory">
      <p role="status">{text(status === "unauthenticated" ? "기억을 보려면 다시 로그인해주세요." : "기억을 불러오는 중")}</p>
      {status === "unauthenticated" ? <Button onClick={() => void refresh()}>{text("다시 시도")}</Button> : null}
    </main>;
  }
  const identity = JSON.stringify([user.id, sessionRevision, runtimeRevision, props.initialWorldId, props.initialSubjectId]);
  return <MemoryWorkspace key={identity} {...props} verifyWorldScope={readWorldLiveness} getLocalWorldSurface={getLocalWorldSurface} listWorldCharacterProfiles={listWorldCharacterProfiles} />;
}
