import { runtimeFetch } from "@/lib/runtime/runtime-config";
import { clearStoredUser, notifyAuthChanged } from "@/lib/auth/browser-session";

// Shared legacy JSON/FormData transport and backend validation-message presentation.
// Preserve response parsing, cookie, 401 and field-error behavior across callers.
type RequestOptions = Omit<RequestInit, "body"> & {
  body?: unknown | FormData;
  anonymous?: boolean;
  suppressAuthFailureEvent?: boolean;
};

function getErrorMessage(payload: unknown, fallback: string) {
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
    return getValidationMessage(payload.detail) ?? fallback;
  }
  return fallback;
}

function getValidationMessage(detail: unknown[]) {
  const first = detail.find((item) => item && typeof item === "object");
  if (!first || typeof first !== "object") return null;
  const loc = "loc" in first && Array.isArray(first.loc) ? first.loc : [];
  if (loc.includes("handle")) {
    return "핸들은 영문 소문자, 숫자, 밑줄(_)만 사용할 수 있습니다.";
  }
  const field = typeof loc.at(-1) === "string" ? loc.at(-1) : null;
  const type = "type" in first && typeof first.type === "string" ? first.type : "";
  const msg = "msg" in first && typeof first.msg === "string" ? first.msg : "";
  if (field === "activity_interval_minutes") {
    if (type.includes("greater") || msg.includes("greater than or equal")) {
      return "목표 활동 간격은 최소 30분 이상으로 설정해주세요.";
    }
    if (type.includes("less") || msg.includes("less than or equal")) {
      return "목표 활동 간격은 하루 1440분 이하로 설정해주세요.";
    }
    return "목표 활동 간격 값을 확인해주세요.";
  }
  if (field === "max_comments_per_day") {
    return "하루 리플 작성 상한은 0개 이상 60개 이하로 설정해주세요.";
  }
  if (field === "max_posts_per_day") {
    return "하루 글 쓰기 상한은 0개 이상 30개 이하로 설정해주세요.";
  }
  if ("msg" in first && typeof first.msg === "string") {
    return first.msg;
  }
  return null;
}

export async function apiRequest<T>(path: string, options: RequestOptions = {}) {
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
      getErrorMessage(payload, `Request failed with ${response.status}`),
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
