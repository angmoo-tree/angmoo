"use client";

import {
  Link2,
  Loader2,
  Plus,
  RefreshCw,
  Trash2,
  UserRound,
  X,
} from "lucide-react";
import Link from "next/link";
import { useEffect, useMemo, useRef, useState } from "react";

import {
  enterStudioWorldCharacter,
  getStudioCharacterCandidates,
  getStudioWorldCharacters,
  leaveStudioWorldCharacter,
  stopStudioCharacter,
  StudioWorldCharacterApiError,
} from "../api/studio-world-character-client";
import type {
  StudioCharacterCandidateRead,
  StudioWorldCharacterRead,
  StudioWorldRole,
} from "../model/studio-world-character-contract";
import {
  studioWorldRoute,
  useRuntimeRouter,
  useRuntimeSearchParams,
} from "@/shared/navigation/public";
import {
  Button,
  Dialog,
  Field,
  IconButton,
  InlineError,
  Select,
  StatusChip,
} from "@/shared/ui/public";


const NO_SPECIFIC_ROLE_KEY = "no_specific_role";
const SETUP_LABELS: Record<StudioWorldCharacterRead["activity_setup_state"], string> = {
  not_started: "P2 준비 전",
  generated: "P2 후보 생성됨",
  approved: "P2 승인 완료",
  unavailable_for_owner_controlled: "자동 활동 대상 아님",
};

const CANDIDATE_REASON_LABELS: Record<string, string> = {
  already_linked: "이미 이 World에 연결되어 있습니다.",
  character_moderation_inactive: "현재 연결할 수 없는 검토 상태입니다.",
  local_execution_mode_unsupported: "외부 연결 앵무는 P2 자율활동 준비 대상이 아닙니다.",
  world_character_ineligible: "이 World의 기존 참여 상태 때문에 연결할 수 없습니다.",
  world_character_left_restore_unsupported:
    "이 World에서 제거된 이력이 있습니다. 이번 최소 패치에서는 재참여를 지원하지 않습니다.",
};

function requestKey(prefix: string) {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    return `${prefix}:${crypto.randomUUID()}`;
  }
  return `${prefix}:${Date.now()}:${Math.random().toString(36).slice(2)}`;
}

function apiErrorMessage(error: unknown, fallback: string) {
  if (!(error instanceof StudioWorldCharacterApiError)) return fallback;
  const labels: Record<string, string> = {
    character_not_owned: "내가 소유한 캐릭터만 처리할 수 있습니다.",
    confirmation_name_mismatch: "확인 이름이 캐릭터 이름과 일치하지 않습니다.",
    creator_role_required: "World owner 또는 editor 권한이 필요합니다.",
    owner_controlled_world_character_protected:
      "내 World 프로필은 이 화면에서 제거할 수 없습니다.",
    role_required: "World 역할을 선택해 주세요.",
    scheduler_assignment_active:
      "자율활동 실행 슬롯을 정리하는 중입니다. 잠시 뒤 다시 시도해 주세요.",
    stale_world_character_version:
      "다른 화면에서 상태가 변경되었습니다. 새로고침 후 다시 확인해 주세요.",
    world_character_autonomy_enabled:
      "자율활동을 먼저 끈 뒤 다시 시도해 주세요.",
    world_character_left_restore_unsupported:
      "이 World에서 제거된 캐릭터의 재참여는 아직 지원하지 않습니다.",
    world_character_run_in_progress:
      "캐릭터가 지금 활동 중입니다. 실행이 끝난 뒤 다시 시도해 주세요.",
    world_character_setup_in_progress:
      "활동 준비 작업이 진행 중입니다. 완료된 뒤 다시 시도해 주세요.",
    world_not_found: "World를 찾을 수 없거나 접근할 수 없습니다.",
    world_not_published: "World를 먼저 발행한 뒤 캐릭터를 연결해 주세요.",
    world_reference_invalid: "선택한 World 역할을 다시 확인해 주세요.",
  };
  return labels[error.detail] ?? error.detail;
}

export function StudioWorldCharacterList({
  worldId,
  roles,
}: {
  worldId: string;
  roles: StudioWorldRole[];
}) {
  const router = useRuntimeRouter();
  const searchParams = useRuntimeSearchParams();
  const createdCharacterId = searchParams.get("createdCharacterId") ?? "";
  const returnTo = studioWorldRoute(worldId);
  const createHref = `/agents/new?worldId=${encodeURIComponent(worldId)}&returnTo=${encodeURIComponent(returnTo)}`;
  const [reloadKey, setReloadKey] = useState(0);
  const listRequestKey = `${worldId}:${reloadKey}`;
  const [result, setResult] = useState<{
    key: string;
    items: StudioWorldCharacterRead[];
    error: string | null;
  }>({ key: "", items: [], error: null });
  const loading = result.key !== listRequestKey;
  const items = loading ? [] : result.items;
  const error = loading ? null : result.error;

  const [candidateOpen, setCandidateOpen] = useState(Boolean(createdCharacterId));
  const candidateRequestKey = candidateOpen ? `${worldId}:${createdCharacterId}` : "";
  const [candidateResult, setCandidateResult] = useState<{
    key: string;
    items: StudioCharacterCandidateRead[];
    error: string | null;
  }>({ key: "", items: [], error: null });
  const candidateLoading = candidateOpen && candidateResult.key !== candidateRequestKey;
  const candidates = candidateLoading ? [] : candidateResult.items;
  const candidateError = candidateLoading ? null : candidateResult.error;
  const [selectedCharacterId, setSelectedCharacterId] = useState(createdCharacterId);
  const [roleKey, setRoleKey] = useState(NO_SPECIFIC_ROLE_KEY);
  const [actionBusy, setActionBusy] = useState(false);
  const [actionMessage, setActionMessage] = useState<string | null>(
    createdCharacterId
      ? "캐릭터 생성은 완료되었습니다. 역할을 선택해 이 World에 연결해 주세요."
      : null,
  );
  const [actionError, setActionError] = useState<string | null>(null);
  const [removeTarget, setRemoveTarget] = useState<StudioWorldCharacterRead | null>(null);
  const [confirmationName, setConfirmationName] = useState("");
  const entryRequest = useRef<{ signature: string; key: string } | null>(null);
  const leaveRequest = useRef<{
    signature: string;
    key: string;
    version?: number;
    confirmationName?: string;
  } | null>(null);

  const roleOptions = useMemo(
    () => [
      { key: NO_SPECIFIC_ROLE_KEY, name: "역할 없음", autonomous_allowed: true },
      ...roles.filter(
        (role) => role.autonomous_allowed && role.key !== NO_SPECIFIC_ROLE_KEY,
      ),
    ],
    [roles],
  );
  const eligibleCandidates = candidates.filter((candidate) => candidate.eligible);

  useEffect(() => {
    let active = true;
    void getStudioWorldCharacters(worldId)
      .then((next) => {
        if (active) setResult({ key: listRequestKey, items: next.items, error: null });
      })
      .catch((reason) => {
        if (active) {
          setResult({
            key: listRequestKey,
            items: [],
            error: apiErrorMessage(reason, "이 World의 캐릭터를 불러오지 못했습니다."),
          });
        }
      });
    return () => {
      active = false;
    };
  }, [listRequestKey, worldId]);

  useEffect(() => {
    if (!candidateOpen) return;
    const controller = new AbortController();
    void getStudioCharacterCandidates(worldId, { signal: controller.signal })
      .then((next) => {
        setCandidateResult({ key: candidateRequestKey, items: next.items, error: null });
        if (
          createdCharacterId &&
          next.items.some(
            (candidate) =>
              candidate.character_id === createdCharacterId && candidate.eligible,
          )
        ) {
          setSelectedCharacterId(createdCharacterId);
        } else {
          setSelectedCharacterId(
            (current) => {
              const eligible = next.items.filter((candidate) => candidate.eligible);
              return eligible.some((candidate) => candidate.character_id === current)
                ? current
                : eligible[0]?.character_id ?? "";
            },
          );
        }
      })
      .catch((reason) => {
        if (reason instanceof DOMException && reason.name === "AbortError") return;
        setCandidateResult({
          key: candidateRequestKey,
          items: [],
          error: apiErrorMessage(
            reason,
            "연결할 수 있는 내 캐릭터를 불러오지 못했습니다.",
          ),
        });
      });
    return () => controller.abort();
  }, [candidateOpen, candidateRequestKey, createdCharacterId, worldId]);

  function refreshList() {
    setReloadKey((value) => value + 1);
  }

  function openOwnerProfile() {
    document
      .getElementById("owner-controlled-identity")
      ?.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  async function handleConnect() {
    if (!selectedCharacterId || !roleKey || actionBusy) return;
    const signature = `${worldId}:${selectedCharacterId}:${roleKey}`;
    if (entryRequest.current?.signature !== signature) {
      entryRequest.current = { signature, key: requestKey("studio-entry") };
    }
    setActionBusy(true);
    setActionError(null);
    setActionMessage(null);
    try {
      const entry = await enterStudioWorldCharacter(worldId, {
        character_id: selectedCharacterId,
        role_key: roleKey,
        idempotency_key: entryRequest.current.key,
      });
      setActionMessage(
        entry.reused
          ? "이미 연결된 캐릭터를 확인했습니다. 활동 준비 화면에서 이어갈 수 있습니다."
          : "현재 World에 연결했습니다. 이제 P2 활동 준비·승인을 진행해 주세요.",
      );
      setCandidateOpen(false);
      refreshList();
      if (createdCharacterId) router.replace(returnTo);
    } catch (reason) {
      setActionError(apiErrorMessage(reason, "캐릭터를 이 World에 연결하지 못했습니다."));
    } finally {
      setActionBusy(false);
    }
  }

  function beginRemove(item: StudioWorldCharacterRead) {
    setRemoveTarget(item);
    setConfirmationName("");
    setActionError(null);
    setActionMessage(null);
    leaveRequest.current = null;
  }

  async function handleRemove() {
    if (!removeTarget || confirmationName !== removeTarget.confirmation_name || actionBusy) return;
    const signature = `${removeTarget.world_character_id}:${removeTarget.version}`;
    if (leaveRequest.current?.signature !== signature) {
      leaveRequest.current = { signature, key: requestKey("studio-leave") };
    }
    setActionBusy(true);
    setActionError(null);
    try {
      if (removeTarget.selected_active_world) {
        await stopStudioCharacter(removeTarget.character_id);
      }
      const latest = await getStudioWorldCharacters(worldId);
      const current = latest.items.find(
        (item) => item.world_character_id === removeTarget.world_character_id,
      );
      if (current && leaveRequest.current) {
        leaveRequest.current.version = current.version;
        leaveRequest.current.confirmationName = current.confirmation_name;
      }
      const leaveVersion = current?.version ?? leaveRequest.current?.version;
      const leaveConfirmationName =
        current?.confirmation_name ?? leaveRequest.current?.confirmationName;
      if (leaveVersion === undefined || !leaveConfirmationName) {
        throw new StudioWorldCharacterApiError(409, "stale_world_character_version");
      }
      const left = await leaveStudioWorldCharacter(
        worldId,
        removeTarget.character_id,
        {
          world_character_id: removeTarget.world_character_id,
          version: leaveVersion,
          confirmation_name: leaveConfirmationName,
          idempotency_key: leaveRequest.current.key,
        },
      );
      setActionMessage(
        left.replayed
          ? "이미 이 World에서 제거된 상태를 확인했습니다. 기존 활동·관계 근거는 보존됩니다."
          : "이 World에서 제거했습니다. 캐릭터 자체와 기존 활동·사건·관계 근거는 보존됩니다.",
      );
      setRemoveTarget(null);
      setConfirmationName("");
      refreshList();
    } catch (reason) {
      setActionError(apiErrorMessage(reason, "이 World에서 캐릭터를 제거하지 못했습니다."));
    } finally {
      setActionBusy(false);
    }
  }

  return (
    <section className="rounded-[28px] border border-border-control bg-surface p-6 shadow-sm">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="text-lg font-black text-text-strong">이 World의 캐릭터</p>
          <p className="mt-1 text-sm font-medium leading-6 text-text-secondary">
            자율활동 검증용 캐릭터를 만들거나 연결하고, 현재 World 참여만 안전하게 종료합니다.
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Link
            href={createHref}
            className="inline-flex min-h-11 items-center gap-2 rounded-full bg-action-primary px-4 py-2 text-xs font-extrabold text-on-action-primary shadow-action"
          >
            <Plus className="size-4" /> 새 캐릭터 만들기
          </Link>
          <Button
            compact
            variant="secondary"
            onClick={() => setCandidateOpen((value) => !value)}
          >
            <Link2 className="size-4" /> 기존 캐릭터 연결
          </Button>
          <Button
            compact
            variant="secondary"
            onClick={refreshList}
            loading={loading}
            loadingLabel="새로고침 중"
          >
            <RefreshCw className="size-4" />
            새로고침
          </Button>
        </div>
      </div>

      {actionMessage ? (
        <p aria-live="polite" className="mt-4 rounded-[18px] border border-state-success-border bg-state-success-surface px-4 py-3 text-sm font-bold text-state-success">
          {actionMessage}
        </p>
      ) : null}
      {actionError ? (
        <InlineError className="mt-4">{actionError}</InlineError>
      ) : null}

      {candidateOpen ? (
        <div className="mt-5 rounded-[22px] border border-brand-soft-border bg-surface-warm p-4">
          <div className="flex items-start justify-between gap-3">
            <div>
              <p className="text-sm font-black text-text-strong">현재 World에 연결</p>
              <p className="mt-1 text-xs font-medium leading-5 text-text-secondary">
                연결만으로 provider 호출이나 공개 글·관계 변화는 생기지 않습니다.
              </p>
            </div>
            <IconButton label="연결 패널 닫기" onClick={() => setCandidateOpen(false)}>
              <X className="size-5" />
            </IconButton>
          </div>
          {candidateLoading ? (
            <p className="mt-4 flex items-center gap-2 text-sm font-bold text-text-secondary">
              <Loader2 className="size-4 animate-spin" /> 내 캐릭터를 확인하는 중입니다.
            </p>
          ) : candidateError ? (
            <InlineError className="mt-4">{candidateError}</InlineError>
          ) : (
            <div className="mt-4 grid gap-4 md:grid-cols-2">
              <Field label="내 캐릭터">
                {(fieldProps) => (
                  <Select
                    {...fieldProps}
                    value={selectedCharacterId}
                    onChange={(event) => setSelectedCharacterId(event.target.value)}
                  >
                    <option value="">선택해 주세요</option>
                    {eligibleCandidates.map((candidate) => (
                      <option key={candidate.character_id} value={candidate.character_id}>
                        {candidate.display_name}
                        {candidate.handle ? ` (@${candidate.handle})` : ""}
                      </option>
                    ))}
                  </Select>
                )}
              </Field>
              <Field label="World 역할">
                {(fieldProps) => (
                  <Select
                    {...fieldProps}
                    value={roleKey}
                    onChange={(event) => setRoleKey(event.target.value)}
                  >
                    {roleOptions.map((role) => (
                      <option key={role.key} value={role.key}>{role.name}</option>
                    ))}
                  </Select>
                )}
              </Field>
            </div>
          )}
          {!candidateLoading && !candidateError && eligibleCandidates.length === 0 ? (
            <p className="mt-4 rounded-2xl bg-surface px-4 py-3 text-xs font-bold text-text-secondary">
              지금 연결할 수 있는 기존 캐릭터가 없습니다. 새 캐릭터를 만들어 주세요.
            </p>
          ) : null}
          {!candidateLoading && candidates.some((candidate) => !candidate.eligible) ? (
            <div className="mt-3 grid gap-1">
              {candidates.filter((candidate) => !candidate.eligible).map((candidate) => (
                <p key={candidate.character_id} className="text-[11px] font-bold text-text-secondary">
                  {candidate.display_name}: {CANDIDATE_REASON_LABELS[candidate.reason_code ?? ""] ?? "연결할 수 없습니다."}
                </p>
              ))}
            </div>
          ) : null}
          <div className="mt-4 flex flex-wrap items-center gap-3">
            <Button
              compact
              variant="strong"
              onClick={() => void handleConnect()}
              disabled={!selectedCharacterId || candidateLoading || actionBusy}
              loading={actionBusy}
              loadingLabel="연결 중"
            >
              <Link2 className="size-4" />
              이 World에 연결
            </Button>
            <Link href={createHref} className="text-xs font-extrabold text-brand-accent underline underline-offset-4">
              새 캐릭터가 필요해요
            </Link>
          </div>
        </div>
      ) : null}

      {loading ? (
        <p className="mt-5 flex items-center gap-2 text-sm font-bold text-text-secondary">
          <Loader2 className="size-4 animate-spin" /> 캐릭터를 확인하는 중입니다.
        </p>
      ) : error ? (
        <InlineError className="mt-5">{error}</InlineError>
      ) : items.length === 0 ? (
        <p className="mt-5 rounded-[18px] bg-surface-muted px-4 py-3 text-sm font-bold text-text-default">
          아직 이 World에 연결된 캐릭터가 없습니다. 새 캐릭터를 만들거나 기존 내 캐릭터를 연결해 활동 준비를 시작하세요.
        </p>
      ) : (
        <div className="mt-5 grid gap-3">
          {items.map((item) => (
            <article key={item.world_character_id} className="rounded-[22px] border border-border-default bg-surface-subtle p-4">
              <div className="flex flex-wrap items-start justify-between gap-4">
                <div className="flex min-w-0 gap-3">
                  <span className="flex size-11 shrink-0 items-center justify-center rounded-2xl bg-surface-muted text-text-secondary">
                    <UserRound className="size-5" />
                  </span>
                  <div className="min-w-0">
                    <p className="truncate text-base font-black text-text-strong">{item.display_name}</p>
                    <p className="mt-1 line-clamp-2 text-xs font-medium leading-5 text-text-secondary">
                      {item.intro || "소개가 아직 없습니다."}
                    </p>
                  </div>
                </div>
                <div className="flex flex-wrap gap-2">
                  {item.control_mode === "autonomous" ? (
                    <>
                      <Link
                        href={`/characters/${encodeURIComponent(item.character_id)}/worlds/${encodeURIComponent(worldId)}/autonomy-setup`}
                        className="inline-flex min-h-11 items-center rounded-full bg-action-dark px-4 py-2 text-xs font-extrabold text-on-action-dark"
                      >
                        활동 준비·상태 보기
                      </Link>
                      <Button
                        compact
                        variant="danger"
                        onClick={() => beginRemove(item)}
                      >
                        <Trash2 className="size-3.5" /> 이 World에서 제거
                      </Button>
                    </>
                  ) : (
                    <Button compact variant="strong" onClick={openOwnerProfile}>
                      프로필 보기
                    </Button>
                  )}
                </div>
              </div>
              <div className="mt-3 flex flex-wrap gap-2 text-[11px] font-extrabold">
                <StatusChip
                  label={item.control_mode === "autonomous" ? "자율 Character" : "내 조종 Character"}
                  tone={item.control_mode === "autonomous" ? "running" : "neutral"}
                />
                <StatusChip label={SETUP_LABELS[item.activity_setup_state]} tone={item.activity_setup_state === "approved" ? "healthy" : "waiting"} />
                <StatusChip label={`자율활동 ${item.autonomous_enabled ? "ON" : "OFF"}`} tone={item.autonomous_enabled ? "running" : "disabled"} />
                <StatusChip label={worldCharacterStatusLabel(item.status)} tone={item.status === "active" ? "healthy" : "neutral"} />
              </div>
            </article>
          ))}
        </div>
      )}

      <p className="mt-5 text-xs font-medium leading-5 text-text-secondary">
        캐릭터 자체 삭제는 여러 World와 채팅·활동 데이터에 더 큰 영향을 줄 수 있습니다. 전역 삭제는{" "}
        <Link href="/agents" className="font-extrabold text-text-strong underline underline-offset-4">내 앵무 관리</Link>
        에서 이름을 다시 확인한 뒤 수행합니다.
      </p>

      <Dialog
        open={Boolean(removeTarget)}
        onOpenChange={(open) => {
          if (!open && !actionBusy) setRemoveTarget(null);
        }}
        title="이 World에서 제거"
        description="이 World에서 새 자율활동은 중지되지만 이미 작성한 글과 확인된 사건·관계 근거는 보존됩니다. 캐릭터 자체와 다른 World의 참여는 삭제되지 않습니다."
        closeButtonAttributes={{ disabled: actionBusy }}
        actions={
          <>
            <Button variant="secondary" disabled={actionBusy} onClick={() => setRemoveTarget(null)}>
              취소
            </Button>
            <Button
              variant="danger"
              disabled={!removeTarget || confirmationName !== removeTarget.confirmation_name}
              loading={actionBusy}
              loadingLabel="제거 중"
              onClick={() => void handleRemove()}
            >
              <Trash2 className="size-4" />
              자율활동 정지 후 제거
            </Button>
          </>
        }
      >
        {removeTarget ? (
          <Field
            label={`확인을 위해 ${removeTarget.confirmation_name} 입력`}
            required
          >
            {(fieldProps) => (
              <input
                {...fieldProps}
                value={confirmationName}
                onChange={(event) => setConfirmationName(event.target.value)}
                autoComplete="off"
                className="min-h-11 w-full rounded-field border border-border-interactive bg-surface px-4 py-3 text-sm font-bold text-text-strong focus-visible:shadow-[var(--focus-ring)] focus-visible:outline-none"
              />
            )}
          </Field>
        ) : null}
      </Dialog>
    </section>
  );
}

function worldCharacterStatusLabel(status: string) {
  const labels: Record<string, string> = {
    active: "참여 중",
    inactive: "비활성",
    left: "참여 종료",
    pending: "연결 준비 중",
  };
  return labels[status] ?? "상태 확인 필요";
}
