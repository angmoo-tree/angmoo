import {clearStoredUser, notifyAuthChanged} from '@/lib/auth/browser-session';
import {runtimeFetch} from '@/lib/runtime/runtime-config';

type RequestOptions = Omit<RequestInit, "body" | "credentials"> & {
  body?: unknown;
  anonymous?: boolean;
  clearAuthOnUnauthorized?: boolean;
};

export async function requestSocialApi<T>(
  path: string,
  options: RequestOptions = {},
) {
  const {
    anonymous = false,
    body,
    clearAuthOnUnauthorized = false,
    headers,
    ...rest
  } = options;
  const response = await runtimeFetch(`/api/backend${path}`, {
    ...rest,
    body: body === undefined ? undefined : JSON.stringify(body),
    cache: "no-store",
    credentials: anonymous ? "omit" : "same-origin",
    headers: { "Content-Type": "application/json", ...(headers ?? {}) },
  });
  const text = await response.text();
  let payload: unknown = null;
  try {
    payload = text ? JSON.parse(text) : null;
  } catch (error) {
    // A successful endpoint must not silently turn a malformed response into a
    // typed null. Error responses still fall through to the stable HTTP reason.
    if (response.ok) throw error;
  }
  if (!response.ok) {
    if (response.status === 401 && !anonymous && clearAuthOnUnauthorized) {
      clearStoredUser();
      notifyAuthChanged();
    }
    const detail =
      typeof payload === "object" &&
      payload !== null &&
      "detail" in payload &&
      typeof payload.detail === "string"
        ? payload.detail
        : `http_${response.status}`;
    throw new Error(detail);
  }
  return payload as T;
}
