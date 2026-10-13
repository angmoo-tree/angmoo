"use client";

import { WorldBanner } from "./world-banner";
import { ChevronDown, ChevronUp } from "lucide-react";
import { useEffect, useId, useRef, useState, type ReactNode } from "react";
import { Button } from "@/components/ui/button";
import { InlineError } from "@/components/ui/feedback";
import { useAuth } from "@/hooks/use-auth";
import { useUiText } from "@/hooks/use-ui-text";
import { captureAuthRequestScope, isCurrentAuthRequestScope } from "@/lib/auth/browser-session";
import { DESKTOP_RUNTIME_CONFIG_CHANGED_EVENT } from "@/lib/runtime/runtime-config";
import { getWorld } from "../api/worlds";
import type { WorldAppWorldRead } from "../types/world-app";
import type { WorldRead } from "../types/worlds";
import styles from "./world-introduction.module.css";


export function WorldIntroduction({ world, characters, myProfile }: {
  world: WorldAppWorldRead; characters: ReactNode; myProfile: ReactNode;
}) {
  const uiText = useUiText("worlds");
  const { status, user } = useAuth();
  const [read, setRead] = useState<{ value: WorldRead; scope: ReturnType<typeof captureAuthRequestScope> } | null>(null);
  const [error, setError] = useState(false);
  const [revision, setRevision] = useState(0);
  const request = useRef<AbortController | null>(null);

  useEffect(() => {
    if (status !== "authenticated") return;
    const controller = new AbortController();
    request.current = controller;
    const scope = captureAuthRequestScope();
    const current = () => !controller.signal.aborted && isCurrentAuthRequestScope(scope);
    queueMicrotask(() => { if (current()) { setRead(null); setError(false); } });
    getWorld(world.world_id, { signal: controller.signal }).then(value => {
      if (current()) setRead({ value, scope });
    }).catch(() => { if (current()) { setRead(null); setError(true); } });
    return () => controller.abort();
  }, [world.world_id, status, user?.id, revision]);

  useEffect(() => {
    const invalidate = () => { request.current?.abort(); setRead(null); setError(false); setRevision(value => value + 1); };
    window.addEventListener(DESKTOP_RUNTIME_CONFIG_CHANGED_EVENT, invalidate);
    return () => window.removeEventListener(DESKTOP_RUNTIME_CONFIG_CHANGED_EVENT, invalidate);
  }, []);

  const visible = read && isCurrentAuthRequestScope(read.scope) ? read.value : null;
  return <section data-world-introduction className={styles.root}>
    <WorldBanner source={visible ? visible.banner_media_id : world.banner_media_id} alt={visible ? visible.banner_alt_text : world.banner_alt_text} />
    <div className={styles.content}>
      <p className={styles.eyebrow}>World</p>
      <h1 className={styles.title}>{visible?.name ?? world.name}</h1>
      {visible && (visible.genre_tags.length > 0 || visible.tone_tags.length > 0) ? <div className={styles.tags} role="list" aria-label={uiText("World 태그")} data-world-tags>
        {[...visible.genre_tags.map(value => ({ value, kind: "genre" as const })), ...visible.tone_tags.map(value => ({ value, kind: "mood" as const }))].map((tag, index) =>
          <span className={styles.tag} role="listitem" key={`${tag.kind}:${index}`} data-world-tag-kind={tag.kind} aria-label={uiText(tag.kind === "genre" ? "장르 태그: {{value0}}" : "분위기 태그: {{value0}}", { value0: tag.value })}>{tag.value}</span>)}
      </div> : null}
      <p className={styles.tagline} data-world-tagline>{visible?.tagline ?? world.tagline}</p>
      {visible ? <>
        <WorldAbout key={visible.id} world={visible} />
        {characters}
        <div className={styles.myProfile}>{myProfile}</div>
      </> : error ? <InlineError className={styles.feedback}>
        <p>{uiText("World 소개를 불러오지 못했어요. 접근 권한과 연결 상태를 확인해주세요.")}</p>
        <Button variant="secondary" onClick={() => setRevision(value => value + 1)}>{uiText("다시 시도")}</Button>
      </InlineError> : <p role="status" className={styles.feedback}>{uiText("World 소개를 불러오는 중…")}</p>}
    </div>
  </section>;
}

function WorldAbout({ world }: { world: WorldRead }) {
  const uiText = useUiText("worlds");
  const [expanded, setExpanded] = useState(false);
  const [overflow, setOverflow] = useState(false);
  const description = useRef<HTMLParagraphElement>(null);
  const contentId = useId();
  const hasDetails = Boolean(world.daily_life_description.trim() || world.places.length || world.roles.length || world.additional_generation_guidance.trim());
  useEffect(() => {
    if (!description.current) return;
    const element = description.current;
    const observer = new ResizeObserver(() => { if (!expanded) setOverflow(element.scrollHeight > element.clientHeight + 1); });
    observer.observe(element);
    return () => observer.disconnect();
  }, [world.setting_description, expanded]);

  return <section className={styles.about} aria-labelledby={`${contentId}-title`} data-world-about>
    <h2 id={`${contentId}-title`}>{uiText("World 소개")}</h2>
    <div id={contentId}>
      <p ref={description} className={`${styles.prose} ${expanded ? "" : styles.collapsed}`} data-world-description>{world.setting_description.trim() ? world.setting_description : uiText("작성된 World 소개가 없어요.")}</p>
      {expanded ? <div className={styles.details} data-world-about-details>
        <section><h3 className={styles.dailyHeading}>{uiText("일상")}</h3><p className={styles.prose}>{world.daily_life_description.trim() ? world.daily_life_description : uiText("작성된 일상 설명이 없어요.")}</p></section>
        <section><h3>{uiText("장소")}</h3>{world.places.length ? <ul className={styles.definitionList}>{world.places.map((place, index) => <li key={`${place.key}:${index}`}><h4>{place.name}</h4><p className={styles.prose}>{place.description}</p></li>)}</ul> : <p className={styles.prose}>{uiText("등록된 장소가 없어요.")}</p>}</section>
        <section><h3>{uiText("역할·직업")}</h3>{world.roles.length ? <ul className={styles.definitionList}>{world.roles.map((role, index) => <li key={`${role.key}:${index}`}><h4>{role.name}</h4><p className={styles.prose}>{role.description}</p>{role.responsibilities.length ? <ul className={styles.responsibilities}>{role.responsibilities.map((value, i) => <li key={i}>{value}</li>)}</ul> : null}</li>)}</ul> : <p className={styles.prose}>{uiText("등록된 역할·직업이 없어요.")}</p>}</section>
        <section><h3>{uiText("추가 생성 지침")}</h3><p className={styles.prose}>{world.additional_generation_guidance.trim() ? world.additional_generation_guidance : uiText("작성된 추가 생성 지침이 없어요.")}</p></section>
      </div> : null}
    </div>
    {hasDetails || overflow || expanded ? <Button className={styles.expand} variant="ghost" aria-expanded={expanded} aria-controls={contentId} onClick={() => setExpanded(value => !value)}>{uiText(expanded ? "접기" : "더 보기")}{expanded ? <ChevronUp size={16} aria-hidden="true" /> : <ChevronDown size={16} aria-hidden="true" />}</Button> : null}
  </section>;
}
