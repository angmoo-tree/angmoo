import { runtimeFetch } from "@/shared/runtime/public";

export const WORLD_PACKAGE_MEDIA_TYPE = "application/vnd.angmoo.world+zip";
export const WORLD_PACKAGE_EXTENSION = ".angmoo-world";

export type WorldPackageLicense = {
  expression: string;
  attribution: string;
  source_url: string | null;
  license_text_path: string | null;
};

export type WorldPackageExportRequest = {
  license_expression: string;
  attribution: string;
  source_url: string | null;
  license_text: string | null;
  confirm_export_rights: true;
  confirm_license: true;
  confirm_exclusions: true;
};

export type WorldPackageExportPreview = {
  source_world_id: string;
  package_id: string;
  package_version: number;
  seed_digest: string;
  recommended_filename: string;
  included_autonomous_characters: number;
  excluded_owner_controlled_characters: number;
  included_assets: number;
  excluded_external_assets: number;
  warnings: string[];
  license: WorldPackageLicense;
};

export type PreparedWorldPackageExport = {
  operation_id: string;
  download_token: string;
  download_path: string;
  expires_at: string;
  preview: WorldPackageExportPreview;
  manifest_digest: string;
  archive_digest: string;
  archive_bytes: number;
  replayed_request: boolean;
};

export type WorldPackageImportPreview = {
  schema_version: string;
  state: string;
  operation_id: string;
  archive_digest: string;
  content_digest: string;
  package_id: string;
  package_version: number;
  producer_name: string;
  producer_version: string;
  min_reader_version: string;
  world_contract_version: string;
  trust_state: string;
  license: WorldPackageLicense;
  world_name: string;
  world_tagline: string;
  character_names: string[];
  role_count: number;
  place_count: number;
  rule_count: number;
  glossary_count: number;
  asset_count: number;
  asset_bytes: number;
  total_decoded_pixels: number;
  excluded_owner_controlled_characters: number;
  excluded_runtime_records: number;
  collision_plan: {
    planned_world_slug: string;
    characters: Array<{
      source_ref: string;
      display_name: string;
      planned_handle: string;
    }>;
    duplicate_state: "new_package" | "already_imported" | "independent_fork";
    commit_allowed_by_default: boolean;
  };
  normalized_assets: Array<{
    source_ref: string;
    normalized_ref: string;
    normalized_sha256: string;
    normalized_bytes: number;
    width: number;
    height: number;
    alt_text: string;
  }>;
  warnings: string[];
  blocking_issues: string[];
  expires_at: string;
};

export type PreparedWorldPackageImport = {
  preview_token: string;
  preview: WorldPackageImportPreview;
};

export type WorldPackageImportResult = {
  import_id: string;
  imported_world_id: string;
  device_home_world_id: string;
  replayed: boolean;
};

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

export function triggerBrowserWorldPackageDownload(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  anchor.rel = "noopener";
  document.body.append(anchor);
  anchor.click();
  anchor.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 0);
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
