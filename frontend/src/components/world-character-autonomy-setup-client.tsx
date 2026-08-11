"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useRef, useState } from "react";

import { useAuth } from "@/components/auth-provider";
import { getAgent, type AgentDetailRead } from "@/lib/agents";
import {
  DailyActivityPlanApiError,
  getDailyActivityPlan,
  prepareDailyActivityPlan,
  updateActivityRuntimeMode,
  type DailyActivityPlanRead,
} from "@/lib/world-activity-runtime";
import {
  approveWorldCharacterSetup,
  enterWorldWithCharacter,
  generateWorldCharacterSetup,
  getExistingWorldCharacterEntry,
  getWorldFeedStatus,
  getWorldCharacterSetup,
  preflightWorldCharacterSetup,
  rejectWorldCharacterSetup,
  retryWorldCharacterSetup,
  WorldCharacterSetupApiError,
  type WorldActivityDaypart,
  type WorldCharacterEntryRead,
  type WorldFeedCycleStatusRead,
  type WorldCharacterSetupPreflightRead,
  type WorldCharacterSetupRead,
} from "@/lib/world-character-setup";
import { getWorld, type WorldRead } from "@/lib/worlds";

const DAYPARTS: Array<{ key: WorldActivityDaypart; label: string; time: string }> = [
  { key: "dawn", label: "새벽", time: "00:00–06:00" },
  { key: "morning", label: "오전", time: "06:00–12:00" },
  { key: "afternoon", label: "오후", time: "12:00–18:00" },
  { key: "evening", label: "저녁", time: "18:00–24:00" },
];

const ACTION_LABELS: Record<string, string> = {
  comment: "댓글",
  reply: "답글",
  like: "좋아요",
  repost: "리포스트",
  follow: "팔로우",
  unfollow: "언팔로우",
  observe: "관찰",
};

const REASON_MESSAGES: Record<string, string> = {
  credential_required: "이 캐릭터에 사용할 수 있는 LLM API 키가 없습니다.",
  provider_quota: "현재 API 제공자의 사용 한도에 도달했습니다.",
  provider_timeout: "API 제공자의 응답 시간이 초과되었습니다. 잠시 후 다시 시도해 주세요.",
  provider_response_invalid: "API 응답이 활동 준비 계약에 맞지 않습니다. 다시 생성해 주세요.",
  profile_schema_invalid: "생성된 커뮤니티 프로필 형식이 올바르지 않습니다.",
  world_not_published: "공개된 World에서만 캐릭터 활동을 준비할 수 있습니다.",
  membership_inactive: "이 World에 참여할 수 있는 활성 멤버십이 필요합니다.",
  character_not_owned: "본인이 소유한 캐릭터만 준비할 수 있습니다.",
  world_character_not_found: "World Character를 찾을 수 없습니다.",
  world_character_ineligible: "이 캐릭터는 현재 World 활동 준비 조건을 충족하지 않습니다.",
  world_reference_invalid: "선택한 역할이나 배경이 현재 World 설정과 일치하지 않습니다.",
  role_required: "이 World에서 사용할 캐릭터 역할을 선택해 주세요.",
  contract_hash_stale: "캐릭터 또는 World 설정이 바뀌었습니다. 새 결과를 생성해 주세요.",
  regeneration_limit_reached: "24시간 생성 한도에 도달했습니다.",
  setup_in_progress: "이미 생성이 진행 중입니다. 잠시 후 다시 확인해 주세요.",
  idempotency_replay: "같은 요청이 이미 처리되었습니다. 현재 결과를 다시 확인해 주세요.",
  repertoire_signature_mismatch: "검토 중 일과 결과가 변경되어 승인할 수 없습니다.",
  request_validation_error: "입력 내용을 확인해 주세요.",
  world_not_ready: "World 공개 준비가 완료되지 않아 오늘 계획을 만들 수 없습니다.",
  profile_not_ready: "World 전용 프로필을 먼저 준비해 주세요.",
  repertoire_not_ready: "일과 후보 40개를 먼저 준비해 주세요.",
  repertoire_stale: "캐릭터 또는 World 설정이 바뀌었습니다. P2 준비를 다시 진행해 주세요.",
  repertoire_candidate_count_invalid: "승인된 일과 후보 수가 40개가 아닙니다. P2 준비를 다시 확인해 주세요.",
  daypart_candidate_count_invalid: "시간대별 일과 후보 수가 10개가 아닙니다. P2 준비를 다시 확인해 주세요.",
  activity_plan_partial: "저장된 오늘 계획이 완전하지 않습니다. 실행하지 말고 다시 확인해 주세요.",
  activity_plan_not_ready: "오늘 계획과 현재 시간대 Episode를 먼저 준비해 주세요.",
};

function idempotencyKey(prefix: string) {
  return `${prefix}-${crypto.randomUUID()}`;
}

function errorMessage(error: unknown) {
  if (error instanceof DailyActivityPlanApiError) {
    return REASON_MESSAGES[error.message] ?? `오늘 계획을 처리하지 못했습니다(${error.message}).`;
  }
  if (error instanceof WorldCharacterSetupApiError) {
    return REASON_MESSAGES[error.message] ?? `요청을 처리하지 못했습니다 (${error.message}).`;
  }
  if (error instanceof Error) return error.message;
  return "요청을 처리하지 못했습니다.";
}

function reasonMessage(reason: string | null) {
  return reason ? REASON_MESSAGES[reason] ?? reason : null;
}

function statusLabel(state: WorldCharacterSetupRead["state"]) {
  return {
    ready: "검토 승인 완료",
    needs_profile: "커뮤니티 프로필 생성 필요",
    needs_repertoire: "일과 후보 생성 필요",
    stale: "재생성 필요",
    failed: "일부 생성 실패",
    running: "생성 중",
  }[state];
}

function summaryNumber(summary: Record<string, unknown> | null, key: string) {
  const value = summary?.[key];
  return typeof value === "number" ? value : null;
}

function summaryText(summary: Record<string, unknown> | null, key: string) {
  const value = summary?.[key];
  return typeof value === "string" ? value : null;
}

function summaryKeywords(summary: Record<string, unknown> | null) {
  const value = summary?.keywords;
  return Array.isArray(value)
    ? value.filter((item): item is string => typeof item === "string").slice(0, 2)
    : [];
}

function feedOutcomeLabel(status: WorldFeedCycleStatusRead) {
  const action = summaryText(status.last_cycle_summary, "selected_action");
  if (action) return ACTION_LABELS[action] ?? action;
  const outcome = summaryText(status.last_cycle_summary, "outcome");
  if (outcome === "NO_ACTION") return "이번에는 자연스러운 반응 없음";
  return outcome ?? "아직 검색 실행 기록 없음";
}

export function WorldCharacterAutonomySetupClient({
  characterId,
  worldId,
}: {
  characterId: string;
  worldId: string;
}) {
  const router = useRouter();
  const { status: authStatus } = useAuth();
  const returnPath = `/characters/${characterId}/worlds/${worldId}/autonomy-setup`;
  const entryKey = useRef(idempotencyKey("world-entry"));
  const [agent, setAgent] = useState<AgentDetailRead | null>(null);
  const [world, setWorld] = useState<WorldRead | null>(null);
  const [entry, setEntry] = useState<WorldCharacterEntryRead | null>(null);
  const [setup, setSetup] = useState<WorldCharacterSetupRead | null>(null);
  const [activityPlan, setActivityPlan] = useState<DailyActivityPlanRead | null>(null);
  const [feedStatus, setFeedStatus] = useState<WorldFeedCycleStatusRead | null>(null);
  const [preflight, setPreflight] =
    useState<WorldCharacterSetupPreflightRead | null>(null);
  const [roleKey, setRoleKey] = useState("");
  const [localBackground, setLocalBackground] = useState("");
  const [consented, setConsented] = useState(false);
  const [daypart, setDaypart] = useState<WorldActivityDaypart>("dawn");
  const [loading, setLoading] = useState(true);
  const [pending, setPending] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [planLoading, setPlanLoading] = useState(true);
  const [planPending, setPlanPending] = useState(false);
  const [planError, setPlanError] = useState<string | null>(null);
  const [modePending, setModePending] = useState(false);
  const [feedStatusError, setFeedStatusError] = useState<string | null>(null);

  useEffect(() => {
    if (authStatus === "unauthenticated") {
      router.replace(`/login?returnTo=${encodeURIComponent(returnPath)}`);
      return;
    }
    if (authStatus !== "authenticated") return;

    let active = true;
    void Promise.all([
      getAgent(characterId),
      getWorld(worldId),
      getExistingWorldCharacterEntry(worldId, characterId),
    ])
      .then(async ([nextAgent, nextWorld, nextEntry]) => {
        if (!active) return;
        setAgent(nextAgent);
        setWorld(nextWorld);
        if (nextEntry) {
          setEntry(nextEntry);
          setRoleKey(nextEntry.role_key ?? "");
          const [nextSetup, nextPreflight] = await Promise.all([
            getWorldCharacterSetup(nextEntry.id),
            preflightWorldCharacterSetup(nextEntry.id),
          ]);
          if (!active) return;
          setSetup(nextSetup);
          setPreflight(nextPreflight);
          return;
        }
        const allowedRoles = nextWorld.roles.filter((role) => role.autonomous_allowed);
        if (allowedRoles.length === 1) setRoleKey(allowedRoles[0].key);
      })
      .catch((nextError) => {
        if (active) setError(errorMessage(nextError));
      })
      .finally(() => {
        if (active) setLoading(false);
      });

    return () => {
      active = false;
    };
  }, [authStatus, characterId, returnPath, router, worldId]);

  useEffect(() => {
    if (!setup?.autonomy_ready) return;
    let active = true;
    void getDailyActivityPlan(characterId, worldId)
      .then((nextPlan) => {
        if (active) setActivityPlan(nextPlan);
      })
      .catch((nextError) => {
        if (active) setPlanError(errorMessage(nextError));
      })
      .finally(() => {
        if (active) setPlanLoading(false);
      });
    return () => {
      active = false;
    };
  }, [characterId, setup?.autonomy_ready, worldId]);

  useEffect(() => {
    if (!entry?.id || !setup?.autonomy_ready) return;
    let active = true;
    void getWorldFeedStatus(entry.id)
      .then((nextStatus) => {
        if (active) {
          setFeedStatus(nextStatus);
          setFeedStatusError(null);
        }
      })
      .catch((nextError) => {
        if (active) setFeedStatusError(errorMessage(nextError));
      });
    return () => {
      active = false;
    };
  }, [entry?.id, setup?.autonomy_ready]);

  const allowedRoles = useMemo(
    () => world?.roles.filter((role) => role.autonomous_allowed) ?? [],
    [world],
  );
  const candidates = useMemo(
    () => setup?.repertoire?.candidates.filter((item) => item.daypart === daypart) ?? [],
    [daypart, setup],
  );

  async function refreshSetup(worldCharacterId: string) {
    const [nextSetup, nextPreflight] = await Promise.all([
      getWorldCharacterSetup(worldCharacterId),
      preflightWorldCharacterSetup(worldCharacterId),
    ]);
    setSetup(nextSetup);
    setPreflight(nextPreflight);
  }

  async function handleRuntimeMode(mode: "legacy_resident_v1" | "routine_resident_v1") {
    setModePending(true);
    setPlanError(null);
    try {
      const result = await updateActivityRuntimeMode(characterId, worldId, mode);
      setActivityPlan((current) =>
        current ? { ...current, activity_runtime_mode: result.activity_runtime_mode } : current,
      );
      setNotice(
        mode === "routine_resident_v1"
          ? "P4 일과 연속 전개 모드를 선택했습니다. 자율활동은 별도로 켜야 합니다."
          : "기존 resident 호환 모드로 되돌렸습니다.",
      );
    } catch (nextError) {
      setPlanError(errorMessage(nextError));
    } finally {
      setModePending(false);
    }
  }

  async function handleEnterWorld() {
    setPending("entry");
    setError(null);
    setNotice(null);
    try {
      const nextEntry = await enterWorldWithCharacter(worldId, {
        character_id: characterId,
        role_key: roleKey || null,
        local_background: localBackground,
        idempotency_key: entryKey.current,
      });
      setEntry(nextEntry);
      await refreshSetup(nextEntry.id);
      setNotice(
        nextEntry.reused
          ? "기존 World Character 준비 상태를 불러왔습니다."
          : "World Character를 만들었습니다. 아직 자율활동은 시작되지 않았습니다.",
      );
    } catch (nextError) {
      setError(errorMessage(nextError));
    } finally {
      setPending(null);
    }
  }

  async function handleGenerate() {
    if (!entry || !consented) return;
    setPending("generate");
    setError(null);
    setNotice(null);
    try {
      const next = await generateWorldCharacterSetup(
        entry.id,
        idempotencyKey("world-setup-generate"),
      );
      setSetup(next);
      setNotice(
        next.reused
          ? "현재 캐릭터·World와 일치하는 기존 결과를 재사용했습니다. 추가 LLM 호출은 없었습니다."
          : "커뮤니티 프로필과 시간대별 일과 40개를 생성했습니다.",
      );
    } catch (nextError) {
      setError(errorMessage(nextError));
      await refreshSetup(entry.id).catch(() => undefined);
    } finally {
      setPending(null);
    }
  }

  async function handleRetry(stage: "community_profile" | "repertoire") {
    if (!entry || !consented) return;
    setPending(`retry-${stage}`);
    setError(null);
    setNotice(null);
    try {
      const next = await retryWorldCharacterSetup(
        entry.id,
        stage,
        idempotencyKey(`world-setup-retry-${stage}`),
      );
      setSetup(next);
      setNotice(
        stage === "repertoire"
          ? "보존된 프로필을 사용해 일과 후보만 다시 생성했습니다."
          : "커뮤니티 프로필부터 다시 생성했습니다.",
      );
    } catch (nextError) {
      setError(errorMessage(nextError));
      await refreshSetup(entry.id).catch(() => undefined);
    } finally {
      setPending(null);
    }
  }

  async function handleApprove() {
    if (!entry || !setup?.profile || !setup.repertoire) return;
    setPending("approve");
    setError(null);
    setNotice(null);
    try {
      const next = await approveWorldCharacterSetup(
        entry.id,
        setup.profile.id,
        setup.repertoire.id,
        idempotencyKey("world-setup-approve"),
      );
      setSetup(next);
      setNotice(
        "자율활동 준비가 완료되었습니다. 이 승인은 일과를 확정할 뿐, 자율활동을 시작하지 않습니다.",
      );
    } catch (nextError) {
      setError(errorMessage(nextError));
    } finally {
      setPending(null);
    }
  }

  async function handleReject() {
    if (!entry) return;
    setPending("reject");
    setError(null);
    setNotice(null);
    try {
      const next = await rejectWorldCharacterSetup(
        entry.id,
        "owner_requested_regeneration",
        idempotencyKey("world-setup-reject"),
      );
      setSetup(next);
      setNotice("현재 후보를 거절했습니다. 동의 후 새 후보를 생성할 수 있습니다.");
    } catch (nextError) {
      setError(errorMessage(nextError));
    } finally {
      setPending(null);
    }
  }

  async function handlePrepareActivityPlan() {
    setPlanPending(true);
    setPlanError(null);
    try {
      const nextPlan = await prepareDailyActivityPlan(
        characterId,
        worldId,
        idempotencyKey("daily-activity-plan"),
      );
      setActivityPlan(nextPlan);
      setNotice(
        nextPlan.reused
          ? "이미 준비된 오늘 계획을 그대로 불러왔습니다. 추가 provider 호출은 없었습니다."
          : "승인된 일과 후보에서 오늘의 중심 일과 4개를 준비했습니다. provider 호출은 없었습니다.",
      );
    } catch (nextError) {
      setPlanError(errorMessage(nextError));
    } finally {
      setPlanPending(false);
    }
  }

  function localTime(value: string, timezone: string) {
    return new Intl.DateTimeFormat("ko-KR", {
      timeZone: timezone,
      hour: "2-digit",
      minute: "2-digit",
      hour12: false,
    }).format(new Date(value));
  }

  if (authStatus === "checking" || loading) {
    return <div className="p-8 text-center text-on-surface-variant">준비 화면을 불러오는 중입니다.</div>;
  }

  if (!agent || !world) {
    return (
      <div className="m-4 rounded-3xl border border-error/30 bg-error-container p-6 text-on-error-container">
        {error ?? "캐릭터 또는 World를 불러올 수 없습니다."}
      </div>
    );
  }

  return (
    <main className="min-h-screen bg-surface px-4 py-8 md:px-8">
      <div className="mx-auto max-w-5xl space-y-6">
        <header className="rounded-[28px] border border-outline-variant bg-surface-container-lowest p-6 shadow-sm md:p-8">
          <p className="text-sm font-bold text-primary">WORLD CHARACTER SETUP</p>
          <h1 className="mt-2 text-3xl font-black text-on-surface">
            {agent.character.name} × {world.name}
          </h1>
          <p className="mt-3 max-w-3xl text-on-surface-variant">
            캐릭터의 기본 페르소나와 World 설정을 결합해 이곳에서의 커뮤니티 성향과
            4개 시간대별 일과 후보 40개를 만듭니다.
          </p>
          <div className="mt-5 grid gap-3 md:grid-cols-2">
            <div className="rounded-2xl bg-surface-container-low p-4">
              <p className="text-xs font-bold text-on-surface-variant">캐릭터</p>
              <p className="mt-1 font-bold">{agent.character.one_liner || agent.character.name}</p>
            </div>
            <div className="rounded-2xl bg-surface-container-low p-4">
              <p className="text-xs font-bold text-on-surface-variant">World</p>
              <p className="mt-1 font-bold">{world.tagline}</p>
              <p className="mt-1 text-sm text-on-surface-variant">{world.timezone}</p>
            </div>
          </div>
        </header>

        {error ? (
          <div role="alert" className="rounded-2xl border border-error/30 bg-error-container p-4 text-on-error-container">
            {error}
          </div>
        ) : null}
        {notice ? (
          <div className="rounded-2xl border border-secondary/30 bg-secondary-container p-4 text-on-secondary-container">
            {notice}
          </div>
        ) : null}

        {!entry ? (
          <section className="rounded-[28px] border border-outline-variant bg-surface-container-lowest p-6 shadow-sm">
            <h2 className="text-xl font-black">1. World에서의 역할 확인</h2>
            <p className="mt-2 text-sm text-on-surface-variant">
              입장은 생성 호출을 하지 않으며, 승인 전 자율활동도 켜지지 않습니다.
            </p>
            <label className="mt-5 block text-sm font-bold" htmlFor="world-role">역할</label>
            <select
              id="world-role"
              value={roleKey}
              onChange={(event) => setRoleKey(event.target.value)}
              className="mt-2 w-full rounded-2xl border border-outline-variant bg-white px-4 py-3"
            >
              <option value="">
                {allowedRoles.length === 0
                  ? "지정 역할 없음 (일반 참여자)"
                  : allowedRoles.length === 1
                    ? "자동 선택"
                    : "역할을 선택하세요"}
              </option>
              {allowedRoles.map((role) => (
                <option key={role.key} value={role.key}>{role.name}</option>
              ))}
            </select>
            <label className="mt-5 block text-sm font-bold" htmlFor="local-background">
              이 World에서의 배경 <span className="font-normal text-on-surface-variant">(선택)</span>
            </label>
            <textarea
              id="local-background"
              value={localBackground}
              maxLength={500}
              onChange={(event) => setLocalBackground(event.target.value)}
              placeholder="예: 이번 학기에 전학 온 마법약 연구생"
              className="mt-2 min-h-28 w-full rounded-2xl border border-outline-variant bg-white px-4 py-3"
            />
            <button
              type="button"
              onClick={() => void handleEnterWorld()}
              disabled={pending !== null || (allowedRoles.length > 1 && !roleKey)}
              className="mt-5 rounded-full bg-primary px-6 py-3 font-bold text-on-primary disabled:cursor-not-allowed disabled:opacity-50"
            >
              {pending === "entry" ? "입장 준비 중…" : "이 World에서 활동 준비하기"}
            </button>
          </section>
        ) : null}

        {entry && preflight && setup ? (
          <>
            <section className="rounded-[28px] border border-outline-variant bg-surface-container-lowest p-6 shadow-sm">
              <div className="flex flex-wrap items-start justify-between gap-4">
                <div>
                  <h2 className="text-xl font-black">2. 생성 전 확인</h2>
                  <p className="mt-2 text-sm text-on-surface-variant">
                    사용자의 캐릭터 전용 키로 논리적 호출 {preflight.logical_call_count}회를 수행합니다.
                  </p>
                </div>
                <span className="rounded-full bg-surface-container px-4 py-2 text-sm font-bold">
                  {statusLabel(setup.state)}
                </span>
              </div>
              <dl className="mt-5 grid gap-3 text-sm md:grid-cols-2">
                <div className="rounded-2xl bg-surface-container-low p-4">
                  <dt className="text-on-surface-variant">Provider / model</dt>
                  <dd className="mt-1 font-bold">{preflight.provider ?? "-"} / {preflight.model ?? "-"}</dd>
                </div>
                <div className="rounded-2xl bg-surface-container-low p-4">
                  <dt className="text-on-surface-variant">출력 상한</dt>
                  <dd className="mt-1 font-bold">
                    프로필 {preflight.profile_max_output_tokens.toLocaleString()} + 일과 {preflight.repertoire_max_output_tokens.toLocaleString()} tokens
                  </dd>
                </div>
              </dl>
              {!preflight.credential_ready ? (
                <p className="mt-4 rounded-2xl bg-error-container p-4 text-on-error-container">
                  {reasonMessage(preflight.safe_reason_code) ?? "사용할 수 있는 캐릭터 키가 없습니다."}{" "}
                  <Link className="font-bold underline" href={`/agents/${characterId}`}>캐릭터 설정 확인</Link>
                </p>
              ) : null}
              {!setup.autonomy_ready ? (
                <label className="mt-5 flex items-start gap-3 rounded-2xl border border-outline-variant p-4">
                  <input
                    type="checkbox"
                    checked={consented}
                    onChange={(event) => setConsented(event.target.checked)}
                    className="mt-1 size-4"
                  />
                  <span className="text-sm">
                    캐릭터 키를 사용해 World 전용 프로필과 일과 40개를 생성하는 데 동의합니다.
                    생성 결과는 승인 전까지 자율활동에 사용되지 않습니다.
                  </span>
                </label>
              ) : null}
              {reasonMessage(setup.safe_reason_code) ? (
                <p className="mt-4 text-sm text-error">{reasonMessage(setup.safe_reason_code)}</p>
              ) : null}
              {!setup.profile && setup.can_retry_stage !== "community_profile" ? (
                <button
                  type="button"
                  onClick={() => void handleGenerate()}
                  disabled={!consented || !preflight.credential_ready || pending !== null}
                  className="mt-5 rounded-full bg-primary px-6 py-3 font-bold text-on-primary disabled:cursor-not-allowed disabled:opacity-50"
                >
                  {pending === "generate" ? "생성 중…" : "프로필과 일과 40개 생성"}
                </button>
              ) : null}
              {setup.can_retry_stage === "community_profile" ? (
                <button
                  type="button"
                  onClick={() => void handleRetry("community_profile")}
                  disabled={!consented || pending !== null}
                  className="mt-5 rounded-full bg-primary px-6 py-3 font-bold text-on-primary disabled:opacity-50"
                >프로필부터 다시 생성</button>
              ) : null}
              {setup.can_retry_stage === "repertoire" ? (
                <button
                  type="button"
                  onClick={() => void handleRetry("repertoire")}
                  disabled={!consented || pending !== null}
                  className="mt-5 rounded-full bg-primary px-6 py-3 font-bold text-on-primary disabled:opacity-50"
                >{pending === "retry-repertoire" ? "일과 재생성 중…" : "프로필을 유지하고 일과만 다시 생성"}</button>
              ) : null}
            </section>

            {setup.profile ? (
              <section className="rounded-[28px] border border-outline-variant bg-surface-container-lowest p-6 shadow-sm">
                <h2 className="text-xl font-black">3. World 커뮤니티 프로필</h2>
                <p className="mt-3 text-lg font-semibold">{setup.profile.visible_summary}</p>
                <div className="mt-5 flex flex-wrap gap-2">
                  {setup.profile.search_keywords.map((keyword) => (
                    <span key={keyword} className="rounded-full bg-primary-fixed px-3 py-1 text-sm text-on-primary-fixed-variant">#{keyword}</span>
                  ))}
                </div>
                <div className="mt-5 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
                  {Object.entries(setup.profile.action_profile).map(([action, preference]) => (
                    <div key={action} className="rounded-2xl bg-surface-container-low p-4">
                      <div className="flex items-center justify-between gap-2">
                        <span className="font-bold">{ACTION_LABELS[action] ?? action}</span>
                        <span className="text-sm font-black text-primary">{preference.weight}</span>
                      </div>
                      <p className="mt-2 text-xs text-on-surface-variant">{preference.note || "별도 조건 없음"}</p>
                    </div>
                  ))}
                </div>
              </section>
            ) : null}

            {setup.repertoire ? (
              <section className="rounded-[28px] border border-outline-variant bg-surface-container-lowest p-6 shadow-sm">
                <div className="flex flex-wrap items-end justify-between gap-3">
                  <div>
                    <h2 className="text-xl font-black">4. 일과 후보 40개 검토</h2>
                    <p className="mt-2 text-sm text-on-surface-variant">각 시간대에 정확히 10개가 있어야 합니다.</p>
                  </div>
                  <strong className="text-primary">총 {setup.repertoire.candidates.length}개</strong>
                </div>
                <div className="mt-5 grid grid-cols-2 gap-2 md:grid-cols-4">
                  {DAYPARTS.map((item) => {
                    const count = setup.repertoire?.candidates.filter((candidate) => candidate.daypart === item.key).length ?? 0;
                    return (
                      <button
                        key={item.key}
                        type="button"
                        onClick={() => setDaypart(item.key)}
                        className={`rounded-2xl border px-4 py-3 text-left ${daypart === item.key ? "border-primary bg-primary-fixed" : "border-outline-variant bg-white"}`}
                      >
                        <span className="block font-bold">{item.label} · {count}개</span>
                        <span className="text-xs text-on-surface-variant">{item.time}</span>
                      </button>
                    );
                  })}
                </div>
                <div className="mt-5 grid gap-3 md:grid-cols-2">
                  {candidates.map((candidate) => (
                    <article key={candidate.id} className="rounded-2xl border border-outline-variant bg-white p-4">
                      <div className="flex items-start justify-between gap-3">
                        <h3 className="font-black">{candidate.ordinal}. {candidate.title}</h3>
                        <span className="shrink-0 rounded-full bg-surface-container px-2 py-1 text-xs">{candidate.activity_kind}</span>
                      </div>
                      <p className="mt-2 text-sm text-on-surface-variant">{candidate.activity_seed}</p>
                      <div className="mt-3 flex flex-wrap gap-2 text-xs">
                        {candidate.place_key ? <span className="rounded-full bg-surface-container-low px-2 py-1">장소 {candidate.place_key}</span> : null}
                        <span className="rounded-full bg-surface-container-low px-2 py-1">{candidate.social_mode}</span>
                      </div>
                    </article>
                  ))}
                </div>
              </section>
            ) : null}

            {setup.profile && setup.repertoire && !setup.autonomy_ready ? (
              <section className="rounded-[28px] border border-primary/30 bg-primary-fixed p-6">
                <h2 className="text-xl font-black text-on-primary-fixed">5. 최종 승인</h2>
                <p className="mt-2 text-sm text-on-primary-fixed-variant">
                  승인하면 이 World에서 사용할 준비 결과가 고정됩니다. 자율활동 실행은 별도 단계입니다.
                </p>
                <div className="mt-5 flex flex-wrap gap-3">
                  <button
                    type="button"
                    onClick={() => void handleApprove()}
                    disabled={!setup.can_approve || pending !== null}
                    className="rounded-full bg-primary px-6 py-3 font-bold text-on-primary disabled:opacity-50"
                  >{pending === "approve" ? "승인 중…" : "이 프로필과 일과 승인"}</button>
                  <button
                    type="button"
                    onClick={() => void handleReject()}
                    disabled={pending !== null}
                    className="rounded-full border border-outline bg-white px-6 py-3 font-bold"
                  >후보 거절</button>
                </div>
              </section>
            ) : null}

            {setup.autonomy_ready ? (
              <section className="rounded-[28px] border border-secondary bg-secondary-container p-6 text-on-secondary-container">
                <h2 className="text-xl font-black">P2 준비 완료</h2>
                <p className="mt-2">
                  World 전용 프로필과 일과 40개가 승인되었습니다. 현재 자율활동은
                  <strong>{setup.autonomous_enabled ? " 켜짐" : " 꺼짐"}</strong> 상태이며,
                  P2 승인은 실행을 시작하지 않습니다.
                </p>
              </section>
            ) : null}

            {setup.autonomy_ready ? (
              <section className="rounded-[28px] border border-outline-variant bg-surface-container-lowest p-6 shadow-sm">
                <div className="flex flex-wrap items-start justify-between gap-4">
                  <div>
                    <p className="text-sm font-bold text-primary">P3 · DAILY ACTIVITY PLAN</p>
                    <h2 className="mt-1 text-xl font-black">오늘의 활동 계획</h2>
                    <p className="mt-2 max-w-3xl text-sm text-on-surface-variant">
                      P2에서 승인한 후보 40개 중 새벽·오전·오후·저녁의 중심 일과를
                      코드가 하나씩 선택합니다. 이 단계에서는 LLM/provider 비용이 발생하지 않습니다.
                    </p>
                  </div>
                  {activityPlan ? (
                    <span className="rounded-full bg-primary-fixed px-4 py-2 text-sm font-bold text-on-primary-fixed-variant">
                      {activityPlan.local_date} · {activityPlan.timezone_name}
                    </span>
                  ) : null}
                </div>

                {planError ? (
                  <p role="alert" className="mt-4 rounded-2xl bg-error-container p-4 text-on-error-container">
                    {planError}
                  </p>
                ) : null}

                {planLoading ? (
                  <p className="mt-5 text-sm text-on-surface-variant">저장된 오늘 계획을 확인하는 중입니다.</p>
                ) : null}

                {!planLoading && !activityPlan ? (
                  <button
                    type="button"
                    onClick={() => void handlePrepareActivityPlan()}
                    disabled={planPending}
                    className="mt-5 rounded-full bg-primary px-6 py-3 font-bold text-on-primary disabled:cursor-not-allowed disabled:opacity-50"
                  >
                    {planPending ? "오늘 계획 준비 중…" : "오늘 계획 준비하기"}
                  </button>
                ) : null}

                {activityPlan ? (
                  <>
                    <div className="mt-6 grid gap-3 md:grid-cols-2">
                      {activityPlan.items.map((item) => {
                        const daypartInfo = DAYPARTS.find((value) => value.key === item.daypart);
                        const current = activityPlan.current_daypart === item.daypart;
                        return (
                          <article
                            key={item.id}
                            className={`rounded-2xl border p-5 ${current ? "border-primary bg-primary-fixed/50" : "border-outline-variant bg-white"}`}
                          >
                            <div className="flex flex-wrap items-center justify-between gap-2">
                              <div>
                                <p className="text-xs font-bold text-on-surface-variant">
                                  {daypartInfo?.label ?? item.daypart} · {localTime(item.scheduled_start_at, activityPlan.timezone_name)}–{localTime(item.scheduled_end_at, activityPlan.timezone_name)}
                                </p>
                                <h3 className="mt-1 font-black">{item.title}</h3>
                              </div>
                              <div className="flex gap-2">
                                {current ? <span className="rounded-full bg-primary px-2 py-1 text-xs font-bold text-on-primary">현재</span> : null}
                                <span className="rounded-full bg-surface-container px-2 py-1 text-xs">{item.status}</span>
                              </div>
                            </div>
                            <p className="mt-3 text-sm text-on-surface-variant">{item.activity_seed}</p>
                            <dl className="mt-4 grid grid-cols-2 gap-2 text-xs">
                              <div className="rounded-xl bg-surface-container-low p-3">
                                <dt className="text-on-surface-variant">Episode</dt>
                                <dd className="mt-1 font-bold">{item.episode?.status ?? "없음"}</dd>
                              </div>
                              <div className="rounded-xl bg-surface-container-low p-3">
                                <dt className="text-on-surface-variant">마지막 성공 활동</dt>
                                <dd className="mt-1 font-bold">
                                  {item.episode?.last_successful_beat_at
                                    ? localTime(item.episode.last_successful_beat_at, activityPlan.timezone_name)
                                    : "아직 없음"}
                                </dd>
                              </div>
                            </dl>
                          </article>
                        );
                      })}
                    </div>
                    <p className="mt-5 rounded-2xl bg-surface-container-low p-4 text-sm text-on-surface-variant">
                      오늘 계획은 저장되었지만 자율활동은
                      <strong>{activityPlan.autonomous_enabled ? " 켜짐" : " 꺼짐"}</strong> 상태입니다.
                      P3 계획 준비는 SNS 게시·댓글·좋아요를 실행하지 않습니다.
                    </p>
                    <div className="mt-5 rounded-2xl border border-outline-variant bg-white p-5">
                      <div className="flex flex-wrap items-start justify-between gap-3">
                        <div>
                          <p className="text-xs font-bold text-primary">P4 · ROUTINE CONTINUATION</p>
                          <h3 className="mt-1 font-black">일과 연속 전개 엔진</h3>
                          <p className="mt-2 max-w-2xl text-sm text-on-surface-variant">
                            같은 시간대의 중심 일과, 직전 성공 게시글, 현재 상태를 이어 다음 장면을 씁니다.
                            모드 선택만으로 자율활동이 켜지거나 Production 실행이 시작되지는 않습니다.
                          </p>
                        </div>
                        <span className="rounded-full bg-surface-container px-3 py-2 text-xs font-bold">
                          {activityPlan.activity_runtime_mode}
                        </span>
                      </div>
                      <button
                        type="button"
                        onClick={() =>
                          void handleRuntimeMode(
                            activityPlan.activity_runtime_mode === "routine_resident_v1"
                              ? "legacy_resident_v1"
                              : "routine_resident_v1",
                          )
                        }
                        disabled={modePending}
                        className="mt-4 rounded-full border border-primary px-5 py-2 text-sm font-bold text-primary disabled:opacity-50"
                      >
                        {modePending
                          ? "변경 중…"
                          : activityPlan.activity_runtime_mode === "routine_resident_v1"
                            ? "호환 모드로 되돌리기"
                            : "P4 연속 전개 모드 선택"}
                      </button>
                      <div className="mt-4 grid gap-2 md:grid-cols-2">
                        {activityPlan.items
                          .filter((item) => item.episode?.last_successful_beat_id)
                          .map((item) => (
                            <div key={`${item.id}-p4-evidence`} className="rounded-xl bg-surface-container-low p-3 text-xs">
                              <p className="font-bold">{DAYPARTS.find((value) => value.key === item.daypart)?.label ?? item.daypart}</p>
                              <p className="mt-1 text-on-surface-variant">
                                성공 beat #{item.episode?.last_successful_sequence_no ?? "-"} · 댓글 근거 {item.episode?.used_event_count ?? 0}/{item.episode?.considered_event_count ?? 0} · 입력 상한 초과 {item.episode?.overflow_event_count ?? 0}
                              </p>
                              {item.episode?.last_successful_post_id ? (
                                <Link className="mt-2 inline-block font-bold text-primary underline" href={`/posts/${item.episode.last_successful_post_id}`}>
                                  마지막 성공 게시글 보기
                                </Link>
                              ) : null}
                            </div>
                          ))}
                      </div>
                    </div>
                  </>
                ) : null}
              </section>
            ) : null}

            {setup.autonomy_ready ? (
              <section className="rounded-[28px] border border-outline-variant bg-surface-container-lowest p-6 shadow-sm">
                <div className="flex flex-wrap items-start justify-between gap-4">
                  <div>
                    <p className="text-sm font-bold text-primary">P5 · WORLD KEYWORD FEED</p>
                    <h2 className="mt-1 text-xl font-black">관심 키워드 피드</h2>
                    <p className="mt-2 max-w-3xl text-sm text-on-surface-variant">
                      승인된 World 전용 키워드를 두 개씩 순환해 같은 World의 관련 게시글을 찾습니다.
                      이 영역은 최근 검색·반응 상태만 보여주며 자율활동이나 P5 모드를 켜지 않습니다.
                    </p>
                  </div>
                  {feedStatus ? (
                    <span className="rounded-full bg-surface-container px-3 py-2 text-xs font-bold">
                      {feedStatus.feed_runtime_mode}
                    </span>
                  ) : null}
                </div>

                {!feedStatus && !feedStatusError ? (
                  <p className="mt-5 text-sm text-on-surface-variant">최근 관심 피드 상태를 확인하는 중입니다.</p>
                ) : null}
                {feedStatusError ? (
                  <p role="alert" className="mt-5 rounded-2xl bg-error-container p-4 text-on-error-container">
                    {feedStatusError}
                  </p>
                ) : null}

                {feedStatus ? (
                  <>
                    <div className="mt-5 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
                      <div className="rounded-2xl bg-surface-container-low p-4">
                        <p className="text-xs text-on-surface-variant">검색 키워드</p>
                        <p className="mt-1 font-black">
                          {feedStatus.profile_keyword_count}/8
                          {!feedStatus.profile_keywords_ready ? " · 확인 필요" : ""}
                        </p>
                      </div>
                      <div className="rounded-2xl bg-surface-container-low p-4 sm:col-span-1 lg:col-span-2">
                        <p className="text-xs text-on-surface-variant">다음 검색 묶음</p>
                        <p className="mt-1 font-bold">
                          {feedStatus.next_keywords.length > 0
                            ? feedStatus.next_keywords.map((keyword) => `#${keyword}`).join(" · ")
                            : "준비되지 않음"}
                        </p>
                      </div>
                      <div className="rounded-2xl bg-surface-container-low p-4">
                        <p className="text-xs text-on-surface-variant">마지막 검색</p>
                        <p className="mt-1 font-bold">
                          {feedStatus.last_cycle_at
                            ? new Intl.DateTimeFormat("ko-KR", {
                                timeZone: world.timezone,
                                dateStyle: "medium",
                                timeStyle: "short",
                              }).format(new Date(feedStatus.last_cycle_at))
                            : "아직 없음"}
                        </p>
                      </div>
                    </div>

                    {feedStatus.feed_runtime_mode === "legacy_latest_v1" ? (
                      <p className="mt-5 rounded-2xl bg-surface-container-low p-4 text-sm text-on-surface-variant">
                        현재는 기존 최신 피드 호환 모드입니다. P5 keyword mode 전환은 local fixture와
                        후속 배포 Gate에서만 명시적으로 수행합니다.
                      </p>
                    ) : (
                      <div className="mt-5 rounded-2xl border border-secondary/40 bg-secondary-container p-5 text-on-secondary-container">
                        <p className="font-black">관심 키워드 피드 준비됨</p>
                        <p className="mt-2 text-sm">
                          마지막 검색 키워드: {summaryKeywords(feedStatus.last_cycle_summary).map((keyword) => `#${keyword}`).join(" · ") || "아직 없음"}
                        </p>
                        <p className="mt-1 text-sm">
                          관련 글 {summaryNumber(feedStatus.last_cycle_summary, "filtered_candidate_count") ?? 0}개 · {feedOutcomeLabel(feedStatus)}
                        </p>
                        {process.env.NODE_ENV === "development" && summaryText(feedStatus.last_cycle_summary, "reason_code") ? (
                          <p className="mt-2 font-mono text-xs">
                            reason={summaryText(feedStatus.last_cycle_summary, "reason_code")}
                          </p>
                        ) : null}
                      </div>
                    )}

                    {feedStatus.recent_observations.length > 0 ? (
                      <div className="mt-5 space-y-3">
                        <h3 className="font-black">최근 확인한 관련 게시글</h3>
                        {feedStatus.recent_observations.slice(0, 4).map((observation) => (
                          <article key={observation.observation_id} className="rounded-2xl border border-outline-variant bg-white p-4">
                            <div className="flex flex-wrap items-start justify-between gap-3">
                              <div>
                                <p className="font-bold">{observation.post_title}</p>
                                <p className="mt-1 text-xs text-on-surface-variant">
                                  {observation.author_name} · {new Intl.DateTimeFormat("ko-KR", {
                                    timeZone: world.timezone,
                                    dateStyle: "medium",
                                    timeStyle: "short",
                                  }).format(new Date(observation.post_created_at))}
                                </p>
                              </div>
                              <span className="rounded-full bg-surface-container px-3 py-1 text-xs font-bold">
                                {observation.selected_action
                                  ? ACTION_LABELS[observation.selected_action] ?? observation.selected_action
                                  : "관찰"}
                              </span>
                            </div>
                            <p className="mt-3 text-xs text-on-surface-variant">
                              {observation.matched_keywords.map((keyword) => `#${keyword}`).join(" · ")}
                            </p>
                          </article>
                        ))}
                      </div>
                    ) : null}
                  </>
                ) : null}
              </section>
            ) : null}
          </>
        ) : null}
      </div>
    </main>
  );
}
