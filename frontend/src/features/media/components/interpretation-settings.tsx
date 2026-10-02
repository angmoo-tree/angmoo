"use client";
import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { InlineError } from "@/components/ui/feedback";
import { getInterpretation, saveInterpretation } from "../api/media-client";
import type { InterpretationSettings } from "../types/media";
import styles from "./media-settings.module.css";

export function InterpretationSettingsPanel() {
  const [value, setValue] = useState<InterpretationSettings | null>(null);
  const [key, setKey] = useState(""); const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false); const [saved, setSaved] = useState(false);
  useEffect(() => { const controller = new AbortController(); getInterpretation(controller.signal).then(setValue).catch(reason => { if (!controller.signal.aborted) setError(String(reason)); }); return () => controller.abort(); }, []);
  async function save(clear = false) {
    if (!value) return; setBusy(true); setError(null); setSaved(false);
    try { setValue(await saveInterpretation({ ...value, expected_revision: value.revision, ...(key ? { api_key: key } : {}), ...(clear ? { clear_api_key: true, enabled: false } : {}) })); setKey(""); setSaved(true); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "설정을 저장하지 못했습니다."); }
    finally { setBusy(false); }
  }
  return <section className={styles.panel} aria-label="이미지 인식 설정"><h3>SNS·Chat 공통 이미지 인식</h3>
    <p>사진을 실제로 읽는 Gemini 설정입니다. 게시글 이미지 생성과 대화 응답 모델 설정은 각각 따로 유지됩니다.</p>
    {value ? <>
      <label className={styles.toggle}><input type="checkbox" checked={value.enabled} disabled={busy} onChange={e => setValue({ ...value, enabled: e.target.checked })} />새 이미지 인식 허용</label>
      <label>인식 모델<select value={value.model} onChange={e => setValue({ ...value, model: e.target.value as InterpretationSettings["model"] })}><option value="gemini-3.1-flash-lite">Gemini 3.1 Flash-Lite</option><option value="gemini-3.5-flash-lite">Gemini 3.5 Flash-Lite</option></select></label>
      <label>생각 수준<select value={value.thinking_level} onChange={e => setValue({ ...value, thinking_level: e.target.value as "medium" | "high" })}><option value="medium">Medium</option><option value="high">High</option></select></label>
      <label>일일 신규 인식 시도 상한<input type="number" min={1} max={10000} value={value.daily_limit ?? ""} onChange={e => setValue({ ...value, daily_limit: e.target.value ? Number(e.target.value) : null })} /></label>
      <label>인식용 Gemini API 키<input autoComplete="off" type="password" value={key} onChange={e => setKey(e.target.value)} placeholder={value.has_api_key ? "키가 저장되어 있습니다" : "키를 입력해 주세요"} /></label>
      <p className={styles.note}>같은 사진의 유효한 분석은 재사용합니다. OFF에서도 저장된 분석을 사용할 수 있습니다. 상한 기준은 Asia/Seoul입니다.</p>
      <div className={styles.actions}><Button disabled={busy} onClick={() => void save()}>인식 설정 저장</Button><Button variant="ghost" disabled={busy || !value.has_api_key} onClick={() => void save(true)}>인식 키 삭제</Button></div>
    </> : <p role="status">설정을 불러오는 중…</p>}
    {saved ? <p role="status">인식 설정을 저장했습니다.</p> : null}{error ? <InlineError>{error}</InlineError> : null}
  </section>;
}
