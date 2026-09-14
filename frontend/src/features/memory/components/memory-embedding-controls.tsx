"use client";

import { useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { Field, Select } from "@/components/ui/form-controls";
import { getMemoryEmbeddingSetting, saveMemoryEmbeddingSetting, MemoryApiError } from "@/features/memory/api/memory-client";
import type { MemoryEmbeddingSetting } from "@/features/memory/types/memory-embedding-contract";
import styles from "./memory-workspace.module.css";

type Props = { worldId: string; subjectId: string; disabled: boolean; acquire: () => boolean; release: () => void };

/** LOCAL: existing Memory form primitives, shared by Next and static/Tauri. */
export function MemoryEmbeddingControls({ worldId, subjectId, disabled, acquire, release }: Props) {
  const [saved, setSaved] = useState<MemoryEmbeddingSetting | null>(null);
  const [draft, setDraft] = useState<MemoryEmbeddingSetting | null>(null);
  const [notice, setNotice] = useState("");
  const [failed, setFailed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [revision, setRevision] = useState(0);
  const active = useRef(false);

  useEffect(() => {
    active.current = true;
    const controller = new AbortController();
    getMemoryEmbeddingSetting(worldId, subjectId, controller.signal).then((value) => {
      if (controller.signal.aborted) return;
      setSaved(value); setDraft(value);
    }).catch(() => {
      if (controller.signal.aborted) return;
      setNotice("의미 검색 설정을 불러오지 못했어요."); setFailed(true);
    });
    return () => { active.current = false; controller.abort(); };
  }, [worldId, subjectId, revision]);

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
          } : previous);
        }
      } catch { /* Keep the last observation; a failed poll must not overwrite an edit. */ }
      if (!controller.signal.aborted) timer = setTimeout(() => void refreshStatus(), 5000);
    }
    timer = setTimeout(() => void refreshStatus(), 5000);
    return () => { controller.abort(); clearTimeout(timer); };
  }, [worldId, subjectId, saved?.enabled, busy]);

  async function save() {
    if (!draft || !acquire()) return;
    setBusy(true); setNotice(""); setFailed(false);
    try {
      const value = await saveMemoryEmbeddingSetting(worldId, subjectId, {
        expected_version: draft.version, enabled: draft.enabled,
        provider: draft.provider, model: draft.model, credential_id: draft.credential_id,
      });
      if (!active.current) return;
      setSaved(value); setDraft(value); setNotice("의미 검색 설정을 저장했어요.");
    } catch (error) {
      if (!active.current) return;
      const conflict = error instanceof MemoryApiError && error.status === 409;
      setNotice(conflict ? "설정이 바뀌었어요. 최신 값을 확인한 뒤 다시 저장해 주세요." : "저장하지 못했어요. 선택한 API 설정을 확인해 주세요.");
      setFailed(true);
      if (conflict) { setSaved(null); setDraft(null); setRevision((value) => value + 1); }
    } finally { if (active.current) setBusy(false); release(); }
  }

  return <section className={styles.batchControls} aria-label="기억 의미 검색">
    <h2>기억 의미 검색</h2>
    <p>표현이 달라도 관련된 기억을 찾습니다. 이 World의 선택한 캐릭터에만 적용됩니다.</p>
    {saved && draft ? <>
      <p role="status">{!saved.enabled ? "의미 검색 꺼짐" : saved.ready ? "의미 검색 설정됨" : "API 설정 확인 필요"}</p>
      {saved.enabled && saved.runtime_status === "recovering" ? <p role="status">검색 자료를 복구하고 있어요. 준비되는 동안 키워드 검색을 사용합니다.</p> : null}
      {saved.enabled && ["degraded", "vector_unavailable", "stopped"].includes(saved.runtime_status) ? <p role="status">의미 검색을 현재 사용할 수 없어 키워드 검색을 사용합니다. 저장된 기억은 보존됩니다.</p> : null}
      {saved.enabled && saved.runtime_status === "ready" ? <p>검색 기능이 준비됐어요. 새 기억의 검색 자료는 순서대로 준비하며, 준비 전에는 키워드로 찾습니다.</p> : null}
      <fieldset disabled={disabled || busy}>
        <label className={styles.batchCheck}><input type="checkbox" checked={draft.enabled} onChange={(event) => setDraft({ ...draft, enabled: event.target.checked })} />의미 검색 사용</label>
        <Field label="임베딩 모델">{(props) => <Select {...props} value={draft.model} disabled><option value="gemini-embedding-2">Gemini Embedding 2</option></Select>}</Field>
        <Field label="의미 검색용 API 설정" helperText="내가 저장한 Google API 설정을 재사용합니다. 쪽지·기억 정리 모델은 변경하지 않습니다.">{(props) => <Select {...props} value={draft.credential_id ?? ""} onChange={(event) => setDraft({ ...draft, credential_id: event.target.value || null })}>
          <option value="">API 설정 선택</option>
          {draft.credential_id && !saved.available_credentials.some((item) => item.id === draft.credential_id) ? <option value={draft.credential_id}>사용할 수 없는 기존 설정</option> : null}
          {saved.available_credentials.map((item) => <option key={item.id} value={item.id}>{item.label}</option>)}
        </Select>}</Field>
        {saved.available_credentials.length === 0 ? <p>사용 가능한 Google API 설정이 없어요. 캐릭터 또는 쪽지 설정에서 먼저 등록해 주세요.</p> : null}
        <p>켜면 새로 정리되는 기억 요약과 검색 문구가 선택한 API로 전송되며 사용료가 발생할 수 있습니다. 끄더라도 저장된 기억과 검색 자료는 보존됩니다.</p>
      </fieldset>
      <Button compact disabled={disabled || (draft.enabled && !draft.credential_id)} loading={busy} loadingLabel="저장 중" onClick={() => void save()}>의미 검색 설정 저장</Button>
    </> : <Button compact variant="secondary" disabled={disabled} onClick={() => setRevision((value) => value + 1)}>{failed ? "설정 다시 불러오기" : "설정 불러오는 중"}</Button>}
    {notice ? <p role={failed ? "alert" : "status"}>{notice}</p> : null}
  </section>;
}
