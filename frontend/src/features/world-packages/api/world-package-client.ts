import { WORLD_PACKAGE_MEDIA_TYPE } from "@/features/world-packages/config/world-package";
import type { PreparedWorldPackageExport,PreparedWorldPackageImport,WorldPackageExportPreview,WorldPackageExportRequest,WorldPackageImportResult } from "@/features/world-packages/types/world-package";
import { runtimeFetch } from "@/lib/runtime/runtime-config";
import { ApiRequestError } from "@/lib/http/error-contract";









const PERSONA_FIELDS = ["one_liner", "personality", "speech_style", "worldview", "character_background", "topic_preferences", "safety_rules", "persona_summary"] as const;
type PersonaFieldName = typeof PERSONA_FIELDS[number];
export type WorldPackagePersonaError = { field: PersonaFieldName; limit: number; actual: number };

export class WorldPackageApiError extends ApiRequestError {
  readonly fields: WorldPackagePersonaError[];

  constructor(status: number, detail: unknown, retryAfter: string | null = null) {
    super("The World Package request could not be completed.", status, worldPackageErrorCode(detail), {}, retryAfter);
    this.name = "WorldPackageApiError";
    this.fields = personaErrorFields(detail);
  }
}

async function apiResponse<T>(response: Response): Promise<T> {
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
        : payload;
    throw new WorldPackageApiError(response.status, detail, response.headers.get("Retry-After"));
  }
  return payload as T;
}

function worldPackageErrorCode(detail: unknown): string | null {
  const code = typeof detail === "string" ? detail
    : typeof detail === "object" && detail !== null && "code" in detail ? detail.code : null;
  return typeof code === "string" && /^world_package_[a-z_]{1,64}$/.test(code) ? code : null;
}

function personaErrorFields(detail: unknown): WorldPackagePersonaError[] {
  if (worldPackageErrorCode(detail) !== "world_package_persona_invalid"
    || typeof detail !== "object" || detail === null || !("fields" in detail) || !Array.isArray(detail.fields)) return [];
  // Keep bounded field names and lengths, never uploaded text or raw validator input.
  return detail.fields.slice(0, PERSONA_FIELDS.length).flatMap((item: unknown) => {
    if (!item || typeof item !== "object" || !("field" in item) || !("limit" in item) || !("actual" in item)
      || !PERSONA_FIELDS.includes(item.field as PersonaFieldName)
      || typeof item.limit !== "number" || !Number.isSafeInteger(item.limit) || item.limit <= 0
      || typeof item.actual !== "number" || !Number.isSafeInteger(item.actual) || item.actual < 0) return [];
    return [{ field: item.field as PersonaFieldName, limit: item.limit, actual: item.actual }];
  });
}

function jsonHeaders(extra: HeadersInit = {}) {
  return {
    Accept: "application/json",
    "Content-Type": "application/json",
    ...extra,
  };
}

function exportPath(worldId: string, suffix = "") {
  return `/api/backend/worlds/${encodeURIComponent(worldId)}/package-exports${suffix}`;
}

export async function previewWorldPackageExport(
  worldId: string,
  request: WorldPackageExportRequest,
) {
  return apiResponse<WorldPackageExportPreview>(
    await runtimeFetch(exportPath(worldId, "/preview"), {
      method: "POST",
      credentials: "same-origin",
      cache: "no-store",
      headers: jsonHeaders(),
      body: JSON.stringify(request),
    }),
  );
}

export async function prepareWorldPackageExport(
  worldId: string,
  request: WorldPackageExportRequest,
) {
  return apiResponse<PreparedWorldPackageExport>(
    await runtimeFetch(exportPath(worldId), {
      method: "POST",
      credentials: "same-origin",
      cache: "no-store",
      headers: jsonHeaders({ "Idempotency-Key": crypto.randomUUID() }),
      body: JSON.stringify(request),
    }),
  );
}

export async function downloadPreparedWorldPackage(
  prepared: PreparedWorldPackageExport,
  mode: "browser_download" | "tauri_save_as",
) {
  const response = await runtimeFetch(`/api/backend${prepared.download_path.slice("/api/v1".length)}`, {
    credentials: "same-origin",
    cache: "no-store",
    headers: {
      Accept: WORLD_PACKAGE_MEDIA_TYPE,
      "X-World-Package-Download-Token": prepared.download_token,
      "X-World-Package-Delivery-Mode": mode,
    },
  });
  if (!response.ok) {
    const payload = await response.json().catch(() => null);
    const detail =
      typeof payload === "object" && payload !== null && "detail" in payload
        ? payload.detail
        : payload;
    throw new WorldPackageApiError(response.status, detail, response.headers.get("Retry-After"));
  }
  return {
    blob: await response.blob(),
    filename: contentDispositionFilename(response.headers.get("Content-Disposition")) ??
      prepared.preview.recommended_filename,
  };
}

export async function acknowledgeNativeWorldPackageDelivery(
  prepared: PreparedWorldPackageExport,
) {
  const response = await runtimeFetch(
    `/api/backend/world-package-exports/${encodeURIComponent(prepared.operation_id)}/delivery-ack`,
    {
      method: "POST",
      credentials: "same-origin",
      headers: { "X-World-Package-Download-Token": prepared.download_token },
    },
  );
  if (!response.ok) await apiResponse<never>(response);
}

export async function discardPreparedWorldPackageExport(
  prepared: PreparedWorldPackageExport,
) {
  const response = await runtimeFetch(
    `/api/backend/world-package-exports/${encodeURIComponent(prepared.operation_id)}`,
    {
      method: "DELETE",
      credentials: "same-origin",
      headers: { "X-World-Package-Download-Token": prepared.download_token },
    },
  );
  if (!response.ok && response.status !== 410) await apiResponse<never>(response);
}

export async function stageWorldPackageImport(file: File) {
  const form = new FormData();
  form.append("package", file, file.name);
  return apiResponse<PreparedWorldPackageImport>(
    await runtimeFetch("/api/backend/world-package-imports/stage", {
      method: "POST",
      credentials: "same-origin",
      cache: "no-store",
      headers: { Accept: "application/json" },
      body: form,
    }),
  );
}

export async function discardWorldPackageImport(
  prepared: PreparedWorldPackageImport,
) {
  const response = await runtimeFetch(
    `/api/backend/world-package-imports/${encodeURIComponent(prepared.preview.operation_id)}`,
    {
      method: "DELETE",
      credentials: "same-origin",
      headers: { "X-World-Package-Preview-Token": prepared.preview_token },
    },
  );
  if (!response.ok && response.status !== 410) await apiResponse<never>(response);
}

export async function commitWorldPackageImport(
  prepared: PreparedWorldPackageImport,
  duplicateStrategy: "reject" | "independent_copy",
) {
  return apiResponse<WorldPackageImportResult>(
    await runtimeFetch(
      `/api/backend/world-package-imports/${encodeURIComponent(prepared.preview.operation_id)}/commit`,
      {
        method: "POST",
        credentials: "same-origin",
        headers: jsonHeaders({
          "Idempotency-Key": crypto.randomUUID(),
          "X-World-Package-Preview-Token": prepared.preview_token,
        }),
        body: JSON.stringify({
          expected_content_digest: prepared.preview.content_digest,
          duplicate_strategy: duplicateStrategy,
        }),
      },
    ),
  );
}


function contentDispositionFilename(value: string | null) {
  const encoded = value?.match(/filename\*=UTF-8''([^;]+)/i)?.[1];
  if (!encoded) return null;
  try {
    return decodeURIComponent(encoded);
  } catch {
    return null;
  }
}
