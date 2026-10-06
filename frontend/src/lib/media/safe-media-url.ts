import { resolveRuntimeMediaUrl } from "@/lib/runtime/runtime-config";

export function safeSameOriginMediaUrl(
  value: string | null | undefined,
  options: { allowBlob?: boolean } = {},
) {
  const trimmed = value?.trim();
  if (!trimmed) return null;
  if (options.allowBlob && trimmed.startsWith("blob:")) {
    return trimmed;
  }
  if (!trimmed.startsWith("/") || trimmed.startsWith("//")) {
    return null;
  }
  try {
    const parsed = new URL(trimmed, "https://angmoo.invalid");
    const isAssetContent = /^\/api\/v1\/media\/assets\/[A-Za-z0-9_-]+\/content$/.test(parsed.pathname);
    if (
      parsed.origin !== "https://angmoo.invalid" ||
      (!parsed.pathname.startsWith("/media/") && !isAssetContent)
    ) {
      return null;
    }
    const relative = `${parsed.pathname}${parsed.search}${parsed.hash}`;
    // Keep authenticated asset paths relative until the runtime media owner
    // fetches them with the current session/launch scope and creates its blob.
    return isAssetContent ? relative : resolveRuntimeMediaUrl(relative);
  } catch {
    return null;
  }
}
