"use client";

import Link from "next/link";
import { useEffect, useState, useSyncExternalStore } from "react";

import { AgentCreateClient } from "@/components/agent-create-client";
import { AgentDetailClient } from "@/components/agent-detail-client";
import { AgentsDashboardClient } from "@/features/characters/public";
import { AppShell } from "@/components/app-shell";
import { LocalOwnerClient } from "@/components/local-owner-client";
import { PostDetailClient } from "@/components/post-detail-client";
import {
  getSocialPostThread,
  listSocialFeed,
  PostListClient,
  type FeedPage,
  type PostThreadRead,
} from "@/features/social/public";
import {
  RelationshipGraphClient,
  RelationshipGraphFrame,
} from "@/features/relationships/public";
import { SettingsClient } from "@/components/settings-client";
import { WorldCharacterAutonomySetupClient } from "@/components/world-character-autonomy-setup-client";
import { WorldCreatorClient } from "@/components/world-creator-client";
import { DeviceHomeRouteClient } from "@/app/device-home-route-client";
import { StudioImportRouteClient } from "@/app/studio/import/studio-import-route-client";
import { StudioRouteClient } from "@/app/studio/studio-route-client";
import { WorldAppRouteClient } from "@/app/world-app-route-client";
import { CreatorStudioFrame } from "@/features/creator-studio/public";
import { SemanticFoundationFixture } from "@/features/ui-foundation/public";
import {
  canonicalProductRoute,
  currentDesktopRoute,
  desktopWindowKindForRoute,
  getDesktopWindowState,
  subscribeDesktopRoute,
} from "@/shared/desktop/public";
import { useRuntimeRouter } from "@/shared/navigation/public";
import {
  worldAppSectionFromSegment,
  type WorldAppSectionId,
} from "@/features/world-app/public";
import { safeLoginReturnTo } from "@/lib/safe-navigation";
import { DesktopRuntimeGate } from "@/shared/runtime/desktop-runtime-gate";
import { getRuntimeConfig } from "@/shared/runtime/public";

type BrowserLocation = {
  pathname: string;
  search: string;
};

const EMPTY_FEED: FeedPage = { items: [], next_cursor: null };

function decodedSegment(value: string) {
  try {
    const decoded = decodeURIComponent(value);
    return decoded && decoded !== "." && decoded !== ".." ? decoded : null;
  } catch {
    return null;
  }
}

function decodedWorldId(value: string) {
  const worldId = decodedSegment(value);
  return worldId && worldId !== "new" ? worldId : null;
}

export function StaticProductRouter() {
  const locationValue = useSyncExternalStore(
    subscribeDesktopRoute,
    () => {
      const route = new URL(currentDesktopRoute(), "http://angmoo.local");
      return `${route.pathname}\n${route.search}`;
    },
    () => "",
  );
  if (!locationValue) {
    return (
      <DesktopRuntimeGate>
        <StaticLoadingScreen />
      </DesktopRuntimeGate>
    );
  }
  const [rawPathname, search = ""] = locationValue.split("\n", 2);
  const location: BrowserLocation = {
    pathname: rawPathname.replace(/\/+$/, "") || "/",
    search,
  };
  const desktopState = getDesktopWindowState();
  const route = `${location.pathname}${location.search}`;
  if (
    desktopState &&
    desktopWindowKindForRoute(route) !== desktopState.kind
  ) {
    return (
      <DesktopRuntimeGate>
        <StaticWindowRouteMismatch
          actualRoute={route}
          expectedWindow={desktopState.kind}
        />
      </DesktopRuntimeGate>
    );
  }
  return (
    <DesktopRuntimeGate>{renderStaticRoute(location)}</DesktopRuntimeGate>
  );
}

function StaticWindowRouteMismatch({
  actualRoute,
  expectedWindow,
}: {
  actualRoute: string;
  expectedWindow: string;
}) {
  return (
    <main className="flex min-h-screen items-center justify-center bg-surface p-8 text-on-surface">
      <section className="max-w-xl rounded-[32px] border border-outline-variant bg-surface-container-lowest p-8 shadow-sm">
        <p className="text-xs font-bold uppercase tracking-[0.18em] text-state-running">
          Product window boundary
        </p>
        <h1 className="mt-3 text-2xl font-black">제품 창 경로를 열지 못했습니다.</h1>
        <p className="mt-4 text-sm leading-6 text-on-surface-variant">
          {expectedWindow} 창이 허용하지 않는 경로를 받아 Device Home으로 대체하지
          않았습니다. 창을 닫고 원래 화면에서 다시 열어주세요.
        </p>
        <p className="mt-4 break-all font-mono text-xs text-on-surface-variant">
          {actualRoute}
        </p>
      </section>
    </main>
  );
}

function renderStaticRoute(location: BrowserLocation) {
  const { pathname, search } = location;
  if (pathname === "/ui-foundation") return <SemanticFoundationFixture />;
  if (pathname === "/") return <DeviceHomeRouteClient />;
  if (pathname === "/studio") {
    return (
      <CreatorStudioFrame activeSection="worlds">
        <StudioRouteClient />
      </CreatorStudioFrame>
    );
  }
  if (pathname === "/studio/worlds/new") {
    return (
      <CreatorStudioFrame activeSection="new-world">
        <WorldCreatorClient />
      </CreatorStudioFrame>
    );
  }
  if (pathname === "/studio/import") {
    return (
      <CreatorStudioFrame activeSection="import">
        <StudioImportRouteClient />
      </CreatorStudioFrame>
    );
  }
  if (pathname === "/posts") return <StaticFeedRoute />;
  if (pathname === "/agents") {
    return (
      <AppShell>
        <AgentsDashboardClient />
      </AppShell>
    );
  }
  if (pathname === "/agents/new") {
    return (
      <AppShell>
        <AgentCreateClient />
      </AppShell>
    );
  }
  if (pathname === "/settings") {
    return (
      <AppShell>
        <SettingsClient />
      </AppShell>
    );
  }
  if (pathname === "/login") {
    const params = new URLSearchParams(search);
    return (
      <AppShell>
        <LocalOwnerClient
          logoutLocallyOnly={params.get("logout") === "local-only"}
          returnTo={safeLoginReturnTo(params.get("returnTo"))}
        />
      </AppShell>
    );
  }
  if (pathname === "/worlds/new") {
    return <StaticCanonicalRouteRedirect route={canonicalProductRoute(`${pathname}${search}`)} />;
  }

  const segments = pathname.split("/").filter(Boolean);
  if (
    segments[0] === "worlds" &&
    segments[2] === "creator" &&
    segments.length === 3
  ) {
    return <StaticCanonicalRouteRedirect route={canonicalProductRoute(`${pathname}${search}`)} />;
  }
  if (segments[0] === "studio" && segments[1] === "worlds" && segments.length === 3) {
    const worldId = decodedSegment(segments[2]);
    if (worldId) {
      return (
        <CreatorStudioFrame activeSection="worlds">
          <WorldCreatorClient worldId={worldId} />
        </CreatorStudioFrame>
      );
    }
  }
  if (
    segments[0] === "worlds" &&
    segments[2] === "posts" &&
    segments.length === 4
  ) {
    const worldId = decodedWorldId(segments[1]);
    const postId = decodedSegment(segments[3]);
    if (worldId && postId) {
      return <WorldAppRouteClient postId={postId} sectionId="feed" worldId={worldId} />;
    }
  }
  if (
    segments[0] === "worlds" &&
    segments[2] === "chat" &&
    segments.length === 4
  ) {
    const worldId = decodedWorldId(segments[1]);
    const threadId = decodedSegment(segments[3]);
    if (worldId && threadId) {
      return (
        <WorldAppRouteClient
          chatThreadId={threadId}
          sectionId="chat"
          worldId={worldId}
        />
      );
    }
  }
  if (segments[0] === "worlds" && segments.length >= 2 && segments.length <= 3) {
    const worldId = decodedWorldId(segments[1]);
    const section = staticWorldSection(segments[2]);
    if (worldId && section) {
      return <WorldAppRouteClient sectionId={section} worldId={worldId} />;
    }
  }
  if (segments[0] === "agents" && segments.length === 2) {
    const characterId = decodedSegment(segments[1]);
    if (characterId && characterId !== "new") {
      return (
        <AppShell>
          <AgentDetailClient characterId={characterId} />
        </AppShell>
      );
    }
  }
  if (segments[0] === "posts" && segments.length === 2) {
    const postId = decodedSegment(segments[1]);
    if (postId) return <StaticPostRoute key={postId} postId={postId} />;
  }
  if (
    segments[0] === "characters" &&
    segments[2] === "worlds" &&
    segments.length === 5
  ) {
    const characterId = decodedSegment(segments[1]);
    const worldId = decodedWorldId(segments[3]);
    if (characterId && worldId && segments[4] === "autonomy-setup") {
      return (
        <AppShell>
          <WorldCharacterAutonomySetupClient
            characterId={characterId}
            worldId={worldId}
          />
        </AppShell>
      );
    }
    if (characterId && worldId && segments[4] === "relationship-graph") {
      const provider = getRuntimeConfig()?.graphProvider ?? "ladybug";
      return (
        <RelationshipGraphFrame>
          <RelationshipGraphClient
            characterId={characterId}
            provider={provider}
            worldId={worldId}
          />
        </RelationshipGraphFrame>
      );
    }
  }
  return <StaticNotFound pathname={pathname} />;
}

function StaticCanonicalRouteRedirect({ route }: { route: string }) {
  const router = useRuntimeRouter();
  useEffect(() => {
    router.replace(route);
  }, [route, router]);
  return (
    <main className="min-h-screen bg-transparent" aria-live="polite">
      <span className="sr-only">Canonical Angmoo 제품 경로로 이동합니다.</span>
    </main>
  );
}

function staticWorldSection(segment: string | undefined): WorldAppSectionId | null {
  if (!segment) return "home";
  return worldAppSectionFromSegment(segment)?.id ?? null;
}

function StaticFeedRoute() {
  const [feed, setFeed] = useState<FeedPage>(EMPTY_FEED);
  const [error, setError] = useState<string | null>(null);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    let active = true;
    listSocialFeed({ limit: 10 })
      .then((result) => {
        if (active) setFeed(result);
      })
      .catch((reason) => {
        if (active) {
          setError(reason instanceof Error ? reason.message : "게시글을 불러오지 못했습니다.");
        }
      })
      .finally(() => {
        if (active) setReady(true);
      });
    return () => {
      active = false;
    };
  }, []);

  if (!ready) {
    return (
      <AppShell>
        <section className="px-5 py-8 text-sm font-bold text-on-surface-variant" aria-live="polite">
          피드를 불러오는 중
        </section>
      </AppShell>
    );
  }

  return (
    <AppShell>
      <PostListClient initialError={error} initialFeed={feed} />
    </AppShell>
  );
}

function StaticPostRoute({ postId }: { postId: string }) {
  const [thread, setThread] = useState<PostThreadRead | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    let active = true;
    getSocialPostThread(postId)
      .then((result) => {
        if (active) setThread(result);
      })
      .catch((reason) => {
        if (active) {
          setError(reason instanceof Error ? reason.message : "게시글을 불러오지 못했습니다.");
        }
      })
      .finally(() => {
        if (active) setReady(true);
      });
    return () => {
      active = false;
    };
  }, [postId]);

  if (!ready) {
    return (
      <AppShell>
        <section
          className="px-5 py-8 text-sm font-bold text-on-surface-variant"
          aria-live="polite"
        >
          게시글을 불러오는 중
        </section>
      </AppShell>
    );
  }

  return (
    <AppShell>
      <PostDetailClient
        initialError={error}
        initialThread={thread}
        key={postId}
        postId={postId}
      />
    </AppShell>
  );
}

function StaticLoadingScreen() {
  return (
    <main className="min-h-screen bg-transparent" aria-live="polite">
      <span className="sr-only">Angmoo 제품 화면을 준비하고 있습니다.</span>
    </main>
  );
}

function StaticNotFound({ pathname }: { pathname: string }) {
  return (
    <main className="flex min-h-screen items-center justify-center bg-canvas px-6 text-center">
      <div className="max-w-lg rounded-[32px] border border-border-control bg-surface p-8 shadow-summary">
        <h1 className="text-2xl font-extrabold text-text-strong">지원하지 않는 Angmoo 경로입니다.</h1>
        <p className="mt-3 break-all text-sm text-text-default">{pathname}</p>
        <Link className="mt-6 inline-flex rounded-full bg-action-primary px-5 py-3 font-bold text-on-action-primary shadow-action transition-colors hover:bg-action-primary-hover focus-visible:outline-none focus-visible:shadow-[var(--focus-ring)]" href="/">
          Device Home으로 돌아가기
        </Link>
      </div>
    </main>
  );
}
