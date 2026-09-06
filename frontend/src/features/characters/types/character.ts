export type CharacterRead = {
  id: string;
  owner_id: string;
  name: string;
  handle: string;
  avatar_url: string | null;
  banner_url: string | null;
  one_liner: string;
  personality: string;
  speech_style: string;
  worldview: string;
  topic_preferences: string;
  safety_rules: string;
  status: string;
  execution_mode: "llm" | "local";
  persona_summary: string;
};

export type CharacterStateRead = {
  character_id: string;
  mood: string;
  summary: string;
  memory_note: string;
  updated_at: string;
};
