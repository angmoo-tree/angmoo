import type {
  AgentActivityMaintenanceRead,
  AgentDetailRead,
  AgentFeedCueRead,
} from "../model/social-agent-contract";
import { requestSocialApi } from "./social-feed-client";

export function getAgentActivityMaintenance() {
  return requestSocialApi<AgentActivityMaintenanceRead>(
    "/maintenance/agent-activity",
    { anonymous: true },
  );
}

export function listAgents() {
  return requestSocialApi<AgentDetailRead[]>("/agents", {
    clearAuthOnUnauthorized: true,
  });
}

export function getAgentFeedCue(characterId: string) {
  return requestSocialApi<AgentFeedCueRead | null>(
    `/agents/${encodeURIComponent(characterId)}/feed-cue`,
    { clearAuthOnUnauthorized: true },
  );
}

export function giveAgentFeedCue(
  characterId: string,
  topic: string,
  options?: { manualRun?: boolean },
) {
  return requestSocialApi<AgentFeedCueRead>(
    `/agents/${encodeURIComponent(characterId)}/feed-cue`,
    {
      method: "POST",
      body: { topic, manual_run: options?.manualRun ?? false },
      clearAuthOnUnauthorized: true,
    },
  );
}
