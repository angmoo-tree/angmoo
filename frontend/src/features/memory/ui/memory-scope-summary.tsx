"use client";

import { useEffect, useState } from "react";

import { LocalProductLink } from "@/features/device-shell/public";

import { getMemorySetting } from "../api/memory-client";
import type { MemorySettingRead } from "../model/memory-contract";
import styles from "./memory-workspace.module.css";

export function MemoryScopeSummary({
  subjectWorldCharacterId,
  worldId,
}: {
  subjectWorldCharacterId: string;
  worldId: string;
}) {
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
        기억 <strong>{failed ? "상태 확인 불가" : setting ? setting.enabled ? "켜짐" : "꺼짐" : "확인 중"}</strong>
      </p>
      <LocalProductLink
        ariaLabel="이 Character의 저장된 기억 보기"
        href={`/memory?${query}`}
      >
        기억 보기
      </LocalProductLink>
    </div>
  );
}
