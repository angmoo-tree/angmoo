import { PRODUCT_ROUTES } from "@/shared/navigation/public";

export type DeviceHomeFixedAppId = "settings" | "studio" | "world-import";

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

export type LocalWorldSurfaceRead = {
  schema_version: "local-world-surface-v1";
  surface: WorldSurface;
  items: WorldSurfaceItem[];
  next_cursor: string | null;
};

export const DEVICE_HOME_VISUAL_CONTRACT = {
  maxWidthPx: 436,
  bezelWidthPx: 3,
  cornerRadiusPx: 34,
  frameStyle: "thin-uniform-flat" as const,
  iconStyle: "squircle-grid" as const,
};

export const DEVICE_HOME_FIXED_APPS: readonly DeviceHomeFixedApp[] = [
  {
    id: "settings",
    label: "설정",
    href: PRODUCT_ROUTES.settings,
    availability: "available",
  },
  {
    id: "studio",
    label: "Creator Studio",
    href: PRODUCT_ROUTES.studio,
    availability: "available",
  },
  {
    id: "world-import",
    label: "World 추가·가져오기",
    href: PRODUCT_ROUTES.studioImport,
    availability: "planned",
  },
] as const;
