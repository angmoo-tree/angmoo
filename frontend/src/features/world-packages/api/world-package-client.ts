import { WORLD_PACKAGE_MEDIA_TYPE } from "@/features/world-packages/config/world-package";
import type { PreparedWorldPackageExport,PreparedWorldPackageImport,WorldPackageExportPreview,WorldPackageExportRequest,WorldPackageImportResult } from "@/features/world-packages/types/world-package";
import { runtimeFetch } from "@/lib/runtime/runtime-config";









export class WorldPackageApiError extends Error {
  constructor(readonly status: number, readonly detail: unknown) {
    super(worldPackageErrorCode(status, detail));
    this.name = "WorldPackageApiError";
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
    throw new WorldPackageApiError(response.status, detail);
  }
  return payload as T;
}

function worldPackageErrorCode(status: number, detail: unknown) {
  if (typeof detail === "string") return detail;
  if (
    typeof detail === "object" &&
    detail !== null &&
    "code" in detail &&
    typeof (detail as { code?: unknown }).code === "string"
  ) {
    return (detail as { code: string }).code;
  }
  return `http_${status}`;
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
    throw new WorldPackageApiError(response.status, detail);
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
