"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import { Field, Input } from "@/components/ui/form-controls";
import { useProductLeaveGuard } from "@/hooks/use-product-leave-guard";
import { useUiText } from "@/hooks/use-ui-text";
import type { AgentProfileMediaUploadInput } from "../types/agents";
import type { WorldCharacterManagementRead, WorldCharacterProfileValues } from "../types/world-character-management";
import type { WorldCharacterPublicProfile } from "../types/world-character-profile";
import { PERSONA_LIMITS, normalizePersonaText, personaLengthError } from "../utils/persona-limits";
import { PersonaField } from "./persona-field";
import { ProfileMediaUploader } from "./profile-media-uploader";
import styles from "./world-character-management.module.css";

export function WorldCharacterProfileEditor({ profile, initialRevision, open, pending, onOpenChange, onSave, onUpload }: {
  profile: WorldCharacterPublicProfile; initialRevision: number; open: boolean; pending: boolean; onOpenChange: (open: boolean) => void;
  onSave: (revision: number, values: Partial<WorldCharacterProfileValues>) => Promise<WorldCharacterManagementRead | null>;
  onUpload: (revision: number, media: AgentProfileMediaUploadInput) => Promise<WorldCharacterManagementRead | null>;
}) {
  const uiText = useUiText("characters");
  const initial: WorldCharacterProfileValues = { display_name: profile.display_name, handle: profile.handle, intro: profile.intro,
    avatar_url: profile.avatar_url, banner_url: profile.banner_url };
  const [baseline, setBaseline] = useState(initial);
  const [draft, setDraft] = useState(initial);
  const [revision, setRevision] = useState(initialRevision);
  const dirty = JSON.stringify(draft) !== JSON.stringify(baseline);
  useProductLeaveGuard(dirty || pending);
  const invalid = !draft.display_name.trim() || Boolean(personaLengthError(draft.intro, PERSONA_LIMITS.one_liner));
  return <Dialog open={open} onOpenChange={next => {
    if (pending) return;
    if (!next && dirty && !window.confirm(uiText("프로필 변경을 버리고 닫을까요?"))) return;
    if (!next) setDraft(baseline);
    onOpenChange(next);
  }} title={uiText("이 World의 프로필 편집")} description={uiText("이 World에서만 적용되는 프로필이에요.")}
    closeOnEscape={!pending} closeOnBackdrop={!pending} closeButtonAttributes={{ disabled: pending }} dialogAttributes={{ "data-world-character-profile-editor": true }}>
    <form className={styles.profileForm} onSubmit={async event => {
      event.preventDefault(); if (pending || invalid) return;
      const normalized: WorldCharacterProfileValues = { ...draft, display_name: draft.display_name.trim(),
        handle: draft.handle?.replace(/^@+/, "").trim() || null, intro: normalizePersonaText(draft.intro) };
      const changes = Object.fromEntries(Object.entries(normalized).filter(([key, value]) => value !== baseline[key as keyof WorldCharacterProfileValues]));
      const result = await onSave(revision, changes);
      if (result) {
        const value = result.item.profile;
        const saved = { display_name: value.display_name, handle: value.handle, intro: value.intro, avatar_url: value.avatar_url, banner_url: value.banner_url };
        setBaseline(saved); setDraft(saved); setRevision(result.item.revision); onOpenChange(false);
      }
    }}>
      <ProfileMediaUploader name={draft.display_name} avatarUrl={draft.avatar_url ?? ""} bannerUrl={draft.banner_url ?? ""} disabled={pending}
        onUpload={async media => {
          const result = await onUpload(revision, media);
          if (!result) throw new Error(uiText("이미지를 저장하지 못했습니다."));
          const mediaValues = { avatar_url: result.item.profile.avatar_url, banner_url: result.item.profile.banner_url };
          setDraft(current => ({ ...current, ...mediaValues })); setBaseline(current => ({ ...current, ...mediaValues })); setRevision(result.item.revision);
        }} />
      <Field label={uiText("이름")} required>{props => <Input {...props} name="display_name" autoComplete="off" maxLength={80} required value={draft.display_name}
        disabled={pending} onChange={event => setDraft(current => ({ ...current, display_name: event.target.value }))} />}</Field>
      <Field label={uiText("핸들")} helperText={uiText("이 World 안에서 사용하는 이름이에요.")}>{props => <Input {...props} name="handle" autoComplete="off" maxLength={80}
        value={draft.handle ?? ""} disabled={pending} onChange={event => setDraft(current => ({ ...current, handle: event.target.value || null }))} />}</Field>
      <PersonaField name="intro" label={uiText("소개")} value={draft.intro} limit={PERSONA_LIMITS.one_liner} disabled={pending}
        onChange={value => setDraft(current => ({ ...current, intro: value }))} />
      {initialRevision > revision ? <div className={styles.formActions}><p className={styles.scopeNotice}>{uiText("저장된 프로필에 새 버전이 있어요. 초안을 유지한 채 최신 버전을 기준으로 저장할 수 있어요.")}</p>
        <Button variant="secondary" disabled={pending} onClick={() => { setRevision(initialRevision); setBaseline(initial); }}>{uiText("최신 버전을 저장 기준으로 사용")}</Button></div> : null}
      <div className={styles.formActions}><Button type="submit" loading={pending} disabled={invalid || !dirty} loadingLabel={uiText("저장 중...")}>{uiText("프로필 저장")}</Button></div>
    </form>
  </Dialog>;
}
