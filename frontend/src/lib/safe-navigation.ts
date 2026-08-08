const ALLOWED_RETURN_PATHS = [
  /^\/agents\/[^/?#]+$/,
  /^\/profiles\/characters\/[^/?#]+$/,
  /^\/messages\/[^/?#]+$/,
];
const ALLOWED_LOGIN_RETURN_PATHS = [
  /^\/worlds\/new$/,
  /^\/worlds\/[^/?#]+\/creator$/,
];

function safeAllowlistedReturnTo(
  value: string | null,
  allowedPaths: RegExp[],
) {
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
  if (!allowedPaths.some((pattern) => pattern.test(parsed.pathname))) {
    return null;
  }
  return `${parsed.pathname}${parsed.search}${parsed.hash}`;
}

export function safeSettingsReturnTo(value: string | null) {
  return safeAllowlistedReturnTo(value, ALLOWED_RETURN_PATHS);
}

export function safeLoginReturnTo(value: string | null) {
  return safeAllowlistedReturnTo(value, ALLOWED_LOGIN_RETURN_PATHS);
}
