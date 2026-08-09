"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useRef, useState } from "react";

import { useAuth } from "@/components/auth-provider";
import { getAgent, type AgentDetailRead } from "@/lib/agents";
import {
  approveWorldCharacterSetup,
  enterWorldWithCharacter,
  generateWorldCharacterSetup,
  getExistingWorldCharacterEntry,
  getWorldCharacterSetup,
  preflightWorldCharacterSetup,
  rejectWorldCharacterSetup,
  retryWorldCharacterSetup,
  WorldCharacterSetupApiError,
  type WorldActivityDaypart,
  type WorldCharacterEntryRead,
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
};

function idempotencyKey(prefix: string) {
  return `${prefix}-${crypto.randomUUID()}`;
}

function errorMessage(error: unknown) {
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
          </>
        ) : null}
      </div>
    </main>
  );
}
