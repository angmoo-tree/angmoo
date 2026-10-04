import { runtimeFetch } from "@/lib/runtime/runtime-config";
import { captureAuthRequestScope, clearStoredUser, isCurrentAuthRequestScope, notifyAuthChanged } from "@/lib/auth/browser-session";

// Product-neutral JSON/FormData transport, parsing and session handling.
// Callers own translated product validation. Provider/validator bodies are never UI messages.
export type RequestOptions = Omit<RequestInit, "body"> & {
  body?: unknown | FormData;
  anonymous?: boolean;
  suppressAuthFailureEvent?: boolean;
};

export type RequestValidationFailure = {
  code: string;
  message: string;
  params?: Partial<Record<"limit" | "minimum" | "maximum" | "remaining", number>>;
};

type ValidationFormatter = (detail: unknown[]) => string | RequestValidationFailure | null;

export { ApiRequestError } from "@/lib/http/error-contract";
import { ApiRequestError } from "@/lib/http/error-contract";

function getErrorMessage(
  payload: unknown,
  fallback: string,
  formatValidation: ValidationFormatter,
) {
  if (
    payload &&
    typeof payload === "object" &&
    "detail" in payload &&
    Array.isArray(payload.detail)
  ) {
    return formatValidation(payload.detail) ?? fallback;
  }
  return fallback;
}

function getValidationMessage(detail: unknown[]) {
  return detail.length ? "Please check the submitted values." : null;
}

function safeErrorDetails(payload: unknown) {
  const detail = payload && typeof payload === "object" && "detail" in payload ? payload.detail : null;
  const record = detail && typeof detail === "object" && !Array.isArray(detail)
    ? detail as Record<string, unknown> : {};
  const candidate = typeof detail === "string" ? detail : record.code;
  const code = typeof candidate === "string" && /^[a-z][a-z0-9_]{0,80}$/.test(candidate) ? candidate : null;
  const params: Record<string, unknown> = {};
  const allowance = record.allowance_available_at;
  if (typeof allowance === "string" && /^\d{4}-\d{2}-\d{2}T[\d:.]+(?:Z|[+-]\d{2}:\d{2})$/.test(allowance)) params.allowance_at = allowance;
  const values = record.params;
  if (values && typeof values === "object" && !Array.isArray(values)) {
    for (const [key, value] of Object.entries(values)) {
      if (["limit", "minimum", "maximum", "remaining"].includes(key) && typeof value === "number" && Number.isFinite(value)) params[key] = value;
      if (["allowance_at", "retry_at"].includes(key) && typeof value === "string" && /^\d{4}-\d{2}-\d{2}T[\d:.]+(?:Z|[+-]\d{2}:\d{2})$/.test(value)) params[key] = value;
    }
  }
  return { code, params };
}

function statusMessage(status: number) {
  if (status === 401) return "Please sign in again.";
  if (status === 403) return "You do not have permission for this action.";
  if (status === 409) return "The state changed. Refresh and try again.";
  if (status === 422) return "Please check the submitted values.";
  if (status === 429) return "The usage limit was reached. Please try again later.";
  return "The request could not be completed. Please try again.";
}

export async function apiRequest<T>(
  path: string,
  options: RequestOptions = {},
  formatValidation: ValidationFormatter = getValidationMessage,
) {
  const {
    body,
    headers,
    anonymous = false,
    suppressAuthFailureEvent = false,
    ...rest
  } = options;
  const scope = captureAuthRequestScope();
  const isFormDataBody = typeof FormData !== "undefined" && body instanceof FormData;
  const response = await runtimeFetch(`/api/backend${path}`, {
    ...rest,
    body:
      body === undefined
        ? undefined
        : isFormDataBody
          ? body
          : JSON.stringify(body),
    cache: "no-store",
    credentials: anonymous ? "omit" : "same-origin",
    headers: {
      ...(isFormDataBody ? {} : { "Content-Type": "application/json" }),
      ...(headers ?? {}),
    },
  });

  const text = await response.text();
  let payload: unknown = null;
  try {
    payload = text ? JSON.parse(text) : null;
  } catch (err) {
    if (!response.ok) {
      throw new ApiRequestError(statusMessage(response.status), response.status, null, {}, response.headers.get("Retry-After"));
    }
    throw err;
  }

  if (!response.ok) {
    if (response.status === 401 && !anonymous && !suppressAuthFailureEvent
        && !rest.signal?.aborted && isCurrentAuthRequestScope(scope)) {
      clearStoredUser();
      notifyAuthChanged();
    }
    const { code, params } = safeErrorDetails(payload);
    const failure = getErrorMessage(payload, statusMessage(response.status), formatValidation);
    const validation = typeof failure === "string" ? null : failure;
    throw new ApiRequestError(typeof failure === "string" ? failure : failure.message,
      response.status, validation?.code ?? code, { ...params, ...validation?.params }, response.headers.get("Retry-After"));
  }

  return payload as T;
}
