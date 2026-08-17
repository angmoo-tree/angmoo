import { PRODUCT_ROUTES } from "@/shared/navigation/public";

export type DeviceHomeFixedAppId = "settings" | "studio" | "world-import";

export type DeviceHomeFixedApp = {
  id: DeviceHomeFixedAppId;
  label: string;
  href: string;
  availability: "available" | "planned";
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
