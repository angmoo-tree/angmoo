const DEFAULT_BACKEND_URL = "http://127.0.0.1:8080";
const BODYLESS_STATUSES = new Set([204, 205, 304]);
const MAX_PROXY_ERROR_BYTES = 64 * 1024;
const MAX_SERVER_JSON_BYTES = 1024 * 1024;

class UpstreamResponseTooLargeError extends Error {}

function getBackendBaseUrl() {
  return (process.env.ANGMOO_API_BASE_URL ?? DEFAULT_BACKEND_URL).replace(
    /\/$/,
    "",
  );
}

export async function proxyBackend(path: string, init?: RequestInit) {
  const upstream = await fetch(`${getBackendBaseUrl()}${path}`, {
    ...init,
    cache: "no-store",
    headers: {
      Accept: "application/json",
      ...(init?.headers ?? {}),
    },
  });

  if (BODYLESS_STATUSES.has(upstream.status)) {
    return new Response(null, {
      status: upstream.status,
    });
  }

  const contentType = upstream.headers.get("content-type") ?? "application/json";
  if (upstream.ok) {
    return new Response(upstream.body, {
      status: upstream.status,
      headers: {
        "content-type": contentType,
      },
    });
  }

  try {
    const text = await readBoundedResponseText(upstream, MAX_PROXY_ERROR_BYTES);
    return new Response(text, {
      status: upstream.status,
      headers: {
        "content-type": contentType,
      },
    });
  } catch (error) {
    if (!(error instanceof UpstreamResponseTooLargeError)) {
      throw error;
    }
    return Response.json(
      { detail: "Backend request failed." },
      { status: upstream.status },
    );
  }
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
