import {
  RuntimeFetchError,
  runtimeFetch,
} from "@/shared/runtime/public";
import type { RelationshipGraphRead } from "@/features/relationships/model/relationship-graph";

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
) {
  const path = `/characters/${encodeURIComponent(characterId)}/worlds/${encodeURIComponent(worldId)}/relationship-graph?view=neighborhood&depth=${depth}&limit=20&provider=${provider}`;
  let response: Response;
  try {
    response = await runtimeFetch(`/api/backend${path}`, {
      cache: "no-store",
      credentials: "same-origin",
      headers: { Accept: "application/json" },
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
  return payload as RelationshipGraphRead;
}
