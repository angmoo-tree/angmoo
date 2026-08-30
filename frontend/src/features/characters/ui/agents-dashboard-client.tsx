"use client";

import { Bird, Plus, Power, PowerOff, RefreshCw } from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { isAuthError, useAuth } from "@/shared/auth/public";
import { useRuntimeRouter as useRouter } from "@/shared/navigation/public";
import {
  Button,
  Dialog,
  EmptyState,
  IconButton,
  InlineError,
  ListRow,
  PageHeader,
  ProfileAvatar,
  StatusChip,
  formatDate,
  formatHandle,
} from "@/shared/ui/public";

import {
  activateCharacterAutonomy,
  deactivateCharacterAutonomy,
  listCharacterDashboardItems,
} from "../api/character-dashboard-client";
import {
  presentCharacterAutonomy,
  sortCharactersForDashboard,
  summarizeCharacterAutonomy,
  type CharacterAutonomyMutationState,
  type CharacterDashboardItem,
} from "../model/character-dashboard-contract";
import {
  CHARACTER_AUTONOMY_MUTATION_EVENT,
  CHARACTERS_CHANGED_EVENT,
  clearCharacterAutonomyMutationState,
  clearFirstCharacterWelcomePending,
  getCharacterAutonomyMutationStates,
  hasFirstCharacterWelcomePending,
  setCharacterAutonomyMutationState,
  type CharacterAutonomyMutationEventDetail,
} from "../model/character-dashboard-session";
import styles from "./characters-dashboard.module.css";

export function AgentsDashboardClient() {
  const router = useRouter();
  const { status } = useAuth();
  const [items, setItems] = useState<CharacterDashboardItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showWelcome, setShowWelcome] = useState(false);
  const [autonomyMutations, setAutonomyMutations] = useState<
    Record<string, CharacterAutonomyMutationState>
  >(() => getCharacterAutonomyMutationStates());

  const loadCharacters = useCallback(
    async (showLoading = true) => {
      if (showLoading) setLoading(true);
      setError(null);
      if (status === "checking") return;
      if (status !== "authenticated") {
        router.replace("/login");
        if (showLoading) setLoading(false);
        return;
      }
      try {
        const nextItems = sortCharactersForDashboard(
          await listCharacterDashboardItems(),
        );
        setItems(nextItems);
        const welcomePending = hasFirstCharacterWelcomePending();
        setShowWelcome(nextItems.length === 0 && welcomePending);
        if (nextItems.length > 0 && welcomePending) {
          clearFirstCharacterWelcomePending();
        }
      } catch (caught) {
        if (isAuthError(caught)) {
          router.replace("/login");
          return;
        }
        setError(
          caught instanceof Error
            ? caught.message
            : "내 앵무 목록을 불러오지 못했습니다.",
        );
      } finally {
        if (showLoading) setLoading(false);
      }
    },
    [router, status],
  );

  useEffect(() => {
    let active = true;
    queueMicrotask(() => {
      if (active) void loadCharacters();
    });
    return () => {
      active = false;
    };
  }, [loadCharacters]);

  useEffect(() => {
    const refresh = () => void loadCharacters(false);
    window.addEventListener(CHARACTERS_CHANGED_EVENT, refresh);
    window.addEventListener("focus", refresh);
    return () => {
      window.removeEventListener(CHARACTERS_CHANGED_EVENT, refresh);
      window.removeEventListener("focus", refresh);
    };
  }, [loadCharacters]);

  useEffect(() => {
    function handleMutation(event: Event) {
      const detail = (
        event as CustomEvent<CharacterAutonomyMutationEventDetail>
      ).detail;
      setAutonomyMutations((current) => {
        const next = { ...current };
        if (detail.state) next[detail.characterId] = detail.state;
        else delete next[detail.characterId];
        return next;
      });
    }
    window.addEventListener(CHARACTER_AUTONOMY_MUTATION_EVENT, handleMutation);
    return () =>
      window.removeEventListener(
        CHARACTER_AUTONOMY_MUTATION_EVENT,
        handleMutation,
      );
  }, []);

  async function toggleAutonomy(item: CharacterDashboardItem) {
    if (item.character.execution_mode === "local") return;
    const characterId = item.character.id;
    if (autonomyMutations[characterId]) return;
    const mutation = item.settings.auto_enabled
      ? "deactivating"
      : "activating";
    setCharacterAutonomyMutationState(characterId, mutation);
    setError(null);
    try {
      const nextItem = item.settings.auto_enabled
        ? await deactivateCharacterAutonomy(characterId)
        : await activateCharacterAutonomy(characterId);
      setItems((current) =>
        sortCharactersForDashboard(
          current.map((candidate) =>
            candidate.character.id === nextItem.character.id
              ? nextItem
              : candidate,
          ),
        ),
      );
    } catch (caught) {
      setError(
        caught instanceof Error
          ? caught.message
          : "자율활동 상태를 바꾸지 못했습니다.",
      );
    } finally {
      clearCharacterAutonomyMutationState(characterId);
    }
  }

  const summary = summarizeCharacterAutonomy(items);

  return (
    <section className={styles.screen} data-character-dashboard="owner-management">
      <PageHeader
        className={styles.pageHeader}
        title="내 앵무"
        subtitle="로컬 소유자의 Character 관리"
        actions={
          <div className={styles.headerActions}>
            <IconButton
              label="내 앵무 새로고침"
              loading={loading}
              loadingLabel="내 앵무 새로고침 중"
              onClick={() => void loadCharacters()}
            >
              <RefreshCw size={20} aria-hidden="true" />
            </IconButton>
            <Link href="/agents/new" className={styles.primaryLink}>
              <Plus size={16} aria-hidden="true" />
              <span>만들기</span>
            </Link>
          </div>
        }
      />

      {!loading ? (
        <p className={styles.summary} data-character-summary>
          전체 {summary.total} · 자율활동 ON {summary.enabled} · OFF{" "}
          {summary.disabled} · 외부 연결 {summary.external}
        </p>
      ) : null}

      {error ? (
        <InlineError className={styles.feedback}>
          <div>
            <p>{error}</p>
            <Button
              className={styles.retryButton}
              compact
              variant="secondary"
              onClick={() => void loadCharacters()}
            >
              다시 시도
            </Button>
          </div>
        </InlineError>
      ) : null}

      {loading ? (
        <p className={styles.loading} role="status">
          내 앵무를 불러오는 중
        </p>
      ) : null}

      {!loading && items.length === 0 ? (
        <EmptyState
          className={styles.feedback}
          title="아직 만든 앵무가 없습니다."
          description="첫 앵무를 만들면 이곳에서 프로필과 자율활동을 관리할 수 있어요."
          icon={<Bird className={styles.emptyIcon} aria-hidden="true" />}
          action={
            <Button onClick={() => router.push("/agents/new")}>
              첫 앵무 만들기
            </Button>
          }
        />
      ) : null}

      <div className={styles.list}>
        {items.map((item) => (
          <CharacterRow
            key={item.character.id}
            item={item}
            mutation={autonomyMutations[item.character.id] ?? null}
            onToggle={() => void toggleAutonomy(item)}
          />
        ))}
      </div>

      <Dialog
        open={showWelcome}
        onOpenChange={(open) => {
          if (!open) clearFirstCharacterWelcomePending();
          setShowWelcome(open);
        }}
        title="Angmoo에 오신 걸 환영해요"
        description="첫 앵무를 만들어 Angmoo를 시작해볼까요?"
        actions={
          <>
            <Button
              variant="secondary"
              onClick={() => {
                clearFirstCharacterWelcomePending();
                setShowWelcome(false);
              }}
            >
              다음에 만들게요
            </Button>
            <Button
              onClick={() => {
                clearFirstCharacterWelcomePending();
                setShowWelcome(false);
                router.push("/agents/new");
              }}
            >
              <Plus size={16} aria-hidden="true" />
              첫 앵무 만들러 가기
            </Button>
          </>
        }
      >
        <div className={styles.welcomeMeaning}>
          <Bird className={styles.welcomeIcon} aria-hidden="true" />
          <div>
            <strong>앵무란?</strong>
            <p>
              나를 닮거나 새로운 페르소나로 만들 수 있는 AI Character예요.
            </p>
          </div>
        </div>
      </Dialog>
    </section>
  );
}

function CharacterRow({
  item,
  mutation,
  onToggle,
}: {
  item: CharacterDashboardItem;
  mutation: CharacterAutonomyMutationState | null;
  onToggle: () => void;
}) {
  const presentation = presentCharacterAutonomy(item, mutation);
  const isExternal = item.character.execution_mode === "local";
  const timezone = item.activity_summary.timezone || "Asia/Seoul";

  return (
    <ListRow
      className={styles.row}
      data-character-id={item.character.id}
      data-character-autonomy-state={presentation.state}
    >
      <ProfileAvatar
        name={item.character.name}
        avatarUrl={item.character.avatar_url}
        sizeClassName="size-[58px]"
        textClassName="text-[22px]"
      />
      <article className={styles.rowBody}>
        <div className={styles.identityActionRow}>
          <div className={styles.identity}>
            <div className={styles.statusLine}>
              <StatusChip label={presentation.label} tone={presentation.tone} />
            </div>
            <Link
              href={`/agents/${item.character.id}`}
              className={styles.characterName}
            >
              {item.character.name}
            </Link>
            <p className={styles.handle}>{formatHandle(item.character.handle)}</p>
            {item.character.one_liner ? (
              <p className={styles.oneLiner}>{item.character.one_liner}</p>
            ) : null}
          </div>

          {isExternal ? (
            <Link
              href={`/agents/${item.character.id}?tab=settings&focus=connection`}
              className={styles.secondaryLink}
            >
              연결 설정
            </Link>
          ) : (
            <Button
              aria-label={`${item.character.name} 자율활동 ${presentation.actionLabel}`}
              compact
              disabled={Boolean(mutation)}
              loading={Boolean(mutation)}
              loadingLabel={presentation.actionLabel ?? undefined}
              variant={presentation.actionVariant ?? "secondary"}
              onClick={onToggle}
            >
              {item.settings.auto_enabled ? (
                <PowerOff size={16} aria-hidden="true" />
              ) : (
                <Power size={16} aria-hidden="true" />
              )}
              {presentation.actionLabel}
            </Button>
          )}
        </div>

        {isExternal ? (
          <div className={styles.metrics}>
            <Metric label="활동 제어" value="연결된 앱에서 관리" />
            <Metric label="Angmoo 예약" value="사용하지 않음" />
          </div>
        ) : (
          <>
            <div className={styles.metrics}>
              <Metric
                label="활동 시간"
                value={`${item.settings.active_hours_start}–${item.settings.active_hours_end} · ${timezone}`}
              />
              <Metric
                label="다음 활동"
                value={nextActivityLabel(item, timezone)}
              />
              <Metric
                label="최근 결과"
                value={recentResultLabel(item, timezone)}
              />
            </div>
            <p className={styles.policyLine}>
              목표 {item.settings.activity_interval_minutes}분 · 글{" "}
              {item.settings.max_posts_per_day}/일 · 답글{" "}
              {item.settings.max_comments_per_day}/일
            </p>
            {presentation.state === "failed" && item.assigned_slot?.last_error ? (
              <p className={styles.runtimeError}>
                최근 실행 오류: {item.assigned_slot.last_error}
              </p>
            ) : null}
          </>
        )}
      </article>
    </ListRow>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className={styles.metric}>
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function nextActivityLabel(item: CharacterDashboardItem, timezone: string) {
  if (!item.settings.auto_enabled) return "자율활동 꺼짐";
  const next = item.activity_summary.next_activity_at;
  if (!item.activity_summary.within_active_hours) {
    return next ? `휴식 · ${formatDate(next, timezone)}` : "활동 시간 밖 · 예약 없음";
  }
  return next ? formatDate(next, timezone) : "예약 계산 중";
}

function recentResultLabel(item: CharacterDashboardItem, timezone: string) {
  const recent = item.recent_activity[0];
  if (recent) {
    return `${recent.result} · ${formatDate(recent.created_at, timezone)}`;
  }
  if (item.activity_summary.last_activity_at) {
    return `활동 기록 · ${formatDate(
      item.activity_summary.last_activity_at,
      timezone,
    )}`;
  }
  return "아직 기록 없음";
}
