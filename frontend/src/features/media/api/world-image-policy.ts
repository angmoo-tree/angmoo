import { apiRequest } from "@/lib/http/api-request";
import type { SecretMetadata, SecretWrite, SecretKeyMetadata } from "@/components/ui/credential-fields";
import type { Connection } from "../types/media";
export type WorldImageSettings = { appearance: string; style: string; negative: string; reference_enabled: boolean; reference_asset_id: string | null; reference_url?: string | null; profiles: Record<string, { options: Record<string, unknown>; connection?: Connection | null }> };
export type WorldImagePolicy = { world_id: string; world_character_id: string; revision: number; generation_limit: number | null; vision_limit: number | null; generation_enabled: boolean; vision_enabled: boolean; generation_settings: Partial<WorldImageSettings>; generation_usage: number; vision_usage: number; timezone: string; reset_at: string };
const path = (world: string, actor: string) => `/worlds/${encodeURIComponent(world)}/world-characters/${encodeURIComponent(actor)}`;
export const getWorldImagePolicy = (world: string, actor: string, signal?: AbortSignal) => apiRequest<WorldImagePolicy>(`${path(world, actor)}/image-policy`, { signal });
export const patchWorldImagePolicy = (world: string, actor: string, expected_revision: number, changes: Partial<Pick<WorldImagePolicy, "generation_limit" | "vision_limit" | "generation_enabled" | "vision_enabled" | "generation_settings">>, signal?: AbortSignal) => apiRequest<WorldImagePolicy>(`${path(world, actor)}/image-policy`, { signal, method: "PATCH", body: { expected_revision, ...changes } });
export const checkWorldImagePolicy = (world: string, actor: string, expected_revision: number, changes: Parameters<typeof patchWorldImagePolicy>[3], signal?: AbortSignal) => apiRequest<WorldImagePolicy>(`${path(world, actor)}/image-policy/check`, { signal, method: "POST", body: { expected_revision, ...changes } });
export function imageCredentialTransport(world: string, actor: string, extra: { partner_api_key?: string; clear_partner_key?: boolean; expected_configuration_revision?: number; provider?: string; expected_key_revision?: number } = {}) {
  const endpoint = `${path(world, actor)}/credentials/image`;
  return { read: (signal: AbortSignal) => apiRequest<SecretMetadata>(endpoint, { signal }),
    readSelectedKey: (provider: string, signal: AbortSignal) => apiRequest<SecretKeyMetadata>(`${path(world, actor)}/image-provider-key/${encodeURIComponent(provider)}`, { signal }),
    save: ({ label: _label, ...data }: SecretWrite, signal: AbortSignal) => { void _label; const { provider: _provider, ...fields } = extra; void _provider; return apiRequest<SecretMetadata>(endpoint, { signal, method: "PUT", body: { ...data, ...fields } }); },
    remove: (expected_revision: number, signal: AbortSignal) => apiRequest<SecretMetadata>(endpoint, { signal, method: "DELETE", body: { expected_revision, provider: extra.provider, expected_key_revision: extra.expected_key_revision, expected_configuration_revision: extra.expected_configuration_revision } }) };
}
