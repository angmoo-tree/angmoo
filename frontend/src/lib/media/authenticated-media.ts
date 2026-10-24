import { resolveRuntimeMediaUrl, runtimeFetch } from "@/lib/runtime/runtime-config";

export async function fetchAuthenticatedMediaObjectUrl(apiPath: string, signal?: AbortSignal) {
  const normalizedPath = apiPath.startsWith("/api/v1")
    ? apiPath.slice("/api/v1".length)
    : apiPath;
  const path = apiPath.startsWith("/media/worlds/") ? resolveRuntimeMediaUrl(apiPath) : `/api/backend${normalizedPath}`;
  const response = await runtimeFetch(path, {
    cache: "no-store",
    credentials: "same-origin",
    signal,
  });
  if (!response.ok) {
    throw new Error(`Private media request failed with ${response.status}`);
  }
  const blob = await response.blob();
  if (signal?.aborted) throw new DOMException("Aborted", "AbortError");
  return URL.createObjectURL(blob);
}
