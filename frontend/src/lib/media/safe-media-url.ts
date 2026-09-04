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
    if (
      parsed.origin !== "https://angmoo.invalid" ||
      !parsed.pathname.startsWith("/media/")
    ) {
      return null;
    }
    return resolveRuntimeMediaUrl(
      `${parsed.pathname}${parsed.search}${parsed.hash}`,
    );
  } catch {
    return null;
  }
}
