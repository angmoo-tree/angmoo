import { runtimeFetch } from "@/lib/runtime/runtime-config";

export async function fetchAuthenticatedMediaObjectUrl(apiPath: string) {
  const normalizedPath = apiPath.startsWith("/api/v1")
    ? apiPath.slice("/api/v1".length)
    : apiPath;
  const response = await runtimeFetch(`/api/backend${normalizedPath}`, {
    cache: "no-store",
    credentials: "same-origin",
  });
  if (!response.ok) {
    throw new Error(`Private media request failed with ${response.status}`);
  }
  return URL.createObjectURL(await response.blob());
}
