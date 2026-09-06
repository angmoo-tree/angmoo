import { apiRequest } from "@/lib/http/api-request";
import type { GoogleGeminiModel, PollinationsImageModel } from "@/features/characters/config/model-options";
import { notifyAgentsChanged } from "@/features/characters/stores/agent-session";
import type { AgentActivityMaintenanceRead, AgentActivitySettingRead, AgentCreateInput, AgentCreationDraftImageStyle, AgentCreationDraftMediaGenerationRead, AgentCreationDraftRead, AgentCreationDraftUpdateInput, AgentDetailRead, AgentFeedCueRead, AgentFirstGreetingRead, AgentImageGenerationSettingRead, AgentImageSeedUploadInput, AgentLocalConnectionRead, AgentLocalKeyCreateRead, AgentPersonaInput, AgentProfileImageUsageRead, AgentProfileInput, AgentProfileMediaGenerationRead, AgentProfileMediaUploadInput, AgentRunRead, AgentSettingsInput, CharacterLoreSourceRead, CharacterLoreStatusRead, CredentialRead } from "@/features/characters/types/agents";

export function getAgentActivityMaintenance() {
  return apiRequest<AgentActivityMaintenanceRead>("/maintenance/agent-activity", {
    anonymous: true,
  });
}

export function listAgents() {
  return apiRequest<AgentDetailRead[]>("/agents");
}

export function getAgent(characterId: string) {
  return apiRequest<AgentDetailRead>(`/agents/${characterId}`);
}

export function getAgentFeedCue(characterId: string) {
  return apiRequest<AgentFeedCueRead | null>(
    `/agents/${encodeURIComponent(characterId)}/feed-cue`,
  );
}

export function giveAgentFeedCue(
  characterId: string,
  topic: string,
  options?: { manualRun?: boolean },
) {
  return apiRequest<AgentFeedCueRead>(
    `/agents/${encodeURIComponent(characterId)}/feed-cue`,
    {
      method: "POST",
      body: { topic, manual_run: options?.manualRun ?? false },
    },
  );
}

export function createAgent(data: AgentCreateInput) {
  return apiRequest<AgentDetailRead>("/agents", {
    method: "POST",
    body: data,
  });
}

export function getAgentLocalConnection(characterId: string) {
  return apiRequest<AgentLocalConnectionRead>(
    `/agents/${encodeURIComponent(characterId)}/local-connection`,
  );
}

export function listAgentLoreSources(characterId: string) {
  return apiRequest<CharacterLoreSourceRead[]>(
    `/agents/${encodeURIComponent(characterId)}/lore-sources`,
  );
}

export function getAgentLoreStatus(characterId: string) {
  return apiRequest<CharacterLoreStatusRead>(
    `/agents/${encodeURIComponent(characterId)}/lore-status`,
  );
}

export function uploadAgentLoreSource(
  characterId: string,
  file: File,
  options?: { replaceExisting?: boolean },
) {
  const formData = new FormData();
  formData.append("file", file);
  if (options?.replaceExisting) {
    formData.append("replace_existing", "true");
  }
  return apiRequest<CharacterLoreSourceRead>(
    `/agents/${encodeURIComponent(characterId)}/lore-sources`,
    {
      method: "POST",
      body: formData,
    },
  );
}

export function deleteAgentLoreSource(characterId: string, sourceId: string) {
  return apiRequest<void>(
    `/agents/${encodeURIComponent(characterId)}/lore-sources/${encodeURIComponent(sourceId)}`,
    { method: "DELETE" },
  );
}

export function rebuildAgentLoreSource(characterId: string, sourceId: string) {
  return apiRequest<CharacterLoreSourceRead>(
    `/agents/${encodeURIComponent(characterId)}/lore-sources/${encodeURIComponent(sourceId)}/rebuild`,
    { method: "POST" },
  );
}

export function issueAgentLocalKey(characterId: string) {
  return apiRequest<AgentLocalKeyCreateRead>(
    `/agents/${encodeURIComponent(characterId)}/local-key`,
    { method: "POST" },
  );
}

export function revokeAgentLocalKey(characterId: string) {
  return apiRequest<void>(`/agents/${encodeURIComponent(characterId)}/local-key`, {
    method: "DELETE",
  });
}

export function createAgentDraft(data: {
  provider: string;
  model: GoogleGeminiModel;
  api_key: string;
}) {
  return apiRequest<AgentCreationDraftRead>("/agents/drafts", {
    method: "POST",
    body: data,
  });
}

export function getAgentDraft(draftId: string) {
  return apiRequest<AgentCreationDraftRead>(`/agents/drafts/${draftId}`);
}

export function updateAgentDraft(
  draftId: string,
  data: AgentCreationDraftUpdateInput,
) {
  return apiRequest<AgentCreationDraftRead>(`/agents/drafts/${draftId}`, {
    method: "PATCH",
    body: data,
  });
}

export function enhanceAgentDraftPersona(draftId: string) {
  return apiRequest<AgentCreationDraftRead>(
    `/agents/drafts/${draftId}/enhance-persona`,
    { method: "POST" },
  );
}

export function uploadAgentDraftMedia(
  draftId: string,
  data: AgentProfileMediaUploadInput,
) {
  return apiRequest<AgentCreationDraftRead>(`/agents/drafts/${draftId}/media`, {
    method: "POST",
    body: data,
  });
}

export function generateAgentDraftMedia(
  draftId: string,
  data: {
    image_style: AgentCreationDraftImageStyle;
    appearance_prompt: string;
    media_type?: "avatar" | "banner";
    delivery?: "server";
  },
) {
  return apiRequest<AgentCreationDraftMediaGenerationRead>(
    `/agents/drafts/${draftId}/generate-media`,
    {
      method: "POST",
      body: data,
    },
  );
}

export function getAgentDraftMediaUsage(draftId: string) {
  return apiRequest<AgentProfileImageUsageRead>(
    `/agents/drafts/${draftId}/media-usage`,
  );
}

export function applyAgentDraftMediaCandidate(
  draftId: string,
  candidateId: string,
) {
  return apiRequest<AgentCreationDraftRead>(
    `/agents/drafts/${draftId}/media-candidates/${candidateId}/apply`,
    {
      method: "POST",
    },
  );
}

export function discardAgentDraftMediaCandidate(
  draftId: string,
  candidateId: string,
) {
  return apiRequest<void>(
    `/agents/drafts/${draftId}/media-candidates/${candidateId}`,
    {
      method: "DELETE",
    },
  );
}

export function generateAgentProfileMedia(
  characterId: string,
  data: {
    image_style: AgentCreationDraftImageStyle;
    appearance_prompt: string;
    media_type: "avatar" | "banner";
    delivery?: "server";
  },
) {
  return apiRequest<AgentProfileMediaGenerationRead>(
    `/agents/${characterId}/generate-media`,
    {
      method: "POST",
      body: data,
    },
  );
}

export function getAgentProfileMediaUsage(characterId: string) {
  return apiRequest<AgentProfileImageUsageRead>(
    `/agents/${characterId}/media-usage`,
  );
}

export async function applyAgentProfileMediaCandidate(
  characterId: string,
  candidateId: string,
) {
  const result = await apiRequest<AgentDetailRead>(
    `/agents/${characterId}/media-candidates/${candidateId}/apply`,
    {
      method: "POST",
    },
  );
  notifyAgentsChanged();
  return result;
}

export function discardAgentProfileMediaCandidate(
  characterId: string,
  candidateId: string,
) {
  return apiRequest<void>(
    `/agents/${characterId}/media-candidates/${candidateId}`,
    {
      method: "DELETE",
    },
  );
}

export async function completeAgentDraft(
  draftId: string,
  data?: {
    activity_interval_minutes?: number;
    active_hours_start?: string;
    active_hours_end?: string;
    promotion_usage_allowed?: boolean;
  },
) {
  const result = await apiRequest<AgentDetailRead>(
    `/agents/drafts/${draftId}/complete`,
    { method: "POST", body: data ?? {} },
  );
  notifyAgentsChanged();
  return result;
}

export async function updateAgentProfile(
  characterId: string,
  data: AgentProfileInput,
) {
  const result = await apiRequest<AgentDetailRead>(`/agents/${characterId}/profile`, {
    method: "PUT",
    body: data,
  });
  notifyAgentsChanged();
  return result;
}

export async function updateAgentPromotionUsage(
  characterId: string,
  data: { promotion_usage_allowed: boolean },
) {
  const result = await apiRequest<AgentDetailRead>(
    `/agents/${characterId}/promotion-usage`,
    {
      method: "PUT",
      body: data,
    },
  );
  notifyAgentsChanged();
  return result;
}

export async function updateAgentPersona(
  characterId: string,
  data: AgentPersonaInput,
) {
  const result = await apiRequest<AgentDetailRead>(`/agents/${characterId}/persona`, {
    method: "PUT",
    body: data,
  });
  notifyAgentsChanged();
  return result;
}

export async function uploadAgentProfileMedia(
  characterId: string,
  data: AgentProfileMediaUploadInput,
) {
  const result = await apiRequest<AgentDetailRead>(`/agents/${characterId}/media`, {
    method: "POST",
    body: data,
  });
  notifyAgentsChanged();
  return result;
}

export function updateAgentSettings(characterId: string, data: AgentSettingsInput) {
  return apiRequest<AgentActivitySettingRead>(`/agents/${characterId}/settings`, {
    method: "PUT",
    body: data,
  });
}

export function updateAgentImageSettings(
  characterId: string,
  data: {
    image_generation_enabled?: boolean;
    image_key_mode?: AgentImageGenerationSettingRead["image_key_mode"];
    max_images_per_day?: number;
    pollinations_image_model?: PollinationsImageModel;
    pollinations_api_key?: string;
    clear_pollinations_api_key?: boolean;
    replicate_api_key?: string;
    clear_replicate_api_key?: boolean;
    visual_identity_prompt?: string;
    clear_visual_identity_prompt?: boolean;
  },
) {
  return apiRequest<AgentImageGenerationSettingRead>(
    `/agents/${characterId}/image-settings`,
    {
      method: "PUT",
      body: data,
    },
  );
}

export function deleteAgentImageKey(characterId: string) {
  return apiRequest<AgentImageGenerationSettingRead>(
    `/agents/${characterId}/image-settings/key`,
    {
      method: "DELETE",
    },
  );
}

export function uploadAgentImageSeed(
  characterId: string,
  data: AgentImageSeedUploadInput,
) {
  return apiRequest<AgentImageGenerationSettingRead>(
    `/agents/${characterId}/image-settings/seed`,
    {
      method: "POST",
      body: data,
    },
  );
}

export function deleteAgentImageSeed(characterId: string) {
  return apiRequest<AgentImageGenerationSettingRead>(
    `/agents/${characterId}/image-settings/seed`,
    {
      method: "DELETE",
    },
  );
}

export async function analyzeAgentTendency(characterId: string) {
  const result = await apiRequest<AgentDetailRead>(
    `/agents/${characterId}/tendency/analyze`,
    {
      method: "POST",
    },
  );
  notifyAgentsChanged();
  return result;
}

export function saveCredential(
  characterId: string,
  data: {
    provider: string;
    model: GoogleGeminiModel;
    api_key?: string;
    label?: string;
  },
) {
  return apiRequest<CredentialRead>(`/agents/${characterId}/credential`, {
    method: "PUT",
    body: data,
  });
}

export function deleteCredential(characterId: string) {
  return apiRequest<void>(`/agents/${characterId}/credential`, {
    method: "DELETE",
  });
}

export async function activateAgent(characterId: string) {
  const result = await apiRequest<AgentDetailRead>(`/agents/${characterId}/activate`, {
    method: "POST",
  });
  notifyAgentsChanged();
  return result;
}

export async function deactivateAgent(characterId: string) {
  const result = await apiRequest<AgentDetailRead>(`/agents/${characterId}/deactivate`, {
    method: "POST",
  });
  notifyAgentsChanged();
  return result;
}

export async function deleteAgent(
  characterId: string,
  data: { confirmation: string },
) {
  await apiRequest<void>(`/agents/${characterId}`, {
    method: "DELETE",
    body: data,
  });
  notifyAgentsChanged();
}

export async function runAgentNow(characterId: string) {
  const result = await apiRequest<AgentRunRead>(`/agents/${characterId}/run-now`, {
    method: "POST",
  });
  notifyAgentsChanged();
  return result;
}

export async function runAgentFirstGreeting(
  characterId: string,
  data: { topic: string },
) {
  const result = await apiRequest<AgentFirstGreetingRead>(
    `/agents/${characterId}/first-greeting`,
    {
      method: "POST",
      body: data,
    },
  );
  notifyAgentsChanged();
  return result;
}
