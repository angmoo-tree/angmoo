import { apiRequest } from "@/lib/http/api-request";

type RequestOptions = Omit<RequestInit, "body" | "credentials"> & {
  body?: unknown;
  anonymous?: boolean;
  clearAuthOnUnauthorized?: boolean;
};

/** Keep the social caller's auth policy while sharing the safe typed transport. */
export function requestSocialApi<T>(path: string, options: RequestOptions = {}) {
  const { clearAuthOnUnauthorized = false, ...rest } = options;
  return apiRequest<T>(path, { ...rest, suppressAuthFailureEvent: !clearAuthOnUnauthorized });
}
