import type {
PostDetail
} from "@/lib/community";
import { apiRequest } from "@/lib/http/api-request";
import {
AUTH_CHANGED_EVENT as SHARED_AUTH_CHANGED_EVENT,
cacheUser as cacheSharedUser,
clearLegacyAuthStorage as clearSharedLegacyAuthStorage,
clearStoredUser as clearSharedStoredUser,
getStoredUser as getSharedStoredUser,
isAuthError as isSharedAuthError,
notifyAuthChanged as notifySharedAuthChanged,
storeUser as storeSharedUser,
type UserRead as SharedUserRead,
} from "@/shared/auth/public";

export {
DEFAULT_MESSAGE_GOOGLE_MODEL,MESSAGE_GOOGLE_GEMINI_MODELS,createMessageThread,deleteMessageThread,
getCharacterMessageSettings,
getMessageSettings,
getMessageThread,
listMessageThreads,retryThreadMessage,
sendThreadMessage,
updateCharacterMessageSettings,
updateMessageSettings,
updateMessageThread
} from "@/features/chat/public";
export type {
CharacterMessageSettingRead,
MessageCredentialSource,
MessageGoogleGeminiModel,
MessageMessageRead,
MessageSendRead,
MessageSettingsRead,
MessageThreadListRead,
MessageThreadRead
} from "@/features/chat/public";

export { GOOGLE_GEMINI_MODELS } from "@/features/characters/config/model-options";

export { DEFAULT_GOOGLE_GEMINI_MODEL,DEFAULT_USER_IMAGE_MODEL,REPLICATE_API_TOKEN_GUIDE_URL,REPLICATE_API_TOKEN_URL,REPLICATE_PRICING_URL,USER_IMAGE_MODELS } from "@/features/characters/config/model-options";

export type { GoogleGeminiModel,PollinationsImageModel } from "@/features/characters/config/model-options";

export { getGoogleGeminiModelNote } from "@/features/characters/config/model-options";
export type { AgentExecutionMode,WritingRepetitionLevel } from "@/features/characters/types/agents";

export type UserRead = SharedUserRead;

export type AuthRead = {
  user: UserRead;
  profile_setup_required: boolean;
};









export type { CredentialRead } from "@/features/characters/types/agents";

export type { AgentImageGenerationSettingRead } from "@/features/characters/types/agents";

export type { AgentActivitySettingRead } from "@/features/characters/types/agents";

export type { AgentActionRangeRead } from "@/features/characters/types/agents";

export type { AgentSlotRead } from "@/features/characters/types/agents";

export type { AgentActivityLogRead } from "@/features/characters/types/agents";

export type { AgentActivityProfileReadinessRead } from "@/features/characters/types/agents";

export type { AgentFeedCueRead } from "@/features/characters/types/agents";

export type { AgentActivitySummaryRead } from "@/features/characters/types/agents";

export type { AgentFirstGreetingRead } from "@/features/characters/types/agents";

export type { AgentRunRead } from "@/features/characters/types/agents";

export type { AgentActivityMaintenanceRead } from "@/features/characters/types/agents";

export type { AgentPromotionUsageRead } from "@/features/characters/types/agents";

export type { AgentDetailRead } from "@/features/characters/types/agents";

export type { AgentTypeCounts } from "@/features/characters/types/agents";

export { getAgentTypeCounts } from "@/features/characters/utils/agent-counts";

export type { AgentLocalConnectionRead } from "@/features/characters/types/agents";

export type { AgentLocalKeyCreateRead } from "@/features/characters/types/agents";

export type { CharacterLoreSourceRead } from "@/features/characters/types/agents";

export type { CharacterLoreStatusRead } from "@/features/characters/types/agents";

export type { AgentCreateInput } from "@/features/characters/types/agents";

export type { AgentProfileInput } from "@/features/characters/types/agents";

export type { AgentPersonaInput } from "@/features/characters/types/agents";

export type { AgentProfileMediaUploadInput } from "@/features/characters/types/agents";

export type { AgentImageSeedUploadInput } from "@/features/characters/types/agents";

export type { AgentCreationDraftImageStyle } from "@/features/characters/types/agents";

export type { AgentCreationDraftRead } from "@/features/characters/types/agents";

export type { AgentCreationDraftUpdateInput } from "@/features/characters/types/agents";

export type { AgentCreationDraftMediaResult } from "@/features/characters/types/agents";

export type { AgentProfileImageUsageStatusRead } from "@/features/characters/types/agents";

export type { AgentProfileImageUsageRead } from "@/features/characters/types/agents";

export type { AgentCreationDraftMediaGenerationRead } from "@/features/characters/types/agents";

export type { AgentProfileMediaGenerationRead } from "@/features/characters/types/agents";

export { AGENTS_CHANGED_EVENT,AGENT_AUTONOMY_MUTATION_EVENT } from "@/features/characters/stores/agent-session";
export type { AgentSettingsInput } from "@/features/characters/types/agents";


export const AUTH_CHANGED_EVENT = SHARED_AUTH_CHANGED_EVENT;



export type { AgentAutonomyMutationState } from "@/features/characters/types/agents";

export type { AgentAutonomyMutationEventDetail } from "@/features/characters/types/agents";







export function getStoredUser() {
  return getSharedStoredUser();
}





export function notifyAuthChanged() {
  notifySharedAuthChanged();
}







export function storeUser(user: UserRead) {
  storeSharedUser(user);
}

export function cacheUser(user: UserRead) {
  cacheSharedUser(user);
}



export function clearStoredUser() {
  clearSharedStoredUser();
}

export function clearLegacyAuthStorage() {
  clearSharedLegacyAuthStorage();
}



export { markFirstAgentWelcomePromptPending } from "@/features/characters/stores/agent-session";

export { hasFirstAgentWelcomePromptPending } from "@/features/characters/stores/agent-session";

export { clearFirstAgentWelcomePromptPending } from "@/features/characters/stores/agent-session";









export { getAgentAutonomyMutationStates } from "@/features/characters/stores/agent-session";

export { getAgentAutonomyMutationState } from "@/features/characters/stores/agent-session";

export { setAgentAutonomyMutationState } from "@/features/characters/stores/agent-session";

export { clearAgentAutonomyMutationState } from "@/features/characters/stores/agent-session";

export function isAuthError(err: unknown) {
  return isSharedAuthError(err);
}




export { fetchAuthenticatedMediaObjectUrl } from "@/lib/media/authenticated-media";


























export { getAgentActivityMaintenance } from "@/features/characters/api/agents";







export { listAgents } from "@/features/characters/api/agents";

export { getAgent } from "@/features/characters/api/agents";

export { getAgentFeedCue } from "@/features/characters/api/agents";

export { giveAgentFeedCue } from "@/features/characters/api/agents";

export { createAgent } from "@/features/characters/api/agents";

export { getAgentLocalConnection } from "@/features/characters/api/agents";

export { listAgentLoreSources } from "@/features/characters/api/agents";

export { getAgentLoreStatus } from "@/features/characters/api/agents";

export { uploadAgentLoreSource } from "@/features/characters/api/agents";

export { deleteAgentLoreSource } from "@/features/characters/api/agents";

export { rebuildAgentLoreSource } from "@/features/characters/api/agents";

export { issueAgentLocalKey } from "@/features/characters/api/agents";

export { revokeAgentLocalKey } from "@/features/characters/api/agents";

export { createAgentDraft } from "@/features/characters/api/agents";

export { getAgentDraft } from "@/features/characters/api/agents";

export { updateAgentDraft } from "@/features/characters/api/agents";

export { enhanceAgentDraftPersona } from "@/features/characters/api/agents";

export { uploadAgentDraftMedia } from "@/features/characters/api/agents";

export { generateAgentDraftMedia } from "@/features/characters/api/agents";

export { getAgentDraftMediaUsage } from "@/features/characters/api/agents";

export { applyAgentDraftMediaCandidate } from "@/features/characters/api/agents";

export { discardAgentDraftMediaCandidate } from "@/features/characters/api/agents";

export { generateAgentProfileMedia } from "@/features/characters/api/agents";

export { getAgentProfileMediaUsage } from "@/features/characters/api/agents";

export { applyAgentProfileMediaCandidate } from "@/features/characters/api/agents";

export { discardAgentProfileMediaCandidate } from "@/features/characters/api/agents";

export { completeAgentDraft } from "@/features/characters/api/agents";

export { updateAgentProfile } from "@/features/characters/api/agents";

export { updateAgentPromotionUsage } from "@/features/characters/api/agents";

export { updateAgentPersona } from "@/features/characters/api/agents";

export { uploadAgentProfileMedia } from "@/features/characters/api/agents";

export { updateAgentSettings } from "@/features/characters/api/agents";

export { updateAgentImageSettings } from "@/features/characters/api/agents";

export { deleteAgentImageKey } from "@/features/characters/api/agents";

export { uploadAgentImageSeed } from "@/features/characters/api/agents";

export { deleteAgentImageSeed } from "@/features/characters/api/agents";

export { analyzeAgentTendency } from "@/features/characters/api/agents";

export { saveCredential } from "@/features/characters/api/agents";

export { deleteCredential } from "@/features/characters/api/agents";

export { activateAgent } from "@/features/characters/api/agents";

export { deactivateAgent } from "@/features/characters/api/agents";

export { deleteAgent } from "@/features/characters/api/agents";

export { runAgentNow } from "@/features/characters/api/agents";

export { runAgentFirstGreeting } from "@/features/characters/api/agents";

export function createCommunityPost(data: {
  title: string;
  body: string;
  author_character_id?: string;
}) {
  return apiRequest<PostDetail>("/posts", {
    method: "POST",
    body: data,
  });
}

export function likeCommunityPost(postId: string, characterId: string) {
  return apiRequest<PostDetail>(`/posts/${postId}/likes`, {
    method: "POST",
    body: { character_id: characterId },
  });
}

export { claimLocalOwner,completeGoogleSignup,createLocalBootstrapChallenge,deleteCurrentAccount,getLocalBootstrapStatus,getMe,googleLogin,issueLocalSession,linkGoogleAccount,login,logoutCurrentSession,signup,updateMe,updateMePreferences } from "@/features/identity/api/identity";
export type { GoogleLoginRead,LocalBootstrapRead,LocalOwnerCandidateRead,PendingGoogleSignup } from "@/features/identity/types/identity";
export { clearPendingGoogleSignup,getPendingGoogleSignup,hasPendingGoogleSignup,storePendingGoogleSignup } from "@/features/identity/utils/pending-signup";
export { clearAuth,storeAuth } from "@/lib/auth/browser-session";
