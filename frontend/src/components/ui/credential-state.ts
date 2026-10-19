import { ApiRequestError } from "@/lib/http/error-contract";

export type SecretMetadata = { provider: string; model: string; thinking_level: string | null; has_key: boolean; has_partner_key?: boolean; fingerprint: string | null; revision: number; configuration_revision?: number | null; key_revision?: number | null };
export type SecretKeyMetadata = { provider: string; has_key: boolean; fingerprint: string | null; key_revision: number };
export type SecretProfile = { label: string; provider: string; model: string; thinking_level: string | null };
export type SecretWrite = SecretProfile & { api_key?: string; expected_revision: number; expected_configuration_revision?: number; expected_key_revision?: number };
export type CredentialFailure = "loadFailed" | "keyLoadFailed" | "saveFailed" | "deleteFailed" | "conflict" | "unknown";
export const profileKey = (p: SecretProfile | SecretMetadata) => `${p.provider}:${p.model}:${p.thinking_level ?? ""}`;

export function sameCredential(a: SecretMetadata, b: SecretMetadata) {
  return a.revision === b.revision && a.key_revision === b.key_revision &&
    profileKey(a) === profileKey(b) && a.has_key === b.has_key &&
    a.has_partner_key === b.has_partner_key && a.fingerprint === b.fingerprint;
}

export function credentialFailure(error: unknown, deleting: boolean): CredentialFailure {
  if (error instanceof ApiRequestError) {
    if (error.status === 409) return "conflict";
    // A gateway/transport failure cannot prove whether the upstream committed.
    if (error.status < 500) return deleting ? "deleteFailed" : "saveFailed";
  }
  return "unknown";
}
