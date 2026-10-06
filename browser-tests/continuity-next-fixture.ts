import type { Page, Route } from "@playwright/test";
import type { ManualSocialPostRead, ManualSocialThreadRead } from "../frontend/src/features/social/types/social-write-contract";
import type { WorldCharacterManagementRead } from "../frontend/src/features/characters/types/world-character-management";
import type { WorldCharacterPublicProfile } from "../frontend/src/features/characters/types/world-character-profile";

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
  ui_language: "ko",
  ui_preference_revision: 0,
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
    const ownerMatch = url.pathname.match(/^\/api\/backend\/worlds\/([^/]+)\/owner-character$/);
    if (ownerMatch && method === "GET") {
      const worldId = decodeURIComponent(ownerMatch[1]);
      return fixture.worldReads?.[worldId]
        ? json(route, uiDOwnerActor(worldId))
        : json(route, { detail: "world_not_found" }, 404);
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


function uiDManualThread(
  selected: ManualSocialPostRead,
  replies: ManualSocialPostRead[] = [],
  { rootId = selected.id, ownerId = "wc-ui-d-owner", pageOffset = 0, nextOffset = null }: {
    rootId?: string; ownerId?: string; pageOffset?: number; nextOffset?: number | null;
  } = {},
): ManualSocialThreadRead {
  const parentIds = [...new Set([selected, ...replies]
    .map((post) => post.reply_to_post_id).filter((id): id is string => id !== null))];
  return {
    schema_version: "owner-manual-social-thread-v2",
    world_id: selected.world_id,
    owner_world_character_id: ownerId,
    selected_post: { ...selected, thread_root_post_id: rootId },
    root_post_id: rootId,
    parent: selected.reply_to_post_id === null ? null : { post_id: selected.reply_to_post_id, state: "available" },
    parent_references: parentIds.map((post_id) => ({ post_id, state: "available" })),
    replies: replies.map((post) => ({ ...post, thread_root_post_id: rootId })),
    page_offset: pageOffset,
    next_offset: nextOffset,
  };
}

function uiDWorldCharacterManagement(profile: WorldCharacterPublicProfile): WorldCharacterManagementRead {
  return {
    contract_version: "world-character-management-v1",
    world_id: profile.world_id,
    world_character_id: profile.world_character_id,
    character_id: profile.character_id,
    can_manage: true,
    item: {
      profile, revision: 1, autonomous_enabled: false,
      status: { state: "off", reason: null },
      settings: profile.control_mode === "owner_controlled" ? null : {
        active_hours_start: "09:00", active_hours_end: "02:00", timezone: "Asia/Seoul",
        activity_interval_minutes: 30, max_posts_per_day: 30, max_comments_per_day: 30,
      },
      next_activity_at: null, recent_activity: null,
      capabilities: {
        can_activate: false, can_deactivate: false, can_run_now: false,
        can_edit_profile: true, can_edit_settings: profile.control_mode === "autonomous",
        can_view_graph: true, reason: "autonomy_not_ready",
      },
    },
  };
}

export { installBackendFixture, json, uiDWorld, uiDOwnerActor, uiDManualPost, uiDManualFeed,
  uiDManualThread, uiDWorldCharacterManagement, UI_D_ROOT_POST_ID };
