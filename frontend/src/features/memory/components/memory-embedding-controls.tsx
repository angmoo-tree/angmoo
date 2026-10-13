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

import type { SavedEmbeddingController } from "../hooks/use-saved-embedding";

type Props = { embedding: SavedEmbeddingController; worldId: string; subjectId: string; disabled: boolean; acquire: () => boolean; release: () => void };
const editable = (value: MemoryEmbeddingSetting) => ({ enabled: value.enabled, provider: value.provider, model: value.model });

/** LOCAL: existing Memory form primitives, shared by Next and static/Tauri. */
export function MemoryEmbeddingControls({ embedding, worldId, subjectId, disabled, acquire, release }: Props) {
  const uiText = useUiText("memory");
  const saved = embedding.saved;
  const [draft, setDraft] = useState<MemoryEmbeddingSetting | null>(null);
  const [notice, setNotice] = useState("");
  const [failed, setFailed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [credentialDirty, setCredentialDirty] = useState(false);
  const credentialReady = !embedding.error && Boolean(embedding.credential?.has_key);
  const active = useRef(false);
  const baseline = useRef<MemoryEmbeddingSetting | null>(null), saving = useRef<AbortController | null>(null);
  const [conflict, setConflict] = useState<MemoryEmbeddingSetting | null>(null);
  useProductLeaveGuard(Boolean(saved && draft && JSON.stringify(editable(saved)) !== JSON.stringify(editable(draft))) || busy);
  useEffect(() => () => saving.current?.abort(), []);

  useEffect(() => { active.current = true; return () => { active.current = false; }; }, []);
  useEffect(() => {
    if (!saved) return;
    queueMicrotask(() => setDraft(previous => {
      const clean = !previous || !baseline.current || JSON.stringify(editable(previous)) === JSON.stringify(editable(baseline.current));
      if (clean) { baseline.current = saved; return saved; }
      return previous;
    }));
  }, [saved]);

  async function save() {
    if (!draft || conflict || !acquire()) return;
    const controller = new AbortController(); saving.current = controller;
    setBusy(true); setNotice(""); setFailed(false);
    try {
      const latest = await getMemoryEmbeddingSetting(worldId, subjectId, controller.signal);
      if (!active.current) return;
      const merged = mergeEditedValue(editable(baseline.current ?? latest), editable(latest), editable(draft));
      if (merged.conflicts.length) {
        embedding.refresh(); setDraft({ ...latest, ...merged.value }); setConflict(latest); setFailed(true);
        setNotice(uiText("다른 곳에서 같은 항목을 변경했어요. 최신 값을 확인한 뒤 저장해주세요.")); return;
      }
      const value = await saveMemoryEmbeddingSetting(worldId, subjectId, {
        expected_version: latest.version, ...merged.value, credential_id: null,
      }, controller.signal);
      if (!active.current) return;
      embedding.refresh(); setDraft(value); setNotice(uiText("의미 검색 설정을 저장했어요."));
      baseline.current = value;
    } catch (error) {
      if (!active.current) return;
      const conflict = error instanceof MemoryApiError && error.status === 409;
      setNotice(conflict ? uiText("설정이 바뀌었어요. 최신 값을 확인한 뒤 다시 저장해 주세요.") : uiText("저장하지 못했어요. 선택한 API 설정을 확인해 주세요."));
      setFailed(true);
      if (conflict) embedding.refresh();
    } finally { if (active.current) setBusy(false); release(); }
  }

  return <SettingsCard elevated title={uiText("임베딩 모델 API 키")} description={uiText("새로 저장된 기억의 의미 검색 자료를 준비하고, 검색할 때 검색 문구를 임베딩하는 데 사용해요.")} icon={<Search size={20} />}>
    {embedding.credential ? <MemoryCredentialFields worldId={worldId} subjectId={subjectId} purpose="embedding" initialMetadata={embedding.credential} onSaved={() => embedding.refresh()} onDirtyChange={setCredentialDirty} /> : null}
    {saved && draft ? <>
      <p role="status">{!saved.enabled ? uiText("의미 검색 꺼짐") : saved.ready ? uiText("의미 검색 설정됨") : uiText("API 설정 확인 필요")}</p>
      {saved.enabled && saved.runtime_status === "recovering" ? <p role="status">{uiText("검색 자료를 복구하고 있어요. 준비되는 동안 키워드 검색을 사용합니다.")}</p> : null}
      {saved.enabled && ["degraded", "vector_unavailable", "stopped"].includes(saved.runtime_status) ? <p role="status">{uiText("의미 검색을 현재 사용할 수 없어 키워드 검색을 사용합니다. 저장된 기억은 보존됩니다.")}</p> : null}
      {saved.enabled && saved.runtime_status === "ready" ? <p>{uiText("검색 기능이 준비됐어요. 새 기억의 검색 자료는 순서대로 준비하며, 준비 전에는 키워드로 찾습니다.")}</p> : null}
      <fieldset disabled={disabled || busy}>
        <label className={styles.batchCheck}><input type="checkbox" checked={draft.enabled} onChange={(event) => setDraft({ ...draft, enabled: event.target.checked })} />{uiText("의미 검색 사용")}</label>
        <p>{uiText("의미 검색을 켜면 두 작업에 같은 API 키를 사용해요. 기억 내용과 검색 문구가 선택한 API로 전송되며 사용료가 발생할 수 있어요.")}</p>
      </fieldset>
      {conflict ? <div role="alert"><p>{uiText("의미 검색 사용")}: {uiText(conflict.enabled ? "켜짐" : "꺼짐")}</p><Button variant="secondary" onClick={() => { baseline.current = conflict; setConflict(null); }}>{uiText("최신 값을 확인했어요. 내 입력 유지")}</Button></div> : null}
      {draft.enabled && !credentialReady ? <p>{uiText("이 용도의 API key를 먼저 등록해주세요.")}</p> : null}
      <Button compact disabled={disabled || Boolean(conflict) || (draft.enabled && (!credentialReady || credentialDirty))} loading={busy} loadingLabel={uiText("저장 중")} onClick={() => void save()}>{uiText("의미 검색 설정 저장")}</Button>
    </> : <Button compact variant="secondary" disabled={disabled} onClick={() => embedding.refresh()}>{failed ? uiText("설정 다시 불러오기") : uiText("설정 불러오는 중")}</Button>}
    {embedding.error ? <p role="alert">{uiText("임베딩 설정 상태를 확인하지 못했어요.")}<Button variant="secondary" onClick={embedding.refresh}>{uiText("다시 시도")}</Button></p> : null}
    {notice ? <p role={failed ? "alert" : "status"}>{notice}</p> : null}
    {saved ? <div><p role="status">{uiText(saved.preparation_state === "running" ? "검색 자료 준비 중" : saved.preparation_state === "ready" ? "검색 자료 준비됨" : saved.preparation_state === "error" ? "검색 자료 준비 실패" : "검색 자료 준비 필요")}</p>{(credentialDirty || (draft && JSON.stringify(editable(draft)) !== JSON.stringify(editable(saved)))) ? <p>{uiText("변경한 설정을 먼저 저장해주세요.")}</p> : null}<Button variant="secondary" disabled={disabled || busy || credentialDirty || !saved.enabled || !saved.ready || saved.preparation_state === "running" || Boolean(draft && JSON.stringify(editable(draft)) !== JSON.stringify(editable(saved)))} onClick={() => {
      if (!acquire()) return;
      const controller = new AbortController(); saving.current = controller;
      setBusy(true);
      void startMemoryEmbeddingPreparation(worldId, subjectId, saved.preparation_revision ?? 0, controller.signal).then(() => { if (active.current && !controller.signal.aborted) embedding.refresh(); }).catch(() => { if (active.current && !controller.signal.aborted) { setFailed(true); setNotice(uiText("검색 자료를 준비하지 못했어요.")); } }).finally(() => { if (active.current && !controller.signal.aborted) setBusy(false); release(); });
    }}>{uiText("검색 자료 준비 시작")}</Button></div> : null}
  </SettingsCard>;
}
