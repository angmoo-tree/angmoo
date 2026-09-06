import type { RelationshipGraphStatus, RelationshipGraphRead, RelationshipGraphPresentationState } from "@/features/relationships/types/relationship-graph";

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
