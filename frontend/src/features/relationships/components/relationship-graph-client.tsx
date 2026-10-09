"use client";
import { SettingsCard } from "@/components/ui/settings-card";
import { Network, GitBranch, List, FileSearch } from "lucide-react";
import { relationshipGraphLayout } from "../utils/graph-layout";
import { useId } from "react";
import { useUiDateFormatter } from "@/hooks/use-ui-date-formatter";

import { useUiText } from "@/hooks/use-ui-text";

import { RelationshipReviewPanel } from "./relationship-review-panel";
import { relationshipGraphPresentationState } from "@/features/relationships/utils/relationship-graph";

import Link from "next/link";
import { useRuntimeRouter as useRouter } from "@/hooks/use-runtime-navigation";
import { worldPostDetailRoute } from "@/lib/navigation/product-routes";
import { useEffect, useMemo, useRef, useState } from "react";
import { captureAuthRequestScope, isCurrentAuthRequestScope } from "@/lib/auth/browser-session";
import { DESKTOP_RUNTIME_CONFIG_CHANGED_EVENT } from "@/lib/runtime/runtime-config";
import { RelationshipGraphNode } from "./relationship-graph-node";

import { useAuth } from "@/hooks/use-auth";
import {
  getRelationshipGraph,
} from "@/features/relationships/api/relationship-graph";
import {
  type RelationshipGraphRead,
  type RelationshipGraphStatus,
} from "@/features/relationships/types/relationship-graph";
import { Button } from "@/components/ui/button";
import { DegradedPanel, EmptyState, InlineError } from "@/components/ui/feedback";
import { StatusChip, type StatusChipTone } from "@/components/ui/status";
import styles from "./relationship-graph-client.module.css";

const STATUS_PRESENTATION: Record<
  RelationshipGraphStatus,
  { label: string; tone: StatusChipTone }
> = {
  disabled: { label: "관계망 기능 꺼짐", tone: "disabled" },
  healthy: { label: "관계망 최신 상태", tone: "healthy" },
  lagging: { label: "새 사건 반영 지연", tone: "waiting" },
  rebuilding: { label: "관계망 다시 구성 중", tone: "waiting" },
  unavailable: { label: "관계망 일시 사용 불가", tone: "degraded" },
  timeout: { label: "관계망 조회 시간 초과", tone: "danger" },
  misconfigured: { label: "관계망 설정 확인 필요", tone: "danger" },
};

const ERROR_LABELS: Record<string, string> = {
  runtime_not_ready: "로컬 엔진이 아직 준비되지 않았습니다. 잠시 후 다시 시도해주세요.",
  runtime_interrupted: "로컬 엔진 연결이 중단되었습니다. 설정에서 runtime 상태를 확인해주세요.",
  launcher_token_invalid: "설치형 앱의 실행 인증이 만료되었습니다. Angmoo를 다시 실행해주세요.",
  graph_projection_rebuilding: "관계망을 다시 구성하고 있습니다. Canonical DB의 직접 관계는 보존됩니다.",
  graph_provider_unavailable: "LadybugDB 관계망을 지금 사용할 수 없습니다. 복구 후 다시 시도해주세요.",
  relationship_query_failed: "관계망 조회를 완료하지 못했습니다. 데이터는 변경되지 않았습니다.",
};

const FALLBACK_LABELS: Record<string, string> = {
  graph_disabled: "관계망 기능 꺼짐",
  graph_rebuilding: "관계망 다시 구성 중",
  graph_rebuild_failed: "관계망 복구 확인 필요",
  ladybug_query_timeout: "관계망 조회 시간 초과",
  schema_not_ready: "관계망 설정 확인 필요",
};

export function RelationshipGraphClient({
  characterId,
  worldId,
  provider = "ladybug",
  embedded = false,
}: {
  characterId: string;
  worldId: string;
  provider?: "ladybug";
  embedded?: boolean;
}) {
  const formatDate = useUiDateFormatter();
  const uiText = useUiText("relationships");
  const router = useRouter();
  const { status, user, sessionRevision } = useAuth();
  const [depth, setDepth] = useState<1 | 2>(1);
  const [storedGraph, setGraph] = useState<RelationshipGraphRead | null>(null);
  const [loadedIdentity, setLoadedIdentity] = useState<string | null>(null);
  const identity = JSON.stringify([characterId, worldId, user?.id ?? null, sessionRevision]);
  const graph = loadedIdentity === identity && status === "authenticated" ? storedGraph : null;
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [requestVersion, setRequestVersion] = useState(0);

  useEffect(() => {
    const changed = () => { setGraph(null); setLoading(true); setRequestVersion((value) => value + 1); };
    window.addEventListener(DESKTOP_RUNTIME_CONFIG_CHANGED_EVENT, changed);
    return () => window.removeEventListener(DESKTOP_RUNTIME_CONFIG_CHANGED_EVENT, changed);
  }, []);

  useEffect(() => {
    if (status === "unauthenticated") {
      const returnTo = `/characters/${characterId}/worlds/${worldId}/relationship-graph`;
      router.replace(`/login?returnTo=${encodeURIComponent(returnTo)}`);
      return;
    }
    if (status !== "authenticated") return;
    let active = true;
    const scope = captureAuthRequestScope();
    const controller = new AbortController();
    queueMicrotask(() => { if (active) { setGraph(null); setLoading(true); } });
    void getRelationshipGraph(characterId, worldId, depth, provider, { signal: controller.signal })
      .then((result) => {
        if (active && !controller.signal.aborted && isCurrentAuthRequestScope(scope)) {
          setGraph(result);
          setLoadedIdentity(JSON.stringify([characterId, worldId, scope.userId, sessionRevision]));
          setError(null);
        }
      })
      .catch((nextError) => {
        if (active && !controller.signal.aborted && isCurrentAuthRequestScope(scope)) {
          const code = nextError instanceof Error ? nextError.message : "relationship_query_failed";
          const responseStatus = nextError && typeof nextError === "object" && "status" in nextError ? nextError.status : null;
          setError(responseStatus === 403 || responseStatus === 404 ? "이 캐릭터의 관계망을 열 수 없습니다. 권한과 World 참여 상태를 확인해주세요." : ERROR_LABELS[code] ?? ERROR_LABELS.relationship_query_failed);
        }
      })
      .finally(() => {
        if (active && !controller.signal.aborted && isCurrentAuthRequestScope(scope)) setLoading(false);
      });
    return () => {
      active = false;
      controller.abort();
    };
  }, [characterId, depth, provider, requestVersion, router, sessionRevision, status, user?.id, worldId]);

  const orderedNodes = useMemo(() => {
    if (!graph) return [];
    return [...graph.nodes].sort((left, right) => {
      if (left.is_center) return -1;
      if (right.is_center) return 1;
      return left.world_character_id.localeCompare(right.world_character_id);
    });
  }, [graph]);
  const layout = useMemo(() => relationshipGraphLayout(orderedNodes), [orderedNodes]);
  const positions = layout.positions;
  const mapViewport = useRef<HTMLDivElement | null>(null);
  useEffect(() => {
    if (!embedded || !graph || !mapViewport.current) return;
    const viewport = mapViewport.current;
    const center = positions.get(graph.center_world_character_id);
    viewport.scrollLeft = Math.max(0, (center?.x ?? layout.width / 2) - viewport.clientWidth / 2);
  }, [embedded, graph, layout.width, positions]);
  const markerId = `relationship-arrow-${useId().replaceAll(":", "")}`;
  const presentationState = relationshipGraphPresentationState({
    graph,
    loading,
    error,
  });
  const showGraph =
    presentationState === "ready" ||
    presentationState === "rebuilding" ||
    presentationState === "degraded";
  const retry = () => {
    setGraph(null);
    setLoading(true);
    setError(null);
    setRequestVersion((value) => value + 1);
  };
  const degradedDescription =
    graph?.meta.source === "canonical_fallback"
      ? uiText("LadybugDB projection 대신 Canonical DB의 직접 관계와 근거만 표시합니다.{{value0}}", {
          value0: graph.meta.fallback_reason ? uiText(" 사유: {{reason}}", {
            reason: uiText(FALLBACK_LABELS[graph.meta.fallback_reason] ?? "관계망 연결 상태 확인 필요"),
          }) : "",
        })
      : uiText("LadybugDB가 새 사건을 아직 모두 반영하지 못했습니다. 표시된 관계는 최신 상태가 아닐 수 있습니다.");
  const rebuildingDescription =
    graph?.meta.source === "canonical_fallback"
      ? uiText("LadybugDB 관계망을 다시 구성하는 동안 Canonical DB의 직접 관계와 근거만 표시합니다.")
      : uiText("LadybugDB 관계망을 다시 구성하고 있습니다. 완료될 때까지 표시된 관계는 최신 상태가 아닐 수 있습니다.");
  const unavailableDescription = graph
    ? uiText("{{value0}} 상태입니다. 안전한 대체 관계 데이터가 없어 그래프를 표시하지 않습니다.", {value0: uiText(STATUS_PRESENTATION[graph.meta.graph_status].label)})
    : uiText("관계망을 지금 조회할 수 없습니다. 잠시 후 다시 시도해주세요.");

  return (
    <div
      className={embedded ? "min-w-0 pb-6" : "mx-auto w-full max-w-7xl space-y-6 px-4 py-8 sm:px-6"}
      data-product-content="relationship-graph"
    >
      {embedded ? <header className={styles.header}>
        <span className={styles.icon}><Network size={20} aria-hidden="true" /></span>
        <div className={styles.identity}><h1>{uiText("이 World의 관계")}</h1><p>{uiText("저장된 경험에서 이어진 관계를 확인해요.")}</p><p>{graph?.nodes.find(node => node.is_center)?.display_name ?? uiText("기준 캐릭터 확인 중")}</p></div>
      </header> : <SettingsCard elevated headingLevel={1} title={uiText("World 관계망")} description={uiText("캐릭터가 상대를 바라보는 방향과 관계 근거를 확인해요.")} icon={<Network size={20} />}>
        {provider === "ladybug" ? <details><summary>{uiText("관계 데이터 정보")}</summary><p>{uiText("설치형 Angmoo의 canonical 관계망 provider는 LadybugDB입니다.")}</p></details> : null}
        <div className="mt-5 flex flex-wrap items-center gap-3">
          <Link
            href={`/characters/${characterId}/worlds/${worldId}/autonomy-setup`}
            className="inline-flex min-h-11 items-center rounded-full border border-outline-variant px-4 py-2 text-sm font-bold focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-action-dark"
          >
            {uiText("활동 준비로 돌아가기")}</Link>

        </div>
      </SettingsCard>}

      <div className={embedded ? styles.body : "space-y-6"}>
      {presentationState === "loading" ? (
        <p data-relationship-graph-state="loading" className="rounded-3xl bg-surface-container p-5">
          {uiText("관계 근거를 확인하는 중입니다.")}</p>
      ) : null}
      {presentationState === "failed" ? (
        <InlineError data-relationship-graph-state="failed">
          <div className="space-y-3">
            <p>{uiText(error ?? "관계망을 지금 조회할 수 없습니다. 잠시 후 다시 시도해주세요.")}</p>
            <Button variant="secondary" onClick={retry}>
              {uiText("다시 시도")}</Button>
          </div>
        </InlineError>
      ) : null}

      {presentationState === "rebuilding" ? (
        <DegradedPanel
          data-relationship-graph-state="rebuilding"
          title={uiText("관계망을 다시 구성하고 있습니다")}
          description={rebuildingDescription}
        />
      ) : null}

      {presentationState === "degraded" ? (
        <DegradedPanel
          data-relationship-graph-state="degraded"
          title={uiText("제한된 관계 데이터입니다")}
          description={degradedDescription}
          action={
            <Button variant="secondary" onClick={retry}>
              {uiText("최신 상태 다시 확인")}</Button>
          }
        />
      ) : null}

      {presentationState === "unavailable" ? (
        <DegradedPanel
          data-relationship-graph-state="unavailable"
          title={uiText("관계망을 사용할 수 없습니다")}
          description={unavailableDescription}
          action={
            <Button variant="secondary" onClick={retry}>
              {uiText("다시 시도")}</Button>
          }
        />
      ) : null}

      {presentationState === "empty" ? (
        <EmptyState
          data-relationship-graph-state="empty"
          title={uiText("아직 관계 근거가 없습니다")}
          description={uiText("관찰에 성공한 방향 관계와 사건 근거가 생기면 이곳에 표시됩니다.")}
          icon={
            graph ? (
              <StatusChip
                label={uiText(STATUS_PRESENTATION[graph.meta.graph_status].label)}
                tone={STATUS_PRESENTATION[graph.meta.graph_status].tone}
              />
            ) : undefined
          }
          action={
            <Button variant="secondary" onClick={retry}>
              {uiText("다시 확인")}</Button>
          }
        />
      ) : null}

      {status === "authenticated" ? <RelationshipReviewPanel key={`${identity}:${requestVersion}`} characterId={characterId} worldId={worldId} revision={requestVersion} authenticated names={Object.fromEntries((graph?.nodes ?? []).map((node) => [node.world_character_id, node.display_name]))} /> : null}

      {graph && showGraph ? (
        <>
          <SettingsCard elevated title={uiText("방향 관계 지도")} description={uiText("화살표는 캐릭터가 상대를 바라보는 방향이에요. 반대 방향은 별도의 관계예요.")} icon={<GitBranch size={20} />}>
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <StatusChip
                  className="mt-2"
                  data-relationship-graph-state={
                    presentationState === "ready" ? "ready" : undefined
                  }
                  label={uiText(STATUS_PRESENTATION[graph.meta.graph_status].label)}
                  tone={STATUS_PRESENTATION[graph.meta.graph_status].tone}
                />
              </div>
              <StatusChip
                label={
                  graph.meta.source === "ladybug"
                    ? uiText("LadybugDB 검증 결과")
                    : uiText("Canonical DB 안전 대체")
                }
                tone={graph.meta.source === "ladybug" ? "healthy" : "degraded"}
              />
            </div>

          <Button
            variant="strong"
            onClick={() => {
              setGraph(null);
              setLoading(true);
              setError(null);
              setDepth((value) => (value === 1 ? 2 : 1));
            }}
          >
            {depth === 1 ? uiText("2단계까지 보기") : uiText("직접 관계만 보기")}
          </Button>
            <div ref={mapViewport} data-relationship-map-viewport className="mt-6 overflow-x-auto" aria-hidden="true">
              <svg viewBox={`0 0 ${layout.width} ${layout.height}`} style={{ minWidth: layout.width, width: "100%" }} aria-hidden="true">
                <defs>
                  <marker id={markerId} markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto">
                    <path d="M0,0 L8,4 L0,8 z" className="fill-state-running" />
                  </marker>
                </defs>
                {graph.edges.map((edge) => {
                  const start = positions.get(edge.actor_world_character_id);
                  const end = positions.get(edge.target_world_character_id);
                  if (!start || !end) return null;
                  const length = Math.hypot(end.x-start.x, end.y-start.y) || 1;
                  const dx = -(end.y-start.y)/length*18;
                  const dy = (end.x-start.x)/length*18;
                  const cx = (start.x+end.x)/2+dx;
                  const cy = (start.y+end.y)/2+dy;
                  const startRadius = orderedNodes.find((node) => node.world_character_id === edge.actor_world_character_id)?.is_center ? 35 : 29;
                  const endRadius = orderedNodes.find((node) => node.world_character_id === edge.target_world_character_id)?.is_center ? 35 : 29;
                  const startDistance = Math.hypot(cx - start.x, cy - start.y) || 1;
                  const endDistance = Math.hypot(cx - end.x, cy - end.y) || 1;
                  const startX = start.x + (cx - start.x) / startDistance * startRadius;
                  const startY = start.y + (cy - start.y) / startDistance * startRadius;
                  const endX = end.x + (cx - end.x) / endDistance * (endRadius + 4);
                  const endY = end.y + (cy - end.y) / endDistance * (endRadius + 4);
                  return (
                    <g key={edge.relationship_state_id}>
                    <path
                      data-relationship-edge={edge.relationship_state_id}
                      data-relationship-from={edge.actor_world_character_id}
                      data-relationship-to={edge.target_world_character_id}
                      d={`M ${startX} ${startY} Q ${cx} ${cy} ${endX} ${endY}`}
                      fill="none"
                      className="stroke-state-running"
                      strokeWidth="2"
                      markerEnd={`url(#${markerId})`}
                    />

                    </g>
                  );
                })}
                {orderedNodes.map((node) => <RelationshipGraphNode key={node.world_character_id} node={node} point={positions.get(node.world_character_id)!} />)}
              </svg>
            </div>
            {graph.meta.truncated ? <p className="mt-3 text-xs text-on-surface-variant">{uiText("표시 상한에 따라 일부 관계만 보입니다.")}</p> : null}
          </SettingsCard>

          <SettingsCard elevated title={uiText("접근 가능한 관계 목록")} description={uiText("방향별 관계 설명과 현재 확인된 근거를 살펴봐요.")} icon={<List size={20} />}>
            <div className="mt-5 space-y-3">
              {graph.edges.length === 0 ? <p className="text-sm text-on-surface-variant">{uiText("아직 검증된 직접 관계가 없습니다.")}</p> : null}
              {graph.edges.map((edge) => {
                const actor = graph.nodes.find((node) => node.world_character_id === edge.actor_world_character_id);
                const target = graph.nodes.find((node) => node.world_character_id === edge.target_world_character_id);
                return (
                  <article key={edge.relationship_state_id} data-relationship-list-item={edge.relationship_state_id} className="min-w-0 rounded-2xl border border-outline-variant p-4 [overflow-wrap:anywhere]">
                    <h3 className="font-black">{actor?.display_name ?? uiText("알 수 없음")} → {target?.display_name ?? uiText("알 수 없음")}</h3>
                    <p className="mt-2 font-semibold">{edge.relationship_label ?? uiText("아직 정리된 관계 유형이 없습니다")}</p>
                    <details className="mt-2">
                      <summary className="cursor-pointer text-sm font-bold">{uiText("상대에 대한 인식 보기")}</summary>
                      <p className="mt-2 whitespace-pre-wrap break-words text-sm">{edge.perception ?? uiText("아직 정리된 인식이 없습니다.")}</p>
                      <p className="mt-2 text-xs text-on-surface-variant">{uiText("인식 변경:")}{edge.view_updated_at ? formatDate(edge.view_updated_at) : uiText("미작성")}</p>
                      <p className="mt-1 text-xs text-on-surface-variant">{uiText("저장 기억 최근 검토:")}{edge.reviewed_at ? formatDate(edge.reviewed_at) : uiText("미검토")}</p>
                    </details>
                    <p className="mt-2 text-sm text-on-surface-variant">
                      {uiText("친숙")}{edge.familiarity} {uiText("· 호감")}{edge.affinity} {uiText("· 신뢰")}{edge.trust} {uiText("· 긴장")}{edge.tension}
                    </p>
                    <p className="mt-1 text-xs text-on-surface-variant">{uiText("실제 상호작용")}{edge.interaction_count}{uiText("회 · 관계 버전")}{edge.relationship_version}</p>
                  </article>
                );
              })}
            </div>
          </SettingsCard>

          {graph.evidence.length > 0 ? (
            <SettingsCard elevated title={uiText("최근 검증된 사건 근거")} description={uiText("관계에 반영된 실제 사건과 원문을 확인해요.")} icon={<FileSearch size={20} />}>
              <div className="mt-5 space-y-3">
                {graph.evidence.map((event) => (
                  <article key={event.event_id} className="rounded-2xl border border-outline-variant p-4">
                    <p className="font-bold">{event.event_type}</p>
                    <p className="mt-1 text-xs text-on-surface-variant">{formatDate(event.occurred_at)}</p>
                    {event.root_post_id || event.source_post_id ? (
                      <Link
                        className="mt-2 inline-block text-sm font-bold text-state-running underline"
                        href={worldPostDetailRoute(worldId, event.root_post_id ?? event.source_post_id!)}
                      >
                        {uiText("근거 게시글 보기")}</Link>
                    ) : null}
                  </article>
                ))}
              </div>
            </SettingsCard>
          ) : null}
        </>
      ) : null}
      </div>
    </div>
  );
}
