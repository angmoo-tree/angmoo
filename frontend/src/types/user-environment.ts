export type UiLanguage = "ko" | "en";

export type UserEnvironment = {
  installation_id: string | null;
  preferred_language: string;
  memory_search_locale: string;
  timezone: string;
  environment_revision: number;
  timezone_revision: number;
  confirmed_at: string | null;
  synchronization: "active_owner" | "awaiting_detector";
  lease_expires_at: string | null;
  lease_token?: string | null;
};
