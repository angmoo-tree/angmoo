export type RelationshipGraphStatus =
  | "disabled"
  | "healthy"
  | "lagging"
  | "rebuilding"
  | "unavailable"
  | "timeout"
  | "misconfigured";

export type RelationshipGraphNode = {
  world_character_id: string;
  character_id: string;
  display_name: string;
  is_center: boolean;
};

export type RelationshipGraphEdge = {
  relationship_state_id: string;
  actor_world_character_id: string;
  target_world_character_id: string;
  familiarity: number;
  affinity: number;
  trust: number;
  tension: number;
  interaction_count: number;
  relationship_version: number;
  last_event_id: string | null;
  last_event_at: string | null;
};

export type RelationshipGraphEvidence = {
  event_id: string;
  event_type: string;
  occurred_at: string;
  actor_world_character_id: string;
  target_world_character_id: string | null;
  root_post_id: string | null;
  source_post_id: string | null;
};

export type RelationshipGraphRead = {
  world_id: string;
  center_world_character_id: string;
  nodes: RelationshipGraphNode[];
  edges: RelationshipGraphEdge[];
  evidence: RelationshipGraphEvidence[];
  meta: {
    template: string;
    source: "ladybug" | "canonical_fallback";
    graph_status: RelationshipGraphStatus;
    truncated: boolean;
    projection_lag_seconds: number | null;
    revalidated_node_count: number;
    revalidated_edge_count: number;
    fallback_reason: string | null;
  };
};

export type RelationshipGraphPresentationState =
  | "loading"
  | "empty"
  | "ready"
  | "rebuilding"
  | "degraded"
  | "unavailable"
  | "failed";

const UNAVAILABLE_GRAPH_STATUSES = new Set<RelationshipGraphStatus>([
  "disabled",
  "unavailable",
  "timeout",
  "misconfigured",
]);

export function relationshipGraphPresentationState({
  graph,
  loading,
  error,
}: {
  graph: RelationshipGraphRead | null;
  loading: boolean;
  error: string | null;
}): RelationshipGraphPresentationState {
  if (loading) return "loading";
  if (error) return "failed";
  if (!graph) return "failed";
  if (graph.meta.graph_status === "rebuilding") return "rebuilding";
  if (graph.meta.source === "canonical_fallback") return "degraded";
  if (graph.meta.graph_status === "lagging") return "degraded";
  if (UNAVAILABLE_GRAPH_STATUSES.has(graph.meta.graph_status)) {
    return "unavailable";
  }
  if (graph.edges.length === 0 && graph.evidence.length === 0) return "empty";
  return "ready";
}
