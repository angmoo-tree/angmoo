import { proxyBackend } from "@/lib/backend";

const DEFAULT_PROXY_MAX_BYTES = 1024 * 1024;
const LORE_UPLOAD_PROXY_MAX_BYTES = 10 * 1024 * 1024 + 256 * 1024;
const PROFILE_MEDIA_PROXY_MAX_BYTES = 8_000_000 + 256 * 1024;

type RouteContext = {
  params: Promise<{
    path: string[];
  }>;
};

class RequestBodyTooLargeError extends Error {}

function isLoreUpload(path: string[], method: string) {
  return (
    method === "POST" &&
    path.length === 3 &&
    path[0] === "agents" &&
    path[2] === "lore-sources"
  );
}

function isProfileMediaUpload(path: string[], method: string) {
  if (!["POST", "PUT", "PATCH"].includes(method) || path[0] !== "agents") {
    return false;
  }
  return (
    (path.length === 4 &&
      path[1] === "drafts" &&
      path[3] === "media") ||
    (path.length === 3 && path[2] === "media") ||
    (path.length === 4 &&
      path[2] === "image-settings" &&
      path[3] === "seed")
  );
}

function requestBodyLimit(path: string[], method: string) {
  if (isLoreUpload(path, method)) {
    return LORE_UPLOAD_PROXY_MAX_BYTES;
  }
  if (isProfileMediaUpload(path, method)) {
    return PROFILE_MEDIA_PROXY_MAX_BYTES;
  }
  return DEFAULT_PROXY_MAX_BYTES;
}

async function readStreamedRequestBody(request: Request, maxBytes: number) {
  if (!request.body) return undefined;
  const reader = request.body.getReader();
  const chunks: Uint8Array[] = [];
  let totalBytes = 0;
  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      totalBytes += value.byteLength;
      if (totalBytes > maxBytes) {
        await reader.cancel();
        throw new RequestBodyTooLargeError();
      }
      chunks.push(value);
    }
  } finally {
    reader.releaseLock();
  }

  const body = new Uint8Array(totalBytes);
  let offset = 0;
  for (const chunk of chunks) {
    body.set(chunk, offset);
    offset += chunk.byteLength;
  }
  return body.buffer;
}

async function readBoundedRequestBody(request: Request, maxBytes: number) {
  const contentLength = Number(request.headers.get("content-length"));
  if (
    Number.isFinite(contentLength) &&
    contentLength >= 0 &&
    contentLength > maxBytes
  ) {
    throw new RequestBodyTooLargeError();
  }
  return readStreamedRequestBody(request, maxBytes);
}

async function proxy(request: Request, context: RouteContext) {
  const { path } = await context.params;
  let body: ArrayBuffer | undefined;
  try {
    body = ["GET", "HEAD"].includes(request.method)
      ? undefined
      : await readBoundedRequestBody(
          request,
          requestBodyLimit(path, request.method),
        );
  } catch (error) {
    if (error instanceof RequestBodyTooLargeError) {
      return Response.json(
        { detail: "Request body exceeds the allowed limit." },
        { status: 413 },
      );
    }
    throw error;
  }
  const query = new URL(request.url).search;
  const authorization = request.headers.get("authorization");

  return proxyBackend(`/api/v1/${path.map(encodeURIComponent).join("/")}${query}`, {
    method: request.method,
    body,
    headers: {
      ...(authorization ? { Authorization: authorization } : {}),
      "Content-Type": request.headers.get("content-type") ?? "application/json",
    },
  });
}

export const GET = proxy;
export const POST = proxy;
export const PUT = proxy;
export const PATCH = proxy;
export const DELETE = proxy;
