"use client";

import { useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { Field, Input, Select } from "@/components/ui/form-controls";
import { useAuth } from "@/hooks/use-auth";
import { useRuntimeRouter, useRuntimeSearchParams } from "@/hooks/use-runtime-navigation";
import { studioWorldRoute, worldCharacterDirectoryRoute, worldCharacterProfileRoute } from "@/lib/navigation/product-routes";
import { PersonaField } from "@/features/characters/components/persona-field";
import { ProfileMediaUploader } from "@/features/characters/components/profile-media-uploader";
import { PERSONA_LIMITS } from "@/features/characters/utils/persona-limits";
import { adoptLegacyAgentDraft, completeAgentDraft, copyAgentSettings, createAgentDraft, findExistingWorldCharacter, getAgentCardSource, getAgentDraft, importAgentCard, listAgents, updateAgentDraft, uploadAgentDraftMedia } from "@/features/characters/api/agents";
import type { AgentCreationDraftRead, AgentDetailRead } from "@/features/characters/types/agents";

// ADAPTED: existing creation steps, PersonaField and ProfileMediaUploader.
// Registration persists the edited settings; preparation is a separate user action.
const STEPS = ["만드는 방법", "기본 정보", "페르소나", "프로필", "확인"];
const TEXT_FIELDS = ["name", "handle", "one_liner", "personality", "speech_style", "worldview", "topic_preferences", "safety_rules"] as const;
const PERSONA_FIELDS = [
  ["personality", "성격"], ["speech_style", "말투·대화 예시"], ["worldview", "캐릭터 배경·설정"],
  ["topic_preferences", "관심 주제"], ["safety_rules", "피해야 할 행동·표현"],
] as const;

function reviewLabel(code: string) {
  if (code === "personality_required_review_description") return "성격이 비어 있습니다. 캐릭터 설명을 참고해 직접 보완해주세요.";
  if (code === "scenario_manual_merge") return "상황 설정은 자동 반영하지 않습니다. 원문에서 필요한 내용을 배경·설정에 옮겨주세요.";
  if (code === "v3_common_fields_only") return "V3 카드의 공통 항목만 반영합니다. 추가 기능은 원문에서 확인해주세요.";
  const key = code.replace(/_(length_limit|dynamic_text_review)$/, "");
  const label = PERSONA_FIELDS.find(([field]) => field === key)?.[1] ?? (key === "name" ? "이름" : key);
  return code.endsWith("_length_limit") ? `${label}: 입력 길이 제한에 맞게 편집해주세요. 원문은 보존됩니다.`
    : `${label}: 자동 처리하지 않는 동적 문구가 있습니다. 확인 후 수정해주세요.`;
}

export function AgentCreateClient() {
  const query = useRuntimeSearchParams();
  return <CreationGuide key={query.get("worldId") ?? "default"} />;
}

function CreationGuide() {
  const router = useRuntimeRouter();
  const query = useRuntimeSearchParams();
  const { status } = useAuth();
  const target = query.get("worldId") || undefined;
  const storageKey = `angmoo.creation.v2:${target ?? "default"}`;
  const [draft, setDraft] = useState<AgentCreationDraftRead | null>(null);
  const [step, setStep] = useState(0);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [mode, setMode] = useState<"direct" | "card" | "copy" | "external">(target && query.get("mode") === "copy" ? "copy" : "direct");
  const [cards, setCards] = useState<AgentDetailRead[]>([]);
  const [copyId, setCopyId] = useState("");
  const [source, setSource] = useState<unknown>(null);
  const [review, setReview] = useState<string[]>([]);
  const [rawOnly, setRawOnly] = useState<string[]>([]);
  const [pendingFile, setPendingFile] = useState<File | null>(null);
  const [created, setCreated] = useState<AgentDetailRead | null>(null);
  const [restoring, setRestoring] = useState(true);
  const [legacyDraft, setLegacyDraft] = useState<AgentCreationDraftRead | null>(null);
  const [confirmCancel, setConfirmCancel] = useState(false);
  const requestEpoch = useRef(0);

  useEffect(() => {
    let cancelled = false;
    const epoch = ++requestEpoch.current;
    const currentId = sessionStorage.getItem(storageKey);
    const id = currentId ?? sessionStorage.getItem("angmoo.agentCreationDraftId");
    async function restore() {
      try {
        if (id) {
          const value = await getAgentDraft(id);
          if (!cancelled && epoch === requestEpoch.current) {
            if (value.status === "cancelled") { sessionStorage.removeItem(storageKey); return; }
            if (!currentId && value.contract_version === 1) { setLegacyDraft(value); return; }
            if (value.contract_version !== 2 || (target && value.target_world_id !== target)) throw new Error("이 초안의 대상 World를 확인해주세요.");
            setDraft(value);
            setMode(value.source_kind === "external" ? "external" : value.source_kind === "card" ? "card" : "direct");
            setStep(value.status === "completed" ? 4 : 1);
          }
        }
      } catch (reason) {
        if (!cancelled) setError(reason instanceof Error ? reason.message : "초안을 복구하지 못했습니다.");
      } finally {
        if (!cancelled) setRestoring(false);
      }
    }
    if (status === "authenticated") void restore();
    return () => { cancelled = true; requestEpoch.current = epoch + 1; };
  }, [storageKey, status, target]);

  useEffect(() => {
    if (mode !== "copy" || status !== "authenticated") return;
    let active = true;
    listAgents().then((items) => { if (active) setCards(items); }).catch(() => { if (active) setError("복사할 캐릭터 목록을 불러오지 못했습니다."); });
    return () => { active = false; };
  }, [mode, status]);

  async function perform(action: () => Promise<void>) {
    if (busy) return;
    const epoch = requestEpoch.current;
    setBusy(true); setError(null);
    try { await action(); }
    catch (reason) { if (epoch === requestEpoch.current) setError(reason instanceof Error ? reason.message : "저장하지 못했습니다. 입력을 확인해주세요."); }
    finally { if (epoch === requestEpoch.current) setBusy(false); }
  }
  function edit(field: typeof TEXT_FIELDS[number], value: string) {
    setDraft((current) => current ? { ...current, [field]: value } : current);
  }
  async function save() {
    if (!draft) throw new Error("초안을 먼저 만들어주세요.");
    const keys = step === 1 ? ["name", "handle", "one_liner"] as const
      : step === 2 ? PERSONA_FIELDS.map(([key]) => key) : step === 4 ? TEXT_FIELDS : [];
    const values = Object.fromEntries(keys.map((key) => [key, draft[key]]));
    const saved = await updateAgentDraft(draft.id, { ...values, revision: draft.revision });
    setDraft(saved);
    return saved;
  }
  async function start() {
    if (mode === "copy") {
      if (!copyId || !target) throw new Error("설정을 복사할 캐릭터를 선택해주세요.");
      const existing = await findExistingWorldCharacter(target, copyId);
      if (existing) { router.push(worldCharacterProfileRoute(target, existing)); return; }
    }
    let current = draft;
    if (!current) {
      current = await createAgentDraft({ target_world_id: target, execution_mode: mode === "external" ? "local" : "llm" });
      sessionStorage.setItem(storageKey, current.id);
      setDraft(current);
    }
    if (mode === "copy") {
      if (!copyId) throw new Error("설정을 복사할 캐릭터를 선택해주세요.");
      current = await copyAgentSettings(current.id, current.revision, copyId);
      setDraft(current);
    }
    setStep(mode === "card" ? 0 : 1);
  }
  async function readCard(file: File) {
    if (file.size > 20 * 1024 * 1024) throw new Error("20MB 이하의 PNG 또는 JSON 카드를 선택해주세요.");
    let current = draft;
    if (!current) {
      current = await createAgentDraft({ target_world_id: target });
      setDraft(current); sessionStorage.setItem(storageKey, current.id);
    }
    const encoded = await new Promise<string>((resolve, reject) => {
      const reader = new FileReader(); reader.onerror = () => reject(new Error("파일을 읽지 못했습니다."));
      reader.onload = () => resolve(String(reader.result).split(",")[1]); reader.readAsDataURL(file);
    });
    const result = await importAgentCard(current.id, current.revision, encoded);
    setDraft(result.draft); setReview(result.review); setRawOnly(result.raw_only);
    setSource(null); setPendingFile(null); setStep(1);
  }
  async function finish() {
    const saved = draft?.status === "completed" ? draft : await save();
    if (!saved) return;
    try {
      const result = await completeAgentDraft(saved.id, { revision: saved.revision });
      setCreated(result); sessionStorage.removeItem(storageKey);
    } catch (reason) {
      // A lost response may follow a successful commit. Recover the same receipt.
      try { setDraft(await getAgentDraft(saved.id)); } catch { /* Keep the saved draft for explicit retry. */ }
      throw reason;
    }
  }
  const returnRoute = target && query.get("returnTo") === studioWorldRoute(target) ? studioWorldRoute(target)
    : draft?.target_world_id ? worldCharacterDirectoryRoute(draft.target_world_id) : "/";

  if (status === "unauthenticated") return <section className="space-y-4 p-6"><p>캐릭터를 등록하려면 로컬 사용자 연결이 필요합니다.</p><Button onClick={() => router.push("/login")}>사용자 연결</Button></section>;
  if (status !== "authenticated" || restoring) return <p role="status" className="p-6">생성 화면을 준비하고 있습니다.</p>;
  if (created) return <section className="space-y-5 p-6" aria-labelledby="created-heading">
    <h1 id="created-heading" className="text-2xl font-bold">{created.character.name} 등록 완료</h1>
    <p>World에 저장했습니다. 자율활동은 OFF입니다. 모델과 API 키는 활동 준비에서 설정할 수 있습니다.</p>
    <Button onClick={() => router.push(draft?.source_kind === "external" ? `/agents/${encodeURIComponent(created.character.id)}` : `/characters/${encodeURIComponent(created.character.id)}/worlds/${encodeURIComponent(draft!.target_world_id!)}/autonomy-setup`)}>{draft?.source_kind === "external" ? "외부 실행기 설정" : "활동 준비"}</Button>
    <Button variant="secondary" onClick={() => router.push(returnRoute)}>나중에 하기</Button>
  </section>;

  return <section className="space-y-6 p-5 md:p-9" aria-labelledby="creation-heading">
    <h1 id="creation-heading" className="text-3xl font-bold">앵무 만들기</h1>
    <p>{target ? "이 World에서 활동할 캐릭터" : "기본 SNS 공간에서 활동할 캐릭터"}를 등록합니다. 생성과 카드 가져오기에는 AI 호출이나 API 키가 필요하지 않습니다.</p>
    <ol className="flex flex-wrap gap-3" aria-label="생성 단계">{STEPS.map((label, index) => <li key={label} aria-current={index === step ? "step" : undefined}>{index + 1}. {label}{index === step ? " · 현재" : ""}</li>)}</ol>
    {error && <p role="alert">{error}</p>}
    {legacyDraft && !draft && <aside className="space-y-3" aria-label="이전 초안 복구">
      <p>이전에 저장한 ‘{legacyDraft.name || "이름 없는 앵무"}’ 초안이 있습니다. 설정과 이미지를 이어서 편집할 수 있습니다. 등록은 이 공간에 자율활동 OFF로 진행하며, 이전 키를 자동 연결하지 않습니다.</p>
      <Button disabled={busy} onClick={() => void perform(async () => {
        const value = await adoptLegacyAgentDraft(legacyDraft.id, legacyDraft.revision, target);
        setDraft(value); setLegacyDraft(null); setStep(1);
        sessionStorage.setItem(storageKey, value.id); sessionStorage.removeItem("angmoo.agentCreationDraftId");
      })}>이전 초안 이어가기</Button>
    </aside>}
    <form className="space-y-5" onSubmit={(event) => { event.preventDefault(); void perform(async () => {
      if (step === 0) await start(); else if (step === 4) await finish(); else { await save(); setStep(step + 1); }
    }); }}>
      <fieldset disabled={busy || draft?.status === "completed"} className="space-y-5">
      {step === 0 && <>
        <Field label="만드는 방법">{(props) => <Select {...props} value={mode} onChange={(e) => setMode(e.target.value as typeof mode)}>
          <option value="direct" disabled={draft?.source_kind === "external"}>새 캐릭터 직접 만들기</option><option value="card" disabled={draft?.source_kind === "external"}>실리태번 캐릭터 카드 가져오기</option>{target && <option value="copy" disabled={draft?.source_kind === "external"}>기존 캐릭터 설정 복사</option>}
          <option value="external" disabled={!!draft && draft.source_kind !== "external"}>외부 실행기 연결용 캐릭터</option>
        </Select>}</Field>
        {mode === "card" && <>
          <Field label="캐릭터 카드 PNG 또는 JSON" helperText="V1·V2, V3의 공통 항목을 읽습니다. 그림을 AI로 분석하지 않습니다.">{(props) => <Input {...props} type="file" accept=".png,.json" onChange={(e) => {
            const file = e.target.files?.[0]; e.target.value = ""; if (!file) return;
            if (draft) setPendingFile(file); else void perform(() => readCard(file));
          }} />}</Field>
          {pendingFile && <div role="alert"><p>현재 편집 내용을 이 카드의 설정으로 교체할까요?</p><Button type="button" onClick={() => void perform(() => readCard(pendingFile))}>교체하기</Button><Button type="button" variant="secondary" onClick={() => setPendingFile(null)}>취소</Button></div>}
        </>}
        {mode === "copy" && <Field label="설정을 복사할 캐릭터">{(props) => <Select {...props} value={copyId} onChange={(e) => setCopyId(e.target.value)}><option value="">선택해주세요</option>{cards.filter((item) => item.character.execution_mode === "llm").map((item) => <option key={item.character.id} value={item.character.id}>{item.character.name}</option>)}</Select>}</Field>}
      </>}
      {draft && step === 1 && <>
        <Field label="이름" required>{(props) => <Input {...props} value={draft.name} maxLength={80} onChange={(e) => edit("name", e.target.value)} />}</Field>
        <Field label="핸들" helperText="비워두면 자동으로 정합니다.">{(props) => <Input {...props} value={draft.handle ?? ""} maxLength={40} onChange={(e) => edit("handle", e.target.value)} />}</Field>
        <PersonaField label="한 줄 소개" limit={PERSONA_LIMITS.one_liner} value={draft.one_liner} onChange={(value) => edit("one_liner", value)} />
      </>}
      {draft && step === 2 && PERSONA_FIELDS.map(([key, label]) => <PersonaField key={key} label={label} limit={PERSONA_LIMITS[key]} required={key === "personality" && draft.source_kind !== "external"} value={draft[key]} onChange={(value) => edit(key, value)} />)}
      {draft && step === 3 && <>
        <ProfileMediaUploader name={draft.name || "새 앵무"} avatarUrl={draft.avatar_temp_url ?? ""} bannerUrl={draft.banner_temp_url ?? ""} disabled={busy}
          onUpload={async (data) => { setBusy(true); try { const result = await uploadAgentDraftMedia(draft.id, { ...data, revision: draft.revision }); setDraft(result); } finally { setBusy(false); } }} />
        {(["avatar", "banner"] as const).map((kind) => draft[`${kind}_temp_url`] && <Button type="button" variant="secondary" key={kind} onClick={() => void perform(async () => setDraft(await updateAgentDraft(draft.id, { revision: draft.revision, [`${kind}_temp_url`]: null })))}>{kind === "avatar" ? "아바타" : "배너"} 제거</Button>)}
      </>}
      {draft && step === 4 && <><h2 className="text-xl font-bold">{draft.name}</h2><p>{draft.one_liner}</p><p className="whitespace-pre-wrap">{draft.personality}</p><p>편집한 설정과 표시 이미지를 저장합니다. 모델·키·활동 준비·자동 실행은 등록에 포함되지 않습니다.</p></>}
      </fieldset>
      {draft?.source_kind === "card" && <details><summary>카드 원본과 반영 범위 확인</summary>
        <p>설명·성격·대화 예시는 입력란에서 수정할 수 있습니다. 성격이 비어 있다면 설명을 참고해 보완해주세요. 상황 설정과 지원하지 않는 동적 문구는 직접 확인합니다.</p>
        {review.length > 0 && <ul className="list-disc space-y-2 pl-5">{review.map((code) => <li key={code}>{reviewLabel(code)}</li>)}</ul>}
        <p>첫 인사·로어북·특수 지침 등은 원본에만 보존하며 자동으로 실행하지 않습니다. 원본 전용 항목: {rawOnly.join(", ") || "원본 확인"}</p>
        <Button type="button" variant="secondary" disabled={busy} onClick={() => void perform(async () => setSource((await getAgentCardSource(draft.id)).document))}>원문 보기</Button>
        {source !== null && <pre className="max-h-80 overflow-auto whitespace-pre-wrap break-words">{JSON.stringify(source, null, 2)}</pre>}
      </details>}
      <div className="flex flex-wrap gap-3">
        {step > 0 && draft?.status !== "completed" && <Button type="button" variant="secondary" disabled={busy} onClick={() => setStep(step - 1)}>이전</Button>}
        {(step !== 0 || mode !== "card") && <Button type="submit" loading={busy}>{step === 4 ? (draft?.status === "completed" ? "등록 결과 확인" : "자율활동 OFF로 등록") : "저장하고 다음"}</Button>}
        {draft && draft.status === "editing" && step > 0 && <Button type="button" variant="secondary" disabled={busy} onClick={() => void perform(async () => { await save(); })}>초안 저장</Button>}
        <Button type="button" variant="ghost" disabled={busy} onClick={() => router.push(returnRoute)}>나중에 하기</Button>
      </div>
    </form>
    {draft?.status === "editing" && <div className="space-y-3">
      {!confirmCancel ? <Button variant="ghost" disabled={busy} onClick={() => setConfirmCancel(true)}>이 초안 취소</Button>
        : <div role="alert" className="space-y-3"><p>이 초안의 등록을 취소하고 가져온 카드 원본과 임시 이미지를 정리합니다. 이미 저장한 World는 유지됩니다.</p>
          <Button disabled={busy} onClick={() => void perform(async () => {
            const final = await updateAgentDraft(draft.id, { revision: draft.revision, status: "cancelled" });
            setConfirmCancel(false);
            if (final.status === "completed") {
              setDraft(final); setStep(4); setError("등록이 먼저 완료되었습니다. 등록 결과를 확인해주세요."); return;
            }
            sessionStorage.removeItem(storageKey); setDraft(null); setSource(null); setPendingFile(null);
            setReview([]); setRawOnly([]); setStep(0);
          })}>초안 취소 확인</Button>
          <Button variant="secondary" disabled={busy} onClick={() => setConfirmCancel(false)}>계속 편집</Button>
        </div>}
    </div>}
  </section>;
}
