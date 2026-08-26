"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";

import {
  getLocalWorldSurface,
  type WorldSurfaceItem,
} from "@/features/device-home/public";
import {
  PRODUCT_ROUTES,
  studioWorldRoute,
  worldAppRoute,
} from "@/shared/navigation/public";

import styles from "./creator-studio-dashboard.module.css";

type StudioGroupId = "live" | "draft" | "private" | "archived";
export type CreatorStudioAuthStatus =
  | "checking"
  | "authenticated"
  | "unauthenticated";

const GROUPS: readonly { id: StudioGroupId; label: string; description: string }[] = [
  { id: "live", label: "실행 중인 World", description: "Device Home에서 열 수 있어요" },
  { id: "draft", label: "작성 중", description: "공개 준비를 마쳐야 해요" },
  { id: "private", label: "비공개", description: "Studio에서만 관리해요" },
  { id: "archived", label: "보관됨", description: "Device Home에는 표시하지 않아요" },
];

export function CreatorStudioDashboard({
  authStatus,
}: {
  authStatus: CreatorStudioAuthStatus;
}) {
  const [worlds, setWorlds] = useState<WorldSurfaceItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);

  useEffect(() => {
    if (authStatus !== "authenticated") return;
    const controller = new AbortController();
    getLocalWorldSurface("creator_studio", { signal: controller.signal })
      .then((surface) => setWorlds(surface.items))
      .catch((reason: unknown) => {
        if (reason instanceof DOMException && reason.name === "AbortError") return;
        setError(true);
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [authStatus]);

  const grouped = useMemo(() => {
    const next = new Map<StudioGroupId, WorldSurfaceItem[]>(
      GROUPS.map((group) => [group.id, []]),
    );
    for (const world of worlds) next.get(groupFor(world))?.push(world);
    return next;
  }, [worlds]);

  if (authStatus === "checking" || (authStatus === "authenticated" && loading)) {
    return <StudioNotice title="World 목록을 불러오는 중입니다" />;
  }
  if (authStatus === "unauthenticated") {
    return (
      <StudioNotice title="로컬 owner 연결이 필요합니다">
        <Link
          className={styles.secondaryAction}
          href={`/login?returnTo=${encodeURIComponent(PRODUCT_ROUTES.studio)}`}
        >
          owner 연결
        </Link>
      </StudioNotice>
    );
  }
  if (error) {
    return <StudioNotice title="Creator Studio를 열지 못했습니다" />;
  }

  return (
    <div className={styles.root}>
      <header className={styles.header}>
        <div>
          <p className={styles.eyebrow}>WORLD WORKSPACE</p>
          <h1 className={styles.title}>내 World</h1>
          <p className={styles.description}>
            초안부터 공개까지 한곳에서 관리합니다. Studio 목록은 이 설치의 local
            owner와 활성 creator membership 범위만 읽습니다.
          </p>
        </div>
        <div className={styles.actions}>
          <Link className={styles.secondaryAction} href={PRODUCT_ROUTES.studioImport}>
            Package 가져오기
          </Link>
          <Link className={styles.primaryAction} href={PRODUCT_ROUTES.studioNewWorld}>
            새 World 만들기
          </Link>
        </div>
      </header>

      {worlds.length === 0 ? (
        <section className={styles.empty}>
          <h2>아직 만든 World가 없습니다</h2>
          <p>첫 World를 만들고 공개 준비를 마치면 Device Home에 앱이 나타납니다.</p>
          <Link className={styles.primaryAction} href={PRODUCT_ROUTES.studioNewWorld}>
            World 초안 시작
          </Link>
        </section>
      ) : (
        <div className={styles.groups}>
          {GROUPS.map((group) => {
            const items = grouped.get(group.id) ?? [];
            if (items.length === 0) return null;
            return (
              <section key={group.id}>
                <div className={styles.groupHeader}>
                  <h2>{group.label}</h2>
                  <span>{group.description} · {items.length}</span>
                </div>
                <div className={styles.worldGrid}>
                  {items.map((world) => <WorldCard key={world.world_id} world={world} />)}
                </div>
              </section>
            );
          })}
        </div>
      )}
    </div>
  );
}

function WorldCard({ world }: { world: WorldSurfaceItem }) {
  return (
    <article className={styles.worldCard}>
      <div className={styles.worldCardHeader}>
        <div>
          <h3>{world.name}</h3>
          <p>{world.tagline || "한 줄 소개가 아직 없습니다."}</p>
        </div>
        <span className={styles.status}>{statusLabel(world)}</span>
      </div>
      <div className={styles.meta}>
        <span>{world.visibility}</span>
        <span>{world.readiness_status}</span>
        <span>{world.membership_role}</span>
      </div>
      <div className={styles.actions}>
        <Link className={styles.secondaryAction} href={studioWorldRoute(world.world_id)}>
          편집
        </Link>
        {world.launchable ? (
          <Link className={styles.primaryAction} href={worldAppRoute(world.world_id)}>
            World 열기
          </Link>
        ) : null}
      </div>
    </article>
  );
}

function StudioNotice({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <section className={styles.notice} role="status">
      <strong>{title}</strong>
      {children ? <div className={styles.actions}>{children}</div> : null}
    </section>
  );
}

function groupFor(world: WorldSurfaceItem): StudioGroupId {
  if (world.status === "archived") return "archived";
  if (world.status !== "published" || world.readiness_status !== "publish_ready") {
    return "draft";
  }
  if (world.visibility === "private") return "private";
  return "live";
}

function statusLabel(world: WorldSurfaceItem): string {
  if (world.status === "archived") return "보관됨";
  if (world.launchable) return "공개됨";
  if (world.visibility === "private" && world.status === "published") return "비공개";
  if (world.readiness_status === "stale") return "재검증 필요";
  return "초안";
}
