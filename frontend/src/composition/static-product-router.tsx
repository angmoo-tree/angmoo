"use client";

import Link from "next/link";
import { useEffect, useState, useSyncExternalStore } from "react";

import { AgentDetailClient } from "@/components/agent-detail-client";
import { AppShell } from "@/components/app-shell";
import { LocalOwnerClient } from "@/components/local-owner-client";
import { PostDetailClient } from "@/components/post-detail-client";
import { PostListClient } from "@/components/post-list-client";
import { RelationshipGraphClient } from "@/components/relationship-graph-client";
import { SettingsClient } from "@/components/settings-client";
import { WorldCharacterAutonomySetupClient } from "@/components/world-character-autonomy-setup-client";
import { WorldCreatorClient } from "@/components/world-creator-client";
import { DeviceHomeRouteClient } from "@/app/device-home-route-client";
import { StudioRouteClient } from "@/app/studio/studio-route-client";
import { WorldAppRouteClient } from "@/app/world-app-route-client";
import { CreatorStudioFrame } from "@/features/creator-studio/public";
import {
  currentDesktopRoute,
  subscribeDesktopRoute,
} from "@/shared/desktop/public";
import {
  worldAppSectionFromSegment,
  type WorldAppSectionId,
} from "@/features/world-app/public";
import {
  getPostThread,
  listFeed,
  type FeedPage,
  type PostThreadRead,
} from "@/lib/community";
import { safeLoginReturnTo } from "@/lib/safe-navigation";
import { DesktopRuntimeGate } from "@/shared/runtime/desktop-runtime-gate";

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
  return (
    <DesktopRuntimeGate>{renderStaticRoute(location)}</DesktopRuntimeGate>
  );
}

function renderStaticRoute(location: BrowserLocation) {
  const { pathname, search } = location;
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
  if (pathname === "/posts") return <StaticFeedRoute />;
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

  const segments = pathname.split("/").filter(Boolean);
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
  if (segments[0] === "worlds" && segments.length >= 2 && segments.length <= 3) {
    const worldId = decodedSegment(segments[1]);
    const section = staticWorldSection(segments[2]);
    if (worldId && section) {
      return <WorldAppRouteClient sectionId={section} worldId={worldId} />;
    }
  }
  if (segments[0] === "agents" && segments.length === 2) {
    const characterId = decodedSegment(segments[1]);
    if (characterId) {
      return (
        <AppShell>
          <AgentDetailClient characterId={characterId} />
        </AppShell>
      );
    }
  }
  if (segments[0] === "posts" && segments.length === 2) {
    const postId = decodedSegment(segments[1]);
    if (postId) return <StaticPostRoute postId={postId} />;
  }
  if (
    segments[0] === "characters" &&
    segments[2] === "worlds" &&
    segments.length === 5
  ) {
    const characterId = decodedSegment(segments[1]);
    const worldId = decodedSegment(segments[3]);
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
      const provider = new URLSearchParams(search).get("provider");
      return (
        <AppShell>
          <RelationshipGraphClient
            characterId={characterId}
            provider={provider === "ladybug" ? "ladybug" : "neo4j"}
            worldId={worldId}
          />
        </AppShell>
      );
    }
  }
  return <StaticNotFound pathname={pathname} />;
}

function staticWorldSection(segment: string | undefined): WorldAppSectionId | null {
  if (!segment) return "home";
  return worldAppSectionFromSegment(segment)?.id ?? null;
}

function StaticFeedRoute() {
  const [feed, setFeed] = useState<FeedPage>(EMPTY_FEED);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    listFeed({ limit: 10 })
      .then((result) => {
        if (active) setFeed(result);
      })
      .catch((reason) => {
        if (active) {
          setError(reason instanceof Error ? reason.message : "게시글을 불러오지 못했습니다.");
        }
      });
    return () => {
      active = false;
    };
  }, []);

  return (
    <AppShell>
      <PostListClient initialError={error} initialFeed={feed} />
    </AppShell>
  );
}

function StaticPostRoute({ postId }: { postId: string }) {
  const [thread, setThread] = useState<PostThreadRead | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    getPostThread(postId)
      .then((result) => {
        if (active) setThread(result);
      })
      .catch((reason) => {
        if (active) {
          setError(reason instanceof Error ? reason.message : "게시글을 불러오지 못했습니다.");
        }
      });
    return () => {
      active = false;
    };
  }, [postId]);

  return (
    <AppShell>
      <PostDetailClient
        initialError={error}
        initialThread={thread}
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
    <main className="flex min-h-screen items-center justify-center bg-[#fff8f7] px-6 text-center">
      <div className="max-w-lg rounded-[32px] border border-[#e0bfbd] bg-white p-8">
        <h1 className="text-2xl font-extrabold text-[#251818]">지원하지 않는 Angmoo 경로입니다.</h1>
        <p className="mt-3 break-all text-sm text-[#584140]">{pathname}</p>
        <Link className="mt-6 inline-flex rounded-full bg-[#ae2f34] px-5 py-3 font-bold text-white" href="/">
          Device Home으로 돌아가기
        </Link>
      </div>
    </main>
  );
}
