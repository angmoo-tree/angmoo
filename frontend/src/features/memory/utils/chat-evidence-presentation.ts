import type { WorldChatEvidenceItemRead, WorldChatEvidenceRead } from "../types/memory-contract";

const readCodes = ["historical_unverified", "current_unavailable", "read_unavailable"];
const degradedReasons = ["canonical_unavailable", "graph_unavailable", "retrieval_timeout", "no_accepted_evidence"];

export function relationshipFieldsMatch(item: WorldChatEvidenceItemRead) {
  const change = item.relationship_change;
  const projection = item.relationship_projection;
  if (change !== undefined && change !== null && !["same", "changed", "not_checked"].includes(change)) return false;
  if (item.kind !== "graph_relationship") return change == null && projection == null;
  if (item.availability !== "available") return change == null && projection == null && item.excerpt === null &&
    item.related_character === null && item.direction === null && item.canonical_href === null && item.episode == null;
  if (projection != null) {
    if (typeof projection !== "object" || Array.isArray(projection) || change == null) return false;
    const keys = ["familiarity", "affinity", "trust", "tension", "interactions", "relationship_label", "perception"];
    if (Object.keys(projection).length !== keys.length || keys.some((key) => !(key in projection))) return false;
    for (const [key, lower, upper] of [["familiarity", 0, 100], ["affinity", -100, 100], ["trust", -100, 100], ["tension", 0, 100], ["interactions", 0, Infinity]] as const) {
      const value = projection[key];
      if (typeof value !== "number" || !Number.isSafeInteger(value) || value < lower || value > upper) return false;
    }
    if ([projection.relationship_label, projection.perception].some((value) => value !== null && (typeof value !== "string" || value.length > 2000))) return false;
  }
  return true;
}

export function evidenceLimitationsMatch(read: WorldChatEvidenceRead) {
  const retrieval = read.retrieval_limitations;
  if (retrieval != null) {
    if (typeof retrieval !== "object" || Array.isArray(retrieval) || Object.keys(retrieval).length !== 2 ||
      !Array.isArray(retrieval.partial_axes) || retrieval.partial_axes.length > 3 ||
      new Set(retrieval.partial_axes).size !== retrieval.partial_axes.length ||
      retrieval.partial_axes.some((axis) => !["canonical", "graph", "image"].includes(axis)) ||
      (retrieval.degraded_reason !== null && !degradedReasons.includes(retrieval.degraded_reason))) return false;
  }
  const current = read.read_limitations;
  return current == null || (Array.isArray(current) && current.length <= 3 && new Set(current).size === current.length &&
    current.every((code) => readCodes.includes(code)));
}

export function evidenceWarnings(read: WorldChatEvidenceRead) {
  const retrieval = read.retrieval_limitations;
  return {
    retrieval: retrieval != null && (retrieval.partial_axes.length > 0 || retrieval.degraded_reason !== null),
    current: (read.read_limitations?.length ?? 0) > 0,
    legacy: read.capability === "degraded" && retrieval == null && read.read_limitations == null,
  };
}

export function relationshipStatus(item: WorldChatEvidenceItemRead, read: WorldChatEvidenceRead) {
  if (item.availability !== "available") return read.read_limitations?.every((code) => code === "historical_unverified") && read.read_limitations.length > 0
    ? "당시 근거 확인 불가" : "현재 표시할 수 없음";
  return { same: "현재도 동일", changed: "이후 변경됨", not_checked: "현재 상태 비교 불가" }[item.relationship_change ?? "not_checked"];
}
