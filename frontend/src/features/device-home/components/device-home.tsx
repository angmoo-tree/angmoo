"use client";
import { useUiText } from "@/hooks/use-ui-text";


import Link from "next/link";
import { BrainCircuit, Cog, Globe2, Hammer, Plus } from "lucide-react";
import { useEffect, useState, type ReactNode } from "react";

import { useRuntimeMediaUrl } from "@/hooks/use-runtime-media-url";
import { safeSameOriginMediaUrl } from "@/lib/media/safe-media-url";
import { PRODUCT_ROUTES, worldAppRoute } from "@/lib/navigation/product-routes";
import { AppIcon } from "@/components/ui/app-icon";
import { Button } from "@/components/ui/button";

import { getLocalWorldSurface } from "@/features/device-home/api/device-home-client";
import type { DeviceHomeAuthStatus, WorldSurfaceItem } from "@/features/device-home/types/index";
import { DEVICE_HOME_FIXED_APPS, presentWorldLaunchability } from "@/features/device-home/utils/device-home-presentation";
import styles from "./device-home.module.css";



type DeviceHomeProps = {
  authStatus: DeviceHomeAuthStatus;
  ensureDefaultSpace?: () => Promise<unknown>;
};

const FIXED_VISUALS = {
  settings: <Cog size={30} strokeWidth={2.2} />,
  studio: <Hammer size={30} strokeWidth={2.2} />,
  "world-import": <Plus size={32} strokeWidth={2.2} />,
  memory: <BrainCircuit size={30} strokeWidth={2.1} />,
} as const;

const FIXED_BACKGROUNDS = {
  settings: "var(--color-brand-soft)",
  studio: "var(--color-state-warning-surface)",
  "world-import": "var(--color-state-running-surface)",
  memory: "var(--color-state-degraded-surface)",
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

export function DeviceHome({ authStatus, ensureDefaultSpace }: DeviceHomeProps) {
  const uiText = useUiText("device-home");
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
    (ensureDefaultSpace ? ensureDefaultSpace() : Promise.resolve())
      .then(() => getLocalWorldSurface("device_home", { signal: controller.signal }))
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
  }, [authStatus, worldRequestRevision, ensureDefaultSpace]);


  const worldEntries = worlds.map((world) => (
    <WorldAppIcon key={world.world_id} world={world} />
  ));

  return (
    <>
      <AppIcon href="/agents/new" label={uiText("캐릭터 추가")} description={uiText("직접 만들거나 실리태번 캐릭터 카드 가져오기")} visual={<Plus size={32} />} visualBackground="var(--color-brand-soft)" />
      {DEVICE_HOME_FIXED_APPS.map((app) => (
        <AppIcon
          key={app.id}
          disabled={app.availability !== "available"}
          href={app.availability === "available" ? app.href : undefined}
          label={uiText(app.label)}
          description={
            app.availability === "available"
              ? uiText("{{value0}} 열기", {value0: uiText(app.label)})
              : uiText("{{value0}}는 후속 단계에서 연결됩니다", {value0: uiText(app.label)})
          }
          visual={FIXED_VISUALS[app.id]}
          visualBackground={FIXED_BACKGROUNDS[app.id]}
        />
      ))}

      {authStatus === "unauthenticated" ? (
        <HomeMessage
          title={uiText("로컬 owner 연결이 필요해요")}
          description={uiText("이 설치의 owner session을 확인한 뒤 World 앱을 불러옵니다.")}
          href={`/login?returnTo=${encodeURIComponent(PRODUCT_ROUTES.deviceHome)}`}
          linkLabel={uiText("owner 연결")}
        />
      ) : worldLoading ? (
        <HomeMessage
          title={uiText("World 앱을 불러오는 중")}
          description={uiText("SQLite의 owner 범위 World 목록만 읽고 있어요.")}
        />
      ) : worldError ? (
        <HomeMessage
          title={uiText("Device Home을 열지 못했어요")}
          description={uiText("World 목록을 읽지 못했습니다. 다시 시도해도 runtime 상태와 World 실행 가능성은 각각 따로 확인합니다.")}
          role="alert"
          action={
            <Button
              compact
              onClick={() => setWorldRequestRevision((revision) => revision + 1)}
              variant="secondary"
            >
              {uiText("World 목록 다시 시도")}</Button>
          }
        />
      ) : worlds.length === 0 ? (
        <HomeMessage
          title={uiText("아직 실행할 World가 없어요")}
          description={uiText("Creator Studio에서 World를 만들고 공개 준비를 마치면 여기에 앱이 나타납니다.")}
        />
      ) : (
        worldEntries
      )}
    </>
  );
}

function WorldAppIcon({ world }: { world: WorldSurfaceItem }) {
  const uiText = useUiText("device-home");
  const launch = presentWorldLaunchability(world);
  const description = launch.state === "launchable"
    ? uiText("{{name}} World 열기. 실행 가능.", { name: world.name })
    : launch.state === "world_archived"
      ? uiText("{{name}} World는 보관되어 Device Home에서 열 수 없습니다.", { name: world.name })
      : launch.state === "world_not_published"
        ? uiText("{{name}} World는 아직 공개되지 않아 Device Home에서 열 수 없습니다.", { name: world.name })
        : launch.state === "world_not_ready"
          ? uiText("{{name}} World는 공개 준비가 완료되지 않아 Device Home에서 열 수 없습니다.", { name: world.name })
          : launch.state === "world_private"
            ? uiText("{{name}} World는 비공개 상태라 Device Home에서 열 수 없습니다.", { name: world.name })
            : uiText("{{name}} World는 현재 Device Home에서 열 수 없습니다.", { name: world.name });
  return (
    <AppIcon
      disabled={!world.launchable}
      href={world.launchable ? worldAppRoute(world.world_id) : undefined}
      label={world.name}
      description={description}
      visual={
        <>
          <WorldVisual world={world} />
          <span
            className={`${styles.worldLaunchBadge} ${WORLD_LAUNCH_TONE_CLASSES[launch.tone]}`}
            data-world-launchability={launch.state}
          >
            {uiText(launch.badgeLabel)}
          </span>
        </>
      }
      visualBackground={worldBackground(world.world_id)}
    />
  );
}

function WorldVisual({ world }: { world: WorldSurfaceItem }) {
  const bannerUrl = safeSameOriginMediaUrl(world.icon_media_id);
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
