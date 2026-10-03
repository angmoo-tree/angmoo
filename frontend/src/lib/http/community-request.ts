import { apiRequest as sendRequest, type RequestOptions } from "@/lib/http/api-request";

/** Community reads preserve their auth policy and never display response bodies. */
export function apiRequest<T>(path: string, options: RequestOptions = {}) {
  return sendRequest<T>(path, { ...options, suppressAuthFailureEvent: true });
}
