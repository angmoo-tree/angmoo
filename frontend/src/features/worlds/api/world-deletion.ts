import { apiRequest } from "./worlds";
import type { WorldDeletionCommand, WorldDeletionPreview, WorldDeletionReceipt } from "../types/world-deletion";

const STATES = new Set(["accepted", "draining", "purging", "cleaning", "verifying", "retry_wait", "failed", "completed"]);
function checkedReceipt(value: WorldDeletionReceipt): WorldDeletionReceipt {
  if (!value || typeof value.request_id !== "string" || typeof value.world_id !== "string" || !STATES.has(value.state) || typeof value.can_retry !== "boolean") {
    throw new Error("world_deletion_receipt_invalid");
  }
  return value;
}
export async function previewWorldDeletion(worldId: string, signal?: AbortSignal) {
  const value = await apiRequest<WorldDeletionPreview>(`/worlds/${encodeURIComponent(worldId)}/deletion-preview`, { signal });
  if (value.world_id !== worldId || typeof value.stored_name !== "string" || !Number.isInteger(value.row_version) || typeof value.can_delete !== "boolean") throw new Error("world_deletion_preview_invalid");
  return value;
}
export async function deleteWorld(worldId: string, body: WorldDeletionCommand, signal?: AbortSignal) {
  const value = checkedReceipt(await apiRequest<WorldDeletionReceipt>(`/worlds/${encodeURIComponent(worldId)}`, { method: "DELETE", body, signal }));
  if (value.world_id !== worldId) throw new Error("world_deletion_scope_invalid");
  return value;
}
export async function getWorldDeletion(requestId: string, signal?: AbortSignal) {
  const value = checkedReceipt(await apiRequest<WorldDeletionReceipt>(`/world-deletions/${encodeURIComponent(requestId)}`, { signal }));
  if (value.request_id !== requestId) throw new Error("world_deletion_scope_invalid");
  return value;
}
export async function listWorldDeletions(signal?: AbortSignal) {
  const values = await apiRequest<WorldDeletionReceipt[]>("/world-deletions?active=true", { signal });
  if (!Array.isArray(values)) throw new Error("world_deletion_receipt_invalid");
  return values.map(checkedReceipt);
}
export async function retryWorldDeletion(requestId: string, signal?: AbortSignal) {
  const value = checkedReceipt(await apiRequest<WorldDeletionReceipt>(`/world-deletions/${encodeURIComponent(requestId)}/retry`, { method: "POST", signal }));
  if (value.request_id !== requestId) throw new Error("world_deletion_scope_invalid");
  return value;
}
