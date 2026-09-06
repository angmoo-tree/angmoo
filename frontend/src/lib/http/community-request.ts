import { runtimeFetch } from "@/lib/runtime/runtime-config";

type RequestOptions = Omit<RequestInit, "body"> & {
  body?: unknown;
  anonymous?: boolean;
};

export async function apiRequest<T>(path: string, options: RequestOptions = {}) {
  const { body, headers, anonymous = false, ...rest } = options;
  const response = await runtimeFetch(`/api/backend${path}`, {
    ...rest,
    body: body === undefined ? undefined : JSON.stringify(body),
    cache: "no-store",
    credentials: anonymous ? "omit" : "same-origin",
    headers: {
      "Content-Type": "application/json",
      ...(headers ?? {}),
    },
  });

  const text = await response.text();
  const payload = text ? JSON.parse(text) : null;

  if (!response.ok) {
    const message =
      typeof payload?.detail === "string"
        ? payload.detail
        : `Request failed with ${response.status}`;
    throw new Error(message);
  }

  return payload as T;
}
