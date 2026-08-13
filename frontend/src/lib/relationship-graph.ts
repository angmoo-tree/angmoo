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
    source: "neo4j" | "postgres_fallback";
    graph_status: RelationshipGraphStatus;
    truncated: boolean;
    projection_lag_seconds: number | null;
    revalidated_node_count: number;
    revalidated_edge_count: number;
    fallback_reason: string | null;
  };
};

export class RelationshipGraphApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
    this.name = "RelationshipGraphApiError";
  }
}

export async function getRelationshipGraph(
  characterId: string,
  worldId: string,
  depth: 1 | 2,
) {
  const path = `/characters/${encodeURIComponent(characterId)}/worlds/${encodeURIComponent(worldId)}/relationship-graph?view=neighborhood&depth=${depth}&limit=20`;
  const response = await fetch(`/api/backend${path}`, {
    cache: "no-store",
    credentials: "same-origin",
    headers: { Accept: "application/json" },
  });
  const payload = (await response.json().catch(() => null)) as
    | RelationshipGraphRead
    | { detail?: unknown }
    | null;
  if (!response.ok) {
    const detail = payload && "detail" in payload ? payload.detail : null;
    throw new RelationshipGraphApiError(
      typeof detail === "string" ? detail : `http_${response.status}`,
      response.status,
    );
  }
  return payload as RelationshipGraphRead;
}
