export type DeviceHomeFixedAppId =
  | "settings"
  | "studio"
  | "world-import"
  | "memory";

export type DeviceHomeFixedApp = {
  id: DeviceHomeFixedAppId;
  label: string;
  href: string;
  availability: "available" | "planned";
};

export type WorldSurface = "device_home" | "creator_studio";

export type WorldSurfaceItem = {
  world_id: string;
  name: string;
  tagline: string;
  banner_media_id: string | null;
  banner_alt_text: string;
  status: "draft" | "published" | "archived";
  visibility: "private" | "unlisted" | "public";
  readiness_status: "not_ready" | "publish_ready" | "stale";
  membership_role: "owner" | "editor" | "member";
  updated_at: string;
  launchable: boolean;
  launch_block_reason:
    | "world_archived"
    | "world_not_published"
    | "world_not_ready"
    | "world_private"
    | null;
};

export type WorldLaunchState =
  | "launchable"
  | "world_archived"
  | "world_not_published"
  | "world_not_ready"
  | "world_private"
  | "unavailable";

export type WorldLaunchPresentation = {
  badgeLabel: string;
  description: string;
  state: WorldLaunchState;
  tone: "disabled" | "healthy" | "waiting";
};

export type LocalWorldSurfaceRead = {
  schema_version: "local-world-surface-v1";
  surface: WorldSurface;
  items: WorldSurfaceItem[];
  next_cursor: string | null;
};

export type DeviceHomeAuthStatus =
  | "checking"
  | "authenticated"
  | "unauthenticated";
