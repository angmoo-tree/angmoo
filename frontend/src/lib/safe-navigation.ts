const ALLOWED_RETURN_PATHS = [
  /^\/agents\/[^/?#]+$/,
  /^\/profiles\/characters\/[^/?#]+$/,
  /^\/messages\/[^/?#]+$/,
];

export function safeSettingsReturnTo(value: string | null) {
  if (!value || !value.startsWith("/") || value.startsWith("//")) {
    return null;
  }
  let parsed: URL;
  try {
    parsed = new URL(value, "https://angmoo.invalid");
  } catch {
    return null;
  }
  if (parsed.origin !== "https://angmoo.invalid") {
    return null;
  }
  if (!ALLOWED_RETURN_PATHS.some((pattern) => pattern.test(parsed.pathname))) {
    return null;
  }
  return `${parsed.pathname}${parsed.search}${parsed.hash}`;
}
