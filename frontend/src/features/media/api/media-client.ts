import { apiRequest } from "@/lib/http/api-request";
import type { Asset, Catalog, GenerationSettings, GenerationWrite, InterpretationSettings, Workflow, UsageSettings, GenerationJob } from "../types/media";

export const getCatalog = (signal?: AbortSignal) => apiRequest<Catalog>("/media/catalog", { signal });
export const getUsage = (signal?: AbortSignal) => apiRequest<UsageSettings>("/media/usage-settings", { signal });
export const saveUsage = (data: { expected_revision: number; daily_limit: number }) => apiRequest<UsageSettings>("/media/usage-settings", { method: "PUT", body: data });
export const getGenerationJob = (postId: string, signal?: AbortSignal) => apiRequest<GenerationJob | null>(`/posts/${encodeURIComponent(postId)}/image-generation`, { signal });
export const changeGenerationJob = (postId: string, action: "cancel" | "retry") => apiRequest<GenerationJob>(`/posts/${encodeURIComponent(postId)}/image-generation/${action}`, { method: "POST" });
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

export async function uploadImage(file: File, scopeKind: "character" | "thread" | "world", scopeId: string, signal?: AbortSignal) {
  if (!["image/png", "image/jpeg", "image/webp"].includes(file.type) || file.size > 10 * 1024 * 1024) throw new Error("PNG·JPEG·WebP 정지 이미지 10MiB 이하를 선택해 주세요.");
  const data = await new Promise<string>((resolve, reject) => {
    const reader = new FileReader();
    reader.onerror = () => reject(new Error("사진을 읽을 수 없습니다."));
    reader.onload = () => resolve(String(reader.result).split(",")[1]);
    reader.readAsDataURL(file);
  });
  return apiRequest<Asset>("/media/assets", { method: "POST", signal, body: { scope_kind: scopeKind, scope_id: scopeId, content_type: file.type, data_base64: data } });
}
