import { RuntimeFetchError, runtimeFetch } from "@/lib/runtime/runtime-config";
import type { RelationshipGraphRead, RelationshipReviewRead } from "@/features/relationships/types/relationship-graph";

export class RelationshipGraphApiError extends Error {
  constructor(
    readonly code: string,
    readonly status: number,
  ) {
    super(code);
    this.name = "RelationshipGraphApiError";
  }
}

export async function getRelationshipGraph(
  characterId: string,
  worldId: string,
  depth: 1 | 2,
  provider: "ladybug" = "ladybug",
  options: { signal?: AbortSignal } = {},
) {
  const path = `/characters/${encodeURIComponent(characterId)}/worlds/${encodeURIComponent(worldId)}/relationship-graph?view=neighborhood&depth=${depth}&limit=20&provider=${provider}`;
  let response: Response;
  try {
    response = await runtimeFetch(`/api/backend${path}`, {
      cache: "no-store",
      credentials: "same-origin",
      headers: { Accept: "application/json" },
      signal: options.signal,
    });
  } catch (reason) {
    if (reason instanceof RuntimeFetchError) {
      throw new RelationshipGraphApiError(reason.code, 503);
    }
    throw reason;
  }
  const payload = (await response.json().catch(() => null)) as
    | RelationshipGraphRead
    | { detail?: unknown }
    | null;
  if (!response.ok) {
    const detail = payload && "detail" in payload ? payload.detail : null;
    const rawCode = typeof detail === "string" ? detail : `http_${response.status}`;
    const code = rawCode === "desktop_token_invalid"
      ? "launcher_token_invalid"
      : rawCode.includes("graph_provider") ||
          rawCode.includes("ladybug")
        ? "graph_provider_unavailable"
        : response.status >= 500
          ? "relationship_query_failed"
          : rawCode;
    throw new RelationshipGraphApiError(
      code,
      response.status,
    );
  }
  if (!payload || !("world_id" in payload) || payload.world_id !== worldId
    || !Array.isArray(payload.nodes) || !Array.isArray(payload.edges) || !Array.isArray(payload.evidence)
    || !payload.meta || typeof payload.center_world_character_id !== "string"
    || !["ladybug", "canonical_fallback"].includes(payload.meta.source)
    || !["disabled", "healthy", "lagging", "rebuilding", "unavailable", "timeout", "misconfigured"].includes(payload.meta.graph_status)
    || payload.nodes.some((node) => !node || typeof node.world_character_id !== "string" || typeof node.character_id !== "string"
      || typeof node.display_name !== "string" || typeof node.is_center !== "boolean")
    || new Set(payload.nodes.map((node) => node.world_character_id)).size !== payload.nodes.length
    || (payload.nodes.length > 0 && payload.nodes.filter(node => node.is_center).length !== 1)
    || payload.nodes.some((node) => node.is_center && (node.character_id !== characterId || node.world_character_id !== payload.center_world_character_id))) {
    throw new RelationshipGraphApiError("relationship_query_failed", 502);
  }
  return { ...payload, nodes: payload.nodes.map((node) => ({ ...node, avatar_url: typeof node.avatar_url === "string" ? node.avatar_url : null })) } as RelationshipGraphRead;
}


export async function getRelationshipReview(characterId: string, worldId: string): Promise<RelationshipReviewRead> {
  const response = await runtimeFetch(`/api/backend/characters/${encodeURIComponent(characterId)}/worlds/${encodeURIComponent(worldId)}/relationship-review`, {
    cache: "no-store", credentials: "same-origin", headers: { Accept: "application/json" },
  });
  if (!response.ok) throw new RelationshipGraphApiError("relationship_review_unavailable", response.status);
  return response.json();
}
