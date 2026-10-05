"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Field, Input, Select } from "@/components/ui/form-controls";
import { useProductLeaveGuard } from "@/hooks/use-product-leave-guard";
import { useUiText } from "@/hooks/use-ui-text";
import { ActiveHoursControl, ACTIVE_HOURS_LIMIT_MESSAGE, isValidActiveHours } from "./activity-hours-control";
import { PersonaField } from "./persona-field";
import { PERSONA_LIMITS, normalizePersonaText, personaLengthError } from "../utils/persona-limits";
import type { WorldCharacterSettingsRead, WorldCharacterSettingsValues } from "../types/world-character-management";
import styles from "./world-character-management.module.css";

const PERSONA_FIELDS = [
  { key: "personality", label: "성격" }, { key: "speech_style", label: "말투" },
  { key: "worldview", label: "세계관" }, { key: "character_background", label: "캐릭터 배경" },
  { key: "topic_preferences", label: "관심 주제" }, { key: "safety_rules", label: "안전 규칙" },
] as const;
const POLICY_FIELDS = [
  { key: "activity_interval_minutes", label: "활동 간격 (분)", min: 30, max: 1440 },
  { key: "max_posts_per_day", label: "하루 게시글 한도", min: 0, max: 1000 },
  { key: "max_comments_per_day", label: "하루 답글 한도", min: 0, max: 1000 },
] as const;
const MODEL_FIELDS = [
  { key: "generation_model", label: "활동 모델", options: "supported_generation_models" },
  { key: "image_model", label: "이미지 모델", options: "supported_image_models" },
] as const;
const OPTIONAL_FIELDS = [
  { key: "image_style", label: "이미지 스타일" }, { key: "appearance_prompt", label: "외형 설명" },
] as const;

export function WorldCharacterSettingsForm({ initial, pending, onSave }: {
  initial: WorldCharacterSettingsRead; pending: boolean;
  onSave: (revision: number, values: Partial<WorldCharacterSettingsValues>) => Promise<WorldCharacterSettingsRead | null>;
}) {
  const uiText = useUiText("characters");
  const [baseline, setBaseline] = useState(initial.settings);
  const [draft, setDraft] = useState(initial.settings);
  const [revision, setRevision] = useState(initial.revision);
  const [saved, setSaved] = useState(false);
  const dirty = JSON.stringify(draft) !== JSON.stringify(baseline);
  useProductLeaveGuard(dirty || pending);
  const personaInvalid = PERSONA_FIELDS.some(field => personaLengthError(draft[field.key], PERSONA_LIMITS[field.key]));
  const hoursInvalid = !isValidActiveHours(draft.active_hours_start, draft.active_hours_end);
  const numbersInvalid = POLICY_FIELDS.some(field => !Number.isInteger(draft[field.key]) || draft[field.key] < field.min || draft[field.key] > field.max);
  const modelsInvalid = MODEL_FIELDS.some(field => draft[field.key] !== baseline[field.key] && draft[field.key]
    && !initial[field.options].some(option => option.enabled && option.value === draft[field.key]));

  function change<K extends keyof WorldCharacterSettingsValues>(key: K, value: WorldCharacterSettingsValues[K]) {
    setDraft(current => ({ ...current, [key]: value })); setSaved(false);
  }

  return <form className={styles.settingsForm} data-world-character-settings-form onSubmit={async event => {
    event.preventDefault();
    if (pending || personaInvalid || hoursInvalid || numbersInvalid || modelsInvalid || !dirty) return;
    const normalized = { ...draft };
    for (const field of PERSONA_FIELDS) normalized[field.key] = normalizePersonaText(normalized[field.key]);
    const values = Object.fromEntries(Object.entries(normalized).filter(([key, value]) => value !== baseline[key as keyof WorldCharacterSettingsValues]));
    const result = await onSave(revision, values);
    if (result) { setBaseline(result.settings); setDraft(result.settings); setRevision(result.revision); setSaved(true); }
  }}>
    <p className={styles.scopeNotice}>{uiText("이 World에서만 적용되는 설정이에요.")}</p>
    <fieldset disabled={pending} className={styles.fieldset}>
      <legend>{uiText("캐릭터 설정")}</legend>
      {PERSONA_FIELDS.map(field => <PersonaField key={field.key} name={field.key} label={uiText(field.label)} value={draft[field.key]}
        limit={PERSONA_LIMITS[field.key]} onChange={value => change(field.key, value)} disabled={pending} />)}
    </fieldset>
    <fieldset disabled={pending} className={styles.fieldset}>
      <legend>{uiText("활동 정책")}</legend>
      <ActiveHoursControl start={draft.active_hours_start} end={draft.active_hours_end} onChange={(start, end) => {
        setDraft(current => ({ ...current, active_hours_start: start, active_hours_end: end })); setSaved(false);
      }} />
      {hoursInvalid ? <p role="alert" className={styles.error}>{uiText(ACTIVE_HOURS_LIMIT_MESSAGE)}</p> : null}
      <div className={styles.policyFields}>{POLICY_FIELDS.map(field => <Field key={field.key} label={uiText(field.label)}>{props => <Input {...props} name={field.key}
        type="number" min={field.min} max={field.max} step={1} required value={Number.isFinite(draft[field.key]) ? draft[field.key] : ""}
        onChange={event => change(field.key, event.target.value === "" ? Number.NaN : Number(event.target.value))} />}</Field>)}</div>
    </fieldset>
    {[...MODEL_FIELDS, ...OPTIONAL_FIELDS].some(field => field.key in initial.settings) ? <fieldset disabled={pending} className={styles.fieldset}>
      <legend>{uiText("모델과 이미지 설정")}</legend>
      <p className={styles.scopeNotice}>{uiText("설치된 모델과 저장된 자격증명을 사용해요. 이 화면에서는 API 키를 변경하지 않아요.")}</p>
      {MODEL_FIELDS.filter(field => field.key in initial.settings).map(field => {
        const value = draft[field.key] ?? "";
        const options = initial[field.options];
        return <Field key={field.key} label={uiText(field.label)}>{props => <Select {...props} name={field.key} value={value}
          onChange={event => change(field.key, event.target.value || null)}>
          <option value="">{uiText("기본 설정 사용")}</option>
          {value && !options.some(option => option.value === value) ? <option value={value} disabled>{uiText("현재 저장된 모델: {{value0}}", { value0: value })}</option> : null}
          {options.map(option => <option key={option.value} value={option.value} disabled={!option.enabled}>{option.label}{!option.enabled ? ` (${uiText("사용할 수 없음")})` : ""}</option>)}
        </Select>}</Field>;
      })}
      {OPTIONAL_FIELDS.filter(field => field.key in initial.settings).map(field => <Field key={field.key} label={uiText(field.label)}>{props => <Input {...props}
        name={field.key} maxLength={10000} value={draft[field.key] ?? ""} onChange={event => change(field.key, event.target.value || null)} />}</Field>)}
    </fieldset> : null}
    {saved ? <p role="status">{uiText("이 World의 설정을 저장했어요.")}</p> : null}
    {initial.revision > revision ? <div className={styles.formActions}><p className={styles.scopeNotice}>{uiText("저장된 설정에 새 버전이 있어요. 초안을 유지한 채 최신 버전을 기준으로 저장할 수 있어요.")}</p>
      <Button variant="secondary" disabled={pending} onClick={() => { setRevision(initial.revision); setBaseline(initial.settings); }}>{uiText("최신 버전을 저장 기준으로 사용")}</Button></div> : null}
    <div className={styles.formActions}><Button variant="secondary" disabled={pending || !dirty} onClick={() => { setDraft(baseline); setSaved(false); }}>{uiText("변경 취소")}</Button>
      <Button type="submit" loading={pending} disabled={!dirty || personaInvalid || hoursInvalid || numbersInvalid || modelsInvalid} loadingLabel={uiText("저장 중...")}>{uiText("설정 저장")}</Button></div>
  </form>;
}
