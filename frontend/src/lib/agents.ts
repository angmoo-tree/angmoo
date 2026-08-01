import type {
  CharacterRead,
  CharacterStateRead,
  FeedContentFilter,
  PostDetail,
  ProfileRef,
} from "@/lib/community";

export const GOOGLE_GEMINI_MODELS = [
  { value: "gemma-4-26b-a4b-it", label: "Gemma 4 26B" },
  { value: "gemini-3.1-flash-lite", label: "Gemini 3.1 Flash-Lite" },
  { value: "gemma-4-31b-it", label: "Gemma 4 31B" },
] as const;

export const MESSAGE_GOOGLE_GEMINI_MODELS = [
  { value: "gemini-2.5-flash-lite", label: "Gemini 2.5 Flash-Lite" },
  { value: "gemini-2.5-flash", label: "Gemini 2.5 Flash" },
  { value: "gemini-3.1-flash-lite", label: "Gemini 3.1 Flash-Lite" },
  { value: "gemma-4-26b-a4b-it", label: "Gemma 4 26B" },
  { value: "gemma-4-31b-it", label: "Gemma 4 31B" },
] as const;

export const DEFAULT_GOOGLE_GEMINI_MODEL = "gemini-3.1-flash-lite";
export const DEFAULT_MESSAGE_GOOGLE_MODEL = "gemini-2.5-flash-lite";
export const USER_IMAGE_MODELS = [
  {
    value: "replicate-zimage-turbo-lora",
    label: "Replicate · Z-Image Turbo LoRA",
    note: "새 장면 생성 · H100 시간 과금 · 약 $0.001/장",
    priceNote: "테스트 기준 약 $0.0009~$0.0012 수준이며 실행시간에 따라 달라집니다.",
    officialUrl: "https://replicate.com/prunaai/z-image-turbo-lora",
  },
  {
    value: "replicate-p-image-edit",
    label: "Replicate · P-Image-Edit",
    note: "참조 이미지 편집 · Replicate 표기 $0.01/장",
    priceNote: "Angmoo 자체 가격이 아닌 Replicate 모델 페이지 표기 기준입니다.",
    officialUrl: "https://replicate.com/prunaai/p-image-edit",
  },
] as const;
export const DEFAULT_USER_IMAGE_MODEL = "replicate-zimage-turbo-lora";
export const REPLICATE_API_TOKEN_GUIDE_URL =
  "https://replicate.com/docs/topics/security/api-tokens";
export const REPLICATE_API_TOKEN_URL =
  "https://replicate.com/account/api-tokens";
export const REPLICATE_PRICING_URL = "https://replicate.com/pricing";
export const MAX_LLM_AGENTS_PER_USER = 3;
export const MAX_LOCAL_AGENTS_PER_USER = 3;
export const MAX_AGENTS_PER_USER =
  MAX_LLM_AGENTS_PER_USER + MAX_LOCAL_AGENTS_PER_USER;
export const LLM_AGENT_LIMIT_MESSAGE = `서버 LLM 앵무는 계정당 최대 ${MAX_LLM_AGENTS_PER_USER}개까지 만들 수 있습니다.`;
export const LOCAL_AGENT_LIMIT_MESSAGE = `외부 연결 앵무는 계정당 최대 ${MAX_LOCAL_AGENTS_PER_USER}개까지 만들 수 있습니다.`;
export const AGENT_LIMIT_MESSAGE = `서버 LLM 앵무 ${MAX_LLM_AGENTS_PER_USER}개와 외부 연결 앵무 ${MAX_LOCAL_AGENTS_PER_USER}개를 모두 만들었습니다.`;

export type GoogleGeminiModel = (typeof GOOGLE_GEMINI_MODELS)[number]["value"];
export type MessageGoogleGeminiModel =
  (typeof MESSAGE_GOOGLE_GEMINI_MODELS)[number]["value"];
export type PollinationsImageModel = (typeof USER_IMAGE_MODELS)[number]["value"];

export function getGoogleGeminiModelNote(model: GoogleGeminiModel) {
  if (model === "gemma-4-31b-it" || model === "gemma-4-26b-a4b-it") {
    return "Gemma 4는 추론형 모델이라 응답이 더 느리거나 불안정할 수 있습니다.";
  }
  return null;
}
export type WritingRepetitionLevel = "off" | "light" | "normal" | "strong";
export type AgentExecutionMode = "llm" | "local";

export type UserRead = {
  id: string;
  email: string | null;
  display_name: string;
  display_name_updated_at: string | null;
  display_name_change_available_at: string | null;
  profile_setup_completed: boolean;
  feed_content_filter: FeedContentFilter;
  is_admin: boolean;
};

export type AuthRead = {
  user: UserRead;
  profile_setup_required: boolean;
};

export type GoogleLoginRead = {
  user: UserRead | null;
  profile_setup_required: boolean;
  signup_required: boolean;
  expires_at: string | null;
  email: string | null;
};

export type PendingGoogleSignup = {
  expires_at: string;
  email: string;
};

export type CredentialRead = {
  id: string;
  owner_id: string;
  character_id: string | null;
  provider: string;
  model: string;
  label: string;
  key_fingerprint: string | null;
  enabled: boolean;
  cooldown_until: string | null;
};

export type AgentImageGenerationSettingRead = {
  character_id: string;
  image_generation_enabled: boolean;
  image_key_mode: "service" | "user" | "disabled";
  max_images_per_day: number;
  pollinations_image_model: string;
  seed_image_url: string | null;
  key_fingerprint: string | null;
  has_pollinations_api_key: boolean;
  replicate_key_fingerprint: string | null;
  has_replicate_api_key: boolean;
  service_image_available: boolean;
  service_image_model: string;
  service_image_model_label: string;
  service_free_quota_limit: number;
  service_free_quota_used: number;
  service_free_quota_remaining: number;
  service_free_quota_date: string | null;
  visual_identity_prompt_available: boolean;
  visual_identity_prompt: string | null;
  visual_identity_mode: "manual" | "auto" | "none";
  visual_identity_source_hash: string | null;
  updated_at: string;
};

export type AgentActivitySettingRead = {
  character_id: string;
  auto_enabled: boolean;
  activity_level: string;
  activity_interval_minutes: number;
  comment_cooldown_minutes: number;
  max_comments_per_day: number;
  post_cooldown_hours: number;
  max_posts_per_day: number;
  allow_post: boolean;
  allow_reply: boolean;
  allow_like: boolean;
  allow_repost: boolean;
  allow_follow: boolean;
  allow_unfollow: boolean;
  allow_observe: boolean;
  tendency_summary: string;
  tendency_action_ranges: Record<string, AgentActionRangeRead>;
  tendency_analysis_ready: boolean;
  tendency_updated_at: string | null;
  tendency_error: string | null;
  active_hours_start: string;
  active_hours_end: string;
  writing_temperature: number;
  writing_repetition_level: WritingRepetitionLevel;
  updated_at: string;
};

export type AgentActionRangeRead = {
  min: number;
  max: number;
  label: string;
  note: string;
};

export type AgentSlotRead = {
  agent_id: string;
  status: string;
  assigned_user_id: string | null;
  assigned_character_id: string | null;
  assigned_credential_id: string | null;
  next_tick_at: string | null;
  last_run_at: string | null;
  heartbeat_interval_seconds: number | null;
  locked_by_run_id: string | null;
  lease_expires_at: string | null;
  last_error: string | null;
  updated_at: string;
};

export type AgentActivityLogRead = {
  id: number;
  user_id: string;
  character_id: string;
  action_type: string;
  target_post_id: string | null;
  target_profile_type: "user" | "character" | null;
  target_profile_id: string | null;
  target_profile_name: string | null;
  target_profile_handle: string | null;
  target_profile_avatar_url: string | null;
  reason: string;
  result: string;
  created_at: string;
};

export type AgentFeedCueRead = {
  id: number;
  user_id: string;
  character_id: string;
  topic: string;
  status: string;
  consumed_run_id: string | null;
  consumed_post_id: string | null;
  created_at: string;
  consumed_at: string | null;
};

export type AgentActivitySummaryRead = {
  within_active_hours: boolean;
  allowed_actions: string[];
  blocked_reasons: Record<string, string>;
  last_activity_at: string | null;
  next_activity_at: string | null;
  manual_run_available_at: string | null;
  first_greeting_available_at: string | null;
  today_comment_count: number;
  max_comments_per_day: number;
  today_post_count: number;
  max_posts_per_day: number;
  today_like_count: number;
};

export type AgentFirstGreetingRead = {
  run_id: string;
  status: string;
  summary: string | null;
  character_id: string;
  post_id: string | null;
  post: PostDetail | null;
  image_attempt: Record<string, unknown> | null;
  first_greeting_available_at: string | null;
  gateway_result: Record<string, unknown>;
};

export type AgentActivityMaintenanceRead = {
  enabled: boolean;
  title: string;
  message: string;
  blocks_auto_ticks: boolean;
  blocks_run_now: boolean;
  blocks_feed_cues: boolean;
  auto_tick_allowlist_active: boolean;
  auto_tick_allowed_count: number;
  notice_enabled: boolean;
  notice_title: string;
  notice_message: string;
};

export type AgentPromotionUsageRead = {
  promotion_usage_allowed: boolean;
  promotion_usage_agreed_at: string | null;
  promotion_usage_revoked_at: string | null;
  promotion_usage_policy_version: string | null;
};

export type AgentDetailRead = {
  character: CharacterRead;
  state: CharacterStateRead | null;
  credential: CredentialRead | null;
  settings: AgentActivitySettingRead;
  image_settings: AgentImageGenerationSettingRead;
  promotion_usage: AgentPromotionUsageRead;
  assigned_slot: AgentSlotRead | null;
  activity_summary: AgentActivitySummaryRead;
  recent_activity: AgentActivityLogRead[];
};

export type AgentQuotaCounts = {
  llm: number;
  local: number;
};

export function getAgentQuotaCounts(agents: AgentDetailRead[]): AgentQuotaCounts {
  return agents.reduce<AgentQuotaCounts>(
    (counts, agent) => {
      if (agent.character.execution_mode === "local") {
        counts.local += 1;
      } else {
        counts.llm += 1;
      }
      return counts;
    },
    { llm: 0, local: 0 },
  );
}

export type AgentLocalConnectionRead = {
  character_id: string;
  execution_mode: AgentExecutionMode;
  has_active_key: boolean;
  token_prefix: string | null;
  last_used_at: string | null;
  created_at: string | null;
  revoked_at: string | null;
};

export type AgentLocalKeyCreateRead = {
  connection: AgentLocalConnectionRead;
  token: string;
};

export type CharacterLoreSourceRead = {
  id: string;
  owner_id: string;
  character_id: string;
  filename: string;
  extension: string;
  content_type: string | null;
  file_size_bytes: number;
  raw_text_hash: string;
  extracted_char_count: number;
  chunk_count: number;
  status: string;
  error_message: string | null;
  created_at: string;
  updated_at: string;
};

export type CharacterLoreStatusRead = {
  character_id: string;
  source_count: number;
  ready_source_count: number;
  chunk_count: number;
  ready_chunk_count: number;
  max_sources: number;
  max_text_chars: number;
  max_chunks: number;
  max_file_bytes: number;
};

export type AgentCreateInput = {
  execution_mode?: AgentExecutionMode;
  name: string;
  handle?: string;
  avatar_url?: string;
  banner_url?: string;
  one_liner: string;
  personality: string;
  speech_style: string;
  worldview: string;
  topic_preferences: string;
  safety_rules: string;
  provider: string;
  model: GoogleGeminiModel;
  api_key?: string;
  activity_interval_minutes?: number;
  active_hours_start?: string;
  active_hours_end?: string;
  promotion_usage_allowed?: boolean;
};

export type AgentProfileInput = {
  name?: string;
  handle?: string;
  avatar_url?: string;
  banner_url?: string;
  one_liner?: string;
};

export type AgentPersonaInput = {
  personality: string;
  speech_style: string;
  worldview: string;
  topic_preferences: string;
  safety_rules: string;
};

export type AgentProfileMediaUploadInput = {
  media_type: "avatar" | "banner";
  filename: string;
  content_type: string;
  data_base64: string;
};

export type AgentImageSeedUploadInput = {
  filename: string;
  content_type: string;
  data_base64: string;
};

export type AgentCreationDraftImageStyle = "기본" | "애니메풍" | "리얼풍" | "3D풍";

export type AgentCreationDraftRead = {
  id: string;
  provider: string;
  model: string;
  key_fingerprint: string | null;
  name: string;
  handle: string | null;
  one_liner: string;
  personality: string;
  speech_style: string;
  worldview: string;
  topic_preferences: string;
  safety_rules: string;
  image_style: string;
  appearance_prompt: string;
  avatar_temp_url: string | null;
  banner_temp_url: string | null;
  persona_enhance_available_at: string | null;
  media_generation_available_at: string | null;
  expires_at: string;
  created_at: string;
  updated_at: string;
};

export type AgentCreationDraftUpdateInput = Partial<
  Pick<
    AgentCreationDraftRead,
    | "name"
    | "handle"
    | "one_liner"
    | "personality"
    | "speech_style"
    | "worldview"
    | "topic_preferences"
    | "safety_rules"
    | "appearance_prompt"
  >
> & {
  image_style?: AgentCreationDraftImageStyle;
  avatar_temp_url?: string | null;
  banner_temp_url?: string | null;
};

export type AgentCreationDraftMediaResult = {
  media_type: "avatar" | "banner";
  url: string | null;
  candidate_id: string | null;
  candidate_url: string | null;
  usage_status: AgentProfileImageUsageStatusRead | null;
  width: number | null;
  height: number | null;
  ok: boolean;
  error: string | null;
};

export type AgentProfileImageUsageStatusRead = {
  bucket: "create_avatar" | "create_banner" | "profile_avatar" | "profile_banner";
  scope: "create" | "profile";
  media_type: "avatar" | "banner";
  used_today: number;
  remaining: number;
  limit: number;
  reset_at: string;
  next_available_at: string | null;
};

export type AgentProfileImageUsageRead = {
  items: AgentProfileImageUsageStatusRead[];
};

export type AgentCreationDraftMediaGenerationRead = {
  draft: AgentCreationDraftRead;
  results: AgentCreationDraftMediaResult[];
};

export type AgentProfileMediaGenerationRead = {
  results: AgentCreationDraftMediaResult[];
};

export type AgentSettingsInput = Partial<
  Pick<
    AgentActivitySettingRead,
    | "activity_interval_minutes"
    | "comment_cooldown_minutes"
    | "max_comments_per_day"
    | "post_cooldown_hours"
    | "max_posts_per_day"
    | "allow_post"
    | "allow_reply"
    | "allow_like"
    | "allow_repost"
    | "allow_follow"
    | "allow_unfollow"
    | "allow_observe"
    | "active_hours_start"
    | "active_hours_end"
    | "writing_temperature"
  >
>;

const LEGACY_TOKEN_KEY = ["angmoo", "authToken"].join(".");
const USER_KEY = "angmoo.user";
const PENDING_GOOGLE_SIGNUP_KEY = "angmoo.pendingGoogleSignup";
const FIRST_AGENT_WELCOME_PROMPT_KEY = "angmoo.firstAgentWelcomePromptPending";
export const AUTH_CHANGED_EVENT = "angmoo:auth-changed";
export const AGENTS_CHANGED_EVENT = "angmoo:agents-changed";
export const AGENT_AUTONOMY_MUTATION_EVENT = "angmoo:agent-autonomy-mutation";

const AGENT_AUTONOMY_MUTATION_KEY = "angmoo.agentAutonomyMutation";

export type AgentAutonomyMutationState = "activating" | "deactivating";

export type AgentAutonomyMutationEventDetail = {
  characterId: string;
  state: AgentAutonomyMutationState | null;
};

type RequestOptions = Omit<RequestInit, "body"> & {
  body?: unknown | FormData;
  anonymous?: boolean;
  suppressAuthFailureEvent?: boolean;
};

function getErrorMessage(payload: unknown, fallback: string) {
  if (
    payload &&
    typeof payload === "object" &&
    "detail" in payload &&
    typeof payload.detail === "string"
  ) {
    return payload.detail;
  }
  if (
    payload &&
    typeof payload === "object" &&
    "detail" in payload &&
    Array.isArray(payload.detail)
  ) {
    return getValidationMessage(payload.detail) ?? fallback;
  }
  return fallback;
}

function getValidationMessage(detail: unknown[]) {
  const first = detail.find((item) => item && typeof item === "object");
  if (!first || typeof first !== "object") return null;
  const loc = "loc" in first && Array.isArray(first.loc) ? first.loc : [];
  if (loc.includes("handle")) {
    return "핸들은 영문 소문자, 숫자, 밑줄(_)만 사용할 수 있습니다.";
  }
  const field = typeof loc.at(-1) === "string" ? loc.at(-1) : null;
  const type = "type" in first && typeof first.type === "string" ? first.type : "";
  const msg = "msg" in first && typeof first.msg === "string" ? first.msg : "";
  if (field === "activity_interval_minutes") {
    if (type.includes("greater") || msg.includes("greater than or equal")) {
      return "목표 활동 간격은 최소 30분 이상으로 설정해주세요.";
    }
    if (type.includes("less") || msg.includes("less than or equal")) {
      return "목표 활동 간격은 하루 1440분 이하로 설정해주세요.";
    }
    return "목표 활동 간격 값을 확인해주세요.";
  }
  if (field === "max_comments_per_day") {
    return "하루 리플 작성 상한은 0개 이상 60개 이하로 설정해주세요.";
  }
  if (field === "max_posts_per_day") {
    return "하루 글 쓰기 상한은 0개 이상 30개 이하로 설정해주세요.";
  }
  if ("msg" in first && typeof first.msg === "string") {
    return first.msg;
  }
  return null;
}

export function getStoredUser() {
  if (typeof window === "undefined") return null;
  const raw = window.sessionStorage.getItem(USER_KEY);
  if (!raw) return null;
  try {
    return normalizeStoredUser(JSON.parse(raw));
  } catch {
    return null;
  }
}

function normalizeStoredUser(value: unknown): UserRead | null {
  if (!value || typeof value !== "object") return null;
  const user = value as Partial<UserRead>;
  if (typeof user.id !== "string" || typeof user.display_name !== "string") {
    return null;
  }
  return {
    id: user.id,
    email: typeof user.email === "string" ? user.email : null,
    display_name: user.display_name,
    display_name_updated_at:
      typeof user.display_name_updated_at === "string"
        ? user.display_name_updated_at
        : null,
    display_name_change_available_at:
      typeof user.display_name_change_available_at === "string"
        ? user.display_name_change_available_at
        : null,
    profile_setup_completed:
      typeof user.profile_setup_completed === "boolean"
        ? user.profile_setup_completed
        : true,
    feed_content_filter: normalizeFeedContentFilter(user.feed_content_filter),
    is_admin: user.is_admin === true,
  };
}

function normalizeFeedContentFilter(value: unknown): FeedContentFilter {
  if (value === "posts" || value === "reposts" || value === "all") {
    return value;
  }
  return "all";
}

export function getPendingGoogleSignup(): PendingGoogleSignup | null {
  if (typeof window === "undefined") return null;
  const raw = window.sessionStorage.getItem(PENDING_GOOGLE_SIGNUP_KEY);
  if (!raw) return null;
  try {
    const parsed = JSON.parse(raw) as Partial<PendingGoogleSignup>;
    if (
      typeof parsed.expires_at !== "string" ||
      typeof parsed.email !== "string"
    ) {
      return null;
    }
    return {
      expires_at: parsed.expires_at,
      email: parsed.email,
    };
  } catch {
    return null;
  }
}

export function hasPendingGoogleSignup() {
  return Boolean(getPendingGoogleSignup());
}

export function notifyAuthChanged() {
  if (typeof window === "undefined") return;
  window.dispatchEvent(new Event(AUTH_CHANGED_EVENT));
}

export function storePendingGoogleSignup(auth: GoogleLoginRead) {
  if (!auth.expires_at || !auth.email) {
    throw new Error("Google signup information is missing.");
  }
  window.sessionStorage.setItem(
    PENDING_GOOGLE_SIGNUP_KEY,
    JSON.stringify({
      expires_at: auth.expires_at,
      email: auth.email,
    }),
  );
  window.sessionStorage.removeItem(USER_KEY);
  removeLegacyAuthTokens();
  window.localStorage.removeItem(USER_KEY);
  notifyAuthChanged();
}

export function clearPendingGoogleSignup() {
  if (typeof window === "undefined") return;
  window.sessionStorage.removeItem(PENDING_GOOGLE_SIGNUP_KEY);
  notifyAuthChanged();
}

export function storeAuth(auth: AuthRead) {
  window.sessionStorage.setItem(USER_KEY, JSON.stringify(auth.user));
  window.sessionStorage.removeItem(PENDING_GOOGLE_SIGNUP_KEY);
  removeLegacyAuthTokens();
  window.localStorage.removeItem(USER_KEY);
  notifyAuthChanged();
}

export function storeUser(user: UserRead) {
  cacheUser(user);
  notifyAuthChanged();
}

export function cacheUser(user: UserRead) {
  window.sessionStorage.setItem(USER_KEY, JSON.stringify(user));
  if (user.profile_setup_completed) {
    window.sessionStorage.removeItem(PENDING_GOOGLE_SIGNUP_KEY);
  }
  window.localStorage.removeItem(USER_KEY);
}

export function clearAuth() {
  window.sessionStorage.removeItem(USER_KEY);
  window.sessionStorage.removeItem(PENDING_GOOGLE_SIGNUP_KEY);
  removeLegacyAuthTokens();
  window.localStorage.removeItem(USER_KEY);
  notifyAuthChanged();
}

export function clearStoredUser() {
  if (typeof window === "undefined") return;
  window.sessionStorage.removeItem(USER_KEY);
  window.localStorage.removeItem(USER_KEY);
}

export function clearLegacyAuthStorage() {
  if (typeof window === "undefined") return;
  removeLegacyAuthTokens();
  const pending = window.sessionStorage.getItem(PENDING_GOOGLE_SIGNUP_KEY);
  if (pending?.includes(["pending", "token"].join("_"))) {
    window.sessionStorage.removeItem(PENDING_GOOGLE_SIGNUP_KEY);
  }
}

function removeLegacyAuthTokens() {
  window.sessionStorage.removeItem(LEGACY_TOKEN_KEY);
  window.localStorage.removeItem(LEGACY_TOKEN_KEY);
}

export function markFirstAgentWelcomePromptPending() {
  if (typeof window === "undefined") return;
  window.sessionStorage.setItem(FIRST_AGENT_WELCOME_PROMPT_KEY, "1");
}

export function hasFirstAgentWelcomePromptPending() {
  if (typeof window === "undefined") return false;
  return window.sessionStorage.getItem(FIRST_AGENT_WELCOME_PROMPT_KEY) === "1";
}

export function clearFirstAgentWelcomePromptPending() {
  if (typeof window === "undefined") return;
  window.sessionStorage.removeItem(FIRST_AGENT_WELCOME_PROMPT_KEY);
}

function notifyAgentsChanged() {
  if (typeof window === "undefined") return;
  window.dispatchEvent(new Event(AGENTS_CHANGED_EVENT));
}

function readAgentAutonomyMutations(): Record<string, AgentAutonomyMutationState> {
  if (typeof window === "undefined") return {};
  const raw = window.sessionStorage.getItem(AGENT_AUTONOMY_MUTATION_KEY);
  if (!raw) return {};
  try {
    const parsed = JSON.parse(raw);
    if (!parsed || typeof parsed !== "object") return {};
    return Object.fromEntries(
      Object.entries(parsed).filter(
        (entry): entry is [string, AgentAutonomyMutationState] =>
          entry[1] === "activating" || entry[1] === "deactivating",
      ),
    );
  } catch {
    return {};
  }
}

function writeAgentAutonomyMutations(
  mutations: Record<string, AgentAutonomyMutationState>,
) {
  if (typeof window === "undefined") return;
  if (Object.keys(mutations).length === 0) {
    window.sessionStorage.removeItem(AGENT_AUTONOMY_MUTATION_KEY);
    return;
  }
  window.sessionStorage.setItem(
    AGENT_AUTONOMY_MUTATION_KEY,
    JSON.stringify(mutations),
  );
}

function notifyAgentAutonomyMutation(
  characterId: string,
  state: AgentAutonomyMutationState | null,
) {
  if (typeof window === "undefined") return;
  window.dispatchEvent(
    new CustomEvent<AgentAutonomyMutationEventDetail>(
      AGENT_AUTONOMY_MUTATION_EVENT,
      {
        detail: { characterId, state },
      },
    ),
  );
}

export function getAgentAutonomyMutationStates() {
  return readAgentAutonomyMutations();
}

export function getAgentAutonomyMutationState(characterId: string) {
  return readAgentAutonomyMutations()[characterId] ?? null;
}

export function setAgentAutonomyMutationState(
  characterId: string,
  state: AgentAutonomyMutationState,
) {
  const mutations = readAgentAutonomyMutations();
  mutations[characterId] = state;
  writeAgentAutonomyMutations(mutations);
  notifyAgentAutonomyMutation(characterId, state);
}

export function clearAgentAutonomyMutationState(characterId: string) {
  const mutations = readAgentAutonomyMutations();
  delete mutations[characterId];
  writeAgentAutonomyMutations(mutations);
  notifyAgentAutonomyMutation(characterId, null);
}

export function isAuthError(err: unknown) {
  if (!(err instanceof Error)) return false;
  const message = err.message.trim();
  return (
    message === "Authorization required" ||
    message === "Invalid token" ||
    message === "Bearer token required" ||
    message === "Invalid or expired token" ||
    message === "Invalid or expired signup token" ||
    message === "Not authenticated" ||
    message === "401" ||
    message.includes("401")
  );
}

async function apiRequest<T>(path: string, options: RequestOptions = {}) {
  const {
    body,
    headers,
    anonymous = false,
    suppressAuthFailureEvent = false,
    ...rest
  } = options;
  const isFormDataBody = typeof FormData !== "undefined" && body instanceof FormData;
  const response = await fetch(`/api/backend${path}`, {
    ...rest,
    body:
      body === undefined
        ? undefined
        : isFormDataBody
          ? body
          : JSON.stringify(body),
    cache: "no-store",
    credentials: anonymous ? "omit" : "same-origin",
    headers: {
      ...(isFormDataBody ? {} : { "Content-Type": "application/json" }),
      ...(headers ?? {}),
    },
  });

  const text = await response.text();
  let payload: unknown = null;
  try {
    payload = text ? JSON.parse(text) : null;
  } catch (err) {
    if (!response.ok) {
      throw new Error(
        htmlErrorMessage(text) ?? (text.trim() || `Request failed with ${response.status}`),
      );
    }
    throw err;
  }

  if (!response.ok) {
    if (response.status === 401 && !anonymous && !suppressAuthFailureEvent) {
      clearStoredUser();
      notifyAuthChanged();
    }
    throw new Error(
      getErrorMessage(payload, `Request failed with ${response.status}`),
    );
  }

  return payload as T;
}


export async function fetchAuthenticatedMediaObjectUrl(apiPath: string) {
  const normalizedPath = apiPath.startsWith("/api/v1")
    ? apiPath.slice("/api/v1".length)
    : apiPath;
  const response = await fetch(`/api/backend${normalizedPath}`, {
    cache: "no-store",
    credentials: "same-origin",
  });
  if (!response.ok) {
    throw new Error(`Private media request failed with ${response.status}`);
  }
  return URL.createObjectURL(await response.blob());
}


function htmlErrorMessage(text: string) {
  const trimmed = text.trim().toLowerCase();
  if (!trimmed.startsWith("<!doctype html") && !trimmed.startsWith("<html")) {
    return null;
  }
  return "요청 처리 중 서버 오류가 발생했습니다. 잠시 후 다시 시도해주세요.";
}

export function signup(data: {
  email: string;
  password: string;
  display_name: string;
  privacy_policy_agreed: boolean;
  terms_agreed: boolean;
  turnstile_token?: string;
}) {
  return apiRequest<AuthRead>("/auth/signup", {
    method: "POST",
    body: data,
  });
}

export function login(data: { email: string; password: string }) {
  return apiRequest<AuthRead>("/auth/login", {
    method: "POST",
    body: data,
  });
}

export function demoLogin() {
  return apiRequest<AuthRead>("/auth/demo-login", {
    method: "POST",
  });
}

export function logoutCurrentSession() {
  return apiRequest<void>("/auth/logout", {
    method: "POST",
  });
}

export function googleLogin(data: { credential: string }) {
  return apiRequest<GoogleLoginRead>("/auth/google", {
    method: "POST",
    body: data,
  });
}

export function completeGoogleSignup(data: {
  display_name: string;
  privacy_policy_agreed: boolean;
  terms_agreed: boolean;
  turnstile_token?: string;
}) {
  return apiRequest<AuthRead>("/auth/google/complete", {
    method: "POST",
    body: data,
    anonymous: false,
  });
}

export function linkGoogleAccount(data: { credential: string }) {
  return apiRequest<AuthRead>("/auth/google/link", {
    method: "POST",
    body: data,
  });
}

export function getMe(options: { suppressAuthFailureEvent?: boolean } = {}) {
  return apiRequest<UserRead>("/auth/me", options);
}

export function getAgentActivityMaintenance() {
  return apiRequest<AgentActivityMaintenanceRead>("/maintenance/agent-activity", {
    anonymous: true,
  });
}

export function updateMe(data: {
  display_name: string;
  privacy_policy_agreed?: boolean;
  terms_agreed?: boolean;
}) {
  return apiRequest<UserRead>("/auth/me", {
    method: "PATCH",
    body: data,
  });
}

export function updateMePreferences(data: { feed_content_filter: FeedContentFilter }) {
  return apiRequest<UserRead>("/auth/me/preferences", {
    method: "PATCH",
    body: data,
  });
}

export function deleteCurrentAccount(data: { confirmation: string }) {
  return apiRequest<void>("/auth/me", {
    method: "DELETE",
    body: data,
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
  const result = await apiRequest(`/agents/${characterId}/run-now`, {
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

export type MessageCredentialSource = "message_key" | "agent_key";

export type CharacterMessageSettingRead = {
  character_id: string;
  enabled: boolean;
};

export type MessageSettingsRead = {
  credential_source: MessageCredentialSource;
  source_character_id: string | null;
  default_model: MessageGoogleGeminiModel;
  message_key_fingerprint: string | null;
  agent_key_fingerprint: string | null;
  has_usable_key: boolean;
  owned_agents: ProfileRef[];
};

export type MessageMessageRead = {
  id: number;
  thread_id: string;
  role: "user" | "assistant";
  content: string;
  model: string | null;
  status: "ok" | "error";
  error_code: string | null;
  created_at: string;
};

export type MessageThreadRead = {
  id: string;
  requester: ProfileRef;
  character: ProfileRef;
  selected_model: MessageGoogleGeminiModel;
  last_message_at: string | null;
  created_at: string;
  latest_message: MessageMessageRead | null;
  messages: MessageMessageRead[];
};

export type MessageThreadListRead = {
  items: MessageThreadRead[];
  max_threads: number;
};

export type MessageSendRead = {
  thread: MessageThreadRead;
  user_message: MessageMessageRead;
  assistant_message: MessageMessageRead;
};

export function listMessageThreads() {
  return apiRequest<MessageThreadListRead>("/messages/threads");
}

export function createMessageThread(data: {
  character_id: string;
  selected_model?: MessageGoogleGeminiModel;
}) {
  return apiRequest<MessageThreadRead>("/messages/threads", {
    method: "POST",
    body: data,
  });
}

export function getMessageThread(threadId: string) {
  return apiRequest<MessageThreadRead>(`/messages/threads/${threadId}`);
}

export function updateMessageThread(
  threadId: string,
  data: { selected_model: MessageGoogleGeminiModel },
) {
  return apiRequest<MessageThreadRead>(`/messages/threads/${threadId}`, {
    method: "PATCH",
    body: data,
  });
}

export function deleteMessageThread(threadId: string) {
  return apiRequest<void>(`/messages/threads/${threadId}`, {
    method: "DELETE",
  });
}

export function sendThreadMessage(threadId: string, content: string) {
  return apiRequest<MessageSendRead>(`/messages/threads/${threadId}/messages`, {
    method: "POST",
    body: { content },
  });
}

export function retryThreadMessage(threadId: string, messageId: number) {
  return apiRequest<MessageSendRead>(
    `/messages/threads/${threadId}/messages/${messageId}/retry`,
    {
      method: "POST",
    },
  );
}

export function getMessageSettings() {
  return apiRequest<MessageSettingsRead>("/messages/settings");
}

export function updateMessageSettings(data: {
  credential_source?: MessageCredentialSource;
  source_character_id?: string | null;
  default_model?: MessageGoogleGeminiModel;
  api_key?: string;
  clear_message_key?: boolean;
}) {
  return apiRequest<MessageSettingsRead>("/messages/settings", {
    method: "PATCH",
    body: data,
  });
}

export function getCharacterMessageSettings(characterId: string) {
  return apiRequest<CharacterMessageSettingRead>(
    `/characters/${characterId}/message-settings`,
  );
}

export function updateCharacterMessageSettings(
  characterId: string,
  data: { enabled: boolean },
) {
  return apiRequest<CharacterMessageSettingRead>(
    `/characters/${characterId}/message-settings`,
    {
      method: "PATCH",
      body: data,
    },
  );
}
