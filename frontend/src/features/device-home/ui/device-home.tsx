"use client";

import Link from "next/link";
import { Cog, Globe2, Hammer, Plus } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import {
  getProductRuntimeState,
  RuntimeStatusSummary,
  type ProductRuntimeState,
} from "@/features/runtime-status/public";
import { safeSameOriginMediaUrl } from "@/shared/media/public";
import { PRODUCT_ROUTES, worldAppRoute } from "@/shared/navigation/public";
import { AppIcon } from "@/shared/ui/public";

import { getLocalWorldSurface } from "../api/device-home-client";
import {
  DEVICE_HOME_FIXED_APPS,
  type WorldSurfaceItem,
} from "../model/device-home-contract";
import { DeviceHomeShell } from "./device-home-shell";
import styles from "./device-home.module.css";


export type DeviceHomeAuthStatus =
  | "checking"
  | "authenticated"
  | "unauthenticated";

type DeviceHomeProps = {
  authStatus: DeviceHomeAuthStatus;
};

const FIXED_VISUALS = {
  settings: <Cog size={30} strokeWidth={2.2} />,
  studio: <Hammer size={30} strokeWidth={2.2} />,
  "world-import": <Plus size={32} strokeWidth={2.2} />,
} as const;

const FIXED_BACKGROUNDS = {
  settings: "linear-gradient(145deg, #f7d6d5, #fff4ef)",
  studio: "linear-gradient(145deg, #ffe1a6, #fff5da)",
  "world-import": "linear-gradient(145deg, #dce7f5, #f5f8fc)",
} as const;

export function DeviceHome({ authStatus }: DeviceHomeProps) {
  const [worlds, setWorlds] = useState<WorldSurfaceItem[]>([]);
  const [runtimeState, setRuntimeState] =
    useState<ProductRuntimeState>("stale_state");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (authStatus !== "authenticated") {
      return;
    }
    const controller = new AbortController();
    Promise.all([
      getLocalWorldSurface("device_home", { signal: controller.signal }),
      getProductRuntimeState({ signal: controller.signal }),
    ])
      .then(([surface, runtime]) => {
        setWorlds(surface.items);
        setRuntimeState(runtime);
      })
      .catch((reason: unknown) => {
        if (reason instanceof DOMException && reason.name === "AbortError") return;
        setError(reason instanceof Error ? reason.message : "device_home_unavailable");
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [authStatus]);

  const worldEntries = useMemo(
    () => worlds.map((world) => <WorldAppIcon key={world.world_id} world={world} />),
    [worlds],
  );

  return (
    <DeviceHomeShell status={<RuntimeStatusSummary state={runtimeState} />}>
      {DEVICE_HOME_FIXED_APPS.map((app) => (
        <AppIcon
          key={app.id}
          disabled={app.availability !== "available"}
          href={app.availability === "available" ? app.href : undefined}
          label={app.label}
          description={
            app.availability === "available"
              ? `${app.label} 열기`
              : `${app.label}는 후속 단계에서 연결됩니다`
          }
          visual={FIXED_VISUALS[app.id]}
          visualBackground={FIXED_BACKGROUNDS[app.id]}
        />
      ))}

      {authStatus === "unauthenticated" ? (
        <HomeMessage
          title="로컬 owner 연결이 필요해요"
          description="이 설치의 owner session을 확인한 뒤 World 앱을 불러옵니다."
          href={`/login?returnTo=${encodeURIComponent(PRODUCT_ROUTES.deviceHome)}`}
          linkLabel="owner 연결"
        />
      ) : loading ? (
        <HomeMessage
          title="World 앱을 불러오는 중"
          description="PostgreSQL의 owner 범위 목록만 읽고 있어요."
        />
      ) : error ? (
        <HomeMessage
          title="Device Home을 열지 못했어요"
          description="설정에서 runtime 상태를 확인한 뒤 다시 시도해주세요."
          href={PRODUCT_ROUTES.settings}
          linkLabel="설정 열기"
        />
      ) : worlds.length === 0 ? (
        <HomeMessage
          title="아직 실행할 World가 없어요"
          description="Creator Studio에서 World를 만들고 공개 준비를 마치면 여기에 앱이 나타납니다."
        />
      ) : (
        worldEntries
      )}
    </DeviceHomeShell>
  );
}

function WorldAppIcon({ world }: { world: WorldSurfaceItem }) {
  const routeReady = false;
  return (
    <AppIcon
      disabled={!routeReady}
      href={routeReady ? worldAppRoute(world.world_id) : undefined}
      label={world.name}
      description={
        routeReady
          ? `${world.name} World 열기`
          : `${world.name} World 앱은 다음 단계에서 연결됩니다`
      }
      visual={<WorldVisual world={world} />}
      visualBackground={worldBackground(world.world_id)}
      badge={<span className={styles.readyBadge}>✓</span>}
    />
  );
}

function WorldVisual({ world }: { world: WorldSurfaceItem }) {
  const bannerUrl = safeSameOriginMediaUrl(world.banner_media_id);
  if (bannerUrl) {
    return (
      // eslint-disable-next-line @next/next/no-img-element
      <img
        alt=""
        className={styles.worldBanner}
        src={bannerUrl}
      />
    );
  }
  const initial = Array.from(world.name.trim())[0];
  return initial ? (
    <span className={styles.worldInitial}>{initial}</span>
  ) : (
    <Globe2 size={31} strokeWidth={2.1} />
  );
}

function HomeMessage({
  title,
  description,
  href,
  linkLabel,
}: {
  title: string;
  description: string;
  href?: string;
  linkLabel?: string;
}) {
  return (
    <section className={styles.message} role="status">
      <strong>{title}</strong>
      <p>{description}</p>
      {href && linkLabel ? <Link href={href}>{linkLabel}</Link> : null}
    </section>
  );
}

function worldBackground(worldId: string): string {
  let hash = 0;
  for (const character of worldId) {
    hash = (hash * 31 + character.charCodeAt(0)) >>> 0;
  }
  const hue = hash % 360;
  return `linear-gradient(145deg, hsl(${hue} 72% 78%), hsl(${(hue + 32) % 360} 68% 92%))`;
}
