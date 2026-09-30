"use client";
import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { InlineError } from "@/components/ui/feedback";
import { getUsage, saveUsage } from "../api/media-client";
import type { UsageSettings } from "../types/media";
import styles from "./media-settings.module.css";

export function ImageUsageSettingsPanel() {
  const [value, setValue] = useState<UsageSettings | null>(null);
  const [limit, setLimit] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  useEffect(() => {
    const controller = new AbortController();
    getUsage(controller.signal).then(data => { setValue(data); setLimit(String(data.daily_limit ?? "")); }).catch(reason => { if (!controller.signal.aborted) setError(reason instanceof Error ? reason.message : "사용량을 불러오지 못했습니다."); });
    return () => controller.abort();
  }, []);
  async function save() {
    if (!value) return;
    setBusy(true); setError(null); setNotice(null);
    try {
      const data = await saveUsage({ expected_revision: value.revision, daily_limit: Number(limit) });
      setValue(data); setLimit(String(data.daily_limit)); setNotice("전체 생성 상한을 저장했습니다.");
    } catch (reason) { setError(reason instanceof Error ? reason.message : "상한을 저장하지 못했습니다."); }
    finally { setBusy(false); }
  }
  return <section className={styles.panel} aria-label="이미지 사용량과 전체 상한"><h3>이미지 사용량과 전체 상한</h3>
    {value ? <><p>{value.quota_day} · Asia/Seoul 기준</p><p>전체 생성 예약·시도 {value.generation_reserved_or_used}회 / {value.daily_limit ?? "미설정"}회</p><p>공통 인식 예약·시도 {value.interpretation_reserved_or_used}회 / {value.interpretation_daily_limit ?? "미설정"}회</p>
      <label>설치 전체 일일 생성 시도 상한<input type="number" min={1} max={10000} disabled={busy} value={limit} onChange={e => setLimit(e.target.value)} /></label>
      <p className={styles.note}>캐릭터별 상한과 전체 상한을 모두 설정해야 자동 생성을 활성화할 수 있습니다. 결과가 불확실한 제출도 시도에 포함합니다. 저장된 분석과 같은 작업의 조회·로컬 복구는 추가 시도로 계산하지 않습니다.</p>
      <Button disabled={busy || !limit || Number(limit) < 1 || Number(limit) > 10000} onClick={() => void save()}>전체 생성 상한 저장</Button>
    </> : <p role="status">사용량을 불러오는 중…</p>}{notice ? <p role="status">{notice}</p> : null}{error ? <InlineError>{error}</InlineError> : null}
  </section>;
}
