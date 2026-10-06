"use client";
import { useUiText } from "@/hooks/use-ui-text";


import { useEffect, useState, type ReactNode } from "react";
import { Button } from "@/components/ui/button";
import { Field, Input, Textarea } from "@/components/ui/form-controls";
import { ensureMyProfile, listOwnerControlledIdentities, patchMyProfile, selectOwnerControlledIdentity, uploadMyProfileMedia } from "@/features/worlds/api/worlds";
import type { OwnerControlledIdentityRead } from "@/features/worlds/types/worlds";

export type MyProfileMediaProps = { name: string; avatarUrl: string; bannerUrl: string; disabled: boolean;
  onUpload: (data: { media_type: "avatar" | "banner"; content_type: string; data_base64: string }) => Promise<void> };

export function MyProfileEditor({ worldId, renderMedia, onSaved }: {
  worldId: string; renderMedia: (props: MyProfileMediaProps) => ReactNode; onSaved?: () => void;
}) {
  const uiText = useUiText("worlds");
  const [identity, setIdentity] = useState<OwnerControlledIdentityRead | null>(null);
  const [preserved, setPreserved] = useState<OwnerControlledIdentityRead[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [dirty, setDirty] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  useEffect(() => {
    let active = true;
    ensureMyProfile(worldId).then((value) => { if (active) setIdentity(value); })
      .catch(async (reason) => {
        if (!active) return;
        setMessage(reason instanceof Error ? uiText(reason.message) : uiText("내 프로필을 확인하지 못했습니다."));
        try { const rows = await listOwnerControlledIdentities(worldId); if (active) setPreserved(rows); }
        catch { /* The original ownership/availability error stays visible. */ }
      }).finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [uiText, worldId]);
  async function perform(action: () => Promise<OwnerControlledIdentityRead>, propagate = false) {
    setBusy(true); setMessage(null);
    try { setIdentity(await action()); setDirty(false); setMessage(uiText("내 프로필을 저장했습니다. 기존 글·대화·관계는 그대로입니다.")); onSaved?.(); }
    catch (reason) { setMessage(reason instanceof Error ? uiText(reason.message) : uiText("저장하지 못했습니다.")); if (propagate) throw reason; }
    finally { setBusy(false); }
  }
  function edit(key: "display_name" | "handle" | "intro", value: string) {
    setDirty(true);
    setIdentity((current) => current ? { ...current, profile: { ...current.profile, [key]: value } } : current);
  }
  if (loading) return <p role="status">{uiText("내 프로필을 확인하고 있습니다.")}</p>;
  return <section className="space-y-4 p-5" aria-label={uiText("내 프로필 편집")}>
    <h2 className="text-xl font-bold">{uiText("내 프로필")}</h2>
    {message && <p role="status">{message}</p>}
    {!identity && preserved.length > 0 && <div><p>{uiText("보존된 인물 중 이어서 사용할 프로필을 선택해주세요. 관계를 합치거나 새 인물을 만들지 않습니다.")}</p>
      {preserved.map((row) => <Button key={row.world_character_id} disabled={busy} onClick={() => void perform(() => selectOwnerControlledIdentity(worldId, row.world_character_id))}>{row.profile.display_name} {uiText("복구")}</Button>)}
    </div>}
    {identity && <>
      <form className="space-y-4" onSubmit={(event) => { event.preventDefault(); void perform(() => patchMyProfile(worldId, {
        version: identity.version, display_name: identity.profile.display_name, handle: identity.profile.handle, intro: identity.profile.intro,
      })); }}>
        <Field label={uiText("이름")} required>{(props) => <Input {...props} maxLength={80} value={identity.profile.display_name} disabled={busy} onChange={(event) => edit("display_name", event.target.value)} />}</Field>
        <Field label={uiText("핸들")} required>{(props) => <Input {...props} maxLength={40} value={identity.profile.handle} disabled={busy} onChange={(event) => edit("handle", event.target.value)} />}</Field>
        <Field label={uiText("한 줄 소개")}>{(props) => <Textarea {...props} maxLength={280} value={identity.profile.intro} disabled={busy} onChange={(event) => edit("intro", event.target.value)} />}</Field>
        <Button type="submit" loading={busy}>{uiText("프로필 저장")}</Button>
      </form>
      {dirty && <p>{uiText("이미지를 바꾸기 전에 수정한 이름·소개를 저장해주세요.")}</p>}
      {renderMedia({ name: identity.profile.display_name, avatarUrl: identity.profile.avatar_url ?? "", bannerUrl: identity.profile.banner_url ?? "", disabled: busy || dirty,
        onUpload: async (data) => { await perform(() => uploadMyProfileMedia(worldId, { version: identity.version, ...data }), true); },
      })}
      {(["avatar", "banner"] as const).map((kind) => identity.profile[`${kind}_url`] && <Button variant="secondary" key={kind} disabled={busy || dirty}
        onClick={() => void perform(() => patchMyProfile(worldId, { version: identity.version, [`${kind}_url`]: null }))}>{kind === "avatar" ? uiText("아바타") : uiText("배너")} {uiText("제거")}</Button>)}
      <details><summary>{uiText("보존된 상세 설정 보기")}</summary><p>{uiText("이전 설정은 보존하며 일반 프로필 편집으로 바꾸지 않습니다.")}</p><pre className="overflow-auto whitespace-pre-wrap">{JSON.stringify({ preferred_address: identity.profile.preferred_address, interests: identity.profile.interests, background: identity.profile.background, role_key: identity.profile.role_key }, null, 2)}</pre></details>
      <Button variant="secondary" onClick={() => {
        const url = URL.createObjectURL(new Blob([JSON.stringify(identity.profile, null, 2)], { type: "application/json" }));
        const link = document.createElement("a"); link.href = url; link.download = "my-profile.json"; link.click(); URL.revokeObjectURL(url);
      }}>{uiText("내 프로필 설정 내보내기")}</Button>
    </>}
  </section>;
}
