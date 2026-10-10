"use client";
import { useUiText } from "@/hooks/use-ui-text";


import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";

import type { StudioWorldItem as WorldSurfaceItem, StudioWorldLoader } from "@/features/creator-studio/types/studio-world-list";
import { PRODUCT_ROUTES, studioWorldRoute, worldAppRoute } from "@/lib/navigation/product-routes";

import styles from "./creator-studio-dashboard.module.css";

type StudioGroupId = "live" | "draft" | "private" | "archived";
export type CreatorStudioAuthStatus =
  | "checking"
  | "authenticated"
  | "unauthenticated";

const GROUPS: readonly { id: StudioGroupId; label: string; description: string }[] = [
  { id: "live", label: "공개한 World", description: "기기 홈에서 열 수 있어요." },
  { id: "draft", label: "작성 중", description: "필수 항목을 채우고 공개를 준비해요." },
  { id: "private", label: "비공개", description: "비공개 World를 관리해요." },
  { id: "archived", label: "보관됨", description: "기기 홈에는 표시되지 않아요." },
];

export function CreatorStudioDashboard({
  authStatus,
  getLocalWorldSurface,
}: {
  authStatus: CreatorStudioAuthStatus;
  getLocalWorldSurface: StudioWorldLoader;
}) {
  const uiText = useUiText("creator-studio");
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
  }, [authStatus, getLocalWorldSurface]);

  const grouped = useMemo(() => {
    const next = new Map<StudioGroupId, WorldSurfaceItem[]>(
      GROUPS.map((group) => [group.id, []]),
    );
    for (const world of worlds) next.get(groupFor(world))?.push(world);
    return next;
  }, [worlds]);

  if (authStatus === "checking" || (authStatus === "authenticated" && loading)) {
    return <StudioNotice title={uiText("World 목록을 불러오는 중…")} />;
  }
  if (authStatus === "unauthenticated") {
    return (
      <StudioNotice title={uiText("Studio를 사용하려면 먼저 연결해주세요.")}>
        <Link
          className={styles.secondaryAction}
          href={`/login?returnTo=${encodeURIComponent(PRODUCT_ROUTES.studio)}`}
        >
          {uiText("연결하기")}</Link>
      </StudioNotice>
    );
  }
  if (error) {
    return <StudioNotice title={uiText("Creator Studio를 열지 못했어요.")} />;
  }

  return (
    <div className={styles.root}>
      <header className={styles.header}>
        <div>
          <p className={styles.eyebrow}>WORLD WORKSPACE</p>
          <h1 className={styles.title}>{uiText("내 World")}</h1>
          <p className={styles.description}>
            {uiText("World를 만들고, 초안을 저장하고, 공개까지 관리해요.")}</p>
        </div>
        <div className={styles.actions}>
          <Link className={styles.secondaryAction} href={PRODUCT_ROUTES.studioImport}>
            {uiText("World 패키지 가져오기")}</Link>
          <Link className={styles.primaryAction} href={PRODUCT_ROUTES.studioNewWorld}>
            {uiText("새 World 만들기")}</Link>
        </div>
      </header>

      {worlds.length === 0 ? (
        <section className={styles.empty}>
          <h2>{uiText("아직 만든 World가 없어요.")}</h2>
          <p>{uiText("첫 World를 만들고 공개하면 기기 홈에서 열 수 있어요.")}</p>
          <Link className={styles.primaryAction} href={PRODUCT_ROUTES.studioNewWorld}>
            {uiText("World 초안 시작")}</Link>
        </section>
      ) : (
        <div className={styles.groups}>
          {GROUPS.map((group) => {
            const items = grouped.get(group.id) ?? [];
            if (items.length === 0) return null;
            return (
              <section key={group.id}>
                <div className={styles.groupHeader}>
                  <h2>{uiText(group.label)}</h2>
                  <span>{uiText(group.description)} · {items.length}</span>
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
  const uiText = useUiText("creator-studio");
  return (
    <article className={styles.worldCard}>
      <div className={styles.worldCardHeader}>
        <div>
          <h3>{world.name}</h3>
          <p>{world.tagline || uiText("한 줄 소개가 아직 없어요.")}</p>
        </div>
        <span className={styles.status}>{uiText(statusLabel(world))}</span>
      </div>
      <div className={styles.meta}>
        <span>{uiText(({ private: "비공개", unlisted: "목록에 표시하지 않음", public: "공개" } as const)[world.visibility] ?? "공개 범위 확인 필요")}</span>
        <span>{uiText(({ not_ready: "작성 중", publish_ready: "공개 준비 완료", stale: "다시 확인 필요" } as const)[world.readiness_status as "not_ready" | "publish_ready" | "stale"] ?? "공개 준비 확인 필요")}</span>
        <span>{uiText(({ owner: "소유자", editor: "편집자", member: "참여자" } as const)[world.membership_role as "owner" | "editor" | "member"] ?? "참여 권한 확인 필요")}</span>
      </div>
      <div className={styles.actions}>
        <Link className={styles.secondaryAction} href={studioWorldRoute(world.world_id)}>
          {uiText("편집")}</Link>
        {world.launchable ? (
          <Link className={styles.primaryAction} href={worldAppRoute(world.world_id)}>
            {uiText("World 열기")}</Link>
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
  if (world.readiness_status === "stale") return "다시 확인 필요";
  return "초안";
}
