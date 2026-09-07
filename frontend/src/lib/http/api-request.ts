import { runtimeFetch } from "@/lib/runtime/runtime-config";
import { clearStoredUser, notifyAuthChanged } from "@/lib/auth/browser-session";

// Product-neutral JSON/FormData transport, parsing and session handling.
// Callers own product validation messages; the default preserves server messages.
export type RequestOptions = Omit<RequestInit, "body"> & {
  body?: unknown | FormData;
  anonymous?: boolean;
  suppressAuthFailureEvent?: boolean;
};

function getErrorMessage(
  payload: unknown,
  fallback: string,
  formatValidation: (detail: unknown[]) => string | null,
) {
  if (
    payload &&
    typeof payload === "object" &&
    "detail" in payload &&
    typeof payload.detail === "string"
  ) {
    return payload.detail;
  }
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
  const first = detail.find((item) => item && typeof item === "object");
  if (!first || typeof first !== "object") return null;
  return "msg" in first && typeof first.msg === "string" ? first.msg : null;
}

export async function apiRequest<T>(
  path: string,
  options: RequestOptions = {},
  formatValidation: (detail: unknown[]) => string | null = getValidationMessage,
) {
  const {
    body,
    headers,
    anonymous = false,
    suppressAuthFailureEvent = false,
    ...rest
  } = options;
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
      throw new Error(
        htmlErrorMessage(text) ?? (text.trim() || `Request failed with ${response.status}`),
      );
    }
    throw err;
  }

  if (!response.ok) {
    if (response.status === 401 && !anonymous && !suppressAuthFailureEvent) {
      clearStoredUser();
      notifyAuthChanged();
    }
    throw new Error(
      getErrorMessage(payload, `Request failed with ${response.status}`, formatValidation),
    );
  }

  return payload as T;
}

function htmlErrorMessage(text: string) {
  const trimmed = text.trim().toLowerCase();
  if (!trimmed.startsWith("<!doctype html") && !trimmed.startsWith("<html")) {
    return null;
  }
  return "요청 처리 중 서버 오류가 발생했습니다. 잠시 후 다시 시도해주세요.";
}
