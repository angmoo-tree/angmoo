import { PRODUCT_ROUTES } from "@/shared/navigation/public";

export type DeviceHomeFixedAppId =
  | "settings"
  | "studio"
  | "world-import"
  | "memory-explorer";

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
    availability: "available",
  },
  {
    id: "memory-explorer",
    label: "Memory Explorer",
    href: "/memory-explorer",
    availability: "planned",
  },
] as const;

export function presentWorldLaunchability(
  world: WorldSurfaceItem,
): WorldLaunchPresentation {
  if (world.launchable) {
    return {
      badgeLabel: "실행 가능",
      description: `${world.name} World 열기. 실행 가능.`,
      state: "launchable",
      tone: "healthy",
    };
  }

  switch (world.launch_block_reason) {
    case "world_archived":
      return {
        badgeLabel: "보관됨",
        description: `${world.name} World는 보관되어 Device Home에서 열 수 없습니다.`,
        state: "world_archived",
        tone: "disabled",
      };
    case "world_not_published":
      return {
        badgeLabel: "공개 전",
        description: `${world.name} World는 아직 공개되지 않아 Device Home에서 열 수 없습니다.`,
        state: "world_not_published",
        tone: "waiting",
      };
    case "world_not_ready":
      return {
        badgeLabel: "준비 필요",
        description: `${world.name} World는 공개 준비가 완료되지 않아 Device Home에서 열 수 없습니다.`,
        state: "world_not_ready",
        tone: "waiting",
      };
    case "world_private":
      return {
        badgeLabel: "비공개",
        description: `${world.name} World는 비공개 상태라 Device Home에서 열 수 없습니다.`,
        state: "world_private",
        tone: "disabled",
      };
    default:
      return {
        badgeLabel: "사용 불가",
        description: `${world.name} World는 현재 Device Home에서 열 수 없습니다.`,
        state: "unavailable",
        tone: "disabled",
      };
  }
}
