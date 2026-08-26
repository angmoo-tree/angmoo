import { proxyBackend } from "@/lib/backend";

const DEFAULT_PROXY_MAX_BYTES = 1024 * 1024;
const LORE_UPLOAD_PROXY_MAX_BYTES = 10 * 1024 * 1024 + 256 * 1024;
const PROFILE_MEDIA_PROXY_MAX_BYTES = 8_000_000 + 256 * 1024;
const FORWARDED_COOKIE_NAMES = new Set([
  "angmoo_browser_session",
  "angmoo_google_signup_pending",
  "angmoo_local_owner_challenge",
]);
const UNSAFE_METHODS = new Set(["POST", "PUT", "PATCH", "DELETE"]);
const WORLD_PACKAGE_CAPABILITY_TOKEN = /^[A-Za-z0-9_-]{32,128}$/;
const WORLD_PACKAGE_DELIVERY_MODES = new Set([
  "browser_download",
  "tauri_save_as",
]);
const WORLD_PACKAGE_CAPABILITY_HEADER_NAMES = [
  "x-world-package-download-token",
  "x-world-package-preview-token",
  "x-world-package-delivery-mode",
] as const;

type RouteContext = {
  params: Promise<{
    path: string[];
  }>;
};

class RequestBodyTooLargeError extends Error {}
class InvalidWorldPackageCapabilityError extends Error {}

type WorldPackageCapabilityKind =
  | "export-download"
  | "export-token"
  | "import-preview"
  | null;

function worldPackageCapabilityKind(
  path: string[],
  method: string,
): WorldPackageCapabilityKind {
  if (path[0] === "world-package-exports") {
    if (method === "GET" && path.length === 3 && path[2] === "download") {
      return "export-download";
    }
    if (
      (method === "POST" &&
        path.length === 3 &&
        path[2] === "delivery-ack") ||
      (method === "DELETE" && path.length === 2)
    ) {
      return "export-token";
    }
  }
  if (path[0] === "world-package-imports") {
    if (
      (method === "GET" && path.length === 3 && path[2] === "preview") ||
      (method === "POST" && path.length === 3 && path[2] === "commit") ||
      (method === "DELETE" && path.length === 2)
    ) {
      return "import-preview";
    }
  }
  return null;
}

function worldPackageCapabilityHeaders(
  request: Request,
  path: string[],
): Record<string, string> {
  const kind = worldPackageCapabilityKind(path, request.method);
  const downloadToken = request.headers.get(
    "x-world-package-download-token",
  );
  const previewToken = request.headers.get("x-world-package-preview-token");
  const deliveryMode = request.headers.get("x-world-package-delivery-mode");
  const hasCapabilityHeader = WORLD_PACKAGE_CAPABILITY_HEADER_NAMES.some(
    (name) => request.headers.has(name),
  );

  if (!kind) {
    if (hasCapabilityHeader) throw new InvalidWorldPackageCapabilityError();
    return {};
  }

  if (kind === "import-preview") {
    if (downloadToken || deliveryMode) {
      throw new InvalidWorldPackageCapabilityError();
    }
    if (previewToken && !WORLD_PACKAGE_CAPABILITY_TOKEN.test(previewToken)) {
      throw new InvalidWorldPackageCapabilityError();
    }
    const headers: Record<string, string> = {};
    if (previewToken) headers["X-World-Package-Preview-Token"] = previewToken;
    return headers;
  }

  if (previewToken) throw new InvalidWorldPackageCapabilityError();
  if (downloadToken && !WORLD_PACKAGE_CAPABILITY_TOKEN.test(downloadToken)) {
    throw new InvalidWorldPackageCapabilityError();
  }
  if (kind !== "export-download" && deliveryMode) {
    throw new InvalidWorldPackageCapabilityError();
  }
  if (deliveryMode && !WORLD_PACKAGE_DELIVERY_MODES.has(deliveryMode)) {
    throw new InvalidWorldPackageCapabilityError();
  }
  const headers: Record<string, string> = {};
  if (downloadToken) {
    headers["X-World-Package-Download-Token"] = downloadToken;
  }
  if (deliveryMode) {
    headers["X-World-Package-Delivery-Mode"] = deliveryMode;
  }
  return headers;
}

function filterForwardedCookies(rawCookie: string | null) {
  if (!rawCookie) return null;
  const cookies = rawCookie
    .split(";")
    .map((item) => item.trim())
    .filter((item) => {
      const separator = item.indexOf("=");
      return separator > 0 && FORWARDED_COOKIE_NAMES.has(item.slice(0, separator));
    });
  return cookies.length > 0 ? cookies.join("; ") : null;
}

function requestFrontendOrigin(request: Request) {
  const host = request.headers.get("host");
  if (!host) return null;
  try {
    const forwardedProtocol = request.headers
      .get("x-forwarded-proto")
      ?.split(",", 1)[0]
      ?.trim()
      .toLowerCase();
    const requestProtocol =
      forwardedProtocol || new URL(request.url).protocol.slice(0, -1);
    if (!["http", "https"].includes(requestProtocol)) return null;
    return new URL(`${requestProtocol}://${host}`).origin;
  } catch {
    return null;
  }
}

function exactSameOrigin(request: Request) {
  const origin = request.headers.get("origin");
  const host = request.headers.get("host");
  if (
    !origin ||
    !host ||
    request.headers.get("sec-fetch-site") === "cross-site"
  ) {
    return null;
  }
  try {
    const parsed = new URL(origin);
    const requestOrigin = requestFrontendOrigin(request);
    if (!requestOrigin) return null;
    if (origin !== parsed.origin || parsed.origin !== requestOrigin) {
      return null;
    }
    return parsed.origin;
  } catch {
    return null;
  }
}

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
  const unsafe = UNSAFE_METHODS.has(request.method);
  const frontendOrigin = requestFrontendOrigin(request);
  const origin = unsafe ? exactSameOrigin(request) : null;
  if (unsafe && !origin) {
    return Response.json({ detail: "csrf_origin_invalid" }, { status: 403 });
  }
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
  const cookie = filterForwardedCookies(request.headers.get("cookie"));
  const idempotencyKey = request.headers.get("idempotency-key");
  let capabilityHeaders: Record<string, string>;
  try {
    capabilityHeaders = worldPackageCapabilityHeaders(request, path);
  } catch (error) {
    if (error instanceof InvalidWorldPackageCapabilityError) {
      return Response.json(
        { detail: "world_package_proxy_capability_invalid" },
        { status: 400 },
      );
    }
    throw error;
  }

  return proxyBackend(`/api/v1/${path.map(encodeURIComponent).join("/")}${query}`, {
    method: request.method,
    body,
    headers: {
      ...(cookie ? { Cookie: cookie } : {}),
      ...(origin ? { Origin: origin } : {}),
      ...(frontendOrigin
        ? { "X-Angmoo-Frontend-Origin": frontendOrigin }
        : {}),
      ...(idempotencyKey ? { "Idempotency-Key": idempotencyKey } : {}),
      ...capabilityHeaders,
      "Content-Type": request.headers.get("content-type") ?? "application/json",
    },
  });
}

export const GET = proxy;
export const POST = proxy;
export const PUT = proxy;
export const PATCH = proxy;
export const DELETE = proxy;
