/** Three-way merge for JSON settings. Arrays and scalar values are atomic fields. */
export function mergeEditedValue<T>(baseline: T, latest: T, draft: T, path = ""): { value: T; conflicts: string[] } {
  const equal = (a: unknown, b: unknown) => JSON.stringify(a) === JSON.stringify(b);
  if (equal(baseline, draft) || equal(latest, draft)) return { value: latest, conflicts: [] };
  if (equal(baseline, latest)) return { value: draft, conflicts: [] };
  const record = (v: unknown): v is Record<string, unknown> => v !== null && typeof v === "object" && !Array.isArray(v);
  if (!record(baseline) || !record(latest) || !record(draft)) return { value: draft, conflicts: [path] };
  const value: Record<string, unknown> = { ...latest }, conflicts: string[] = [];
  for (const key of new Set([...Object.keys(baseline), ...Object.keys(draft)])) {
    const merged = mergeEditedValue(baseline[key], latest[key], draft[key], path ? `${path}.${key}` : key);
    if (merged.value === undefined) delete value[key]; else value[key] = merged.value;
    conflicts.push(...merged.conflicts);
  }
  return { value: value as T, conflicts };
}
