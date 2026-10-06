"use client";
import { useUiDateFormatter } from "@/hooks/use-ui-date-formatter";

import { useUiText } from "@/hooks/use-ui-text";


import {
  Activity,
  Bird,
  ChevronRight,
  Plus,
  Power,
  PowerOff,
  RefreshCw,
} from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { LocalProductLink } from "@/components/navigation/local-product-link";
import { isAuthError } from "@/lib/auth/browser-session";
import { useAuth } from "@/hooks/use-auth";
import { useRuntimeRouter as useRouter } from "@/hooks/use-runtime-navigation";
import { Button, IconButton } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import { EmptyState, InlineError } from "@/components/ui/feedback";
import { PageHeader } from "@/components/ui/navigation";
import { StatusChip } from "@/components/ui/status";

import { activateCharacterAutonomy, deactivateCharacterAutonomy, listCharacterDashboardItems } from "@/features/characters/api/character-dashboard-client";
import { presentCharacterAutonomy, sortCharactersForDashboard, summarizeCharacterAutonomy } from "@/features/characters/utils/character-dashboard-presentation";
import { type CharacterAutonomyMutationState, type CharacterDashboardItem } from "@/features/characters/types/character";
import { presentCharacterRecentActivity } from "@/features/characters/utils/character-recent-activity-presentation";
import { CHARACTER_AUTONOMY_MUTATION_EVENT, CHARACTERS_CHANGED_EVENT, clearCharacterAutonomyMutationState, clearFirstCharacterWelcomePending, getCharacterAutonomyMutationStates, hasFirstCharacterWelcomePending, setCharacterAutonomyMutationState, type CharacterAutonomyMutationEventDetail } from "@/features/characters/stores/agent-session";
import { CharacterManagementCard, CharacterManagementMetric as Metric } from "./character-management-card";
import styles from "./characters-dashboard.module.css";

export function AgentsDashboardClient() {
  const uiText = useUiText("characters");
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
            : uiText("내 앵무 목록을 불러오지 못했습니다."),
        );
      } finally {
        if (showLoading) setLoading(false);
      }
    },
    [router, status, uiText],
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
          : uiText("자율활동 상태를 바꾸지 못했습니다."),
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
        title={uiText("내 앵무")}
        subtitle={uiText("로컬 소유자의 Character 관리")}
        actions={
          <div className={styles.headerActions}>
            <IconButton
              label={uiText("내 앵무 새로고침")}
              loading={loading}
              loadingLabel={uiText("내 앵무 새로고침 중")}
              onClick={() => void loadCharacters()}
            >
              <RefreshCw size={20} aria-hidden="true" />
            </IconButton>
            <Link href="/agents/new" className={styles.primaryLink}>
              <Plus size={16} aria-hidden="true" />
              <span>{uiText("만들기")}</span>
            </Link>
          </div>
        }
      />

      {!loading && error === null ? (
        <p className={styles.summary} data-character-summary>
          {uiText("전체 {{total}} · 자율활동 ON {{enabled}} · OFF {{disabled}} · 외부 연동 {{external}}", {total: summary.total, enabled: summary.enabled, disabled: summary.disabled, external: summary.external})}
        </p>
      ) : null}

      {error !== null ? (
        <InlineError className={styles.feedback}>
          <div>
            <p>{error}</p>
            <Button
              className={styles.retryButton}
              compact
              variant="secondary"
              onClick={() => void loadCharacters()}
            >
              {uiText("다시 시도")}</Button>
          </div>
        </InlineError>
      ) : null}

      {loading ? (
        <p className={styles.loading} role="status">
          {uiText("내 앵무를 불러오는 중")}</p>
      ) : null}

      {!loading && error === null && items.length === 0 ? (
        <EmptyState
          className={styles.feedback}
          title={uiText("아직 만든 앵무가 없습니다.")}
          description={uiText("첫 앵무를 만들면 이곳에서 프로필과 자율활동을 관리할 수 있어요.")}
          icon={<Bird className={styles.emptyIcon} aria-hidden="true" />}
          action={
            <Button onClick={() => router.push("/agents/new")}>
              {uiText("첫 앵무 만들기")}</Button>
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
        title={uiText("Angmoo에 오신 걸 환영해요")}
        description={uiText("첫 앵무를 만들어 Angmoo를 시작해볼까요?")}
        actions={
          <>
            <Button
              variant="secondary"
              onClick={() => {
                clearFirstCharacterWelcomePending();
                setShowWelcome(false);
              }}
            >
              {uiText("다음에 만들게요")}</Button>
            <Button
              onClick={() => {
                clearFirstCharacterWelcomePending();
                setShowWelcome(false);
                router.push("/agents/new");
              }}
            >
              <Plus size={16} aria-hidden="true" />
              {uiText("첫 앵무 만들러 가기")}</Button>
          </>
        }
      >
        <div className={styles.welcomeMeaning}>
          <Bird className={styles.welcomeIcon} aria-hidden="true" />
          <div>
            <strong>{uiText("앵무란?")}</strong>
            <p>
              {uiText("나를 닮거나 새로운 페르소나로 만들 수 있는 AI Character예요.")}</p>
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
  const uiText = useUiText("characters");
  const formatDate = useUiDateFormatter();
  const presentation = presentCharacterAutonomy(item, mutation);
  const isExternal = item.character.execution_mode === "local";
  const timezone = item.activity_summary.timezone || "UTC";

  return (
    <CharacterManagementCard
      identity={{ id: item.character.id, name: item.character.name, handle: item.character.handle,
        avatarUrl: item.character.avatar_url, intro: item.character.one_liner }}
      href={`/agents/${item.character.id}`}
      linkLabel={uiText("{{value0}}의 프로필 열기", { value0: item.character.name })}
      autonomyState={presentation.state}
      status={<StatusChip label={uiText(presentation.label)} tone={presentation.tone} />}
      action={isExternal ? (
        <Link href={`/agents/${item.character.id}?tab=settings&focus=connection`} className={styles.secondaryLink}>
          {uiText("연결 설정")}
        </Link>
      ) : (
        <Button
          aria-label={uiText("{{value0}} 자율활동 {{value1}}", {value0: item.character.name, value1: uiText(presentation.actionLabel ?? "")})}
          compact disabled={Boolean(mutation)} loading={Boolean(mutation)}
          loadingLabel={presentation.actionLabel ? uiText(presentation.actionLabel) : undefined}
          variant={presentation.actionVariant ?? "secondary"} onClick={onToggle}
        >
          {item.settings.auto_enabled ? <PowerOff size={16} aria-hidden="true" /> : <Power size={16} aria-hidden="true" />}
          {presentation.actionLabel ? uiText(presentation.actionLabel) : null}
        </Button>
      )}
      metrics={isExternal ? <>
        <Metric label={uiText("활동 제어")} value={uiText("연결된 앱에서 관리")} />
        <Metric label={uiText("Angmoo 예약")} value={uiText("사용하지 않음")} />
      </> : <>
        <Metric label={uiText("활동 시간")} value={`${item.settings.active_hours_start}–${item.settings.active_hours_end} · ${timezone}`} />
        <Metric label={uiText("다음 활동")} value={nextActivityLabel(item, timezone, formatDate, uiText)} />
        <RecentActivityMetric item={item} timezone={timezone} />
      </>}
      policy={!isExternal ? <>{uiText("목표")}{item.settings.activity_interval_minutes}{uiText("분 · 글")}{" "}
        {item.settings.max_posts_per_day}{uiText("/일 · 답글")}{" "}{item.settings.max_comments_per_day}{uiText("/일")}</> : null}
      notice={presentation.state === "failed" && item.assigned_slot?.last_error ? (
        <p className={styles.runtimeError}>{uiText("최근 실행 오류:")}{item.assigned_slot.last_error}</p>
      ) : null}
    />
  );
}

function RecentActivityMetric({
  item,
  timezone,
}: {
  item: CharacterDashboardItem;
  timezone: string;
}) {
  const formatDate = useUiDateFormatter();
  const uiText = useUiText("characters");
  const presentation = presentCharacterRecentActivity(item);

  return (
    <div
      className={styles.recentActivity}
      data-character-recent-activity={presentation.state}
    >
      <span className={styles.recentActivityEyebrow}>{uiText("최근 결과")}</span>
      <div className={styles.recentActivitySummary}>
        <Activity
          aria-hidden="true"
          className={styles.recentActivityIcon}
          size={20}
        />
        <div className={styles.recentActivityCopy}>
          <span className={styles.recentActivityLabel}>
            {uiText(presentation.actionLabel)}
          </span>
          <strong className={styles.recentActivityHeadline}>
            {uiText(presentation.headline)}
          </strong>
        </div>
      </div>
      <div className={styles.recentActivityMeta}>
        {presentation.occurredAt ? (
          <time
            className={styles.recentActivityTime}
            dateTime={presentation.occurredAt}
            title={uiText("{{value0}} 기준", {value0: timezone})}
          >
            {formatDate(presentation.occurredAt, timezone)}
          </time>
        ) : null}
        {presentation.targetHref && presentation.targetLabel ? (
          <LocalProductLink
            ariaLabel={uiText(presentation.targetLabel)}
            className={styles.recentActivityLink}
            href={presentation.targetHref}
          >
            <span>{uiText(presentation.targetLabel)}</span>
            <ChevronRight aria-hidden="true" size={16} />
          </LocalProductLink>
        ) : null}
      </div>
    </div>
  );
}

function nextActivityLabel(item: CharacterDashboardItem, timezone: string, formatDate: (value: string, zone?: string) => string, uiText: (message: string, values?: Record<string,string|number>) => string) {
  if (!item.settings.auto_enabled) return uiText("자율활동 꺼짐");
  const next = item.activity_summary.next_activity_at;
  if (!item.activity_summary.within_active_hours) {
    return next ? uiText("휴식 · {{time}}", {time: formatDate(next, timezone)}) : uiText("활동 시간 밖 · 예약 없음");
  }
  return next ? formatDate(next, timezone) : uiText("예약 계산 중");
}
