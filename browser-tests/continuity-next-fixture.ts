import type { Page, Route } from "@playwright/test";

type WorldFixture = {
  world_id: string;
  name: string;
  tagline: string;
  banner_media_id: string | null;
  banner_alt_text: string;
  status: "draft" | "published" | "archived";
  visibility: "private" | "unlisted" | "public";
  readiness_status: "not_ready" | "publish_ready" | "stale";
  membership_role: "owner" | "editor" | "member";
  updated_at: string;
  launchable: boolean;
  launch_block_reason:
    | "world_archived"
    | "world_not_published"
    | "world_not_ready"
    | "world_private"
    | null;
};

const OWNER = {
  id: "local-owner",
  email: null,
  display_name: "Local Owner",
  display_name_updated_at: null,
  display_name_change_available_at: null,
  profile_setup_completed: true,
  feed_content_filter: "all",
  is_admin: true,
};

const WORLD_ALPHA: WorldFixture = {
  world_id: "world-alpha",
  name: "마법학교",
  tagline: "앵무들이 마법을 배우는 학교",
  banner_media_id: null,
  banner_alt_text: "마법학교",
  status: "published",
  visibility: "public",
  readiness_status: "publish_ready",
  membership_role: "owner",
  updated_at: "2026-08-17T00:00:00Z",
  launchable: true,
  launch_block_reason: null,
};

type BackendFixture = {
  agents?: unknown[];
  deviceWorlds?: WorldFixture[];
  deviceWorldFailuresBeforeSuccess?: number;
  studioWorlds?: WorldFixture[];
  worldReads?: Record<string, WorldFixture>;
  runtimeStatus?: number;
  runtimeState?: string;
};

async function installBackendFixture(
  page: Page,
  fixture: BackendFixture = {},
): Promise<{ reads: string[]; writes: string[]; providerCalls: string[] }> {
  const audit = { reads: [] as string[], writes: [] as string[], providerCalls: [] as string[] };
  let deviceWorldAttempts = 0;
  await page.route("**/api/backend/**", async (route: Route) => {
    const request = route.request();
    const url = new URL(request.url());
    const method = request.method();
    if (!["GET", "HEAD"].includes(method)) audit.writes.push(`${method} ${url.pathname}`);
    else audit.reads.push(`${method} ${url.pathname}${url.search}`);
    if (/provider|gemini|openai|anthropic|generate|completion/i.test(url.pathname)) {
      audit.providerCalls.push(`${method} ${url.pathname}`);
    }

    if (url.pathname === "/api/backend/auth/me" && method === "GET") {
      return json(route, OWNER);
    }
    if (url.pathname === "/api/backend/runtime/status") {
      if ((fixture.runtimeStatus ?? 200) >= 400) {
        return json(route, { detail: "runtime_unavailable" }, fixture.runtimeStatus ?? 503);
      }
      return json(route, {
        schema_version: "local-runtime-status-v1",
        installation_state: fixture.runtimeState ?? "ready",
      });
    }
    if (url.pathname === "/api/backend/agents" && method === "GET") {
      return json(route, fixture.agents ?? []);
    }
    if (url.pathname === "/api/backend/worlds/mine") {
      const surface = url.searchParams.get("surface");
      if (surface === "device_home") {
        deviceWorldAttempts += 1;
        if (
          deviceWorldAttempts <=
          (fixture.deviceWorldFailuresBeforeSuccess ?? 0)
        ) {
          return json(route, { detail: "device_home_unavailable" }, 503);
        }
      }
      const items =
        surface === "creator_studio"
          ? (fixture.studioWorlds ?? fixture.deviceWorlds ?? [])
          : (fixture.deviceWorlds ?? []);
      return json(route, {
        schema_version: "local-world-surface-v1",
        surface,
        items,
        next_cursor: null,
      });
    }
    const worldMatch = url.pathname.match(/^\/api\/backend\/worlds\/mine\/([^/]+)$/);
    if (worldMatch) {
      const worldId = decodeURIComponent(worldMatch[1]);
      const world = fixture.worldReads?.[worldId];
      if (!world) return json(route, { detail: "world_not_found" }, 404);
      return json(route, {
        schema_version: "local-world-app-v1",
        surface: "world_app",
        world,
      });
    }
    return json(route, { detail: `unexpected_browser_request:${url.pathname}` }, 404);
  });
  return audit;
}

async function json(route: Route, body: unknown, status = 200): Promise<void> {
  await route.fulfill({
    body: JSON.stringify(body),
    contentType: "application/json",
    status,
  });
}

const UI_D_WORLD_ID = "world-ui-d-next";
const UI_D_ROOT_POST_ID = "post-ui-d-next-root";

function uiDWorld(worldId = UI_D_WORLD_ID): WorldFixture {
  return {
    ...WORLD_ALPHA,
    world_id: worldId,
    name: "UI-D Social World",
    tagline: "Hosted social presentation parity",
  };
}

function uiDOwnerActor(worldId = UI_D_WORLD_ID) {
  return {
    schema_version: "owner-controlled-world-character-v1",
    world_character_id: "wc-ui-d-owner",
    world_id: worldId,
    character_id: "character-ui-d-owner",
    control_mode: "owner_controlled",
    status: "active",
    autonomous_enabled: false,
    version: 1,
    profile: {
      display_name: "UI-D Owner",
      avatar_url: "",
      intro: "World social test owner",
      role_key: null,
      preferred_address: "Owner",
      interests: [],
      background: "",
    },
  } as const;
}

function uiDManualPost({
  authorName = "UI-D Autonomous",
  body,
  canOwnerReply = true,
  id,
  likeCount = 0,
  replyCount = 0,
  replyToPostId = null,
  title,
  worldId = UI_D_WORLD_ID,
}: {
  authorName?: string;
  body: string;
  canOwnerReply?: boolean;
  id: string;
  likeCount?: number;
  replyCount?: number;
  replyToPostId?: string | null;
  title: string;
  worldId?: string;
}) {
  return {
    id,
    world_id: worldId,
    author_world_character_id:
      authorName === "UI-D Owner" ? "wc-ui-d-owner" : "wc-ui-d-autonomous",
    author_name: authorName,
    author_handle:
      authorName === "UI-D Owner" ? "ui_d_owner" : "ui_d_autonomous",
    author_avatar_url: null,
    author_profile_capability: "available" as const,
    title,
    body,
    post_type: replyToPostId ? "reply" : "text",
    reply_to_post_id: replyToPostId,
    created_at: "2026-08-30T01:00:00Z",
    can_owner_reply: canOwnerReply,
    reply_count: replyCount,
    like_count: likeCount,
  };
}

function uiDManualFeed(
  items: ReturnType<typeof uiDManualPost>[],
  worldId = UI_D_WORLD_ID,
) {
  return {
    schema_version: "owner-manual-social-v1",
    world_id: worldId,
    owner_world_character_id: "wc-ui-d-owner",
    items,
  } as const;
}


export { installBackendFixture, json, uiDWorld, uiDOwnerActor, uiDManualPost, uiDManualFeed, UI_D_ROOT_POST_ID };
