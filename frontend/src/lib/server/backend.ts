import { cancelledResponse, failedProxyResponse, forwardResponseStream, isRequestCancellation, proxyLifecycle, type ProxyLifecycle, type ProxyPhase } from "./proxy-lifecycle";

const DEFAULT_BACKEND_URL = "http://127.0.0.1:8080";
const BODYLESS_STATUSES = new Set([204, 205, 304]);
const MAX_PROXY_ERROR_BYTES = 64 * 1024;
const MAX_SERVER_JSON_BYTES = 1024 * 1024;
const FORWARDED_SET_COOKIE_NAMES = [
  "angmoo_browser_session",
  "angmoo_google_signup_pending",
  "angmoo_local_owner_challenge",
];

class UpstreamResponseTooLargeError extends Error {}

export function getBackendBaseUrl() {
  const url = new URL(process.env.ANGMOO_API_BASE_URL ?? DEFAULT_BACKEND_URL);
  if (!["http:", "https:"].includes(url.protocol) || url.username || url.password || url.search || url.hash || url.pathname !== "/") {
    throw new Error("backend_upstream_invalid");
  }
  return url.origin;
}

export async function proxyBackend(path: string, init?: RequestInit, lifecycle: ProxyLifecycle = proxyLifecycle(init?.method ?? "GET", "community")) {
  const downstream = init?.signal;
  const controller = new AbortController();
  const abort = () => controller.abort(downstream?.reason);
  const detach = () => downstream?.removeEventListener("abort", abort);
  downstream?.addEventListener("abort", abort, { once: true });
  let phase: ProxyPhase = "upstream_headers";
  try {
    if (downstream?.aborted) throw downstream.reason;
    const upstream = await fetch(`${getBackendBaseUrl()}${path}`, {
      ...init,
      signal: controller.signal,
      cache: "no-store",
      headers: {
        Accept: "application/json",
        ...(init?.headers ?? {}),
      },
    });
    const responseHeaders = forwardedResponseHeaders(upstream);

    if (BODYLESS_STATUSES.has(upstream.status)) {
      detach();
      return new Response(null, {
        status: upstream.status,
        headers: responseHeaders,
      });
    }

    if (upstream.ok) {
      if (!upstream.body) detach();
      return new Response(upstream.body ? forwardResponseStream(upstream.body, controller, downstream, lifecycle, upstream.status, detach) : null, {
        status: upstream.status,
        headers: responseHeaders,
      });
    }

    phase = "error_body";
    try {
      const text = await readBoundedResponseText(upstream, MAX_PROXY_ERROR_BYTES);
      if (downstream?.aborted) throw downstream.reason;
      return new Response(text, {
        status: upstream.status,
        headers: responseHeaders,
      });
    } catch (error) {
      if (!(error instanceof UpstreamResponseTooLargeError)) {
        throw error;
      }
      responseHeaders.set("content-type", "application/json");
      return new Response(JSON.stringify({ detail: "Backend request failed." }), {
        status: upstream.status,
        headers: responseHeaders,
      });
    } finally {
      detach();
    }
  } catch (error) {
    detach();
    if (isRequestCancellation(error, downstream)) {
      lifecycle.finish(phase, "cancelled");
      return cancelledResponse();
    }
    lifecycle.finish(phase, "failed");
    return failedProxyResponse();
  }
}

function forwardedResponseHeaders(upstream: Response) {
  const headers = new Headers({
    "content-type": upstream.headers.get("content-type") ?? "application/json",
  });
  // Keep private-source response protections across the existing Next proxy.
  for (const name of ["cache-control", "x-content-type-options", "retry-after"]) {
    const value = upstream.headers.get(name);
    if (value !== null) headers.set(name, value);
  }
  const getSetCookie = (
    upstream.headers as Headers & { getSetCookie?: () => string[] }
  ).getSetCookie;
  const values = getSetCookie
    ? getSetCookie.call(upstream.headers)
    : [upstream.headers.get("set-cookie")].filter(
        (value): value is string => Boolean(value),
      );
  for (const value of values) {
    if (
      FORWARDED_SET_COOKIE_NAMES.some((name) =>
        value.toLowerCase().startsWith(`${name.toLowerCase()}=`),
      )
    ) {
      headers.append("set-cookie", value);
    }
  }
  return headers;
}

export async function fetchBackendJson<T>(path: string) {
  const upstream = await fetch(`${getBackendBaseUrl()}${path}`, {
    cache: "no-store",
    headers: {
      Accept: "application/json",
    },
  });

  const text = await readBoundedResponseText(upstream, MAX_SERVER_JSON_BYTES);
  const payload = text ? JSON.parse(text) : null;

  if (!upstream.ok) {
    const message =
      typeof payload?.detail === "string"
        ? payload.detail
        : `Backend request failed with ${upstream.status}`;
    throw new Error(message);
  }

  return payload as T;
}

async function readBoundedResponseText(response: Response, maxBytes: number) {
  if (!response.body) return "";
  const contentLength = Number(response.headers.get("content-length"));
  if (
    Number.isFinite(contentLength) &&
    contentLength >= 0 &&
    contentLength > maxBytes
  ) {
    await response.body.cancel();
    throw new UpstreamResponseTooLargeError();
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let totalBytes = 0;
  let text = "";
  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      totalBytes += value.byteLength;
      if (totalBytes > maxBytes) {
        await reader.cancel();
        throw new UpstreamResponseTooLargeError();
      }
      text += decoder.decode(value, { stream: true });
    }
    return text + decoder.decode();
  } finally {
    reader.releaseLock();
  }
}
