"use client";
import { SettingsCard } from "@/components/ui/settings-card";
import { Search } from "lucide-react";
import { MemoryCredentialFields } from "./memory-credential-fields";
import { useUiText } from "@/hooks/use-ui-text";


import { useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { getMemoryEmbeddingSetting, saveMemoryEmbeddingSetting, startMemoryEmbeddingPreparation, MemoryApiError } from "@/features/memory/api/memory-client";
import type { MemoryEmbeddingSetting } from "@/features/memory/types/memory-embedding-contract";
import styles from "./memory-workspace.module.css";
import { mergeEditedValue } from "@/lib/state/edited-fields";
import { useProductLeaveGuard } from "@/hooks/use-product-leave-guard";

type Props = { worldId: string; subjectId: string; disabled: boolean; acquire: () => boolean; release: () => void };
const editable = (value: MemoryEmbeddingSetting) => ({ enabled: value.enabled, provider: value.provider, model: value.model });

/** LOCAL: existing Memory form primitives, shared by Next and static/Tauri. */
export function MemoryEmbeddingControls({ worldId, subjectId, disabled, acquire, release }: Props) {
  const uiText = useUiText("memory");
  const [saved, setSaved] = useState<MemoryEmbeddingSetting | null>(null);
  const [draft, setDraft] = useState<MemoryEmbeddingSetting | null>(null);
  const [notice, setNotice] = useState("");
  const [failed, setFailed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [revision, setRevision] = useState(0);
  const [credentialDirty, setCredentialDirty] = useState(false);
  const [credentialReady, setCredentialReady] = useState(false);
  const active = useRef(false);
  const baseline = useRef<MemoryEmbeddingSetting | null>(null), saving = useRef<AbortController | null>(null);
  const [conflict, setConflict] = useState<MemoryEmbeddingSetting | null>(null);
  useProductLeaveGuard(Boolean(saved && draft && JSON.stringify(editable(saved)) !== JSON.stringify(editable(draft))) || busy);
  useEffect(() => () => saving.current?.abort(), []);

  useEffect(() => {
    active.current = true;
    const controller = new AbortController();
    getMemoryEmbeddingSetting(worldId, subjectId, controller.signal).then((value) => {
      if (controller.signal.aborted) return;
      setSaved(value); setDraft(previous => previous ?? value);
      baseline.current ??= value;
    }).catch(() => {
      if (controller.signal.aborted) return;
      setNotice(uiText("의미 검색 설정을 불러오지 못했어요.")); setFailed(true);
    });
    return () => { active.current = false; controller.abort(); };
  }, [worldId, subjectId, revision, uiText]);

  useEffect(() => {
    if (!saved?.enabled || busy) return;
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout>;
    async function refreshStatus() {
      try {
        const value = await getMemoryEmbeddingSetting(worldId, subjectId, controller.signal);
        if (!controller.signal.aborted) {
          setSaved((previous) => previous ? {
            ...previous, runtime_status: value.runtime_status, ready: value.ready,
            reason_code: value.reason_code, available_credentials: value.available_credentials,
            preparation_state: value.preparation_state, preparation_revision: value.preparation_revision,
          } : previous);
        }
      } catch { /* Keep the last observation; a failed poll must not overwrite an edit. */ }
      if (!controller.signal.aborted) timer = setTimeout(() => void refreshStatus(), 5000);
    }
    timer = setTimeout(() => void refreshStatus(), 5000);
    return () => { controller.abort(); clearTimeout(timer); };
  }, [worldId, subjectId, saved?.enabled, busy]);

  async function save() {
    if (!draft || conflict || !acquire()) return;
    const controller = new AbortController(); saving.current = controller;
    setBusy(true); setNotice(""); setFailed(false);
    try {
      const latest = await getMemoryEmbeddingSetting(worldId, subjectId, controller.signal);
      if (!active.current) return;
      const merged = mergeEditedValue(editable(baseline.current ?? latest), editable(latest), editable(draft));
      if (merged.conflicts.length) {
        setSaved(latest); setDraft({ ...latest, ...merged.value }); setConflict(latest); setFailed(true);
        setNotice(uiText("다른 곳에서 같은 항목을 변경했어요. 최신 값을 확인한 뒤 저장해주세요.")); return;
      }
      const value = await saveMemoryEmbeddingSetting(worldId, subjectId, {
        expected_version: latest.version, ...merged.value, credential_id: null,
      }, controller.signal);
      if (!active.current) return;
      setSaved(value); setDraft(value); setNotice(uiText("의미 검색 설정을 저장했어요."));
      baseline.current = value;
    } catch (error) {
      if (!active.current) return;
      const conflict = error instanceof MemoryApiError && error.status === 409;
      setNotice(conflict ? uiText("설정이 바뀌었어요. 최신 값을 확인한 뒤 다시 저장해 주세요.") : uiText("저장하지 못했어요. 선택한 API 설정을 확인해 주세요."));
      setFailed(true);
      if (conflict) setRevision((value) => value + 1);
    } finally { if (active.current) setBusy(false); release(); }
  }

  return <SettingsCard title={uiText("기억 의미 검색")} description={uiText("선택한 캐릭터의 기억을 의미로 찾아요.")} icon={<Search size={20} />}>
    <MemoryCredentialFields worldId={worldId} subjectId={subjectId} purpose="embedding" onMetadata={value => { setCredentialReady(value.has_key); setRevision(value => value + 1); }} onDirtyChange={setCredentialDirty} />
    {saved && draft ? <>
      <p role="status">{!saved.enabled ? uiText("의미 검색 꺼짐") : saved.ready ? uiText("의미 검색 설정됨") : uiText("API 설정 확인 필요")}</p>
      {saved.enabled && saved.runtime_status === "recovering" ? <p role="status">{uiText("검색 자료를 복구하고 있어요. 준비되는 동안 키워드 검색을 사용합니다.")}</p> : null}
      {saved.enabled && ["degraded", "vector_unavailable", "stopped"].includes(saved.runtime_status) ? <p role="status">{uiText("의미 검색을 현재 사용할 수 없어 키워드 검색을 사용합니다. 저장된 기억은 보존됩니다.")}</p> : null}
      {saved.enabled && saved.runtime_status === "ready" ? <p>{uiText("검색 기능이 준비됐어요. 새 기억의 검색 자료는 순서대로 준비하며, 준비 전에는 키워드로 찾습니다.")}</p> : null}
      <fieldset disabled={disabled || busy}>
        <label className={styles.batchCheck}><input type="checkbox" checked={draft.enabled} onChange={(event) => setDraft({ ...draft, enabled: event.target.checked })} />{uiText("의미 검색 사용")}</label>
        <p>{uiText("켜면 새로 정리되는 기억 요약과 검색 문구가 선택한 API로 전송되며 사용료가 발생할 수 있습니다. 끄더라도 저장된 기억과 검색 자료는 보존됩니다.")}</p>
      </fieldset>
      {conflict ? <div role="alert"><p>{uiText("의미 검색 사용")}: {uiText(conflict.enabled ? "켜짐" : "꺼짐")}</p><Button variant="secondary" onClick={() => { baseline.current = conflict; setConflict(null); }}>{uiText("최신 값을 확인했어요. 내 입력 유지")}</Button></div> : null}
      {draft.enabled && !credentialReady ? <p>{uiText("이 용도의 API key를 먼저 등록해주세요.")}</p> : null}
      <Button compact disabled={disabled || Boolean(conflict) || (draft.enabled && (!credentialReady || credentialDirty))} loading={busy} loadingLabel={uiText("저장 중")} onClick={() => void save()}>{uiText("의미 검색 설정 저장")}</Button>
    </> : <Button compact variant="secondary" disabled={disabled} onClick={() => setRevision((value) => value + 1)}>{failed ? uiText("설정 다시 불러오기") : uiText("설정 불러오는 중")}</Button>}
    {notice ? <p role={failed ? "alert" : "status"}>{notice}</p> : null}
    {saved ? <div><p role="status">{uiText(saved.preparation_state === "running" ? "검색 자료 준비 중" : saved.preparation_state === "ready" ? "검색 자료 준비됨" : saved.preparation_state === "error" ? "검색 자료 준비 실패" : "검색 자료 준비 필요")}</p>{(credentialDirty || (draft && JSON.stringify(editable(draft)) !== JSON.stringify(editable(saved)))) ? <p>{uiText("변경한 설정을 먼저 저장해주세요.")}</p> : null}<Button variant="secondary" disabled={disabled || busy || credentialDirty || !saved.enabled || !saved.ready || saved.preparation_state === "running" || Boolean(draft && JSON.stringify(editable(draft)) !== JSON.stringify(editable(saved)))} onClick={() => {
      if (!acquire()) return;
      const controller = new AbortController(); saving.current = controller;
      setBusy(true);
      void startMemoryEmbeddingPreparation(worldId, subjectId, saved.preparation_revision ?? 0, controller.signal).then(() => { if (active.current && !controller.signal.aborted) setRevision(v => v + 1); }).catch(() => { if (active.current && !controller.signal.aborted) { setFailed(true); setNotice(uiText("검색 자료를 준비하지 못했어요.")); } }).finally(() => { if (active.current && !controller.signal.aborted) setBusy(false); release(); });
    }}>{uiText("검색 자료 준비 시작")}</Button></div> : null}
  </SettingsCard>;
}
