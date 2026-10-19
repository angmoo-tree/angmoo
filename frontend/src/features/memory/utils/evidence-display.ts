import { evidenceDisplayKeys, type WorldChatEvidenceItemRead } from "../types/memory-contract";

export { evidenceDisplayKeys } from "../types/memory-contract";
export type { EvidenceDisplayKey } from "../types/memory-contract";

export const evidenceKindKeys: Record<WorldChatEvidenceItemRead["kind"], string> = {
  canonical_source: "evidenceKind.canonical_source", graph_relationship: "답변 당시 관계",
  graph_event: "evidenceKind.graph_event", today_sns_activity: "evidenceKind.today_sns_activity",
  episode_memory: "evidenceKind.episode_memory", current_image_analysis: "evidenceKind.current_image_analysis",
};

export function displaySegmentsMatch(item: WorldChatEvidenceItemRead) {
  const segments = item.display_segments;
  if (segments == null) return true;
  if (item.kind !== "today_sns_activity" || item.availability !== "available" || !Array.isArray(segments) ||
      segments.length < 1 || segments.length > 128) return false;
  if (!segments.every(s => s && Object.keys(s).length === 2 && typeof s.text === "string" && s.text.length > 0 &&
      Array.from(s.text).length <= 500 && (s.key === null || evidenceDisplayKeys.includes(s.key)))) return false;
  return segments.map(s => s.text).join("") === item.excerpt && Array.from(item.excerpt ?? "").length <= 500;
}
