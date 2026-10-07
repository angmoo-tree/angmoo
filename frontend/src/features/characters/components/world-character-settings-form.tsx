"use client";

import { SettingsCard } from "@/components/ui/settings-card";
import { Sparkles, Settings2 } from "lucide-react";
import { WorldCredentialCard } from "./world-credential-card";
import { useEffect, useEffectEvent, useState, type ReactNode } from "react";
import { Button } from "@/components/ui/button";
import { Field, Input } from "@/components/ui/form-controls";
import { useProductLeaveGuard } from "@/hooks/use-product-leave-guard";
import { useUiText } from "@/hooks/use-ui-text";
import { ActiveHoursControl, ACTIVE_HOURS_LIMIT_MESSAGE, isValidActiveHours } from "./activity-hours-control";
import { PersonaField } from "./persona-field";
import { PERSONA_LIMITS, normalizePersonaText, personaLengthError } from "../utils/persona-limits";
import type { WorldCharacterSettingsRead, WorldCharacterSettingsValues } from "../types/world-character-management";
import styles from "./world-character-management.module.css";

const PERSONA_FIELDS = [
  { key: "worldview", label: "캐릭터 설명" },
  { key: "personality", label: "성격" }, { key: "speech_style", label: "말투" },
  { key: "character_background", label: "캐릭터 배경" },
  { key: "topic_preferences", label: "관심 주제" }, { key: "safety_rules", label: "안전 규칙" },
] as const;
const POLICY_FIELDS = [
  { key: "activity_interval_minutes", label: "활동 간격 (분)", min: 30, max: 1440 },
  { key: "max_posts_per_day", label: "하루 게시글 한도", min: 0, max: 1000 },
  { key: "max_comments_per_day", label: "하루 답글 한도", min: 0, max: 1000 },
] as const;
function SettingsEditor({ initial, pending, onSave, kind }: {
  kind: "persona" | "activity";
  initial: WorldCharacterSettingsRead; pending: boolean;
  onSave: (revision: number, values: Partial<WorldCharacterSettingsValues>) => Promise<WorldCharacterSettingsRead | null>;
}) {
  const uiText = useUiText("characters");
  const [baseline, setBaseline] = useState(initial.settings);
  const [draft, setDraft] = useState(initial.settings);
  const [conflict, setConflict] = useState(false);
  const [saved, setSaved] = useState(false);
  const keys: (keyof WorldCharacterSettingsValues)[] = kind === "persona" ? PERSONA_FIELDS.map(f => f.key) : [...POLICY_FIELDS.map(f => f.key), "active_hours_start", "active_hours_end", "allow_post", "allow_reply", "allow_like"];
  const dirty = keys.some(key => draft[key] !== baseline[key]);
  useProductLeaveGuard(dirty || pending);
  const personaInvalid = PERSONA_FIELDS.some(field => personaLengthError(draft[field.key], PERSONA_LIMITS[field.key]));
  const hoursInvalid = !isValidActiveHours(draft.active_hours_start, draft.active_hours_end);
  const numbersInvalid = POLICY_FIELDS.some(field => !Number.isInteger(draft[field.key]) || draft[field.key] < field.min || draft[field.key] > field.max);
  const reconcileRead = useEffectEvent((next: WorldCharacterSettingsValues) => {
    setDraft(Object.fromEntries(Object.entries(next).map(([key, value]) => [key,
      draft[key as keyof WorldCharacterSettingsValues] === baseline[key as keyof WorldCharacterSettingsValues] ? value : draft[key as keyof WorldCharacterSettingsValues]])) as WorldCharacterSettingsValues);
    setBaseline(Object.fromEntries(Object.entries(next).map(([key, value]) => [key,
      draft[key as keyof WorldCharacterSettingsValues] === baseline[key as keyof WorldCharacterSettingsValues] ? value : baseline[key as keyof WorldCharacterSettingsValues]])) as WorldCharacterSettingsValues);
  });
  useEffect(() => {
    let current = true;
    queueMicrotask(() => {
      if (!current) return;
      reconcileRead(initial.settings);
    });
    return () => { current = false; };
  }, [initial.settings]);

  function change<K extends keyof WorldCharacterSettingsValues>(key: K, value: WorldCharacterSettingsValues[K]) {
    setDraft(current => ({ ...current, [key]: value })); setSaved(false); setConflict(false);
  }

  return <SettingsCard elevated data-world-character-settings-card={kind} title={uiText(kind === "persona" ? "캐릭터 페르소나 설정" : "활동 설정")} description={uiText(kind === "persona" ? "캐릭터 설명과 성격·말투를 설정해요." : "활동 시간, 허용 행동, 작성 상한을 설정해요.")} icon={kind === "persona" ? <Sparkles size={20} /> : <Settings2 size={20} />}><form className={styles.settingsForm} data-world-character-settings-editor onSubmit={async event => {
    event.preventDefault();
    if (pending || (kind === "persona" ? personaInvalid : hoursInvalid || numbersInvalid) || !dirty) return;
    const edited = keys.filter(key => draft[key] !== baseline[key]);
    if (edited.some(key => initial.settings[key] !== baseline[key] && initial.settings[key] !== draft[key])) { setSaved(false); setConflict(true); return; }
    const normalized = { ...draft };
    for (const field of PERSONA_FIELDS) normalized[field.key] = normalizePersonaText(normalized[field.key]);
    const values = Object.fromEntries(Object.entries(normalized).filter(([key]) => edited.includes(key as keyof WorldCharacterSettingsValues)));
    const result = await onSave(initial.revision, values);
    if (result) { setBaseline(result.settings); setDraft(result.settings); setSaved(true); setConflict(false); }
  }}>
    <p className={styles.scopeNotice}>{uiText("이 World에서만 적용되는 설정이에요.")}</p>
    {kind === "persona" ? <fieldset disabled={pending} className={styles.fieldset}>
      {PERSONA_FIELDS.map(field => <PersonaField key={field.key} name={field.key} label={uiText(field.label)} value={draft[field.key]}
        limit={PERSONA_LIMITS[field.key]} onChange={value => change(field.key, value)} disabled={pending} />)}
    </fieldset> : null}
    {kind === "activity" ? <fieldset disabled={pending} className={styles.fieldset}>

      <ActiveHoursControl start={draft.active_hours_start} end={draft.active_hours_end} onChange={(start, end) => {
        setDraft(current => ({ ...current, active_hours_start: start, active_hours_end: end })); setSaved(false);
      }} />
      {hoursInvalid ? <p role="alert" className={styles.error}>{uiText(ACTIVE_HOURS_LIMIT_MESSAGE)}</p> : null}
      <div className={styles.policyFields}>{([['allow_post', '게시글 작성'], ['allow_reply', '답글 작성'], ['allow_like', '좋아요']] as const).map(([key, label]) => <label className="flex min-h-11 items-center justify-between gap-3 rounded-xl border border-border-default px-4" key={key}>{uiText(label)}<input type="checkbox" className="accent-action-primary" checked={draft[key]} onChange={event => change(key, event.target.checked)} /></label>)}</div>
      <div className={styles.policyFields}>{POLICY_FIELDS.map(field => <Field key={field.key} label={uiText(field.label)}>{props => <Input {...props} name={field.key}
        type="number" min={field.min} max={field.max} step={1} required value={Number.isFinite(draft[field.key]) ? draft[field.key] : ""}
        onChange={event => change(field.key, event.target.value === "" ? Number.NaN : Number(event.target.value))} />}</Field>)}</div>
    </fieldset> : null}
    {saved ? <p role="status">{uiText("이 World의 설정을 저장했어요.")}</p> : null}
    {conflict ? <div role="alert"><p>{uiText("같은 항목이 다른 곳에서 변경되었어요. 입력을 보존했으니 최신 값과 확인해주세요.")}</p>
      <dl>{keys.filter(key => draft[key] !== baseline[key] && initial.settings[key] !== baseline[key]).map(key => <div key={key}><dt>{uiText(PERSONA_FIELDS.find(f => f.key === key)?.label ?? POLICY_FIELDS.find(f => f.key === key)?.label ?? (key === "active_hours_start" ? "활동 시작" : key === "active_hours_end" ? "활동 마감" : key === "allow_post" ? "게시글 작성" : key === "allow_reply" ? "답글 작성" : "좋아요"))}</dt><dd className="whitespace-pre-wrap break-words">{String(initial.settings[key])}</dd></div>)}</dl>
      <Button variant="secondary" onClick={() => { setBaseline(initial.settings); setConflict(false); }}>{uiText("최신 값을 확인했어요. 내 입력 유지")}</Button></div> : null}
    <div className={styles.formActions}><Button variant="secondary" disabled={pending || !dirty} onClick={() => { setDraft(baseline); setSaved(false); }}>{uiText("변경 취소")}</Button>
      <Button type="submit" loading={pending} disabled={!dirty || (kind === "persona" ? personaInvalid : hoursInvalid || numbersInvalid)} loadingLabel={uiText("저장 중...")}>{uiText("설정 저장")}</Button></div>
  </form></SettingsCard>;
}

export function WorldCharacterSettingsForm(props: {
  initial: WorldCharacterSettingsRead; pending: boolean;
  onSave: (revision: number, values: Partial<WorldCharacterSettingsValues>) => Promise<WorldCharacterSettingsRead | null>;
  imageCard?: ReactNode; visionControls?: ReactNode; interestCard?: ReactNode; modeCard?: ReactNode; dayCard?: ReactNode; deleteCard?: ReactNode;
}) {
 const { initial } = props;
 return <div className={styles.settingsForm} data-world-character-settings-form>
  <SettingsEditor {...props} kind="persona" />
  <SettingsEditor {...props} kind="activity" />
  <WorldCredentialCard worldId={initial.world_id} actorId={initial.world_character_id} purpose="sns" />
  {props.imageCard}
  <WorldCredentialCard worldId={initial.world_id} actorId={initial.world_character_id} purpose="chat" />
  <WorldCredentialCard worldId={initial.world_id} actorId={initial.world_character_id} purpose="vision">{props.visionControls}</WorldCredentialCard>
  {props.interestCard}{props.modeCard}{props.dayCard}{props.deleteCard}
 </div>;
}
