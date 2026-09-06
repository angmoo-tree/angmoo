export type StudioWorldItem = {
  world_id: string; name: string; tagline: string; launchable: boolean;
  status: "draft" | "published" | "archived";
  visibility: "private" | "unlisted" | "public";
  readiness_status: "not_ready" | "publish_ready" | "stale";
  membership_role: "owner" | "editor" | "member";
};
export type StudioWorldLoader = (surface: "creator_studio", options: { signal: AbortSignal }) => Promise<{ items: StudioWorldItem[] }>;
