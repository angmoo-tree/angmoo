import { apiRequest } from "@/lib/http/api-request";
import type { Asset, Catalog, GenerationSettings, GenerationWrite, InterpretationSettings, Workflow, UsageSettings, GenerationJob } from "../types/media";

export const getCatalog = (signal?: AbortSignal) => apiRequest<Catalog>("/media/catalog", { signal });
export const getUsage = (signal?: AbortSignal) => apiRequest<UsageSettings>("/media/usage-settings", { signal });
export const saveUsage = (data: { expected_revision: number; daily_limit: number }) => apiRequest<UsageSettings>("/media/usage-settings", { method: "PUT", body: data });
const generationJobPath = (worldId: string, postId: string) => `/media/worlds/${encodeURIComponent(worldId)}/posts/${encodeURIComponent(postId)}/image-generation`;
export const getGenerationJob = (worldId: string, postId: string, signal?: AbortSignal) => apiRequest<GenerationJob | null>(generationJobPath(worldId, postId), { signal });
export const changeGenerationJob = (worldId: string, postId: string, action: "cancel" | "retry") => apiRequest<GenerationJob>(`${generationJobPath(worldId, postId)}/${action}`, { method: "POST" });
export const getGeneration = (id: string, signal?: AbortSignal) => apiRequest<GenerationSettings>(`/agents/${encodeURIComponent(id)}/generation-settings`, { signal });
export const saveGeneration = (id: string, data: GenerationWrite, check = false) => apiRequest<GenerationSettings>(`/agents/${encodeURIComponent(id)}/generation-settings${check ? "/check" : ""}`, { method: check ? "POST" : "PUT", body: data });
export const getInterpretation = (signal?: AbortSignal) => apiRequest<InterpretationSettings>("/media/interpretation-settings", { signal });
export const saveInterpretation = (data: InterpretationSettings & { expected_revision: number; api_key?: string; clear_api_key?: boolean }) => {
  const { revision: _revision, has_api_key: _hasKey, ...body } = data;
  void _revision; void _hasKey;
  return apiRequest<InterpretationSettings>("/media/interpretation-settings", { method: "PUT", body });
};
export const discardDraft = (id: string) => apiRequest<void>(`/media/assets/${encodeURIComponent(id)}`, { method: "DELETE" });
export const preflightImage = (id: string, signal?: AbortSignal) => apiRequest<{ allowed: boolean; reason: string | null; settings_path?: string }>(`/media/assets/${encodeURIComponent(id)}/preflight`, { signal });
export const getComfySample = (kind: "text" | "reference") => apiRequest<{ workflow: Workflow; values: Record<string, string | number>; dependencies: { nodes: string[]; models: string[] } }>(`/media/comfy-samples/${kind}`);

const IMAGE_INPUT_MESSAGES = {
  image_file_unsupported: "Choose a still PNG, JPEG, or WebP image up to 10 MiB.",
  image_file_read_failed: "The photo could not be read. Please select it again.",
};

export class ImageUploadInputError extends Error {
  constructor(readonly code: "image_file_unsupported" | "image_file_read_failed") {
    super(IMAGE_INPUT_MESSAGES[code]);
    this.name = "ImageUploadInputError";
  }
}

export async function uploadImage(file: File, scopeKind: "character" | "thread" | "world", scopeId: string, signal?: AbortSignal) {
  if (!["image/png", "image/jpeg", "image/webp"].includes(file.type) || file.size > 10 * 1024 * 1024) throw new ImageUploadInputError("image_file_unsupported");
  const data = await new Promise<string>((resolve, reject) => {
    const reader = new FileReader();
    reader.onerror = () => reject(new ImageUploadInputError("image_file_read_failed"));
    reader.onload = () => resolve(String(reader.result).split(",")[1]);
    reader.readAsDataURL(file);
  });
  return apiRequest<Asset>("/media/assets", { method: "POST", signal, body: { scope_kind: scopeKind, scope_id: scopeId, content_type: file.type, data_base64: data } });
}
