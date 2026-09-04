"use client";

import {
  ArrowLeft,
  BookOpenText,
  BrainCircuit,
  Clock3,
  ExternalLink,
  LoaderCircle,
  PencilLine,
  Pin,
  PinOff,
  ShieldCheck,
  Trash2,
} from "lucide-react";
import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";

import { listWorldCharacterProfiles } from "@/features/characters/public";
import type { WorldCharacterPublicProfile } from "@/features/characters/public";
import { getLocalWorldSurface } from "@/features/device-home/public";
import type { WorldSurfaceItem } from "@/features/device-home/public";
import { LocalProductLink } from "@/features/device-shell/public";
import { PRODUCT_ROUTES, useRuntimeRouter } from "@/shared/navigation/public";
import { Button, Dialog, Field, ProfileAvatar, Textarea } from "@/shared/ui/public";

import {
  correctMemoryItem,
  deleteMemoryItem,
  getMemoryItem,
  getMemorySetting,
  listMemoryItems,
  MemoryApiError,
  setMemoryPin,
  updateMemorySetting,
} from "../api/memory-client";
import type {
  MemoryItemDetailRead,
  MemoryItemListRead,
  MemorySettingRead,
} from "../model/memory-contract";
import styles from "./memory-workspace.module.css";
import { MemoryBatchControls } from "./memory-batch-controls";

type MemoryWorkspaceProps = {
  initialMemoryId?: string;
  initialSubjectId?: string;
  initialWorldId?: string;
};

type OwnerMutation =
  | { kind: "setting"; enabled: boolean; expectedVersion: number; idempotencyKey: string }
  | { kind: "pin"; memoryId: string; pinned: boolean; expectedVersion: number; idempotencyKey: string }
  | { kind: "correct"; memoryId: string; summary: string; expectedItemVersion: number; expectedScopeVersion: number; idempotencyKey: string }
  | { kind: "delete"; memoryId: string; expectedVersion: number; idempotencyKey: string };

type MutationFailure = { message: string; request: OwnerMutation; stale: boolean };

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
  const [mutationKind, setMutationKind] = useState<OwnerMutation["kind"] | "batch" | null>(null);
  const [mutationFailure, setMutationFailure] = useState<MutationFailure | null>(null);
  const [mutationNotice, setMutationNotice] = useState<string | null>(null);
  const [correctionOpen, setCorrectionOpen] = useState(false);
  const [correctionText, setCorrectionText] = useState("");
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [revision, setRevision] = useState(0);
  const correctionRef = useRef<HTMLTextAreaElement>(null);
  const mutationLockRef = useRef(false);
  const acquireBatch = useCallback(() => {
    if (mutationLockRef.current) return false;
    mutationLockRef.current = true;
    setMutationKind("batch");
    return true;
  }, []);
  const releaseBatch = useCallback(() => { mutationLockRef.current = false; setMutationKind(null); }, []);
  const refreshBatchItems = useCallback(() => setRevision((value) => value + 1), []);

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
    if (!worldId || !subjectId || !memoryId || phase !== "ready") return;
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

  function resetMutationPresentation() {
    setMutationFailure(null);
    setMutationNotice(null);
    setCorrectionOpen(false);
    setDeleteOpen(false);
  }

  function chooseWorld(nextWorldId: string) {
    setPhase("loading");
    setError(null);
    setWorldId(nextWorldId);
    setSubjectId("");
    setMemoryId("");
    setDetail(null);
    setDetailPhase("idle");
    resetMutationPresentation();
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
    resetMutationPresentation();
    syncRoute(worldId, nextSubjectId);
    setRevision((value) => value + 1);
  }

  function chooseMemory(nextMemoryId: string) {
    setMemoryId(nextMemoryId);
    setDetail(null);
    setDetailPhase("loading");
    setMutationFailure(null);
    setMutationNotice(null);
    syncRoute(worldId, subjectId, nextMemoryId);
  }

  async function loadMore() {
    if (!list?.next_cursor || pagePhase === "loading") return;
    setPagePhase("loading");
    try {
      const next = await listMemoryItems(worldId, subjectId, { cursor: list.next_cursor });
      setList((current) => {
        if (!current) return next;
        const known = new Set(current.items.map((item) => item.id));
        return {
          ...next,
          items: [...current.items, ...next.items.filter((item) => !known.has(item.id))],
        };
      });
      setPagePhase("idle");
    } catch {
      setPagePhase("error");
    }
  }

  async function reloadCurrentScope(nextMemoryId = memoryId) {
    if (!worldId || !subjectId) return;
    setMutationFailure(null);
    const [settingRead, listRead] = await Promise.all([
      getMemorySetting(worldId, subjectId),
      listMemoryItems(worldId, subjectId),
    ]);
    setSetting(settingRead);
    setList(listRead);
    if (nextMemoryId && listRead.items.some((item) => item.id === nextMemoryId)) {
      const detailRead = await getMemoryItem(worldId, subjectId, nextMemoryId);
      setMemoryId(nextMemoryId);
      setDetail(detailRead);
      setDetailPhase("ready");
      syncRoute(worldId, subjectId, nextMemoryId);
    } else {
      setMemoryId("");
      setDetail(null);
      setDetailPhase("idle");
      syncRoute(worldId, subjectId);
    }
  }

  async function runOwnerMutation(ownerRequest: OwnerMutation) {
    if (mutationLockRef.current) return;
    mutationLockRef.current = true;
    setMutationKind(ownerRequest.kind);
    setMutationFailure(null);
    setMutationNotice(null);
    try {
      if (ownerRequest.kind === "setting") {
        const result = await updateMemorySetting(worldId, subjectId, {
          expected_version: ownerRequest.expectedVersion,
          enabled: ownerRequest.enabled,
          idempotency_key: ownerRequest.idempotencyKey,
        });
        setSetting(result.setting);
        setList((current) => current ? { ...current, memory_enabled: result.setting.enabled } : current);
        setMutationNotice(ownerRequest.enabled
          ? "기억을 켰어요. 이제부터 검증된 새 기억을 쌓을 수 있습니다."
          : "기억을 껐어요. 새 기억 생성과 회상은 중단되고 기존 기록은 관리할 수 있습니다.");
      } else if (ownerRequest.kind === "pin") {
        const result = await setMemoryPin(worldId, subjectId, ownerRequest.memoryId, {
          expected_version: ownerRequest.expectedVersion,
          pinned: ownerRequest.pinned,
          idempotency_key: ownerRequest.idempotencyKey,
        });
        setList((current) => current ? {
          ...current,
          items: current.items.map((item) => item.id === result.item.id ? result.item : item),
        } : current);
        setDetail((current) => current?.id === result.item.id ? { ...current, ...result.item } : current);
        setMutationNotice(ownerRequest.pinned
          ? "이 기억을 고정했어요. 보존 기간이 지나도 유지됩니다."
          : "기억 고정을 해제했어요. 다시 보존 기간 정책을 따릅니다.");
      } else if (ownerRequest.kind === "correct") {
        const result = await correctMemoryItem(worldId, subjectId, ownerRequest.memoryId, {
          expected_item_version: ownerRequest.expectedItemVersion,
          expected_scope_version: ownerRequest.expectedScopeVersion,
          summary: ownerRequest.summary,
          idempotency_key: ownerRequest.idempotencyKey,
        });
        setCorrectionOpen(false);
        setCorrectionText("");
        await reloadCurrentScope(result.item.id);
        setMutationNotice("기억을 정정했어요. 이전 기억은 교체됨으로 남고 새 기억만 회상에 사용됩니다.");
      } else {
        await deleteMemoryItem(worldId, subjectId, ownerRequest.memoryId, {
          expected_version: ownerRequest.expectedVersion,
          idempotency_key: ownerRequest.idempotencyKey,
        });
        setDeleteOpen(false);
        await reloadCurrentScope("");
        setMutationNotice("기억을 삭제했어요. 이후 회상에서는 즉시 제외되며 검색용 사본은 자동으로 정리됩니다.");
      }
    } catch (reason: unknown) {
      const stale = reason instanceof MemoryApiError && reason.status === 409;
      if (ownerRequest.kind === "correct") setCorrectionOpen(false);
      if (ownerRequest.kind === "delete") setDeleteOpen(false);
      setMutationFailure({ message: mutationErrorMessage(reason), request: ownerRequest, stale });
    } finally {
      mutationLockRef.current = false;
      setMutationKind(null);
    }
  }

  function toggleMemory() {
    if (!setting) return;
    void runOwnerMutation({
      kind: "setting",
      enabled: !setting.enabled,
      expectedVersion: setting.version,
      idempotencyKey: newMutationKey("memory-setting"),
    });
  }

  function togglePin() {
    if (!detail) return;
    void runOwnerMutation({
      kind: "pin",
      memoryId: detail.id,
      pinned: !detail.pinned,
      expectedVersion: detail.version,
      idempotencyKey: newMutationKey("memory-pin"),
    });
  }

  function openCorrection() {
    if (!detail) return;
    setCorrectionText(detail.summary);
    setMutationFailure(null);
    setCorrectionOpen(true);
  }

  function submitCorrection() {
    if (!detail || !setting) return;
    const summary = correctionText.trim();
    if (!summary || summary.length > 2_000) return;
    void runOwnerMutation({
      kind: "correct",
      memoryId: detail.id,
      summary,
      expectedItemVersion: detail.version,
      expectedScopeVersion: setting.version,
      idempotencyKey: newMutationKey("memory-correction"),
    });
  }

  function confirmDelete() {
    if (!detail) return;
    void runOwnerMutation({
      kind: "delete",
      memoryId: detail.id,
      expectedVersion: detail.version,
      idempotencyKey: newMutationKey("memory-delete"),
    });
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
          <p>Character가 보존한 기억과 현재 확인 가능한 근거를 관리합니다.</p>
        </div>
      </header>

      <section className={styles.scopeBar} aria-label="기억 범위">
        <label>
          <span>World</span>
          <select disabled={mutationKind !== null} onChange={(event) => chooseWorld(event.target.value)} value={worldId}>
            {worlds.map((world) => <option key={world.world_id} value={world.world_id}>{world.name}</option>)}
          </select>
        </label>
        <label>
          <span>기억하는 Character</span>
          <select disabled={mutationKind !== null} onChange={(event) => chooseSubject(event.target.value)} value={subjectId}>
            {characters.map((character) => <option key={character.world_character_id} value={character.world_character_id}>{character.display_name}</option>)}
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
      {phase === "empty-scope" ? <MemoryState icon={<BookOpenText />} title="관리할 수 있는 기억 범위가 없어요" description="실행 가능한 World와 active Character를 먼저 준비해 주세요." /> : null}
      {phase === "error" ? <MemoryState icon={<BrainCircuit />} title="기억을 불러오지 못했어요" description={error ?? undefined} action={<Button compact onClick={() => { setPhase("loading"); setError(null); setRevision((value) => value + 1); }} variant="secondary">다시 시도</Button>} /> : null}

      {phase === "ready" && list ? (
        <div className={styles.workspace}>
          <section className={styles.listPane} aria-label="저장된 기억 목록">
            <div className={styles.scopeNotice} data-memory-enabled={setting?.enabled ?? false}>
              <ShieldCheck aria-hidden="true" size={18} />
              <div className={styles.scopeNoticeCopy}>
                <strong>{setting?.enabled ? "기억 사용 중" : "기억이 꺼져 있어요"}</strong>
                <p>{setting?.enabled ? "검증된 새 기억을 만들고 이후 대화에서 회상합니다." : "새 장기 기억 생성과 회상은 중단되지만 기존 기억은 관리할 수 있습니다. 현재 대화와 오늘의 World SNS 활동은 대화 연속성을 위해 계속 사용할 수 있습니다."}</p>
              </div>
              <Button aria-pressed={setting?.enabled ?? false} compact disabled={!setting || mutationKind !== null} loading={mutationKind === "setting"} loadingLabel="저장 중" onClick={toggleMemory} variant={setting?.enabled ? "secondary" : "primary"}>
                {setting?.enabled ? "기억 끄기" : "기억 켜기"}
              </Button>
            </div>
            {mutationNotice ? <p className={styles.mutationNotice} role="status">{mutationNotice}</p> : null}
            <MemoryBatchControls key={`${worldId}:${subjectId}:${setting?.version}`} worldId={worldId} subjectId={subjectId} disabled={mutationKind !== null} acquire={acquireBatch} release={releaseBatch} onCompleted={refreshBatchItems} />
            {mutationFailure ? (
              <div className={styles.mutationError} role="alert">
                <p>{mutationFailure.message}</p>
                <Button compact onClick={() => {
                  if (mutationFailure.stale) {
                    void reloadCurrentScope().catch(() => setMutationFailure({ ...mutationFailure, message: "최신 상태도 불러오지 못했어요. 잠시 뒤 다시 시도해 주세요." }));
                  } else {
                    void runOwnerMutation(mutationFailure.request);
                  }
                }} variant="secondary">{mutationFailure.stale ? "최신 상태 불러오기" : "다시 시도"}</Button>
              </div>
            ) : null}
            {list.items.length === 0 ? (
              <MemoryState icon={<BookOpenText />} title="아직 저장된 기억이 없어요" description="기억이 켜진 뒤 성공한 대화와 활동에서 검증된 기억이 생기면 여기에 표시됩니다." />
            ) : (
              <ol className={styles.memoryList}>
                {list.items.map((item) => (
                  <li key={item.id}>
                    <button aria-current={item.id === memoryId ? "true" : undefined} disabled={mutationKind !== null} onClick={() => chooseMemory(item.id)} type="button">
                      <span className={styles.kind}>{memoryKindLabel(item.memory_kind)}{item.pinned ? " · 고정" : ""}</span>
                      <strong>{item.summary}</strong>
                      <span className={styles.itemMeta}><Clock3 aria-hidden="true" size={14} />{formatDate(item.formed_at)} · {lifecycleLabel(item.lifecycle)}</span>
                    </button>
                  </li>
                ))}
              </ol>
            )}
            {list.next_cursor ? (
              <div className={styles.pagination}>
                <Button compact disabled={pagePhase === "loading" || mutationKind !== null} onClick={() => void loadMore()} variant="secondary">{pagePhase === "loading" ? "더 불러오는 중" : "기억 더 보기"}</Button>
                {pagePhase === "error" ? <p role="alert">기억을 더 불러오지 못했어요. 다시 시도해 주세요.</p> : null}
              </div>
            ) : null}
          </section>
          <section className={styles.detailPane} aria-label="기억 상세">
            {detailPhase === "idle" ? <MemoryState icon={<BookOpenText />} title="기억을 선택해 주세요" description="요약, 생명주기, 현재 다시 확인한 canonical 근거와 owner control을 볼 수 있습니다." /> : null}
            {detailPhase === "loading" ? <MemoryState icon={<LoaderCircle className={styles.spin} />} title="근거를 다시 확인하는 중" /> : null}
            {detailPhase === "error" ? <MemoryState icon={<BrainCircuit />} title="이 기억의 근거를 확인하지 못했어요" description="목록 범위는 유지됩니다. 잠시 뒤 다시 선택해 주세요." /> : null}
            {detailPhase === "ready" && detail ? <MemoryDetail detail={detail} memoryEnabled={setting?.enabled ?? false} mutationKind={mutationKind} onCorrect={openCorrection} onDelete={() => { setMutationFailure(null); setDeleteOpen(true); }} onSelectMemory={chooseMemory} onTogglePin={togglePin} /> : null}
          </section>
        </div>
      ) : null}

      <Dialog
        actions={<><Button disabled={mutationKind !== null} onClick={() => setCorrectionOpen(false)} variant="secondary">취소</Button><Button disabled={!correctionText.trim() || correctionText.trim().length > 2_000} loading={mutationKind === "correct"} loadingLabel="정정 중" onClick={submitCorrection}>정정 저장</Button></>}
        description="기존 canonical 근거를 다시 확인한 뒤 새 기억으로 교체합니다. 이전 기억은 이력으로 남지만 회상에는 사용되지 않습니다."
        initialFocusRef={correctionRef}
        onOpenChange={(open) => { if (mutationKind === null) setCorrectionOpen(open); }}
        open={correctionOpen}
        title="기억 정정"
      >
        <Field error={correctionText.trim().length > 2_000 ? "기억 요약은 2,000자 이하여야 합니다." : undefined} helperText={`${correctionText.trim().length.toLocaleString("ko-KR")} / 2,000자`} label="정정할 기억 요약" required>
          {(field) => <Textarea {...field} maxLength={2_001} onChange={(event) => setCorrectionText(event.target.value)} ref={correctionRef} rows={7} value={correctionText} />}
        </Field>
      </Dialog>

      <Dialog
        actions={<><Button disabled={mutationKind !== null} onClick={() => setDeleteOpen(false)} variant="secondary">취소</Button><Button loading={mutationKind === "delete"} loadingLabel="삭제 중" onClick={confirmDelete} variant="danger">기억 삭제</Button></>}
        description="삭제한 기억은 이후 대화에서 즉시 회상되지 않습니다. 이 작업은 되돌릴 수 없습니다."
        onOpenChange={(open) => { if (mutationKind === null) setDeleteOpen(open); }}
        open={deleteOpen}
        title="이 기억을 삭제할까요?"
      >
        <p className={styles.dialogCopy}>{detail?.summary}</p>
      </Dialog>
    </main>
  );
}

function MemoryDetail({ detail, memoryEnabled, mutationKind, onCorrect, onDelete, onSelectMemory, onTogglePin }: {
  detail: MemoryItemDetailRead;
  memoryEnabled: boolean;
  mutationKind: OwnerMutation["kind"] | "batch" | null;
  onCorrect: () => void;
  onDelete: () => void;
  onSelectMemory: (memoryId: string) => void;
  onTogglePin: () => void;
}) {
  const active = detail.lifecycle === "active";
  return (
    <article className={styles.detail}>
      <p className={styles.kind}>{memoryKindLabel(detail.memory_kind)}</p>
      <h2>{detail.summary}</h2>
      {active ? (
        <div className={styles.ownerActions} aria-label="기억 관리">
          <Button compact disabled={mutationKind !== null} loading={mutationKind === "pin"} loadingLabel="저장 중" onClick={onTogglePin} variant="secondary">{detail.pinned ? <PinOff aria-hidden="true" size={16} /> : <Pin aria-hidden="true" size={16} />}{detail.pinned ? "고정 해제" : "고정"}</Button>
          <Button compact disabled={!memoryEnabled || mutationKind !== null} onClick={onCorrect} variant="secondary"><PencilLine aria-hidden="true" size={16} /> 정정</Button>
          <Button compact disabled={mutationKind !== null} onClick={onDelete} variant="danger"><Trash2 aria-hidden="true" size={16} /> 삭제</Button>
        </div>
      ) : null}
      {active && !memoryEnabled ? <p className={styles.controlHint}>새 기억으로 정정하려면 먼저 이 범위의 기억을 켜 주세요. 고정 해제와 삭제는 계속할 수 있습니다.</p> : null}
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
                {evidence.canonical_href ? <LocalProductLink ariaLabel={`${evidence.source_label} 원문 열기`} className={styles.sourceLink} href={evidence.canonical_href}>원문 열기 <ExternalLink aria-hidden="true" size={15} /></LocalProductLink> : null}
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

function newMutationKey(prefix: string) {
  const suffix = typeof crypto !== "undefined" && typeof crypto.randomUUID === "function" ? crypto.randomUUID() : `${Date.now()}-${Math.random().toString(16).slice(2)}`;
  return `${prefix}:${suffix}`;
}

function memoryKindLabel(kind: string) { return ({ OWNER_PREFERENCE: "주인 선호", AUTOBIOGRAPHICAL_EVENT: "경험", DIRECTIONAL_RELATIONSHIP: "관계", THREAD_SUMMARY: "대화 요약", ACCEPTED_JOINT_COMMITMENT: "함께한 약속" } as Record<string, string>)[kind] ?? "기억"; }
function lifecycleLabel(value: string) { return ({ active: "활성", expired: "보존 기간 만료", superseded: "새 기억으로 교체됨", deleted: "삭제됨" } as Record<string, string>)[value] ?? value; }
function availabilityLabel(value: string) { return ({ available: "현재 확인됨", deleted: "원문 삭제됨", unavailable: "현재 확인 불가" } as Record<string, string>)[value] ?? value; }
function formatDate(value: string) { return new Intl.DateTimeFormat("ko-KR", { dateStyle: "medium", timeStyle: "short" }).format(new Date(value)); }
function memoryErrorMessage(reason: unknown) {
  if (reason instanceof MemoryApiError && reason.status === 404) return "이 World 또는 Character의 기억 범위를 찾을 수 없습니다.";
  if (reason instanceof MemoryApiError && reason.status === 403) return "이 기억 범위를 볼 권한이 없습니다.";
  return "로컬 runtime에서 기억 데이터를 읽지 못했습니다.";
}
function mutationErrorMessage(reason: unknown) {
  if (reason instanceof MemoryApiError && reason.status === 409) return "다른 변경이 먼저 저장됐어요. 최신 상태를 불러온 뒤 다시 선택해 주세요.";
  if (reason instanceof MemoryApiError && reason.status === 404) return "이 기억이 더 이상 현재 범위에 없어요. 최신 상태를 확인해 주세요.";
  if (reason instanceof MemoryApiError && reason.status === 422) return "입력한 변경 내용을 적용할 수 없어요. 내용을 확인해 주세요.";
  if (reason instanceof MemoryApiError && reason.status === 403) return "이 기억을 변경할 권한이 없습니다.";
  return "변경을 저장하지 못했어요. 같은 요청으로 다시 시도할 수 있습니다.";
}
