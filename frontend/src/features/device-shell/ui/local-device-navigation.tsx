"use client";

import { Bird, House, Newspaper, Settings } from "lucide-react";
import type { ReactNode } from "react";

import { useRuntimePathname } from "@/shared/navigation/public";
import { BottomNavigation, type BottomNavigationItem } from "@/shared/ui/public";

import {
  activeLocalDeviceNavigation,
  LOCAL_DEVICE_NAVIGATION,
  type LocalDeviceNavigationId,
} from "../model/device-navigation";

const NAVIGATION_LABELS: Record<LocalDeviceNavigationId, string> = {
  agents: "내 앵무",
  feed: "피드",
  home: "홈",
  settings: "설정",
};

const NAVIGATION_ICONS: Record<LocalDeviceNavigationId, ReactNode> = {
  agents: <Bird size={21} strokeWidth={2.2} />,
  feed: <Newspaper size={21} strokeWidth={2.2} />,
  home: <House size={21} strokeWidth={2.2} />,
  settings: <Settings size={21} strokeWidth={2.2} />,
};

const ITEMS: BottomNavigationItem[] = LOCAL_DEVICE_NAVIGATION.map(({ href, id }) => ({
  href,
  icon: NAVIGATION_ICONS[id],
  id,
  label: NAVIGATION_LABELS[id],
}));

export function LocalDeviceNavigation() {
  const pathname = useRuntimePathname();
  return (
    <BottomNavigation
      activeId={activeLocalDeviceNavigation(pathname)}
      ariaLabel="모바일 주요 메뉴"
      items={ITEMS}
    />
  );
}
