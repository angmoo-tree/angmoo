"use client";
import { useUiText, type UiText } from "@/hooks/use-ui-text";


import { useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { Field, Input, Select } from "@/components/ui/form-controls";
import { useAuth } from "@/hooks/use-auth";
import { useRuntimeRouter, useRuntimeSearchParams } from "@/hooks/use-runtime-navigation";
import { isTauriDesktopRuntime, navigateDesktopProductRoute } from "@/lib/desktop/product-window";
import { studioWorldRoute, worldCharacterDirectoryRoute, worldCharacterProfileRoute } from "@/lib/navigation/product-routes";
import { PersonaField } from "@/features/characters/components/persona-field";
import { ProfileMediaUploader } from "@/features/characters/components/profile-media-uploader";
import { PERSONA_LIMITS } from "@/features/characters/utils/persona-limits";
import { adoptLegacyAgentDraft, completeAgentDraft, copyAgentSettings, createAgentDraft, findExistingWorldCharacter, getAgentCardMetadata, getAgentCardSource, getAgentDraft, importAgentCard, listAgents, updateAgentDraft, uploadAgentDraftMedia } from "@/features/characters/api/agents";
import type { AgentCreationDraftRead, AgentDetailRead, CharacterCardMetadataSelection } from "@/features/characters/types/agents";

// ADAPTED: existing creation steps, PersonaField and ProfileMediaUploader.
// Registration persists the edited settings; preparation is a separate user action.
const STEPS = ["만드는 방법", "기본 정보", "페르소나", "프로필", "확인"];
const TEXT_FIELDS = ["name", "handle", "one_liner", "worldview", "personality", "speech_style", "character_background", "topic_preferences", "safety_rules"] as const;
const PERSONA_FIELDS = [
  ["worldview", "캐릭터 설명"], ["personality", "성격"], ["speech_style", "말투·대화 예시"], ["character_background", "캐릭터 배경·세계관"],
  ["topic_preferences", "관심 주제"], ["safety_rules", "피해야 할 행동·표현"],
] as const;

function reviewLabel(code: string, uiText: UiText) {
  if (code === "description_required_review") return uiText("캐릭터 설명이 비어 있습니다. 등록 전에 짧은 설명을 작성해주세요.");
  if (code === "scenario_manual_merge") return uiText("상황 설정은 자동 반영하지 않습니다. 원문에서 필요한 내용을 배경·설정에 옮겨주세요.");
  if (code === "v3_common_fields_only") return uiText("V3 카드의 공통 항목만 반영합니다. 추가 기능은 원문에서 확인해주세요.");
  const key = code.replace(/_(length_limit|dynamic_text_review|name_binding)$/, "");
  const label = uiText(PERSONA_FIELDS.find(([field]) => field === key)?.[1] ?? (key === "name" ? "이름" : key));
  if (code.endsWith("_name_binding")) return uiText("{{label}}: 이름 표기는 활동할 때 현재 World의 이름으로 적용됩니다. 원본 설정은 유지됩니다.", {label});
  return code.endsWith("_length_limit") ? uiText("{{label}}: 입력 길이 제한에 맞게 편집해주세요. 원문은 보존됩니다.", {label})
    : uiText("{{label}}: 자동 처리하지 않는 동적 문구가 있습니다. 확인 후 수정해주세요.", {label});
}

export function AgentCreateClient() {
  const query = useRuntimeSearchParams();
  return <CreationGuide key={query.get("worldId") ?? "default"} />;
}

function CreationGuide() {
  const uiText = useUiText("characters");
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
  const [metadataSelection, setMetadataSelection] = useState<CharacterCardMetadataSelection | null>(null);
  const [cardMetadataError, setCardMetadataError] = useState<string | null>(null);
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
            if (value.contract_version !== 2 || (target && value.target_world_id !== target)) throw new Error(uiText("이 초안의 대상 World를 확인해주세요."));
            setDraft(value);
            setMode(value.source_kind === "external" ? "external" : value.source_kind === "card" ? "card" : "direct");
            setStep(value.status === "completed" ? 4 : 1);
            if (value.source_kind === "card") {
              try {
                const summary = await getAgentCardMetadata(value.id);
                if (!cancelled && epoch === requestEpoch.current) {
                  setMetadataSelection(summary.metadata_selection);
                  setReview(summary.review); setRawOnly(summary.raw_only);
                }
              } catch {
                if (!cancelled && epoch === requestEpoch.current) setCardMetadataError(uiText("카드의 선택 정보를 불러오지 못했습니다. 편집 내용은 유지됩니다."));
              }
            }
          }
        }
      } catch (reason) {
        if (!cancelled) setError(reason instanceof Error ? uiText(reason.message) : uiText("초안을 복구하지 못했습니다."));
      } finally {
        if (!cancelled) setRestoring(false);
      }
    }
    if (status === "authenticated") void restore();
    return () => { cancelled = true; requestEpoch.current = epoch + 1; };
  }, [storageKey, status, target, uiText]);

  useEffect(() => {
    if (mode !== "copy" || status !== "authenticated") return;
    let active = true;
    listAgents().then((items) => { if (active) setCards(items); }).catch(() => { if (active) setError(uiText("복사할 캐릭터 목록을 불러오지 못했습니다.")); });
    return () => { active = false; };
  }, [mode, status, uiText]);

  async function perform(action: () => Promise<void>) {
    if (busy) return;
    const epoch = requestEpoch.current;
    setBusy(true); setError(null);
    try { await action(); }
    catch (reason) { if (epoch === requestEpoch.current) setError(reason instanceof Error ? uiText(reason.message) : uiText("저장하지 못했습니다. 입력을 확인해주세요.")); }
    finally { if (epoch === requestEpoch.current) setBusy(false); }
  }
  function edit(field: typeof TEXT_FIELDS[number], value: string) {
    setDraft((current) => current ? { ...current, [field]: value } : current);
  }
  async function save() {
    if (!draft) throw new Error(uiText("초안을 먼저 만들어주세요."));
    const keys = step === 1 ? ["name", "handle", "one_liner"] as const
      : step === 2 ? PERSONA_FIELDS.map(([key]) => key) : step === 4 ? TEXT_FIELDS : [];
    const values = Object.fromEntries(keys.map((key) => [key, draft[key]]));
    const saved = await updateAgentDraft(draft.id, { ...values, revision: draft.revision });
    setDraft(saved);
    return saved;
  }
  async function start() {
    if (mode === "copy") {
      if (!copyId || !target) throw new Error(uiText("설정을 복사할 캐릭터를 선택해주세요."));
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
      if (!copyId) throw new Error(uiText("설정을 복사할 캐릭터를 선택해주세요."));
      current = await copyAgentSettings(current.id, current.revision, copyId);
      setDraft(current);
    }
    setStep(mode === "card" ? 0 : 1);
  }
  async function readCard(file: File) {
    const epoch = requestEpoch.current;
    if (file.size > 20 * 1024 * 1024) throw new Error(uiText("20MB 이하의 PNG 또는 JSON 카드를 선택해주세요."));
    let current = draft;
    if (!current) {
      current = await createAgentDraft({ target_world_id: target });
      if (epoch !== requestEpoch.current) return;
      setDraft(current); sessionStorage.setItem(storageKey, current.id);
    }
    const encoded = await new Promise<string>((resolve, reject) => {
      const reader = new FileReader(); reader.onerror = () => reject(new Error(uiText("파일을 읽지 못했습니다.")));
      reader.onload = () => resolve(String(reader.result).split(",")[1]); reader.readAsDataURL(file);
    });
    if (epoch !== requestEpoch.current) return;
    const result = await importAgentCard(current.id, current.revision, encoded);
    if (epoch !== requestEpoch.current) return;
    setDraft(result.draft); setReview(result.review); setRawOnly(result.raw_only);
    setMetadataSelection(result.metadata_selection); setCardMetadataError(null);
    setSource(null); setPendingFile(null); setStep(1);
  }
  async function reloadCardMetadata() {
    if (!draft || draft.source_kind !== "card") return;
    const epoch = requestEpoch.current;
    try {
      const summary = await getAgentCardMetadata(draft.id);
      if (epoch !== requestEpoch.current) return;
      setMetadataSelection(summary.metadata_selection);
      setReview(summary.review); setRawOnly(summary.raw_only); setCardMetadataError(null);
    } catch {
      if (epoch === requestEpoch.current) setCardMetadataError(uiText("카드의 선택 정보를 불러오지 못했습니다. 편집 내용은 유지됩니다."));
    }
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
  async function returnAfterRegistration() {
    const href = target && created && returnRoute === studioWorldRoute(target)
      ? `${returnRoute}?createdCharacterId=${encodeURIComponent(created.character.id)}` : returnRoute;
    try {
      if (isTauriDesktopRuntime()) await navigateDesktopProductRoute(href);
      else router.push(href);
    } catch {
      throw new Error(uiText("캐릭터는 등록되었습니다. 돌아갈 화면을 열지 못했습니다. 다시 시도해주세요."));
    }
  }

  if (status === "unauthenticated") return <section className="space-y-4 p-6"><p>{uiText("캐릭터를 등록하려면 로컬 사용자 연결이 필요합니다.")}</p><Button onClick={() => router.push("/login")}>{uiText("사용자 연결")}</Button></section>;
  if (status !== "authenticated" || restoring) return <p role="status" className="p-6">{uiText("생성 화면을 준비하고 있습니다.")}</p>;
  if (created) return <section className="space-y-5 p-6" aria-labelledby="created-heading">
    <h1 id="created-heading" className="text-2xl font-bold">{created.character.name} {uiText("등록 완료")}</h1>
    <p>{uiText("World에 저장했습니다. 자율활동은 OFF입니다. 모델과 API 키는 활동 준비에서 설정할 수 있습니다.")}</p>
    {error && <p role="alert">{error}</p>}
    <Button onClick={() => router.push(draft?.source_kind === "external" ? `/agents/${encodeURIComponent(created.character.id)}` : `/characters/${encodeURIComponent(created.character.id)}/worlds/${encodeURIComponent(draft!.target_world_id!)}/autonomy-setup`)}>{draft?.source_kind === "external" ? uiText("외부 실행기 설정") : uiText("활동 준비")}</Button>
    <Button variant="secondary" loading={busy} onClick={() => void perform(returnAfterRegistration)}>{uiText("나중에 하기")}</Button>
  </section>;

  return <section className="space-y-6 p-5 md:p-9" aria-labelledby="creation-heading">
    <h1 id="creation-heading" className="text-3xl font-bold">{uiText("앵무 만들기")}</h1>
    <p>{target ? uiText("이 World에서 활동할 캐릭터") : uiText("기본 SNS 공간에서 활동할 캐릭터")}{uiText("를 등록합니다. 생성과 카드 가져오기에는 AI 호출이나 API 키가 필요하지 않습니다.")}</p>
    <ol className="flex flex-wrap gap-3" aria-label={uiText("생성 단계")}>{STEPS.map((label, index) => <li key={label} aria-current={index === step ? "step" : undefined}>{index + 1}. {uiText(label)}{index === step ? uiText("· 현재") : ""}</li>)}</ol>
    {error && <p role="alert">{error}</p>}
    {/* LOCAL: non-blocking metadata notice, shared by Next and static creation. */}
    {draft?.source_kind === "card" && mode === "card" && metadataSelection?.multiple_definitions && <p role="status" className="rounded-xl border border-state-warning-border bg-state-warning-surface p-4 text-sm text-state-warning">
      {uiText("이 카드에는 같은 형식의 캐릭터 정의가 여러 개 있습니다. 실리태번과 같은 순서로 첫 번째 정의를 가져왔습니다. 등록 전에 이름과 설명을 확인해주세요.")}</p>}
    {draft?.source_kind === "card" && mode === "card" && cardMetadataError && <div className="space-y-2">
      <p role="alert">{cardMetadataError}</p>
      <Button type="button" variant="secondary" disabled={busy} onClick={() => void perform(reloadCardMetadata)}>{uiText("카드 정보 다시 불러오기")}</Button>
    </div>}
    {legacyDraft && !draft && <aside className="space-y-3" aria-label={uiText("이전 초안 복구")}>
      <p>{uiText("이전에 저장한 ‘")}{legacyDraft.name || uiText("이름 없는 앵무")}{uiText("’ 초안이 있습니다. 설정과 이미지를 이어서 편집할 수 있습니다. 등록은 이 공간에 자율활동 OFF로 진행하며, 이전 키를 자동 연결하지 않습니다.")}</p>
      <Button disabled={busy} onClick={() => void perform(async () => {
        const value = await adoptLegacyAgentDraft(legacyDraft.id, legacyDraft.revision, target);
        setDraft(value); setLegacyDraft(null); setStep(1);
        sessionStorage.setItem(storageKey, value.id); sessionStorage.removeItem("angmoo.agentCreationDraftId");
      })}>{uiText("이전 초안 이어가기")}</Button>
    </aside>}
    <form className="space-y-5" onSubmit={(event) => { event.preventDefault(); void perform(async () => {
      if (step === 0) await start(); else if (step === 4) await finish(); else { await save(); setStep(step + 1); }
    }); }}>
      <fieldset disabled={busy || draft?.status === "completed"} className="space-y-5">
      {step === 0 && <>
        <Field label={uiText("만드는 방법")}>{(props) => <Select {...props} value={mode} onChange={(e) => {
          const nextMode = e.target.value as typeof mode;
          setMode(nextMode); setPendingFile(null); setSource(null);
          if (nextMode !== "card") { setMetadataSelection(null); setCardMetadataError(null); setReview([]); setRawOnly([]); }
          else if (draft?.source_kind === "card") void perform(reloadCardMetadata);
        }}>
          <option value="direct" disabled={draft?.source_kind === "external"}>{uiText("새 캐릭터 직접 만들기")}</option><option value="card" disabled={draft?.source_kind === "external"}>{uiText("실리태번 캐릭터 카드 가져오기")}</option>{target && <option value="copy" disabled={draft?.source_kind === "external"}>{uiText("기존 캐릭터 설정 복사")}</option>}
          <option value="external" disabled={!!draft && draft.source_kind !== "external"}>{uiText("외부 실행기 연결용 캐릭터")}</option>
        </Select>}</Field>
        {mode === "card" && <>
          <Field label={uiText("캐릭터 카드 PNG 또는 JSON")} helperText={uiText("V1·V2, V3의 공통 항목을 읽습니다. 그림을 AI로 분석하지 않습니다.")}>{(props) => <Input {...props} type="file" accept=".png,.json" onChange={(e) => {
            const file = e.target.files?.[0]; e.target.value = ""; if (!file) return;
            if (draft) setPendingFile(file); else void perform(() => readCard(file));
          }} />}</Field>
          {pendingFile && <div role="alert"><p>{uiText("현재 편집 내용을 이 카드의 설정으로 교체할까요?")}</p><Button type="button" onClick={() => void perform(() => readCard(pendingFile))}>{uiText("교체하기")}</Button><Button type="button" variant="secondary" onClick={() => setPendingFile(null)}>{uiText("취소")}</Button></div>}
        </>}
        {mode === "copy" && <Field label={uiText("설정을 복사할 캐릭터")}>{(props) => <Select {...props} value={copyId} onChange={(e) => setCopyId(e.target.value)}><option value="">{uiText("선택해주세요")}</option>{cards.filter((item) => item.character.execution_mode === "llm").map((item) => <option key={item.character.id} value={item.character.id}>{item.character.name}</option>)}</Select>}</Field>}
      </>}
      {draft && step === 1 && <>
        <Field label={uiText("이름")} required>{(props) => <Input {...props} value={draft.name} maxLength={80} onChange={(e) => edit("name", e.target.value)} />}</Field>
        <Field label={uiText("핸들")} helperText={uiText("비워두면 자동으로 정합니다.")}>{(props) => <Input {...props} value={draft.handle ?? ""} maxLength={40} onChange={(e) => edit("handle", e.target.value)} />}</Field>
        <PersonaField label={uiText("한 줄 소개")} limit={PERSONA_LIMITS.one_liner} value={draft.one_liner} onChange={(value) => edit("one_liner", value)} />
      </>}
      {draft && step === 2 && <>
        <PersonaField label={uiText("캐릭터 설명")} limit={PERSONA_LIMITS.worldview} required={draft.source_kind !== "external"} value={draft.worldview} onChange={(value) => edit("worldview", value)} />
        <p className="text-sm text-muted-foreground">{uiText("성격·말투·배경을 설명에 함께 적어도 됩니다. 더 나누어 관리하고 싶으면 아래 선택 항목을 사용하세요.")}</p>
        <details open={Boolean(draft.personality || draft.speech_style || draft.character_background || draft.topic_preferences || draft.safety_rules)}>
          <summary className="cursor-pointer font-semibold">{uiText("선택 상세 설정")}</summary>
          <div className="mt-4 space-y-4">{PERSONA_FIELDS.filter(([key]) => key !== "worldview").map(([key, label]) => <PersonaField key={key} label={uiText(label)} limit={PERSONA_LIMITS[key]} value={draft[key] ?? ""} onChange={(value) => edit(key, value)} />)}</div>
        </details>
      </>}
      {draft && step === 3 && <>
        <ProfileMediaUploader name={draft.name || uiText("새 앵무")} avatarUrl={draft.avatar_temp_url ?? ""} bannerUrl={draft.banner_temp_url ?? ""} disabled={busy}
          onUpload={async (data) => { setBusy(true); try { const result = await uploadAgentDraftMedia(draft.id, { ...data, revision: draft.revision }); setDraft(result); } finally { setBusy(false); } }} />
        {(["avatar", "banner"] as const).map((kind) => draft[`${kind}_temp_url`] && <Button type="button" variant="secondary" key={kind} onClick={() => void perform(async () => setDraft(await updateAgentDraft(draft.id, { revision: draft.revision, [`${kind}_temp_url`]: null })))}>{kind === "avatar" ? uiText("아바타") : uiText("배너")} {uiText("제거")}</Button>)}
      </>}
      {draft && step === 4 && <><h2 className="text-xl font-bold">{draft.name}</h2><p>{draft.one_liner}</p>{PERSONA_FIELDS.filter(([key]) => Boolean(draft[key])).map(([key, label]) => <div key={key}><h3 className="font-semibold">{uiText(label)}</h3><p className="whitespace-pre-wrap">{draft[key]}</p></div>)}<p>{uiText("편집한 설정과 표시 이미지를 저장합니다. 모델·키·활동 준비·자동 실행은 등록에 포함되지 않습니다.")}</p></>}
      </fieldset>
      {draft?.source_kind === "card" && mode === "card" && <details><summary>{uiText("카드 원본과 반영 범위 확인")}</summary>
        <p>{uiText("설명·성격·대화 예시는 입력란에서 수정할 수 있습니다. 설명이 비어 있다면 등록 전에 작성해주세요. 상황 설정과 지원하지 않는 동적 문구는 직접 확인합니다.")}</p>
        {metadataSelection && <p>{uiText("반영한 정의:")}{metadataSelection.keyword}{uiText("의 첫 번째 항목 / 같은 형식의 정의")}{metadataSelection.same_keyword_count}{uiText("개. 원본 PNG 전체는 그대로 보존합니다.")}</p>}
        {review.length > 0 && <ul className="list-disc space-y-2 pl-5">{review.map((code) => <li key={code}>{reviewLabel(code, uiText)}</li>)}</ul>}
        <p>{uiText("첫 인사·로어북·특수 지침 등은 원본에만 보존하며 자동으로 실행하지 않습니다. 원본 전용 항목:")}{rawOnly.join(", ") || uiText("원본 확인")}</p>
        <p>{uiText("원문 보기는 선택된 한 정의의 JSON을 표시합니다. 편집한 캐릭터 설정과 보관한 카드 원본은 구분됩니다.")}</p>
        <Button type="button" variant="secondary" disabled={busy} onClick={() => void perform(async () => {
          const epoch = requestEpoch.current;
          const result = await getAgentCardSource(draft.id);
          if (epoch === requestEpoch.current) setSource(result.document);
        })}>{uiText("원문 보기")}</Button>
        {source !== null && <pre className="max-h-80 overflow-auto whitespace-pre-wrap break-words">{JSON.stringify(source, null, 2)}</pre>}
      </details>}
      <div className="flex flex-wrap gap-3">
        {step > 0 && draft?.status !== "completed" && <Button type="button" variant="secondary" disabled={busy} onClick={() => setStep(step - 1)}>{uiText("이전")}</Button>}
        {(step !== 0 || mode !== "card") && <Button type="submit" loading={busy}>{step === 4 ? (draft?.status === "completed" ? uiText("등록 결과 확인") : uiText("자율활동 OFF로 등록")) : uiText("저장하고 다음")}</Button>}
        {draft && draft.status === "editing" && step > 0 && <Button type="button" variant="secondary" disabled={busy} onClick={() => void perform(async () => { await save(); })}>{uiText("초안 저장")}</Button>}
        <Button type="button" variant="ghost" disabled={busy} onClick={() => router.push(returnRoute)}>{uiText("나중에 하기")}</Button>
      </div>
    </form>
    {draft?.status === "editing" && <div className="space-y-3">
      {!confirmCancel ? <Button variant="ghost" disabled={busy} onClick={() => setConfirmCancel(true)}>{uiText("이 초안 취소")}</Button>
        : <div role="alert" className="space-y-3"><p>{uiText("이 초안의 등록을 취소하고 가져온 카드 원본과 임시 이미지를 정리합니다. 이미 저장한 World는 유지됩니다.")}</p>
          <Button disabled={busy} onClick={() => void perform(async () => {
            const final = await updateAgentDraft(draft.id, { revision: draft.revision, status: "cancelled" });
            setConfirmCancel(false);
            if (final.status === "completed") {
              setDraft(final); setStep(4); setError(uiText("등록이 먼저 완료되었습니다. 등록 결과를 확인해주세요.")); return;
            }
            sessionStorage.removeItem(storageKey); setDraft(null); setSource(null); setPendingFile(null);
            setReview([]); setRawOnly([]); setStep(0);
            setMetadataSelection(null); setCardMetadataError(null);
          })}>{uiText("초안 취소 확인")}</Button>
          <Button variant="secondary" disabled={busy} onClick={() => setConfirmCancel(false)}>{uiText("계속 편집")}</Button>
        </div>}
    </div>}
  </section>;
}
