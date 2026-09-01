"use client";

import Link from "next/link";
import {
  ArrowLeft,
  House,
  MessageCircle,
  Network,
  Newspaper,
  Users,
} from "lucide-react";
import { useEffect, useState, type ReactNode } from "react";

import type { WorldSurfaceItem } from "@/features/device-home/public";
import { WorldChat } from "@/features/chat/public";
import {
  WorldCharacterDirectory,
  WorldCharacterProfile,
} from "@/features/characters/public";
import { WorldSocialFeed } from "@/features/social/public";
import {
  PRODUCT_ROUTES,
  relationshipGraphRoute,
  worldCharacterProfileRoute,
} from "@/shared/navigation/public";
import {
  BottomNavigation,
  StatusBadge,
  type BottomNavigationItem,
} from "@/shared/ui/public";
import {
  getLocalWorldApp,
  getOwnerControlledActor,
  type OwnerControlledActorRead,
  WorldAppApiError,
} from "../api/world-app-client";
import {
  WORLD_APP_SECTIONS,
  worldAppSectionRoute,
  type WorldAppSection,
  type WorldAppSectionId,
} from "../model/world-app-contract";
import { WorldAppShell } from "./world-app-shell";
import styles from "./world-app.module.css";


export type WorldAppAuthStatus =
  | "checking"
  | "authenticated"
  | "unauthenticated";

type WorldAppProps = {
  authStatus: WorldAppAuthStatus;
  chatThreadId?: string;
  postId?: string;
  sectionId: WorldAppSectionId;
  worldCharacterId?: string;
  worldId: string;
};

const SECTION_ICONS: Record<WorldAppSectionId, ReactNode> = {
  home: <House size={19} strokeWidth={2.2} />,
  feed: <Newspaper size={19} strokeWidth={2.2} />,
  chat: <MessageCircle size={19} strokeWidth={2.2} />,
  characters: <Users size={19} strokeWidth={2.2} />,
  relationships: <Network size={19} strokeWidth={2.2} />,
};

const NO_SPECIFIC_ROLE_KEY = "no_specific_role";

function worldRoleLabel(roleKey: string | null) {
  return !roleKey || roleKey === NO_SPECIFIC_ROLE_KEY ? "역할 없음" : roleKey;
}

export function WorldApp({
  authStatus,
  chatThreadId,
  postId,
  sectionId,
  worldCharacterId,
  worldId,
}: WorldAppProps) {
  const [world, setWorld] = useState<WorldSurfaceItem | null>(null);
  const [ownerActor, setOwnerActor] = useState<OwnerControlledActorRead | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<WorldAppApiError | Error | null>(null);

  useEffect(() => {
    if (authStatus !== "authenticated") return;
    const controller = new AbortController();
    void Promise.all([
      getLocalWorldApp(worldId, { signal: controller.signal }),
      getOwnerControlledActor(worldId, { signal: controller.signal }),
    ])
      .then(([read, identity]) => {
        setWorld(read.world);
        setOwnerActor(identity);
      })
      .catch((reason: unknown) => {
        if (reason instanceof DOMException && reason.name === "AbortError") return;
        setWorld(null);
        setError(reason instanceof Error ? reason : new Error("world_app_unavailable"));
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [authStatus, worldId]);

  const activeSection =
    WORLD_APP_SECTIONS.find((section) => section.id === sectionId) ?? WORLD_APP_SECTIONS[0];

  if (authStatus === "checking" || (authStatus === "authenticated" && loading)) {
    return (
      <WorldGate
        activeSection={activeSection}
        title="World 앱을 확인하는 중"
        description="owner 권한과 World 상태를 안전하게 확인하고 있어요."
        worldId={worldId}
      />
    );
  }
  if (authStatus === "unauthenticated") {
    const returnTo =
      sectionId === "characters" && worldCharacterId
        ? worldCharacterProfileRoute(worldId, worldCharacterId)
        : sectionId === "chat" && chatThreadId
        ? `${worldAppSectionRoute(worldId, activeSection)}/${encodeURIComponent(chatThreadId)}`
        : worldAppSectionRoute(worldId, activeSection);
    return (
      <WorldGate
        activeSection={activeSection}
        title="로컬 owner 연결이 필요해요"
        description="owner session을 확인한 뒤 이 World 앱을 다시 엽니다."
        href={`/login?returnTo=${encodeURIComponent(returnTo)}`}
        linkLabel="owner 연결"
        worldId={worldId}
      />
    );
  }
  if (error || !world) {
    const unavailable = error instanceof WorldAppApiError && [403, 404].includes(error.status);
    return (
      <WorldGate
        activeSection={activeSection}
        title={unavailable ? "이 World 앱을 열 수 없어요" : "World 앱을 불러오지 못했어요"}
        description={
          unavailable
            ? "권한이 없거나 World가 보관·비공개 상태로 바뀌었습니다. 다른 World로 자동 이동하지 않습니다."
            : "runtime 상태를 확인한 뒤 다시 시도해주세요."
        }
        href={unavailable ? PRODUCT_ROUTES.deviceHome : PRODUCT_ROUTES.settings}
        linkLabel={unavailable ? "Device Home으로 돌아가기" : "설정 열기"}
        worldId={worldId}
      />
    );
  }

  return (
    <WorldAppShell
      navigation={<WorldNavigation activeSection={activeSection} worldId={worldId} />}
      status={
        <WorldHomeReturn />
      }
      worldId={world.world_id}
      worldName={world.name}
    >
      <WorldSection
        activeSection={activeSection}
        chatThreadId={chatThreadId}
        ownerActor={ownerActor}
        postId={postId}
        world={world}
        worldCharacterId={worldCharacterId}
        worldId={worldId}
      />
    </WorldAppShell>
  );
}

function WorldNavigation({
  activeSection,
  worldId,
}: {
  activeSection: WorldAppSection;
  worldId: string;
}) {
  const items: BottomNavigationItem[] = WORLD_APP_SECTIONS.map((section) => ({
    href: worldAppSectionRoute(worldId, section),
    icon: SECTION_ICONS[section.id],
    id: section.id,
    label: section.label,
  }));
  return (
    <BottomNavigation
      activeId={activeSection.id}
      ariaLabel="World 앱 기능"
      items={items}
    />
  );
}

function WorldHomeReturn() {
  return (
    <Link className={styles.homeReturn} href={PRODUCT_ROUTES.deviceHome}>
      <ArrowLeft size={16} aria-hidden="true" />
      Device Home
    </Link>
  );
}

function WorldSection({
  activeSection,
  chatThreadId,
  ownerActor,
  postId,
  world,
  worldCharacterId,
  worldId,
}: {
  activeSection: WorldAppSection;
  chatThreadId?: string;
  ownerActor: OwnerControlledActorRead | null;
  postId?: string;
  world: WorldSurfaceItem;
  worldCharacterId?: string;
  worldId: string;
}) {
  if (activeSection.id === "home") {
    return (
      <section className={styles.worldOverview}>
        <div className={styles.overviewHeading}>
          <StatusBadge label="실행 가능" tone="healthy" />
          <span className={styles.role}>{world.membership_role}</span>
        </div>
        <h2>{world.name}</h2>
        <p className={styles.tagline}>{world.tagline || "이 World의 일상을 만나보세요."}</p>
        <div className={styles.scopeNotice}>
          <strong>World 경계가 적용됐어요</strong>
          <p>아래 기능은 항상 이 World의 식별자를 유지하며, 다른 World로 자동 fallback하지 않습니다.</p>
        </div>
        <div className={styles.scopeNotice}>
          <strong>이 World에서 내가 조종하는 앵무</strong>
          {ownerActor ? (
            <p>
              {ownerActor.profile.display_name} · 자동 활동 OFF · {worldRoleLabel(ownerActor.profile.role_key)}
            </p>
          ) : (
            <p>Creator Studio에서 사용자 조종 앵무를 만들 수 있습니다.</p>
          )}
        </div>
      </section>
    );
  }

  if (activeSection.id === "feed") {
    return (
      <WorldSocialFeed
        key={`${worldId}:${postId ?? "feed"}`}
        ownerActor={ownerActor}
        postId={postId}
        worldId={worldId}
      />
    );
  }

  if (activeSection.id === "chat") {
    return <WorldChat threadId={chatThreadId} worldId={worldId} />;
  }

  if (activeSection.id === "characters") {
    return worldCharacterId ? (
      <WorldCharacterProfile
        worldCharacterId={worldCharacterId}
        worldId={worldId}
      />
    ) : (
      <WorldCharacterDirectory worldId={worldId} />
    );
  }

  if (activeSection.id === "relationships") {
    return (
      <section className={styles.capability}>
        <div className={styles.capabilityIcon}>{SECTION_ICONS[activeSection.id]}</div>
        <p className={styles.capabilityKicker}>{activeSection.label}</p>
        <h2>이 World의 관계망</h2>
        {ownerActor ? (
          <>
            <p>
              기준 캐릭터: {ownerActor.profile.display_name}. 이 World 안의 관계와
              근거를 확인합니다.
            </p>
            <Link
              className={styles.capabilityAction}
              href={relationshipGraphRoute(ownerActor.character_id, worldId)}
            >
              내 조종 앵무 관계망 열기
            </Link>
          </>
        ) : (
          <p>Creator Studio에서 사용자 조종 앵무를 만든 뒤 관계망을 열 수 있습니다.</p>
        )}
      </section>
    );
  }

  return (
    <section className={styles.capability} role="status">
      <div className={styles.capabilityIcon}>{SECTION_ICONS[activeSection.id]}</div>
      <p className={styles.capabilityKicker}>{activeSection.label}</p>
      <h2>이 World 전용 기능은 준비 중이에요</h2>
      <p>{activeSection.description}</p>
    </section>
  );
}

function WorldGate({
  activeSection,
  description,
  href,
  linkLabel,
  title,
  worldId,
}: {
  activeSection: WorldAppSection;
  description: string;
  href?: string;
  linkLabel?: string;
  title: string;
  worldId: string;
}) {
  return (
    <WorldAppShell
      navigation={<WorldNavigation activeSection={activeSection} worldId={worldId} />}
      status={<WorldHomeReturn />}
      worldId={worldId}
      worldName="World 앱"
    >
      <section className={styles.gate} role="status">
        <div className={styles.gateCard}>
          <h1>{title}</h1>
          <p>{description}</p>
          {href && linkLabel ? <Link href={href}>{linkLabel}</Link> : null}
        </div>
      </section>
    </WorldAppShell>
  );
}
