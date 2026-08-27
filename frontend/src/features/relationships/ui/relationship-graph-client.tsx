"use client";

import Link from "next/link";
import {
  useRuntimeRouter as useRouter,
  worldPostDetailRoute,
} from "@/shared/navigation/public";
import { useEffect, useMemo, useState } from "react";

import { useAuth } from "@/components/auth-provider";
import {
  getRelationshipGraph,
} from "@/features/relationships/api/relationship-graph";
import {
  relationshipGraphPresentationState,
  type RelationshipGraphRead,
} from "@/features/relationships/model/relationship-graph";

const STATUS_LABELS: Record<string, string> = {
  disabled: "관계망 기능 꺼짐 · Canonical DB 직접 관계 표시",
  healthy: "관계망 최신 상태",
  lagging: "새 사건을 관계망에 반영하는 중",
  rebuilding: "관계망을 다시 구성하는 중 · 직접 관계만 표시",
  unavailable: "관계망 일시 사용 불가 · 직접 관계만 표시",
  timeout: "관계망 조회 시간 초과 · 직접 관계만 표시",
  misconfigured: "관계망 설정 확인 필요 · 직접 관계만 표시",
};

const ERROR_LABELS: Record<string, string> = {
  runtime_not_ready: "로컬 엔진이 아직 준비되지 않았습니다. 잠시 후 다시 시도해주세요.",
  runtime_interrupted: "로컬 엔진 연결이 중단되었습니다. 설정에서 runtime 상태를 확인해주세요.",
  launcher_token_invalid: "설치형 앱의 실행 인증이 만료되었습니다. Angmoo를 다시 실행해주세요.",
  graph_projection_rebuilding: "관계망을 다시 구성하고 있습니다. Canonical DB의 직접 관계는 보존됩니다.",
  graph_provider_unavailable: "LadybugDB 관계망을 지금 사용할 수 없습니다. 복구 후 다시 시도해주세요.",
  relationship_query_failed: "관계망 조회를 완료하지 못했습니다. 데이터는 변경되지 않았습니다.",
};

function position(index: number, count: number) {
  if (index === 0) return { x: 240, y: 170 };
  const outerCount = Math.max(1, count - 1);
  const angle = ((index - 1) / outerCount) * Math.PI * 2 - Math.PI / 2;
  return { x: 240 + Math.cos(angle) * 145, y: 170 + Math.sin(angle) * 120 };
}

export function RelationshipGraphClient({
  characterId,
  worldId,
  provider = "ladybug",
}: {
  characterId: string;
  worldId: string;
  provider?: "ladybug";
}) {
  const router = useRouter();
  const { status } = useAuth();
  const [depth, setDepth] = useState<1 | 2>(1);
  const [graph, setGraph] = useState<RelationshipGraphRead | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (status === "unauthenticated") {
      const returnTo = `/characters/${characterId}/worlds/${worldId}/relationship-graph`;
      router.replace(`/login?returnTo=${encodeURIComponent(returnTo)}`);
      return;
    }
    if (status !== "authenticated") return;
    let active = true;
    void getRelationshipGraph(characterId, worldId, depth, provider)
      .then((result) => {
        if (active) setGraph(result);
      })
      .catch((nextError) => {
        if (active) {
          const code = nextError instanceof Error ? nextError.message : "relationship_query_failed";
          setError(ERROR_LABELS[code] ?? code);
        }
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [characterId, depth, provider, router, status, worldId]);

  const orderedNodes = useMemo(() => {
    if (!graph) return [];
    return [...graph.nodes].sort((left, right) => {
      if (left.is_center) return -1;
      if (right.is_center) return 1;
      return left.world_character_id.localeCompare(right.world_character_id);
    });
  }, [graph]);
  const positions = useMemo(
    () => new Map(orderedNodes.map((node, index) => [node.world_character_id, position(index, orderedNodes.length)])),
    [orderedNodes],
  );
  const presentationState = relationshipGraphPresentationState({
    graph,
    loading,
    error,
  });

  return (
    <main className="mx-auto w-full max-w-5xl space-y-6 px-4 py-8 sm:px-6">
      <header className="rounded-[28px] bg-surface-container-lowest p-6 shadow-sm">
        <p className="text-sm font-bold text-primary">P7 · RELATIONSHIP GRAPH</p>
        <h1 className="mt-2 text-3xl font-black">World 관계망</h1>
        <p className="mt-3 max-w-3xl text-sm text-on-surface-variant">
          실제 SNS 쓰기에 성공한 사건만 관계 근거로 사용합니다. 화살표는 보는 방향을 뜻하며,
          반대 방향은 별도의 관계입니다.
        </p>
        {provider === "ladybug" ? (
          <p className="mt-3 rounded-2xl bg-tertiary-container px-4 py-3 text-sm font-bold text-on-tertiary-container">
            설치형 Angmoo의 canonical 관계망 provider는 LadybugDB입니다.
          </p>
        ) : null}
        <div className="mt-5 flex flex-wrap items-center gap-3">
          <Link
            href={`/characters/${characterId}/worlds/${worldId}/autonomy-setup`}
            className="rounded-full border border-outline-variant px-4 py-2 text-sm font-bold"
          >
            활동 준비로 돌아가기
          </Link>
          <button
            type="button"
            onClick={() => {
              setLoading(true);
              setError(null);
              setDepth((value) => (value === 1 ? 2 : 1));
            }}
            className="rounded-full bg-primary px-4 py-2 text-sm font-bold text-on-primary"
          >
            {depth === 1 ? "2단계까지 보기" : "직접 관계만 보기"}
          </button>
        </div>
      </header>

      {presentationState === "loading" ? (
        <p data-relationship-graph-state="loading" className="rounded-3xl bg-surface-container p-5">
          관계 근거를 확인하는 중입니다.
        </p>
      ) : null}
      {presentationState === "failed" ? (
        <p data-relationship-graph-state="failed" role="alert" className="rounded-3xl bg-error-container p-5 text-on-error-container">
          {error}
        </p>
      ) : null}

      {presentationState === "rebuilding" ? (
        <p data-relationship-graph-state="rebuilding" role="status" className="rounded-3xl bg-tertiary-container p-5 text-on-tertiary-container">
          LadybugDB 관계망을 다시 구성하고 있습니다. 그동안 Canonical DB의 직접 관계와 근거 요약만 안전하게 표시합니다.
        </p>
      ) : null}

      {presentationState === "degraded" ? (
        <p data-relationship-graph-state="degraded" role="status" className="rounded-3xl bg-tertiary-container p-5 text-on-tertiary-container">
          관계망 projection을 사용할 수 없어 Canonical DB의 직접 관계만 표시합니다.
          {graph?.meta.fallback_reason ? ` 사유: ${graph.meta.fallback_reason}` : ""}
        </p>
      ) : null}

      {presentationState === "empty" ? (
        <p data-relationship-graph-state="empty" role="status" className="rounded-3xl bg-surface-container p-5">
          아직 관찰에 성공한 방향 관계와 사건 근거가 없습니다.
        </p>
      ) : null}

      {graph ? (
        <>
          <section className="rounded-[28px] bg-surface-container-lowest p-6 shadow-sm">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <h2 className="text-xl font-black">방향 관계 지도</h2>
                <p className="mt-1 text-sm text-on-surface-variant">
                  {STATUS_LABELS[graph.meta.graph_status] ?? graph.meta.graph_status}
                </p>
              </div>
              <span className="rounded-full bg-surface-container px-3 py-2 text-xs font-bold">
                {graph.meta.source === "ladybug"
                    ? "LadybugDB 검증 결과"
                    : "Canonical DB 안전 대체"}
              </span>
            </div>

            <div className="mt-6 overflow-x-auto" aria-hidden="true">
              <svg viewBox="0 0 480 340" className="min-w-[480px]" role="img" aria-label="방향 관계 그래프">
                <defs>
                  <marker id="arrow" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto">
                    <path d="M0,0 L8,4 L0,8 z" className="fill-primary" />
                  </marker>
                </defs>
                {graph.edges.map((edge) => {
                  const start = positions.get(edge.actor_world_character_id);
                  const end = positions.get(edge.target_world_character_id);
                  if (!start || !end) return null;
                  return (
                    <line
                      key={edge.relationship_state_id}
                      x1={start.x}
                      y1={start.y}
                      x2={end.x}
                      y2={end.y}
                      className="stroke-primary"
                      strokeWidth="2"
                      markerEnd="url(#arrow)"
                    />
                  );
                })}
                {orderedNodes.map((node) => {
                  const point = positions.get(node.world_character_id)!;
                  return (
                    <g key={node.world_character_id}>
                      <circle cx={point.x} cy={point.y} r={node.is_center ? 35 : 29} className={node.is_center ? "fill-primary" : "fill-surface-container-high"} />
                      <text x={point.x} y={point.y + 4} textAnchor="middle" className={node.is_center ? "fill-on-primary text-[12px] font-bold" : "fill-on-surface text-[11px] font-bold"}>
                        {node.display_name.slice(0, 8)}
                      </text>
                    </g>
                  );
                })}
              </svg>
            </div>
            {graph.meta.truncated ? <p className="mt-3 text-xs text-on-surface-variant">표시 상한에 따라 일부 관계만 보입니다.</p> : null}
          </section>

          <section className="rounded-[28px] bg-surface-container-lowest p-6 shadow-sm">
            <h2 className="text-xl font-black">접근 가능한 관계 목록</h2>
            <div className="mt-5 space-y-3">
              {graph.edges.length === 0 ? <p className="text-sm text-on-surface-variant">아직 검증된 직접 관계가 없습니다.</p> : null}
              {graph.edges.map((edge) => {
                const actor = graph.nodes.find((node) => node.world_character_id === edge.actor_world_character_id);
                const target = graph.nodes.find((node) => node.world_character_id === edge.target_world_character_id);
                return (
                  <article key={edge.relationship_state_id} className="rounded-2xl border border-outline-variant p-4">
                    <h3 className="font-black">{actor?.display_name ?? "알 수 없음"} → {target?.display_name ?? "알 수 없음"}</h3>
                    <p className="mt-2 text-sm text-on-surface-variant">
                      친숙 {edge.familiarity} · 호감 {edge.affinity} · 신뢰 {edge.trust} · 긴장 {edge.tension}
                    </p>
                    <p className="mt-1 text-xs text-on-surface-variant">실제 상호작용 {edge.interaction_count}회 · 관계 버전 {edge.relationship_version}</p>
                  </article>
                );
              })}
            </div>
          </section>

          {graph.evidence.length > 0 ? (
            <section className="rounded-[28px] bg-surface-container-lowest p-6 shadow-sm">
              <h2 className="text-xl font-black">최근 검증된 사건 근거</h2>
              <div className="mt-5 space-y-3">
                {graph.evidence.map((event) => (
                  <article key={event.event_id} className="rounded-2xl border border-outline-variant p-4">
                    <p className="font-bold">{event.event_type}</p>
                    <p className="mt-1 text-xs text-on-surface-variant">{new Intl.DateTimeFormat("ko-KR", { dateStyle: "medium", timeStyle: "short" }).format(new Date(event.occurred_at))}</p>
                    {event.root_post_id || event.source_post_id ? (
                      <Link
                        className="mt-2 inline-block text-sm font-bold text-primary underline"
                        href={worldPostDetailRoute(worldId, event.root_post_id ?? event.source_post_id!)}
                      >
                        근거 게시글 보기
                      </Link>
                    ) : null}
                  </article>
                ))}
              </div>
            </section>
          ) : null}
        </>
      ) : null}
    </main>
  );
}
