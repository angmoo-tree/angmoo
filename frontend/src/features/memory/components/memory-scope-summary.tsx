"use client";
import { useUiText } from "@/hooks/use-ui-text";


import { useEffect, useState } from "react";

import { LocalProductLink } from "@/components/navigation/local-product-link";

import { getMemorySetting } from "@/features/memory/api/memory-client";
import type { MemorySettingRead } from "@/features/memory/types/memory-contract";
import styles from "./memory-workspace.module.css";

export function MemoryScopeSummary({
  subjectWorldCharacterId,
  worldId,
}: {
  subjectWorldCharacterId: string;
  worldId: string;
}) {
  const uiText = useUiText("memory");
  const [setting, setSetting] = useState<MemorySettingRead | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    const controller = new AbortController();
    void getMemorySetting(worldId, subjectWorldCharacterId, {
      signal: controller.signal,
    })
      .then((read) => {
        setSetting(read);
        setFailed(false);
      })
      .catch((reason: unknown) => {
        if (reason instanceof DOMException && reason.name === "AbortError") return;
        setFailed(true);
      });
    return () => controller.abort();
  }, [subjectWorldCharacterId, worldId]);

  const query = new URLSearchParams({
    subject: subjectWorldCharacterId,
    world: worldId,
  });
  return (
    <div className={styles.scopeSummary} data-memory-scope-summary="true">
      <p role="status">
        {uiText("기억")}<strong>{failed ? uiText("상태 확인 불가") : setting ? setting.enabled ? uiText("켜짐") : uiText("꺼짐") : uiText("확인 중")}</strong>
      </p>
      <LocalProductLink
        ariaLabel={uiText("이 Character의 저장된 기억 보기")}
        href={`/memory?${query}`}
      >
        {uiText("기억 보기")}</LocalProductLink>
    </div>
  );
}
