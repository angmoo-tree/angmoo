"use client";

import Link from "next/link";
import { BrainCircuit, Cog, Globe2, Hammer, Plus } from "lucide-react";
import { useEffect, useState, type ReactNode } from "react";

import {
  getProductRuntimeState,
  RuntimeStatusSummary,
  type ProductRuntimeState,
} from "@/features/runtime-status/public";
import {
  safeSameOriginMediaUrl,
  useRuntimeMediaUrl,
} from "@/shared/media/public";
import { PRODUCT_ROUTES, worldAppRoute } from "@/shared/navigation/public";
import { AppIcon, Button } from "@/shared/ui/public";

import { getLocalWorldSurface } from "../api/device-home-client";
import {
  DEVICE_HOME_FIXED_APPS,
  presentWorldLaunchability,
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
  "memory-explorer": <BrainCircuit size={30} strokeWidth={2.1} />,
} as const;

const FIXED_BACKGROUNDS = {
  settings: "var(--color-brand-soft)",
  studio: "var(--color-state-warning-surface)",
  "world-import": "var(--color-state-running-surface)",
  "memory-explorer": "var(--color-state-degraded-surface)",
} as const;

const WORLD_BACKGROUNDS = [
  "var(--color-brand-soft)",
  "var(--color-state-running-surface)",
  "var(--color-state-warning-surface)",
  "var(--color-state-degraded-surface)",
] as const;

const WORLD_LAUNCH_TONE_CLASSES = {
  disabled: styles.worldLaunchBadgeDisabled,
  healthy: styles.worldLaunchBadgeHealthy,
  waiting: styles.worldLaunchBadgeWaiting,
} as const;

export function DeviceHome({ authStatus }: DeviceHomeProps) {
  const [runtimeState, setRuntimeState] =
    useState<ProductRuntimeState>("stale_state");
  const [worldRequestRevision, setWorldRequestRevision] = useState(0);
  const [worldRead, setWorldRead] = useState<{
    error: string | null;
    items: WorldSurfaceItem[];
    revision: number;
  }>({ error: null, items: [], revision: -1 });
  const worldLoading = worldRead.revision !== worldRequestRevision;
  const worldError = worldLoading ? null : worldRead.error;
  const worlds = worldLoading ? [] : worldRead.items;

  useEffect(() => {
    if (authStatus !== "authenticated") {
      return;
    }
    const controller = new AbortController();
    getLocalWorldSurface("device_home", { signal: controller.signal })
      .then((surface) => {
        setWorldRead({
          error: null,
          items: surface.items,
          revision: worldRequestRevision,
        });
      })
      .catch((reason: unknown) => {
        if (reason instanceof DOMException && reason.name === "AbortError") return;
        setWorldRead({
          error:
            reason instanceof Error
              ? reason.message
              : "device_home_unavailable",
          items: [],
          revision: worldRequestRevision,
        });
      });
    return () => controller.abort();
  }, [authStatus, worldRequestRevision]);

  useEffect(() => {
    if (authStatus !== "authenticated") {
      return;
    }
    const controller = new AbortController();
    getProductRuntimeState({ signal: controller.signal })
      .then(setRuntimeState)
      .catch((reason: unknown) => {
        if (reason instanceof DOMException && reason.name === "AbortError") return;
        setRuntimeState("stale_state");
      });
    return () => controller.abort();
  }, [authStatus]);

  const worldEntries = worlds.map((world) => (
    <WorldAppIcon key={world.world_id} world={world} />
  ));

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
      ) : worldLoading ? (
        <HomeMessage
          title="World 앱을 불러오는 중"
          description="SQLite의 owner 범위 World 목록만 읽고 있어요."
        />
      ) : worldError ? (
        <HomeMessage
          title="Device Home을 열지 못했어요"
          description="World 목록을 읽지 못했습니다. 다시 시도해도 runtime 상태와 World 실행 가능성은 각각 따로 확인합니다."
          role="alert"
          action={
            <Button
              compact
              onClick={() => setWorldRequestRevision((revision) => revision + 1)}
              variant="secondary"
            >
              World 목록 다시 시도
            </Button>
          }
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
  const launch = presentWorldLaunchability(world);
  return (
    <AppIcon
      disabled={!world.launchable}
      href={world.launchable ? worldAppRoute(world.world_id) : undefined}
      label={world.name}
      description={launch.description}
      visual={
        <>
          <WorldVisual world={world} />
          <span
            className={`${styles.worldLaunchBadge} ${WORLD_LAUNCH_TONE_CLASSES[launch.tone]}`}
            data-world-launchability={launch.state}
          >
            {launch.badgeLabel}
          </span>
        </>
      }
      visualBackground={worldBackground(world.world_id)}
    />
  );
}

function WorldVisual({ world }: { world: WorldSurfaceItem }) {
  const bannerUrl = safeSameOriginMediaUrl(world.banner_media_id);
  const resolvedBannerUrl = useRuntimeMediaUrl(bannerUrl);
  if (resolvedBannerUrl) {
    return (
      // eslint-disable-next-line @next/next/no-img-element
      <img
        alt=""
        className={styles.worldBanner}
        src={resolvedBannerUrl}
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
  action,
  role = "status",
}: {
  title: string;
  description: string;
  href?: string;
  linkLabel?: string;
  action?: ReactNode;
  role?: "alert" | "status";
}) {
  return (
    <section className={styles.message} role={role}>
      <strong>{title}</strong>
      <p>{description}</p>
      {href && linkLabel ? <Link href={href}>{linkLabel}</Link> : null}
      {action}
    </section>
  );
}

function worldBackground(worldId: string): string {
  let hash = 0;
  for (const character of worldId) {
    hash = (hash * 31 + character.charCodeAt(0)) >>> 0;
  }
  return WORLD_BACKGROUNDS[hash % WORLD_BACKGROUNDS.length];
}
