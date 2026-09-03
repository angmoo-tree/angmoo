"use client";

import {
  ArrowLeft,
  BookOpenText,
  BrainCircuit,
  Clock3,
  ExternalLink,
  LoaderCircle,
  ShieldCheck,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useState, type ReactNode } from "react";

import { listWorldCharacterProfiles } from "@/features/characters/public";
import type { WorldCharacterPublicProfile } from "@/features/characters/public";
import { getLocalWorldSurface } from "@/features/device-home/public";
import type { WorldSurfaceItem } from "@/features/device-home/public";
import { LocalProductLink } from "@/features/device-shell/public";
import { PRODUCT_ROUTES, useRuntimeRouter } from "@/shared/navigation/public";
import { Button, ProfileAvatar } from "@/shared/ui/public";

import {
  getMemoryItem,
  getMemorySetting,
  listMemoryItems,
  MemoryApiError,
} from "../api/memory-client";
import type {
  MemoryItemDetailRead,
  MemoryItemListRead,
  MemorySettingRead,
} from "../model/memory-contract";
import styles from "./memory-workspace.module.css";

type MemoryWorkspaceProps = {
  initialMemoryId?: string;
  initialSubjectId?: string;
  initialWorldId?: string;
};

export function MemoryWorkspace({
  initialMemoryId,
  initialSubjectId,
  initialWorldId,
}: MemoryWorkspaceProps) {
  const router = useRuntimeRouter();
  const [worlds, setWorlds] = useState<WorldSurfaceItem[]>([]);
  const [characters, setCharacters] = useState<WorldCharacterPublicProfile[]>([]);
  const [worldId, setWorldId] = useState(initialWorldId ?? "");
  const [subjectId, setSubjectId] = useState(initialSubjectId ?? "");
  const [memoryId, setMemoryId] = useState(initialMemoryId ?? "");
  const [setting, setSetting] = useState<MemorySettingRead | null>(null);
  const [list, setList] = useState<MemoryItemListRead | null>(null);
  const [detail, setDetail] = useState<MemoryItemDetailRead | null>(null);
  const [phase, setPhase] = useState<"loading" | "ready" | "empty-scope" | "error">("loading");
  const [detailPhase, setDetailPhase] = useState<"idle" | "loading" | "ready" | "error">(
    initialMemoryId ? "loading" : "idle",
  );
  const [pagePhase, setPagePhase] = useState<"idle" | "loading" | "error">("idle");
  const [error, setError] = useState<string | null>(null);
  const [revision, setRevision] = useState(0);

  const syncRoute = useCallback((nextWorld: string, nextSubject: string, nextMemory = "") => {
    const query = new URLSearchParams();
    if (nextWorld) query.set("world", nextWorld);
    if (nextSubject) query.set("subject", nextSubject);
    if (nextMemory) query.set("memory", nextMemory);
    router.replace(`/memory${query.size ? `?${query}` : ""}`);
  }, [router]);

  useEffect(() => {
    const controller = new AbortController();
    void getLocalWorldSurface("device_home", { signal: controller.signal })
      .then(async (worldRead) => {
        const available = worldRead.items.filter((world) => world.launchable);
        setWorlds(available);
        const requestedWorldExists = available.some((world) => world.world_id === worldId);
        if (worldId && !requestedWorldExists) {
          setCharacters([]);
          setPhase("empty-scope");
          return;
        }
        const selectedWorld = requestedWorldExists ? worldId : available[0]?.world_id ?? "";
        if (!selectedWorld) {
          setCharacters([]);
          setWorldId("");
          setSubjectId("");
          setPhase("empty-scope");
          return;
        }
        const characterRead = await listWorldCharacterProfiles(selectedWorld, {
          signal: controller.signal,
        });
        setCharacters(characterRead.items);
        const requestedSubjectExists = characterRead.items.some(
          (character) => character.world_character_id === subjectId,
        );
        if (subjectId && !requestedSubjectExists) {
          setWorldId(selectedWorld);
          setCharacters(characterRead.items);
          setPhase("empty-scope");
          return;
        }
        const selectedSubject = requestedSubjectExists
          ? subjectId
          : characterRead.items[0]?.world_character_id ?? "";
        setWorldId(selectedWorld);
        setSubjectId(selectedSubject);
        if (!selectedSubject) {
          setPhase("empty-scope");
          syncRoute(selectedWorld, "");
          return;
        }
        const [settingRead, listRead] = await Promise.all([
          getMemorySetting(selectedWorld, selectedSubject, { signal: controller.signal }),
          listMemoryItems(selectedWorld, selectedSubject, { signal: controller.signal }),
        ]);
        setSetting(settingRead);
        setList(listRead);
        setPagePhase("idle");
        setError(null);
        setPhase("ready");
      })
      .catch((reason: unknown) => {
        if (reason instanceof DOMException && reason.name === "AbortError") return;
        setError(memoryErrorMessage(reason));
        setPhase("error");
      });
    return () => controller.abort();
  }, [revision, subjectId, syncRoute, worldId]);

  useEffect(() => {
    if (!worldId || !subjectId || !memoryId || phase !== "ready") {
      return;
    }
    const controller = new AbortController();
    void getMemoryItem(worldId, subjectId, memoryId, { signal: controller.signal })
      .then((read) => {
        setDetail(read);
        setDetailPhase("ready");
      })
      .catch((reason: unknown) => {
        if (reason instanceof DOMException && reason.name === "AbortError") return;
        setDetail(null);
        setDetailPhase("error");
      });
    return () => controller.abort();
  }, [memoryId, phase, subjectId, worldId]);

  const selectedCharacter = useMemo(
    () => characters.find((item) => item.world_character_id === subjectId) ?? null,
    [characters, subjectId],
  );

  function chooseWorld(nextWorldId: string) {
    setPhase("loading");
    setError(null);
    setWorldId(nextWorldId);
    setSubjectId("");
    setMemoryId("");
    setDetail(null);
    setDetailPhase("idle");
    syncRoute(nextWorldId, "");
    setRevision((value) => value + 1);
  }

  function chooseSubject(nextSubjectId: string) {
    setPhase("loading");
    setError(null);
    setSubjectId(nextSubjectId);
    setMemoryId("");
    setDetail(null);
    setDetailPhase("idle");
    syncRoute(worldId, nextSubjectId);
    setRevision((value) => value + 1);
  }

  function chooseMemory(nextMemoryId: string) {
    setMemoryId(nextMemoryId);
    setDetail(null);
    setDetailPhase("loading");
    syncRoute(worldId, subjectId, nextMemoryId);
  }

  async function loadMore() {
    if (!list?.next_cursor || pagePhase === "loading") return;
    setPagePhase("loading");
    try {
      const next = await listMemoryItems(worldId, subjectId, {
        cursor: list.next_cursor,
      });
      setList((current) => {
        if (!current) return next;
        const known = new Set(current.items.map((item) => item.id));
        return {
          ...next,
          items: [
            ...current.items,
            ...next.items.filter((item) => !known.has(item.id)),
          ],
        };
      });
      setPagePhase("idle");
    } catch {
      setPagePhase("error");
    }
  }

  return (
    <main className={styles.shell} data-main-landmark-owner="memory" data-product-shell="memory">
      <header className={styles.header}>
        <LocalProductLink ariaLabel="Device Home으로 돌아가기" className={styles.homeLink} href={PRODUCT_ROUTES.deviceHome}>
          <ArrowLeft aria-hidden="true" size={20} />
        </LocalProductLink>
        <div className={styles.brandMark}><BrainCircuit aria-hidden="true" size={24} /></div>
        <div>
          <p className={styles.kicker}>LOCAL MEMORY</p>
          <h1>기억</h1>
          <p>Character가 보존한 기억과 현재 확인 가능한 근거를 읽습니다.</p>
        </div>
      </header>

      <section className={styles.scopeBar} aria-label="기억 범위">
        <label>
          <span>World</span>
          <select onChange={(event) => chooseWorld(event.target.value)} value={worldId}>
            {worlds.map((world) => <option key={world.world_id} value={world.world_id}>{world.name}</option>)}
          </select>
        </label>
        <label>
          <span>기억하는 Character</span>
          <select onChange={(event) => chooseSubject(event.target.value)} value={subjectId}>
            {characters.map((character) => (
              <option key={character.world_character_id} value={character.world_character_id}>
                {character.display_name}
              </option>
            ))}
          </select>
        </label>
        {selectedCharacter ? (
          <div className={styles.subjectCard}>
            <ProfileAvatar avatarUrl={selectedCharacter.avatar_url} name={selectedCharacter.display_name} sizeClassName="size-10" textClassName="text-sm" />
            <strong>{selectedCharacter.display_name}</strong>
          </div>
        ) : null}
      </section>

      {phase === "loading" ? <MemoryState icon={<LoaderCircle className={styles.spin} />} title="기억을 불러오는 중" /> : null}
      {phase === "empty-scope" ? <MemoryState icon={<BookOpenText />} title="읽을 수 있는 기억 범위가 없어요" description="실행 가능한 World와 active Character를 먼저 준비해 주세요." /> : null}
      {phase === "error" ? (
        <MemoryState icon={<BrainCircuit />} title="기억을 불러오지 못했어요" description={error ?? undefined} action={<Button compact onClick={() => { setPhase("loading"); setError(null); setRevision((value) => value + 1); }} variant="secondary">다시 시도</Button>} />
      ) : null}

      {phase === "ready" && list ? (
        <div className={styles.workspace}>
          <section className={styles.listPane} aria-label="저장된 기억 목록">
            <div className={styles.scopeNotice} data-memory-enabled={setting?.enabled ?? false}>
              <ShieldCheck aria-hidden="true" size={18} />
              <div>
                <strong>{setting?.enabled ? "기억 사용 중" : "기억이 꺼져 있어요"}</strong>
                <p>{setting?.enabled ? "새 기억 후보를 만들 수 있습니다." : "기존 기억은 읽을 수 있지만 새 기억은 쌓이지 않습니다."}</p>
              </div>
            </div>
            {list.items.length === 0 ? (
              <MemoryState icon={<BookOpenText />} title="아직 저장된 기억이 없어요" description="기억이 켜진 뒤 성공한 대화와 활동에서 검증된 기억이 생기면 여기에 표시됩니다." />
            ) : (
              <ol className={styles.memoryList}>
                {list.items.map((item) => (
                  <li key={item.id}>
                    <button aria-current={item.id === memoryId ? "true" : undefined} onClick={() => chooseMemory(item.id)} type="button">
                      <span className={styles.kind}>{memoryKindLabel(item.memory_kind)}</span>
                      <strong>{item.summary}</strong>
                      <span className={styles.itemMeta}><Clock3 aria-hidden="true" size={14} />{formatDate(item.formed_at)} · {lifecycleLabel(item.lifecycle)}</span>
                    </button>
                  </li>
                ))}
              </ol>
            )}
            {list.next_cursor ? (
              <div className={styles.pagination}>
                <Button compact disabled={pagePhase === "loading"} onClick={() => void loadMore()} variant="secondary">
                  {pagePhase === "loading" ? "더 불러오는 중" : "기억 더 보기"}
                </Button>
                {pagePhase === "error" ? <p role="alert">기억을 더 불러오지 못했어요. 다시 시도해 주세요.</p> : null}
              </div>
            ) : null}
          </section>
          <section className={styles.detailPane} aria-label="기억 상세">
            {detailPhase === "idle" ? <MemoryState icon={<BookOpenText />} title="기억을 선택해 주세요" description="요약, 생명주기, 그리고 현재 다시 확인한 canonical 근거를 볼 수 있습니다." /> : null}
            {detailPhase === "loading" ? <MemoryState icon={<LoaderCircle className={styles.spin} />} title="근거를 다시 확인하는 중" /> : null}
            {detailPhase === "error" ? <MemoryState icon={<BrainCircuit />} title="이 기억의 근거를 확인하지 못했어요" description="목록 범위는 유지됩니다. 잠시 뒤 다시 선택해 주세요." /> : null}
            {detailPhase === "ready" && detail ? <MemoryDetail detail={detail} onSelectMemory={chooseMemory} /> : null}
          </section>
        </div>
      ) : null}
    </main>
  );
}

function MemoryDetail({ detail, onSelectMemory }: { detail: MemoryItemDetailRead; onSelectMemory: (memoryId: string) => void }) {
  return (
    <article className={styles.detail}>
      <p className={styles.kind}>{memoryKindLabel(detail.memory_kind)}</p>
      <h2>{detail.summary}</h2>
      <dl className={styles.facts}>
        <div><dt>상태</dt><dd>{lifecycleLabel(detail.lifecycle)}</dd></div>
        <div><dt>형성</dt><dd>{formatDate(detail.formed_at)}</dd></div>
        <div><dt>보존</dt><dd>{detail.pinned ? "고정됨" : `${detail.retention_days}일 정책`}</dd></div>
        {detail.related_character ? <div><dt>관련 Character</dt><dd>{detail.related_character.display_name}</dd></div> : null}
        {detail.superseded_by_memory_id ? <div><dt>교체 상태</dt><dd><button className={styles.inlineButton} onClick={() => onSelectMemory(detail.superseded_by_memory_id ?? "")} type="button">새 기억 열기</button></dd></div> : null}
      </dl>
      <section className={styles.evidenceSection}>
        <div className={styles.sectionHeading}><h3>근거</h3><span>{detail.provenance_summary}</span></div>
        {detail.evidence.length === 0 ? <p className={styles.muted}>연결된 근거가 없습니다.</p> : (
          <ol className={styles.evidenceList}>
            {detail.evidence.map((evidence, index) => (
              <li key={`${evidence.source_kind}:${evidence.source_created_at}:${index}`} data-availability={evidence.availability}>
                <div className={styles.evidenceHeading}><strong>{evidence.source_label}</strong><span>{availabilityLabel(evidence.availability)}</span></div>
                <time dateTime={evidence.source_created_at}>{formatDate(evidence.source_created_at)}</time>
                {evidence.excerpt ? <p>{evidence.excerpt}</p> : <p className={styles.muted}>원문은 현재 사용할 수 없습니다.</p>}
                {evidence.canonical_href ? (
                  <LocalProductLink ariaLabel={`${evidence.source_label} 원문 열기`} className={styles.sourceLink} href={evidence.canonical_href}>
                    원문 열기 <ExternalLink aria-hidden="true" size={15} />
                  </LocalProductLink>
                ) : null}
              </li>
            ))}
          </ol>
        )}
      </section>
    </article>
  );
}

function MemoryState({ icon, title, description, action }: { icon: ReactNode; title: string; description?: string; action?: ReactNode }) {
  return <div className={styles.state} role={title.includes("못") ? "alert" : "status"}>{icon}<h2>{title}</h2>{description ? <p>{description}</p> : null}{action}</div>;
}

function memoryKindLabel(kind: string) {
  return ({ OWNER_PREFERENCE: "주인 선호", AUTOBIOGRAPHICAL_EVENT: "경험", DIRECTIONAL_RELATIONSHIP: "관계", THREAD_SUMMARY: "대화 요약", ACCEPTED_JOINT_COMMITMENT: "함께한 약속" } as Record<string, string>)[kind] ?? "기억";
}
function lifecycleLabel(value: string) { return ({ active: "활성", expired: "보존 기간 만료", superseded: "새 기억으로 교체됨", deleted: "삭제됨" } as Record<string, string>)[value] ?? value; }
function availabilityLabel(value: string) { return ({ available: "현재 확인됨", deleted: "원문 삭제됨", unavailable: "현재 확인 불가" } as Record<string, string>)[value] ?? value; }
function formatDate(value: string) { return new Intl.DateTimeFormat("ko-KR", { dateStyle: "medium", timeStyle: "short" }).format(new Date(value)); }
function memoryErrorMessage(reason: unknown) {
  if (reason instanceof MemoryApiError && reason.status === 404) return "이 World 또는 Character의 기억 범위를 찾을 수 없습니다.";
  if (reason instanceof MemoryApiError && reason.status === 403) return "이 기억 범위를 볼 권한이 없습니다.";
  return "로컬 runtime에서 기억 데이터를 읽지 못했습니다.";
}
