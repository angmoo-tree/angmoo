import { apiRequest } from "@/lib/http/api-request";
import type { SecretMetadata, SecretWrite } from "@/components/ui/credential-fields";

export type CredentialPurpose = "sns" | "image" | "chat" | "vision";
export function worldCredentialTransport(worldId: string, actorId: string, purpose: CredentialPurpose) {
  const path = `/worlds/${encodeURIComponent(worldId)}/world-characters/${encodeURIComponent(actorId)}/credentials/${purpose}`;
  return {
    read: (signal: AbortSignal) => apiRequest<SecretMetadata>(path, { signal }),
    save: ({ label: _label, ...data }: SecretWrite, signal: AbortSignal) => { void _label; return apiRequest<SecretMetadata>(path, { signal, method: "PUT", body: data }); },
    remove: (expected_revision: number, signal: AbortSignal) => apiRequest<SecretMetadata>(path, { signal, method: "DELETE", body: { expected_revision } }),
  };
}
