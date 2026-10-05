"use client";
import { useUiText } from "@/hooks/use-ui-text";


import Link from "next/link";
import Image from "next/image";
import type { LocalWorldAppRead, OwnerControlledActorRead } from "@/features/worlds/types/world-app";
import {
  ArrowLeft,
  House,
  MessageCircle,
  Network,
  Newspaper,
  Users,
} from "lucide-react";
import { useEffect, useState, type ReactNode } from "react";

import { WorldCharacterManagementScreen } from "@/composition/screens/world-character-management-screen";
import { WorldChatScreen as WorldChat } from "@/composition/screens/world-chat-screen";
import { WorldCharacterDirectory } from "@/features/characters/components/world-character-directory";
import { WorldSocialFeed } from "@/features/social/components/world-social-feed";
import { ImagePicker } from "@/features/media/components/image-picker";
import { FeedHeader } from "@/components/layout/feed-header";
import { LocalProductLink } from "@/components/navigation/local-product-link";
import { ProfileAvatar } from "@/components/ui/profile-avatar";
import { GenerationStatus } from "@/features/media/components/generation-status";
import { PRODUCT_ROUTES, relationshipGraphRoute, studioWorldRoute, worldCharacterProfileRoute } from "@/lib/navigation/product-routes";
import { BottomNavigation, type BottomNavigationItem } from "@/components/ui/navigation";
import { StatusBadge } from "@/components/ui/status-badge";
import { getLocalWorldApp, getOwnerControlledActor, WorldAppApiError } from "@/features/worlds/api/world-app-client";
import { ensureMyProfile, WorldApiError } from "@/features/worlds/api/worlds";
import { WORLD_APP_SECTIONS, worldAppSectionRoute, type WorldAppSection, type WorldAppSectionId } from "@/composition/shells/world-app-navigation";
import { WorldAppShell } from "@/composition/shells/world-app-shell";
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

export function WorldApp(props: WorldAppProps) {
  return <WorldAppContent key={`${props.worldId}:${props.authStatus}`} {...props} />;
}

function WorldAppContent({
  authStatus,
  chatThreadId,
  postId,
  sectionId,
  worldCharacterId,
  worldId,
}: WorldAppProps) {
  const uiText = useUiText("shell");
  const [world, setWorld] = useState<LocalWorldAppRead["world"] | null>(null);
  const [ownerActor, setOwnerActor] = useState<OwnerControlledActorRead | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<WorldAppApiError | Error | null>(null);

  useEffect(() => {
    if (authStatus !== "authenticated") return;
    const controller = new AbortController();
    const worldRead = getLocalWorldApp(worldId, { signal: controller.signal });
    void Promise.all([
      worldRead,
      getOwnerControlledActor(worldId, { signal: controller.signal }).then(async (actor) => {
        if (actor) return actor;
        // Reads may overlap, but a new identity requires a verified launchable
        // owner World. A rejected or abandoned route must not start a write.
        await worldRead;
        return controller.signal.aborted ? null : ensureMyProfile(worldId);
      }),
    ])
      .then(([read, identity]) => {
        if (controller.signal.aborted) return;
        setWorld(read.world);
        setOwnerActor(identity);
      })
      .catch((reason: unknown) => {
        if (controller.signal.aborted) return;
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
        title={uiText("World 앱을 확인하는 중")}
        description={uiText("owner 권한과 World 상태를 안전하게 확인하고 있어요.")}
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
        title={uiText("로컬 owner 연결이 필요해요")}
        description={uiText("owner session을 확인한 뒤 이 World 앱을 다시 엽니다.")}
        href={`/login?returnTo=${encodeURIComponent(returnTo)}`}
        linkLabel={uiText("owner 연결")}
        worldId={worldId}
      />
    );
  }
  if (error || !world) {
    const recovery = error instanceof WorldApiError && error.status === 409 && error.message.includes("preserved_identity_selection_required");
    const unavailable = error instanceof WorldAppApiError && [403, 404].includes(error.status);
    return (
      <WorldGate
        activeSection={activeSection}
        title={recovery ? uiText("이어서 사용할 내 프로필을 선택해주세요") : unavailable ? uiText("이 World 앱을 열 수 없어요") : uiText("World 앱을 불러오지 못했어요")}
        description={
          recovery ? uiText("보존된 프로필이 있습니다. World 관리에서 하나를 선택하면 기존 글·대화·관계를 그대로 이어갑니다.") : unavailable
            ? uiText("권한이 없거나 World가 보관 상태로 바뀌었습니다. 다른 World로 자동 이동하지 않습니다.")
            : uiText("runtime 상태를 확인한 뒤 다시 시도해주세요.")
        }
        href={recovery ? studioWorldRoute(worldId) : unavailable ? PRODUCT_ROUTES.deviceHome : PRODUCT_ROUTES.settings}
        linkLabel={recovery ? uiText("내 프로필 복구") : unavailable ? uiText("Device Home으로 돌아가기") : uiText("설정 열기")}
        worldId={worldId}
      />
    );
  }

  return (
    <WorldAppShell
      headerMode={activeSection.id === "home" ? "shell" : "content"}
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
  const uiText = useUiText("shell");
  const items: BottomNavigationItem[] = WORLD_APP_SECTIONS.map((section) => ({
    href: worldAppSectionRoute(worldId, section),
    icon: SECTION_ICONS[section.id],
    id: section.id,
    label: uiText(section.label),
  }));
  return (
    <BottomNavigation
      activeId={activeSection.id}
      ariaLabel={uiText("World 앱 기능")}
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

function WorldFeedHeader({ ownerActor, worldId }: { ownerActor: OwnerControlledActorRead | null; worldId: string }) {
  const uiText = useUiText("shell");
  const socialText = useUiText("social");
  return (
    <FeedHeader
      title={uiText("피드")}
      center={
        <LocalProductLink ariaLabel="Angmoo" className={styles.feedLogo} href={PRODUCT_ROUTES.deviceHome}>
          <Image src="/icon.svg" alt={uiText("Angmoo 로고")} width={48} height={48} priority />
        </LocalProductLink>
      }
      right={ownerActor ? (
        <LocalProductLink ariaLabel={socialText("내 프로필")} title={socialText("내 프로필")} className={styles.feedProfile}
          href={worldCharacterProfileRoute(worldId, ownerActor.world_character_id)}>
          <ProfileAvatar name={ownerActor.profile.display_name} avatarUrl={ownerActor.profile.avatar_url}
            sizeClassName={styles.feedProfileAvatar} textClassName={styles.feedProfileInitial} />
        </LocalProductLink>
      ) : null}
    />
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
  world: LocalWorldAppRead["world"];
  worldCharacterId?: string;
  worldId: string;
}) {
  const uiText = useUiText("shell");
  if (activeSection.id === "home") {
    return (
      <section className={styles.worldOverview}>
        <div className={styles.overviewHeading}>
          <StatusBadge label={uiText("실행 가능")} tone="healthy" />
          <span className={styles.role}>{world.membership_role}</span>
        </div>
        <h2>{world.name}</h2>
        <p className={styles.tagline}>{world.tagline || uiText("이 World의 일상을 만나보세요.")}</p>
        <div className={styles.scopeNotice}>
          <strong>{uiText("World 경계가 적용됐어요")}</strong>
          <p>{uiText("아래 기능은 항상 이 World의 식별자를 유지하며, 다른 World로 자동 fallback하지 않습니다.")}</p>
        </div>
        <div className={styles.scopeNotice}>
          <strong>{uiText("이 World의 내 프로필")}</strong>
          {ownerActor ? (
            <p>
              {ownerActor.profile.display_name} · @{ownerActor.profile.handle}
            </p>
          ) : (
            <p>{uiText("World 관리에서 내 프로필을 확인할 수 있습니다.")}</p>
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
        feedHeader={<WorldFeedHeader ownerActor={ownerActor} worldId={worldId} />}
        renderImagePicker={input => <ImagePicker scopeKind="world" scopeId={worldId} value={input.value} onChange={input.onChange} disabled={input.disabled} onBusyChange={input.onBusyChange} renderLayout={input.renderLayout} />}
        imageStatus={GenerationStatus}
      />
    );
  }

  if (activeSection.id === "chat") {
    return <WorldChat threadId={chatThreadId} worldId={worldId} />;
  }

  if (activeSection.id === "characters") {
    return worldCharacterId ? (
      <WorldCharacterManagementScreen
        worldCharacterId={worldCharacterId}
        worldId={worldId}
      />
    ) : (
      <WorldCharacterDirectory key={worldId} worldId={worldId} />
    );
  }

  if (activeSection.id === "relationships") {
    return (
      <section className={styles.capability}>
        <div className={styles.capabilityIcon}>{SECTION_ICONS[activeSection.id]}</div>
        <p className={styles.capabilityKicker}>{activeSection.label}</p>
        <h2>{uiText("이 World의 관계망")}</h2>
        {ownerActor ? (
          <>
            <p>
              {uiText("기준 캐릭터: {{name}}. 이 World 안의 관계와 근거를 확인합니다.", {name: ownerActor.profile.display_name})}</p>
            <Link
              className={styles.capabilityAction}
              href={relationshipGraphRoute(ownerActor.character_id, worldId)}
            >
              {uiText("내 조종 앵무 관계망 열기")}</Link>
          </>
        ) : (
          <p>{uiText("Creator Studio에서 사용자 조종 앵무를 만든 뒤 관계망을 열 수 있습니다.")}</p>
        )}
      </section>
    );
  }

  return (
    <section className={styles.capability} role="status">
      <div className={styles.capabilityIcon}>{SECTION_ICONS[activeSection.id]}</div>
      <p className={styles.capabilityKicker}>{activeSection.label}</p>
      <h2>{uiText("이 World 전용 기능은 준비 중이에요")}</h2>
      <p>{uiText(activeSection.description)}</p>
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
  const uiText = useUiText("shell");
  return (
    <WorldAppShell
      navigation={<WorldNavigation activeSection={activeSection} worldId={worldId} />}
      status={<WorldHomeReturn />}
      worldId={worldId}
      worldName={uiText("World 앱")}
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
