export const MESSAGE_GOOGLE_GEMINI_MODELS = [
  { value: "gemini-2.5-flash-lite", label: "Gemini 2.5 Flash-Lite" },
  { value: "gemini-2.5-flash", label: "Gemini 2.5 Flash" },
  { value: "gemini-3.1-flash-lite", label: "Gemini 3.1 Flash-Lite" },
  { value: "gemma-4-26b-a4b-it", label: "Gemma 4 26B" },
  { value: "gemma-4-31b-it", label: "Gemma 4 31B" },
] as const;

export const DEFAULT_MESSAGE_GOOGLE_MODEL = "gemini-2.5-flash-lite";

export type MessageGoogleGeminiModel =
  (typeof MESSAGE_GOOGLE_GEMINI_MODELS)[number]["value"];

export type MessageCredentialSource = "message_key" | "agent_key";

export type MessageProfileRef = {
  profile_type: "user" | "character";
  id: string;
  display_name: string;
  handle: string | null;
  avatar_url: string | null;
  banner_url: string | null;
};

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
  owned_agents: MessageProfileRef[];
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
  requester: MessageProfileRef;
  character: MessageProfileRef;
  selected_model: MessageGoogleGeminiModel;
  last_message_at: string | null;
  created_at: string;
  latest_message: MessageMessageRead | null;
  messages: MessageMessageRead[];
  world_id: string | null;
  requester_world_character_id: string | null;
  responding_world_character_id: string | null;
  world_scope_status: "resolved" | "ambiguous" | "quarantined";
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
