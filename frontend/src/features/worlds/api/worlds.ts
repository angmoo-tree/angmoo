import type { OwnerControlledIdentityRead,OwnerControlledProfileWrite,WorldCreatorContext,WorldDraftCreate,WorldGenerationContext,WorldRead,WorldReadiness,WorldUpdate } from "@/features/worlds/types/worlds";
import { runtimeFetch } from "@/lib/runtime/runtime-config";



































type RequestOptions = Omit<RequestInit, "body"> & { body?: unknown };

export class WorldApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
    readonly detail: unknown,
  ) {
    super(message);
    this.name = "WorldApiError";
  }
}

type FastApiValidationIssue = { loc?: unknown; msg?: unknown };

function isFastApiValidationIssue(value: unknown): value is FastApiValidationIssue {
  return typeof value === "object" && value !== null;
}

export function requestValidationFields(detail: unknown) {
  if (!Array.isArray(detail)) return [];
  return Array.from(
    new Set(
      detail.flatMap((issue) => {
        if (!isFastApiValidationIssue(issue) || !Array.isArray(issue.loc)) return [];
        const path = issue.loc
          .filter((item) => item !== "body")
          .map(String)
          .join(".");
        return path ? [path] : [];
      }),
    ),
  );
}

async function apiRequest<T>(path: string, options: RequestOptions = {}) {
  const { body, headers, ...rest } = options;
  const response = await runtimeFetch(`/api/backend${path}`, {
    ...rest,
    body: body === undefined ? undefined : JSON.stringify(body),
    cache: "no-store",
    credentials: "same-origin",
    headers: {
      Accept: "application/json",
      ...(body === undefined ? {} : { "Content-Type": "application/json" }),
      ...(headers ?? {}),
    },
  });
  const text = await response.text();
  let payload: unknown = null;
  try {
    payload = text ? JSON.parse(text) : null;
  } catch {
    payload = null;
  }
  if (!response.ok) {
    const detail =
      typeof payload === "object" && payload !== null && "detail" in payload
        ? (payload as { detail: unknown }).detail
        : null;
    const code =
      typeof detail === "string"
        ? detail
        : typeof detail === "object" &&
            detail !== null &&
            "code" in detail &&
            typeof (detail as { code?: unknown }).code === "string"
          ? (detail as { code: string }).code
          : Array.isArray(detail)
            ? "request_validation_error"
            : `http_${response.status}`;
    throw new WorldApiError(code, response.status, detail);
  }
  return payload as T;
}

function worldPath(worldId: string, suffix = "") {
  return `/worlds/${encodeURIComponent(worldId)}${suffix}`;
}

export function createWorld(data: WorldDraftCreate) {
  return apiRequest<WorldCreatorContext>("/worlds", {
    method: "POST",
    body: data,
  });
}

export function getWorldCreatorContext(worldId: string) {
  return apiRequest<WorldCreatorContext>(worldPath(worldId, "/creator-context"));
}

export function getWorld(worldId: string) {
  return apiRequest<WorldRead>(worldPath(worldId));
}

export function updateWorld(worldId: string, data: WorldUpdate) {
  return apiRequest<WorldCreatorContext>(worldPath(worldId), {
    method: "PATCH",
    body: data,
  });
}

export function validateWorld(worldId: string) {
  return apiRequest<WorldReadiness>(worldPath(worldId, "/validate"), {
    method: "POST",
  });
}

export function publishWorld(worldId: string, rowVersion: number) {
  return apiRequest<WorldCreatorContext>(worldPath(worldId, "/publish"), {
    method: "POST",
    body: { row_version: rowVersion },
  });
}

export function archiveWorld(worldId: string, rowVersion: number) {
  return apiRequest<WorldCreatorContext>(worldPath(worldId, "/archive"), {
    method: "POST",
    body: { row_version: rowVersion },
  });
}

export function uploadWorldBanner(
  worldId: string,
  data: {
    row_version: number;
    content_type: string;
    data_base64: string;
    alt_text: string;
  },
) {
  return apiRequest<WorldCreatorContext>(worldPath(worldId, "/banner"), {
    method: "POST",
    body: data,
  });
}

export function removeWorldBanner(worldId: string, rowVersion: number) {
  return apiRequest<WorldCreatorContext>(worldPath(worldId, "/banner"), {
    method: "DELETE",
    body: { row_version: rowVersion },
  });
}

export function getWorldGenerationContext(worldId: string) {
  return apiRequest<WorldGenerationContext>(
    worldPath(worldId, "/generation-context"),
  );
}

export function getOwnerControlledIdentity(worldId: string) {
  return apiRequest<OwnerControlledIdentityRead>(
    worldPath(worldId, "/owner-character"),
  );
}

export function createOwnerControlledIdentity(
  worldId: string,
  data: OwnerControlledProfileWrite,
) {
  return apiRequest<OwnerControlledIdentityRead>(
    worldPath(worldId, "/owner-character"),
    { method: "POST", body: data },
  );
}

export function updateOwnerControlledIdentity(
  worldId: string,
  data: OwnerControlledProfileWrite,
) {
  return apiRequest<OwnerControlledIdentityRead>(
    worldPath(worldId, "/owner-character"),
    { method: "PATCH", body: data },
  );
}
