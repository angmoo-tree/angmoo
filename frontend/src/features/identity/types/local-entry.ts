import type { UserRead } from "@/lib/auth/browser-session";
import type { LocalBootstrapRead, LocalClientState } from "./identity";
export type { LocalClientState } from "./identity";
export type LocalClientRequest = Omit<LocalClientState, "generation" | "state"> & { expected_generation: number };
export type ConnectionIntent = "active" | "ending" | "stopped" | "end_unconfirmed";
export type StoredConnection = { clientId: string; generation: number; intent: ConnectionIntent };
export type LocalEntryPhase = "checking" | "preparing" | "authenticated" | "selection_required" | "recovery_required" | "ending" | "stopped" | "end_unconfirmed" | "unavailable";
export type LocalEntrySnapshot = {
  sessionRevision: number;
  phase: LocalEntryPhase;
  user: UserRead | null;
  bootstrap: LocalBootstrapRead | null;
  errorCode: string | null;
};
