"use client";

import { ChevronRight } from "lucide-react";
import { useEffect, useState } from "react";
import { LocalProductLink } from "@/components/navigation/local-product-link";
import { ProfileAvatar } from "@/components/ui/profile-avatar";
import { Button } from "@/components/ui/button";
import { InlineError } from "@/components/ui/feedback";
import { useAuth } from "@/hooks/use-auth";
import { useUiText } from "@/hooks/use-ui-text";
import { captureAuthRequestScope, isCurrentAuthRequestScope } from "@/lib/auth/browser-session";
import { worldCharacterDirectoryRoute, worldCharacterProfileRoute, studioWorldRoute } from "@/lib/navigation/product-routes";
import { listWorldCharacterProfiles } from "../api/world-character-profile-client";
import type { WorldCharacterProfileListRead } from "../types/world-character-profile";
import styles from "./world-character-preview.module.css";

export function WorldCharacterPreview({ worldId, canAdd }: { worldId: string; canAdd: boolean }) {
  const uiText = useUiText("characters");
  const { status, user } = useAuth();
  const [read, setRead] = useState<{ value: WorldCharacterProfileListRead; scope: ReturnType<typeof captureAuthRequestScope> } | null>(null);
  const [error, setError] = useState(false);
  const [revision, setRevision] = useState(0);
  useEffect(() => {
    if (status !== "authenticated") return;
    const controller = new AbortController();
    const scope = captureAuthRequestScope();
    const current = () => !controller.signal.aborted && isCurrentAuthRequestScope(scope);
    queueMicrotask(() => { if (current()) { setRead(null); setError(false); } });
    listWorldCharacterProfiles(worldId, { signal: controller.signal }).then(value => {
      if (current()) setRead({ value, scope });
    }).catch(() => { if (current()) { setRead(null); setError(true); } });
    return () => controller.abort();
  }, [worldId, status, user?.id, revision]);
  const visible = read && read.value.world_id === worldId && isCurrentAuthRequestScope(read.scope) ? read.value.items.filter(profile => profile.control_mode === "autonomous") : null;
  return <section className={styles.root} aria-labelledby={`world-preview-${worldId}`} data-world-character-preview>
    <header className={styles.heading}><h2 id={`world-preview-${worldId}`}>{uiText("World의 캐릭터")}</h2><LocalProductLink className={styles.all} href={worldCharacterDirectoryRoute(worldId)}>{uiText("전체 보기")}<ChevronRight size={16} aria-hidden="true" /></LocalProductLink></header>
    {error ? <InlineError><p>{uiText("캐릭터를 불러오지 못했어요.")}</p><Button variant="secondary" onClick={() => setRevision(value => value + 1)}>{uiText("다시 시도")}</Button></InlineError> : visible === null ? <p role="status">{uiText("캐릭터를 불러오는 중…")}</p> : visible.length === 0 ? <div className={styles.empty}><p>{uiText("이 World에 참여 중인 자율 캐릭터가 없어요.")}</p>{canAdd ? <LocalProductLink href={studioWorldRoute(worldId)} className={styles.all}>{uiText("캐릭터 추가")}<ChevronRight size={16} aria-hidden="true" /></LocalProductLink> : null}</div> :
      <ul className={styles.list} data-world-character-preview-list>{visible.map(profile => <li key={profile.world_character_id}><LocalProductLink className={styles.character} ariaLabel={profile.display_name} href={worldCharacterProfileRoute(worldId, profile.world_character_id)}>
        <ProfileAvatar name={profile.display_name} avatarUrl={profile.avatar_url} sizeClassName={styles.avatar} textClassName={styles.initial} /><span className={styles.name}>{profile.display_name}</span>
      </LocalProductLink></li>)}</ul>}
  </section>;
}
