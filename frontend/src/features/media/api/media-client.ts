import { apiRequest } from "@/lib/http/api-request";
import type { PreparedImageUpload } from "../types/photo-preparation";
import type { Asset, Catalog, GenerationSettings, GenerationWrite, InterpretationSettings, Workflow, WorkflowAnalysis, UsageSettings, GenerationJob, ApiGraph, RetainedComfyContract } from "../types/media";

export const getCatalog = (signal?: AbortSignal) => apiRequest<Catalog>("/media/catalog", { signal });
export const analyzeComfyWorkflow = (source_json: string, input_mode: "placeholders" | "node_bindings", signal?: AbortSignal, retained_contract?: RetainedComfyContract) => apiRequest<WorkflowAnalysis>("/media/comfy-workflows/analyze", { method: "POST", body: { source_json, input_mode, ...(retained_contract ? {retained_contract} : {}) }, signal });
export const getUsage = (signal?: AbortSignal) => apiRequest<UsageSettings>("/media/usage-settings", { signal });
export const saveUsage = (data: { expected_revision: number; daily_limit: number }) => apiRequest<UsageSettings>("/media/usage-settings", { method: "PUT", body: data });
const generationJobPath = (worldId: string, postId: string) => `/media/worlds/${encodeURIComponent(worldId)}/posts/${encodeURIComponent(postId)}/image-generation`;
export const getGenerationJob = (worldId: string, postId: string, signal?: AbortSignal) => apiRequest<GenerationJob | null>(generationJobPath(worldId, postId), { signal });
export const changeGenerationJob = (worldId: string, postId: string, action: "cancel" | "retry") => apiRequest<GenerationJob>(`${generationJobPath(worldId, postId)}/${action}`, { method: "POST" });
export const getGeneration = (id: string, signal?: AbortSignal) => apiRequest<GenerationSettings>(`/agents/${encodeURIComponent(id)}/generation-settings`, { signal });
export const getGenerationProviderKey = (id: string, provider: string, signal: AbortSignal) => apiRequest<import("@/components/ui/credential-fields").SecretKeyMetadata>(`/agents/${encodeURIComponent(id)}/generation-provider-key/${encodeURIComponent(provider)}`, { signal });
export const saveGeneration = (id: string, data: GenerationWrite, check = false, signal?: AbortSignal) => apiRequest<GenerationSettings>(`/agents/${encodeURIComponent(id)}/generation-settings${check ? "/check" : ""}`, { method: check ? "POST" : "PUT", body: data, signal });
export const getInterpretation = (signal?: AbortSignal) => apiRequest<InterpretationSettings>("/media/interpretation-settings", { signal });
export const saveInterpretation = (data: InterpretationSettings & { expected_revision: number; api_key?: string; clear_api_key?: boolean }) => {
  const { revision: _revision, has_api_key: _hasKey, ...body } = data;
  void _revision; void _hasKey;
  return apiRequest<InterpretationSettings>("/media/interpretation-settings", { method: "PUT", body });
};
export const discardDraft = (id: string) => apiRequest<void>(`/media/assets/${encodeURIComponent(id)}`, { method: "DELETE" });
export const preflightImage = (id: string, signal?: AbortSignal) => apiRequest<{ allowed: boolean; reason: string | null; settings_path?: string }>(`/media/assets/${encodeURIComponent(id)}/preflight`, { signal });
export const getComfySample = (kind: "text" | "reference") => apiRequest<{ workflow: Workflow; values: Record<string, string | number>; dependencies: { nodes: string[]; models: string[] } }>(`/media/comfy-samples/${kind}`);
export const getComfyApiSample = (kind: "text" | "reference", signal?: AbortSignal) => apiRequest<ApiGraph>(`/media/comfy-samples/${kind}?format=api_json`, {signal});

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

export async function uploadImage(input: PreparedImageUpload, scopeKind: "character" | "thread" | "world" | "world_character", scopeId: string, signal?: AbortSignal) {
  const { file } = input;
  if (!["image/png", "image/jpeg", "image/webp"].includes(file.type) || file.size > 10 * 1024 * 1024) throw new ImageUploadInputError("image_file_unsupported");
  const data = await new Promise<string>((resolve, reject) => {
    const reader = new FileReader();
    const abort = () => { reader.abort(); reject(new DOMException("Aborted", "AbortError")); };
    if (signal?.aborted) { abort(); return; }
    signal?.addEventListener("abort", abort, { once: true });
    reader.onloadend = () => signal?.removeEventListener("abort", abort);
    reader.onerror = () => reject(new ImageUploadInputError("image_file_read_failed"));
    reader.onload = () => resolve(String(reader.result).split(",")[1]);
    reader.readAsDataURL(file);
  });
  if (signal?.aborted) throw new DOMException("Aborted", "AbortError");
  return apiRequest<Asset>("/media/assets", { method: "POST", signal, body: { scope_kind: scopeKind, scope_id: scopeId, content_type: file.type, data_base64: data } });
}
