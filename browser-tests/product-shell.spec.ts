import { expect, test, type Page, type Route } from "@playwright/test";

import type { CharacterDashboardItem } from "../frontend/src/features/characters/model/character-dashboard-contract";
import { presentCharacterRecentActivity } from "../frontend/src/features/characters/model/character-recent-activity-presentation";
import type {
  MessageThreadRead,
  WorldChatThreadRead,
} from "../frontend/src/features/chat/public";

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

const WORLD_BETA: WorldFixture = {
  ...WORLD_ALPHA,
  world_id: "world-beta",
  name: "별빛정원",
  tagline: "밤마다 별이 피는 정원",
  visibility: "unlisted",
  updated_at: "2026-08-16T00:00:00Z",
};

const WORLD_PRIVATE: WorldFixture = {
  ...WORLD_ALPHA,
  world_id: "world-private",
  name: "비공개 작업실",
  tagline: "아직 공개하지 않은 World",
  visibility: "private",
  launchable: false,
  launch_block_reason: "world_private",
};

const WORLD_DRAFT: WorldFixture = {
  ...WORLD_ALPHA,
  world_id: "world-draft",
  name: "초안 마을",
  tagline: "준비 중인 World",
  status: "draft",
  visibility: "private",
  readiness_status: "not_ready",
  launchable: false,
  launch_block_reason: "world_not_published",
};

const WORLD_NOT_READY: WorldFixture = {
  ...WORLD_ALPHA,
  world_id: "world-not-ready",
  name: "준비 중인 광장",
  tagline: "공개 준비를 마치는 중인 World",
  readiness_status: "not_ready",
  launchable: false,
  launch_block_reason: "world_not_ready",
};

const WORLD_ARCHIVED: WorldFixture = {
  ...WORLD_ALPHA,
  world_id: "world-archived",
  name: "보관된 도서관",
  tagline: "보관된 World",
  status: "archived",
  launchable: false,
  launch_block_reason: "world_archived",
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

function uiERecentActivityCharacter(): CharacterDashboardItem {
  const characterId = "character-ui-e-recent-result";
  return {
    character: {
      id: characterId,
      name: "최근 결과 앵무",
      handle: "recent_result_bird",
      avatar_url: null,
      one_liner: "사용자에게 이해하기 쉬운 활동 결과를 보여줘요.",
      execution_mode: "llm",
    },
    settings: {
      auto_enabled: true,
      activity_interval_minutes: 60,
      max_comments_per_day: 30,
      max_posts_per_day: 20,
      active_hours_start: "08:00",
      active_hours_end: "22:00",
    },
    assigned_slot: {
      agent_id: "runtime-ui-e-recent-result",
      status: "idle",
      last_run_at: "2026-08-29T23:15:00Z",
      last_error: null,
    },
    activity_summary: {
      within_active_hours: true,
      timezone: "America/New_York",
      last_activity_at: "2026-08-29T23:15:00Z",
      next_activity_at: "2026-08-30T00:30:00Z",
    },
    recent_activity: [
      {
        id: 1,
        action_type: "post_created",
        target_post_id: "post-character-ui-e-authoritative",
        reason: "scheduled_activity",
        result: JSON.stringify({
          message: "Created post post-json-decoy.",
          created_post_id: "post-json-decoy",
          topic_signature: "내부 topic signature",
          novelty_basis: "내부 novelty metadata",
          lore_chunk_ids: ["lore-internal-1"],
          retrieval_mode: "hybrid",
          internal_blob: "x".repeat(4_000),
        }),
        created_at: "2026-08-29T23:15:00Z",
      },
    ],
  };
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

function uiDWorldCharacterSocialProfile(
  tab: "posts" | "replies" | "likes",
  worldId = UI_D_WORLD_ID,
  worldCharacterId = "wc-ui-d-autonomous",
) {
  const replyToPostId = tab === "replies" ? "post-p8-l-e" : null;
  const ownerActivity = tab === "likes";
  return {
    schema_version: "world-character-social-profile-v1",
    world_id: worldId,
    world_character_id: worldCharacterId,
    character_id: "character-ui-d-autonomous",
    counts: {
      post_count: 16,
      reply_count: 10,
      liked_post_count: 9,
      received_like_count: 7,
    },
    tab,
    items: [
      {
        id: `profile-${tab}-current-world`,
        world_id: worldId,
        author_world_character_id: ownerActivity
          ? "wc-ui-d-owner"
          : worldCharacterId,
        author_name: ownerActivity ? "UI-D Owner" : "UI-D Autonomous",
        author_handle: ownerActivity ? "ui_d_owner" : "ui_d_autonomous",
        author_avatar_url: null,
        title: tab === "replies" ? "" : `현재 World ${tab} 활동`,
        body: `CURRENT WORLD ${tab.toUpperCase()} ACTIVITY`,
        post_type: replyToPostId ? "reply" : "text",
        reply_to_post_id: replyToPostId,
        created_at: "2026-09-01T05:00:00Z",
        reply_count: 3,
        like_count: 4,
        author_profile_capability: "available",
        mentioned_characters: [],
        media: [],
      },
    ],
    next_cursor: null,
  } as const;
}

function uiDManualWrite(
  post: ReturnType<typeof uiDManualPost>,
  operation: "post" | "reply" = "reply",
) {
  const writePost = {
    id: post.id,
    world_id: post.world_id,
    author_world_character_id: post.author_world_character_id,
    author_name: post.author_name,
    author_handle: post.author_handle,
    author_avatar_url: post.author_avatar_url,
    author_profile_capability: post.author_profile_capability,
    title: post.title,
    body: post.body,
    post_type: post.post_type,
    reply_to_post_id: post.reply_to_post_id,
    created_at: post.created_at,
    can_owner_reply: post.can_owner_reply,
  };
  return {
    schema_version: "owner-manual-social-v1",
    operation,
    replayed: false,
    post: writePost,
    delivery: {
      provider_call_count: 0,
      inbox_candidate_id: operation === "reply" ? "inbox-ui-d-reply" : null,
      inbox_status: operation === "reply" ? "pending" : "not_applicable",
      public_reaction_required: false,
    },
  } as const;
}

test("canonical Home keeps the phone shell at 390px and handles zero World", async ({ page }) => {
  const audit = await installBackendFixture(page);
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/");

  await expect(page.locator('main[data-product-surface="device-home"]')).toBeVisible();
  await expect(page.getByRole("heading", { name: "Angmoo" })).toBeVisible();
  await expect(page.getByText("아직 실행할 World가 없어요")).toBeVisible();
  await expect(page.getByRole("link", { name: "Creator Studio 열기" })).toBeVisible();
  await expect(page.getByText("최근 게시물", { exact: true })).toHaveCount(0);
  const frame = await page.locator('[data-product-shell="device"]').boundingBox();
  expect(frame).not.toBeNull();
  expect(frame!.width).toBeLessThanOrEqual(390);
  expect(audit.writes).toEqual([]);
  expect(audit.providerCalls).toEqual([]);
});

test("Next nested product pages keep one shell-owned main landmark", async ({ page }) => {
  await installBackendFixture(page, {
    deviceWorlds: [WORLD_ALPHA],
    studioWorlds: [WORLD_ALPHA],
    worldReads: { [WORLD_ALPHA.world_id]: WORLD_ALPHA },
  });

  for (const route of [
    "/angmoo-api",
    "/licenses",
    "/characters/character-probe/worlds/world-alpha/autonomy-setup",
    "/characters/character-probe/worlds/world-alpha/relationship-graph",
    "/studio/worlds/new",
  ]) {
    await page.goto(route);
    await expect(page.locator("main")).toHaveCount(1);
    await expect(page.locator("main main")).toHaveCount(0);
  }
});

test("Next Phone routes share one centered frame, one scroll owner, and local navigation", async ({
  page,
}) => {
  const audit = await installBackendFixture(page);

  for (const viewport of [
    { width: 360, height: 800 },
    { width: 390, height: 844 },
    { width: 436, height: 880 },
    { width: 1440, height: 900 },
  ]) {
    await page.setViewportSize(viewport);
    await page.goto("/agents");

    const frame = page.locator('[data-product-shell="device"]');
    await expect(frame).toHaveCount(1);
    await expect(page.locator('[data-device-shell="phone"]')).toHaveCount(1);
    await expect(page.locator('[data-device-scroll-owner="true"]')).toHaveCount(1);
    await expect(page.locator(".angmoo-left-rail, .angmoo-right-rail")).toHaveCount(0);

    const navigation = page.getByRole("navigation", { name: "모바일 주요 메뉴" });
    await expect(navigation.locator("a")).toHaveCount(4);
    expect(
      await navigation
        .locator("a")
        .evaluateAll((anchors) => anchors.map((anchor) => anchor.getAttribute("href"))),
    ).toEqual(["/", "/posts", "/agents", "/settings"]);
    await expect(navigation.locator('[aria-current="page"]')).toHaveCount(1);
    const selectedNavigationItem = navigation.locator('a[href="/agents"]');
    await expect(selectedNavigationItem).toHaveAttribute(
      "aria-current",
      "page",
    );
    await expect(selectedNavigationItem).toHaveCSS(
      "background-color",
      "rgb(255, 240, 239)",
    );
    await expect(selectedNavigationItem).toHaveCSS("color", "rgb(255, 107, 107)");

    const geometry = await frame.evaluate((node) => {
      const rect = node.getBoundingClientRect();
      return {
        documentOverflow:
          document.documentElement.scrollWidth - document.documentElement.clientWidth,
        documentWidth: document.documentElement.clientWidth,
        left: rect.left,
        width: rect.width,
      };
    });
    expect(geometry.documentOverflow).toBe(0);
    expect(geometry.width).toBeLessThanOrEqual(436);
    if (viewport.width <= 436) {
      expect(Math.abs(geometry.width - geometry.documentWidth)).toBeLessThanOrEqual(1);
    } else {
      expect(
        Math.abs(geometry.left - (geometry.documentWidth - geometry.width) / 2),
      ).toBeLessThanOrEqual(1);
    }
  }

  expect(audit.writes).toEqual([]);
  expect(audit.providerCalls).toEqual([]);
});

test("wide browser keeps one phone device and exposes multiple launchable Worlds", async ({ page }) => {
  const audit = await installBackendFixture(page, {
    deviceWorlds: [WORLD_ALPHA, WORLD_BETA],
  });
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/");

  await expect(page.getByRole("link", { name: "마법학교 World 열기" })).toBeVisible();
  await expect(page.getByRole("link", { name: "별빛정원 World 열기" })).toBeVisible();
  const frame = await page.locator('[data-product-shell="device"]').boundingBox();
  expect(frame).not.toBeNull();
  expect(frame!.width).toBeLessThanOrEqual(436);

  await page.getByRole("link", { name: "설정 열기" }).focus();
  await expect(page.getByRole("link", { name: "설정 열기" })).toBeFocused();
  await page.keyboard.press("Tab");
  await expect(page.getByRole("link", { name: "Creator Studio 열기" })).toBeFocused();
  expect(audit.writes).toEqual([]);
  expect(audit.providerCalls).toEqual([]);
});

test("Next canonicalizes legacy Creator aliases without losing repeated query values", async ({
  page,
}) => {
  const audit = await installBackendFixture(page);

  await page.goto("/worlds/new?template=hero&tag=a&tag=b&empty=");
  await expect(page).toHaveURL(
    /\/studio\/worlds\/new\?template=hero&tag=a&tag=b&empty=$/,
  );
  await expect(page.locator('[data-product-shell="creator-studio"]')).toBeVisible();

  await page.goto(
    "/worlds/world-alpha/creator?tab=characters&focus=first&focus=second&empty=",
  );
  await expect(page).toHaveURL(
    /\/studio\/worlds\/world-alpha\?tab=characters&focus=first&focus=second&empty=$/,
  );
  await expect(page.locator('[data-product-shell="creator-studio"]')).toBeVisible();
  expect(audit.writes).toEqual([]);
  expect(audit.providerCalls).toEqual([]);
});
test("Creator Studio is a wide owner workspace and preserves private and draft Worlds", async ({ page }) => {
  const audit = await installBackendFixture(page, {
    deviceWorlds: [WORLD_ALPHA],
    studioWorlds: [WORLD_ALPHA, WORLD_PRIVATE, WORLD_DRAFT],
  });
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/");
  await page.getByRole("link", { name: "Creator Studio 열기" }).click();

  await expect(page).toHaveURL(/\/studio$/);
  await expect(page.locator('[data-product-shell="creator-studio"]')).toBeVisible();
  await expect(page.getByRole("heading", { name: "내 World" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "실행 중인 World" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "비공개", exact: true })).toBeVisible();
  await expect(page.getByRole("heading", { name: "작성 중", exact: true })).toBeVisible();
  await expect(page.getByText("비공개 작업실", { exact: true })).toBeVisible();
  await expect(page.getByText("초안 마을", { exact: true })).toBeVisible();

  await page.getByRole("link", { name: "Device Home으로 돌아가기" }).click();
  await expect(page).toHaveURL(/\/$/);
  await expect(page.getByRole("link", { name: "마법학교 World 열기" })).toBeVisible();
  await expect(page.getByText("비공개 작업실", { exact: true })).toHaveCount(0);
  expect(audit.writes).toEqual([]);
  expect(audit.providerCalls).toEqual([]);
});

test("World App keeps the requested World boundary and never falls back", async ({ page }) => {
  const audit = await installBackendFixture(page, {
    worldReads: { [WORLD_ALPHA.world_id]: WORLD_ALPHA },
  });
  await page.goto(`/worlds/${WORLD_ALPHA.world_id}`);

  const worldApp = page.locator('main[data-product-surface="world-app"]');
  await expect(worldApp).toHaveAttribute("data-world-id", WORLD_ALPHA.world_id);
  await expect(page.getByRole("heading", { name: WORLD_ALPHA.name }).first()).toBeVisible();
  await page.getByRole("link", { name: "Feed" }).click();
  await expect(page).toHaveURL(new RegExp(`/worlds/${WORLD_ALPHA.world_id}/feed$`));
  await expect(worldApp).toHaveAttribute("data-world-id", WORLD_ALPHA.world_id);
  await expect(
    page.getByRole("heading", { name: "이 World에서 내가 조종할 앵무가 필요해요" }),
  ).toBeVisible();
  await expect(page.getByText("Creator Studio에서 owner-controlled 앵무를 만든 뒤")).toBeVisible();

  await page.goto("/worlds/world-foreign");
  await expect(page.getByRole("heading", { name: "이 World 앱을 열 수 없어요" })).toBeVisible();
  await expect(page.getByText(WORLD_ALPHA.name, { exact: true })).toHaveCount(0);
  await expect(page.locator('main[data-product-surface="world-app"]')).toHaveCount(1);
  await expect(page.locator('[data-device-shell="phone"]')).toHaveCount(1);
  await expect(page.locator('[data-device-scroll-owner="true"]')).toHaveCount(1);
  await expect(page.getByRole("navigation", { name: "World 앱 기능" })).toBeVisible();
  await expect(page.getByRole("link", { name: "Device Home", exact: true })).toBeVisible();
  expect(audit.writes).toEqual([]);
  expect(audit.providerCalls).toEqual([]);
});

test("P8-L-D/P World Chat identity, composer, typing and CRG-only stream converge on the scoped route", async ({
  page,
}) => {
  const audit = await installBackendFixture(page, {
    worldReads: { [WORLD_ALPHA.world_id]: WORLD_ALPHA },
  });
  const worldId = WORLD_ALPHA.world_id;
  const threadId = "thread-p8-l-d";
  const worldThread: WorldChatThreadRead = {
    id: threadId,
    world_id: worldId,
    requester: {
      world_character_id: "wc-p8-l-d-owner",
      character_id: "character-p8-l-d-owner",
      display_name: "사용자 앵무",
      handle: "owner_bird",
      avatar_url: null,
      banner_url: null,
      role_key: "student",
      control_mode: "owner_controlled",
      profile_capability: "available",
    },
    responding: {
      world_character_id: "wc-p8-l-d-friend",
      character_id: "character-p8-l-d-friend",
      display_name: "친구 앵무",
      handle: "friend_bird",
      avatar_url: null,
      banner_url: null,
      role_key: "mentor",
      control_mode: "autonomous",
      profile_capability: "available",
    },
    selected_model: "gemini-3.1-flash-lite",
    default_model: "gemini-3.1-flash-lite",
    model_binding_mode: "default",
    last_message_at: "2026-09-01T03:04:00Z",
    created_at: "2026-09-01T03:00:00Z",
    latest_message: {
      id: 2,
      thread_id: threadId,
      role: "assistant",
      content: "World 경계를 기억하고 있어요.",
      model: "gemini-2.5-flash-lite",
      status: "ok",
      error_code: null,
      created_at: "2026-09-01T03:04:00Z",
    },
    messages: [
      {
        id: 1,
        thread_id: threadId,
        role: "user",
        content: "여기는 어느 World야?",
        model: "gemini-2.5-flash-lite",
        status: "ok",
        error_code: null,
        created_at: "2026-09-01T03:03:00Z",
      },
      {
        id: 2,
        thread_id: threadId,
        role: "assistant",
        content: "World 경계를 기억하고 있어요.",
        model: "gemini-2.5-flash-lite",
        status: "ok",
        error_code: null,
        created_at: "2026-09-01T03:04:00Z",
      },
    ],
  };
  const worldChatCalls: string[] = [];
  const sentUserMessage = {
    id: 3,
    thread_id: threadId,
    role: "user" as const,
    content: "오늘 기억나는 일을 말해 줘.",
    model: null,
    status: "ok",
    error_code: null,
    created_at: "2026-09-02T08:00:00Z",
  };
  const generatedAssistantMessage = {
    id: 4,
    thread_id: threadId,
    role: "assistant" as const,
    content: "오늘은 함께 걷던 길이 가장 또렷하게 기억나.",
    model: "gemini-2.5-flash-lite",
    status: "ok",
    error_code: null,
    created_at: "2026-09-02T08:00:03Z",
  };
  const acceptedRequest = {
    protocol_version: "chat-generation-stream.v1" as const,
    request_id: "request-p8-l-p-browser",
    request_scope_hash: "a".repeat(64),
    generation_id: "generation-p8-l-p-browser",
    attempt_number: 1,
    response_slot_id: "response-p8-l-p-browser",
    state: "accepted" as const,
    route: null,
    retryable: false,
    failure_class: null,
    last_accepted_sequence: -1,
    user_message: sentUserMessage,
    assistant_message: null,
    response_metadata: {},
  };
  let messageAccepted = false;
  let responseCommitted = false;
  let failNextModelUpdate = false;

  await page.route(`**/api/backend/worlds/${worldId}/chat/**`, async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    worldChatCalls.push(`${request.method()} ${url.pathname}`);
    if (
      request.method() === "GET" &&
      url.pathname === `/api/backend/worlds/${worldId}/chat/threads`
    ) {
      return json(route, {
        items: [worldThread],
        ambiguous_legacy_count: 1,
        max_threads: 5,
      });
    }
    if (
      request.method() === "PATCH" &&
      url.pathname ===
        `/api/backend/worlds/${worldId}/chat/threads/${threadId}/model`
    ) {
      if (failNextModelUpdate) {
        failNextModelUpdate = false;
        return json(route, { detail: "temporary_model_update_failure" }, 503);
      }
      const body = request.postDataJSON() as {
        mode: "default" | "thread_override";
        selected_model?: WorldChatThreadRead["selected_model"];
      };
      worldThread.model_binding_mode = body.mode;
      worldThread.selected_model =
        body.mode === "default"
          ? worldThread.default_model
          : (body.selected_model ?? worldThread.selected_model);
      return json(route, worldThread);
    }
    if (
      request.method() === "GET" &&
      url.pathname ===
        `/api/backend/worlds/${worldId}/chat/threads/${threadId}`
    ) {
      return json(route, {
        ...worldThread,
        latest_message: responseCommitted
          ? generatedAssistantMessage
          : messageAccepted
            ? sentUserMessage
            : worldThread.latest_message,
        messages: [
          ...worldThread.messages,
          ...(messageAccepted ? [sentUserMessage] : []),
          ...(responseCommitted ? [generatedAssistantMessage] : []),
        ],
      });
    }
    if (
      request.method() === "GET" &&
      url.pathname ===
        `/api/backend/worlds/${worldId}/chat/threads/${threadId}/requests/latest`
    ) {
      return json(route, {
        response_request: messageAccepted
          ? {
              ...acceptedRequest,
              state: responseCommitted ? "committed" : "accepted",
              assistant_message: responseCommitted
                ? generatedAssistantMessage
                : null,
              last_accepted_sequence: responseCommitted ? 2 : -1,
            }
          : null,
      });
    }
    if (
      request.method() === "POST" &&
      url.pathname ===
        `/api/backend/worlds/${worldId}/chat/threads/${threadId}/messages`
    ) {
      expect(request.postDataJSON()).toMatchObject({
        content: sentUserMessage.content,
      });
      messageAccepted = true;
      return json(route, {
        outcome: "accepted",
        user_message: sentUserMessage,
        response_request: acceptedRequest,
      });
    }
    if (
      request.method() === "GET" &&
      url.pathname ===
        `/api/backend/worlds/${worldId}/chat/threads/${threadId}/requests/${acceptedRequest.request_id}/events`
    ) {
      await new Promise((resolve) => setTimeout(resolve, 650));
      responseCommitted = true;
      return route.fulfill({
        body: [
          {
            ...acceptedRequest,
            payload: {},
            protocol_version: "chat-generation-stream.v1",
            sequence: 0,
            type: "accepted",
          },
          {
            ...acceptedRequest,
            payload: { text: generatedAssistantMessage.content },
            protocol_version: "chat-generation-stream.v1",
            sequence: 1,
            type: "delta",
          },
          {
            ...acceptedRequest,
            payload: {},
            protocol_version: "chat-generation-stream.v1",
            sequence: 2,
            type: "completed",
          },
        ]
          .map((value) => JSON.stringify(value))
          .join("\n"),
        contentType: "application/x-ndjson",
        status: 200,
      });
    }
    if (
      request.method() === "GET" &&
      url.pathname ===
        `/api/backend/worlds/${worldId}/chat/threads/${threadId}/requests/${acceptedRequest.request_id}`
    ) {
      return json(route, {
        ...acceptedRequest,
        state: "committed",
        assistant_message: generatedAssistantMessage,
        last_accepted_sequence: 2,
      });
    }
    return json(route, { detail: "unexpected_world_chat_request" }, 404);
  });
  await page.route(
    `**/api/backend/messages/threads/${threadId}`,
    async (route) =>
      json(route, {
        id: threadId,
        requester: {
          profile_type: "user",
          id: OWNER.id,
          display_name: OWNER.display_name,
          handle: null,
          avatar_url: null,
          banner_url: null,
        },
        character: {
          profile_type: "character",
          id: worldThread.responding.character_id,
          display_name: worldThread.responding.display_name,
          handle: worldThread.responding.handle,
          avatar_url: null,
          banner_url: null,
        },
        selected_model: worldThread.selected_model,
        last_message_at: worldThread.last_message_at,
        created_at: worldThread.created_at,
        latest_message: worldThread.latest_message,
        messages: worldThread.messages,
        world_id: worldId,
        requester_world_character_id: worldThread.requester.world_character_id,
        responding_world_character_id: worldThread.responding.world_character_id,
        world_scope_status: "resolved",
      }),
  );

  await page.goto(`/worlds/${worldId}/chat`);
  await expect(page.locator('[data-world-chat-surface="list"]')).toHaveAttribute(
    "data-world-id",
    worldId,
  );
  await expect(page.getByRole("heading", { name: "대화", exact: true })).toBeVisible();
  await expect(page.getByText("친구 앵무", { exact: true })).toBeVisible();
  await expect(page.getByText("사용자 앵무(으)로 대화", { exact: true })).toBeVisible();
  await expect(page.getByText("1개의 이전 대화는 임의의 World에 연결하지")).toBeVisible();
  await expect(page.getByRole("textbox")).toHaveCount(0);
  await page.getByRole("link", { name: "친구 앵무와의 대화 열기" }).click();

  await expect(page).toHaveURL(
    new RegExp(`/worlds/${worldId}/chat/${threadId}$`),
  );
  await expect(page.locator('[data-world-chat-surface="thread"]')).toHaveAttribute(
    "data-thread-id",
    threadId,
  );
  await expect(page.getByText("말하는 앵무", { exact: true })).toBeVisible();
  await expect(page.getByText("답하는 앵무", { exact: true })).toBeVisible();
  await expect(page.getByText("여기는 어느 World야?", { exact: true })).toBeVisible();
  await expect(page.getByText("World 경계를 기억하고 있어요.", { exact: true })).toBeVisible();
  const modelSelect = page.getByRole("combobox", { name: "응답 모델" });
  await expect(modelSelect).toHaveValue("default");
  await modelSelect.selectOption("gemini-3.5-flash-lite");
  await expect(modelSelect).toHaveValue("gemini-3.5-flash-lite");
  await expect(
    page.getByText("Gemini 3.5 Flash-Lite을 이 대화에서 고정해 사용합니다."),
  ).toBeVisible();
  failNextModelUpdate = true;
  await modelSelect.selectOption("default");
  await expect(modelSelect).toHaveValue("gemini-3.5-flash-lite");
  const modelFailure = page.getByRole("alert").filter({
    hasText: "모델을 바꾸지 못했어요.",
  });
  await expect(modelFailure).toBeVisible();
  await modelFailure.getByRole("button", { name: "다시 시도" }).click();
  await expect(modelSelect).toHaveValue("default");
  await expect(
    page.getByText("기본 모델 Gemini 3.1 Flash-Lite을 다음 답장에 사용합니다."),
  ).toBeVisible();
  const composer = page.getByRole("textbox", {
    name: "친구 앵무에게 보낼 메시지",
  });
  await expect(composer).toBeVisible();
  await composer.fill(sentUserMessage.content);
  await page.getByRole("button", { name: "메시지 보내기" }).click();
  await expect(page.getByText(sentUserMessage.content, { exact: true })).toBeVisible();
  await expect(
    page.getByRole("status", { name: "친구 앵무가 응답을 입력하고 있습니다." }),
  ).toBeVisible();
  await expect(modelSelect).toBeDisabled();
  await expect(
    page.getByText(generatedAssistantMessage.content, { exact: true }),
  ).toBeVisible();
  await expect(modelSelect).toBeEnabled();
  await expect(page.getByText("Canonical Planner", { exact: false })).toHaveCount(0);
  await expect(page.getByText("Evidence Bundle", { exact: false })).toHaveCount(0);

  await page.goto(`/messages/${threadId}`);
  await expect(page).toHaveURL(
    new RegExp(`/worlds/${worldId}/chat/${threadId}$`),
  );
  await expect(page.locator('[data-world-chat-surface="thread"]')).toBeVisible();
  expect(worldChatCalls).toContain(
    `PATCH /api/backend/worlds/${worldId}/chat/threads/${threadId}/model`,
  );
  expect(worldChatCalls).toContain(
    `POST /api/backend/worlds/${worldId}/chat/threads/${threadId}/messages`,
  );
  expect(worldChatCalls).toContain(
    `GET /api/backend/worlds/${worldId}/chat/threads/${threadId}/requests/${acceptedRequest.request_id}/events`,
  );
  expect(audit.writes).toEqual([]);
  expect(audit.providerCalls).toEqual([]);
});

test("P8-L-E World social author profile and letter CTA open one exact World Chat thread", async ({
  page,
}) => {
  const worldId = UI_D_WORLD_ID;
  const respondingId = "wc-ui-d-autonomous";
  const requesterId = "wc-ui-d-owner";
  const threadId = "thread-p8-l-e";
  const audit = await installBackendFixture(page, {
    worldReads: { [worldId]: uiDWorld(worldId) },
  });
  const post = uiDManualPost({
    body: "프로필과 편지 Chat 진입을 확인하는 게시글입니다.",
    id: "post-p8-l-e",
    title: "P8-L-E author entry",
    worldId,
  });
  const requester = {
    world_character_id: requesterId,
    character_id: "character-ui-d-owner",
    display_name: "UI-D Owner",
    handle: "ui_d_owner",
    avatar_url: null,
    banner_url: null,
    role_key: "student",
    control_mode: "owner_controlled" as const,
    profile_capability: "available" as const,
  };
  const responding = {
    world_character_id: respondingId,
    character_id: "character-ui-d-autonomous",
    display_name: "UI-D Autonomous",
    handle: "ui_d_autonomous",
    avatar_url: null,
    banner_url: null,
    role_key: "mentor",
    control_mode: "autonomous" as const,
    profile_capability: "available" as const,
  };
  const thread: WorldChatThreadRead = {
    id: threadId,
    world_id: worldId,
    requester,
    responding,
    selected_model: "gemini-3.1-flash-lite",
    default_model: "gemini-3.1-flash-lite",
    model_binding_mode: "default",
    last_message_at: null,
    created_at: "2026-09-01T04:00:00Z",
    latest_message: null,
    messages: [],
  };
  const requests: string[] = [];
  const profileTabs: string[] = [];
  let createCalls = 0;

  await page.route("**/api/backend/**", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const method = request.method();
    if (!url.pathname.includes(`/worlds/${worldId}/`)) {
      await route.fallback();
      return;
    }
    requests.push(`${method} ${url.pathname}`);
    if (url.pathname === `/api/backend/worlds/${worldId}/owner-character`) {
      await json(route, uiDOwnerActor(worldId));
      return;
    }
    if (
      method === "GET" &&
      url.pathname === `/api/backend/worlds/${worldId}/manual-social/feed`
    ) {
      await json(route, uiDManualFeed([post], worldId));
      return;
    }
    if (
      method === "GET" &&
      url.pathname ===
        `/api/backend/worlds/${worldId}/world-characters/${respondingId}/social-profile`
    ) {
      const tab = url.searchParams.get("tab") ?? "posts";
      expect(["posts", "replies", "likes"]).toContain(tab);
      profileTabs.push(tab);
      await json(
        route,
        uiDWorldCharacterSocialProfile(
          tab as "posts" | "replies" | "likes",
          worldId,
          respondingId,
        ),
      );
      return;
    }
    if (
      method === "GET" &&
      url.pathname === `/api/backend/worlds/${worldId}/world-characters`
    ) {
      await json(route, {
        schema_version: "world-character-profile-list-v1",
        world_id: worldId,
        items: [
          {
            schema_version: "world-character-profile-v1",
            world_id: worldId,
            world_character_id: respondingId,
            character_id: responding.character_id,
            display_name: responding.display_name,
            handle: responding.handle,
            avatar_url: null,
            banner_url: null,
            intro: "같은 World에서 활동하는 자율 앵무입니다.",
            role_key: responding.role_key,
            control_mode: responding.control_mode,
            status: "active",
            profile_capability: "available",
          },
        ],
      });
      return;
    }
    if (
      method === "GET" &&
      url.pathname ===
        `/api/backend/worlds/${worldId}/world-characters/${respondingId}`
    ) {
      await json(route, {
        schema_version: "world-character-profile-v1",
        world_id: worldId,
        world_character_id: respondingId,
        character_id: responding.character_id,
        display_name: responding.display_name,
        handle: responding.handle,
        avatar_url: null,
        banner_url: null,
        intro: "같은 World에서 활동하는 자율 앵무입니다.",
        role_key: responding.role_key,
        control_mode: responding.control_mode,
        status: "active",
        profile_capability: "available",
      });
      return;
    }
    if (
      method === "GET" &&
      url.pathname ===
        `/api/backend/worlds/${worldId}/world-characters/${respondingId}/chat-entry`
    ) {
      await json(route, {
        schema_version: "world-chat-entry-v1",
        world_id: worldId,
        responding,
        requester_cardinality: "one",
        requester,
        create_or_get_capability: "available",
        disabled_reason: null,
      });
      return;
    }
    if (
      method === "POST" &&
      url.pathname === `/api/backend/worlds/${worldId}/chat/threads`
    ) {
      createCalls += 1;
      expect(request.postDataJSON()).toEqual({
        responding_world_character_id: respondingId,
        requester_world_character_id: requesterId,
      });
      await json(route, {
        outcome: createCalls === 1 ? "created" : "reused",
        thread,
        resolution_code: null,
      });
      return;
    }
    if (
      method === "GET" &&
      url.pathname === `/api/backend/worlds/${worldId}/chat/threads/${threadId}`
    ) {
      await json(route, thread);
      return;
    }
    if (
      method === "GET" &&
      url.pathname ===
        `/api/backend/worlds/${worldId}/chat/threads/${threadId}/requests/latest`
    ) {
      await json(route, { response_request: null });
      return;
    }
    await route.fallback();
  });

  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto(`/worlds/${worldId}/characters`);
  const directoryIcon = page.locator("[data-world-character-directory-icon]");
  const directoryIconOffset = await directoryIcon.evaluate((tile) => {
    const icon = tile.querySelector("svg");
    if (!icon) return null;
    const tileRect = tile.getBoundingClientRect();
    const iconRect = icon.getBoundingClientRect();
    return {
      x: Math.abs(
        iconRect.left + iconRect.width / 2 - (tileRect.left + tileRect.width / 2),
      ),
      y: Math.abs(
        iconRect.top + iconRect.height / 2 - (tileRect.top + tileRect.height / 2),
      ),
    };
  });
  expect(directoryIconOffset).not.toBeNull();
  expect(directoryIconOffset?.x).toBeLessThanOrEqual(1);
  expect(directoryIconOffset?.y).toBeLessThanOrEqual(1);

  await page.goto(`/worlds/${worldId}/feed`);
  await expect(page.getByText("P8-L-E author entry", { exact: true })).toBeVisible();
  const authorLinks = page.getByRole("link", {
    name: "UI-D Autonomous 프로필 열기",
  });
  await expect(authorLinks).toHaveCount(2);
  await authorLinks.first().click();

  await expect(page).toHaveURL(
    new RegExp(`/worlds/${worldId}/characters/${respondingId}$`),
  );
  const profile = page.locator('[data-world-character-surface="profile"]');
  await expect(profile).toHaveAttribute("data-world-character-id", respondingId);
  await expect(profile.getByRole("heading", { name: "UI-D Autonomous" })).toBeVisible();
  await expect(
    profile.getByRole("paragraph").filter({ hasText: "@ui_d_autonomous" }),
  ).toBeVisible();
  await expect(profile.getByText("같은 World에서 활동하는 자율 앵무입니다.")).toBeVisible();
  await profile.getByRole("button", { name: "이전 화면으로" }).click();
  await expect(page.locator('[data-world-social-surface="feed"]')).toBeVisible();
  await authorLinks.first().click();
  await expect(profile).toBeVisible();
  const activity = profile.locator("[data-world-character-social-activity]");
  await expect(activity).toBeVisible();
  const metrics = activity.locator("dl");
  for (const text of ["지저귐", "16", "대꾸", "10", "좋아요", "9", "받은 좋아요", "7"]) {
    await expect(metrics).toContainText(text);
  }
  await expect(activity.getByRole("tab")).toHaveCount(3);
  await expect(activity.getByRole("tab", { name: "받은 좋아요" })).toHaveCount(0);
  await expect(activity.getByText("CURRENT WORLD POSTS ACTIVITY")).toBeVisible();
  await expect(activity.getByText("다른 World 비밀 활동")).toHaveCount(0);
  await expect(profile.getByRole("textbox")).toHaveCount(0);
  await expect(
    profile.getByRole("button", { name: /프로필 수정|자율활동|설정/ }),
  ).toHaveCount(0);

  await activity.getByRole("tab", { name: "대꾸" }).click();
  await expect(page).toHaveURL(new RegExp(`\\?tab=replies$`));
  await expect(activity.getByText("CURRENT WORLD REPLIES ACTIVITY")).toBeVisible();
  await activity.getByRole("tab", { name: "좋아요" }).click();
  await expect(page).toHaveURL(new RegExp(`\\?tab=likes$`));
  await expect(activity.getByText("CURRENT WORLD LIKES ACTIVITY")).toBeVisible();

  const scrollOwner = page.locator('[data-device-scroll-owner="true"]');
  const scrollContract = await scrollOwner.evaluate((element) => {
    const style = getComputedStyle(element);
    return {
      gutter: style.scrollbarGutter,
      scrollbarWidth: style.scrollbarWidth,
      reservedWidth: element.offsetWidth - element.clientWidth,
      scrollable: element.scrollHeight > element.clientHeight,
    };
  });
  expect(scrollContract.gutter).not.toContain("stable");
  expect(scrollContract.scrollbarWidth).toBe("none");
  expect(scrollContract.reservedWidth).toBe(0);
  expect(scrollContract.scrollable).toBe(true);
  await scrollOwner.evaluate((element) => {
    element.scrollTop = 0;
  });
  await scrollOwner.hover();
  await page.mouse.wheel(0, 480);
  await expect
    .poll(() => scrollOwner.evaluate((element) => element.scrollTop))
    .toBeGreaterThan(0);

  const letter = profile.getByRole("button", {
    name: "UI-D Autonomous와 채팅 시작",
  });
  await expect(letter).toBeEnabled();
  await letter.evaluate((button: HTMLButtonElement) => {
    button.click();
    button.click();
  });
  await expect(page).toHaveURL(
    new RegExp(`/worlds/${worldId}/chat/${threadId}$`),
  );
  await expect(page.locator('[data-world-chat-surface="thread"]')).toBeVisible();
  expect(createCalls).toBe(1);

  await page.goBack();
  await expect(page.locator('[data-world-character-surface="profile"]')).toBeVisible();
  await page.goBack();
  await expect(page.locator('[data-world-social-surface="feed"]')).toBeVisible();
  expect(profileTabs).toEqual(expect.arrayContaining(["posts", "replies", "likes"]));
  expect(requests).not.toContain(
    `GET /api/backend/worlds/${worldId}/manual-social/posts/post-p8-l-e`,
  );
  expect(audit.providerCalls).toEqual([]);
});

test("P8-L-E letter CTA renders zero and anomalous requester guidance without creating a thread", async ({
  page,
}) => {
  const worldId = UI_D_WORLD_ID;
  const respondingId = "wc-ui-d-autonomous";
  await installBackendFixture(page, {
    worldReads: { [worldId]: uiDWorld(worldId) },
  });
  let mode: "zero" | "anomaly" = "zero";
  let createCalls = 0;
  const responding = {
    world_character_id: respondingId,
    character_id: "character-ui-d-autonomous",
    display_name: "UI-D Autonomous",
    handle: "ui_d_autonomous",
    avatar_url: null,
    banner_url: null,
    role_key: "mentor",
    control_mode: "autonomous",
    profile_capability: "available",
  };

  await page.route("**/api/backend/**", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    if (
      request.method() === "GET" &&
      url.pathname ===
        `/api/backend/worlds/${worldId}/world-characters/${respondingId}`
    ) {
      await json(route, {
        schema_version: "world-character-profile-v1",
        world_id: worldId,
        world_character_id: respondingId,
        character_id: responding.character_id,
        display_name: responding.display_name,
        handle: responding.handle,
        avatar_url: null,
        banner_url: null,
        intro: "requester resolution guidance fixture",
        role_key: responding.role_key,
        control_mode: responding.control_mode,
        status: "active",
        profile_capability: "available",
      });
      return;
    }
    if (
      request.method() === "GET" &&
      url.pathname ===
        `/api/backend/worlds/${worldId}/world-characters/${respondingId}/chat-entry`
    ) {
      await json(route, {
        schema_version: "world-chat-entry-v1",
        world_id: worldId,
        responding,
        requester_cardinality: mode,
        requester: null,
        create_or_get_capability: "unavailable",
        disabled_reason:
          mode === "zero" ? "requester_missing" : "requester_cardinality_anomaly",
      });
      return;
    }
    if (
      request.method() === "POST" &&
      url.pathname === `/api/backend/worlds/${worldId}/chat/threads`
    ) {
      createCalls += 1;
      await json(route, { detail: "must_not_create" }, 500);
      return;
    }
    await route.fallback();
  });

  await page.goto(`/worlds/${worldId}/characters/${respondingId}`);
  const letter = page.getByRole("button", {
    name: "UI-D Autonomous와 채팅 시작",
  });
  await expect(letter).toBeDisabled();
  await expect(
    page.getByText("이 World에서 조종하는 앵무를 먼저 연결해 주세요."),
  ).toBeVisible();

  mode = "anomaly";
  await page.reload();
  await expect(letter).toBeDisabled();
  await expect(
    page.getByText("조종 앵무 identity를 하나로 정리한 뒤 대화를 시작할 수 있어요."),
  ).toBeVisible();
  expect(createCalls).toBe(0);
});

test("UI-D Next World social core keeps compact composition, flat rows, exact detail navigation, and scoped replies", async ({
  page,
}) => {
  const world = uiDWorld();
  const audit = await installBackendFixture(page, {
    worldReads: { [world.world_id]: world },
  });
  const longBody = Array.from(
    { length: 36 },
    (_, index) => `선택 가능한 긴 본문 ${index + 1}번째 문장입니다.`,
  ).join(" ");
  const rootPost = uiDManualPost({
    body: longBody,
    id: UI_D_ROOT_POST_ID,
    likeCount: 1,
    replyCount: 1,
    title: "UI-D World root",
  });
  const zeroReactionPost = uiDManualPost({
    body: "답글과 좋아요가 아직 없는 게시글입니다.",
    canOwnerReply: false,
    id: "post-ui-d-next-zero-reaction",
    title: "UI-D zero reactions",
  });
  const existingReply = uiDManualPost({
    authorName: "UI-D Friend",
    body: "기존 대꾸도 같은 flat social presentation을 사용합니다.",
    canOwnerReply: false,
    id: "reply-ui-d-next-existing",
    replyToPostId: UI_D_ROOT_POST_ID,
    title: "",
  });
  const ownerReply = uiDManualPost({
    authorName: "UI-D Owner",
    body: "UI-D Owner reply arrived.",
    canOwnerReply: false,
    id: "reply-ui-d-next-owner",
    replyToPostId: UI_D_ROOT_POST_ID,
    title: "",
  });
  const postedRoot = uiDManualPost({
    authorName: "UI-D Owner",
    body: "변경한 직접 게시글 내용",
    canOwnerReply: false,
    id: "post-ui-d-next-owner-new",
    title: "공백을 정리한 제목",
  });
  let feedItems = [rootPost, zeroReactionPost, existingReply];
  let detailItems = [rootPost, existingReply];
  const postRequestBodies: unknown[] = [];
  const postIdempotencyKeys: Array<string | undefined> = [];
  let replyRequestBody: unknown = null;
  let replyIdempotencyKey: string | undefined;
  const requestedSocialPaths: string[] = [];
  const globalSocialPaths: string[] = [];
  const feedCuePaths: string[] = [];
  const likeMutationPaths: string[] = [];

  await page.route("**/api/backend/**", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const method = request.method();
    if (/^\/api\/backend\/(feed|posts)(\/|$)/.test(url.pathname)) {
      globalSocialPaths.push(`${method} ${url.pathname}`);
    }
    if (url.pathname.includes("/feed-cue")) {
      feedCuePaths.push(`${method} ${url.pathname}`);
    }
    if (
      /\/likes$/.test(url.pathname) &&
      (method === "POST" || method === "DELETE")
    ) {
      likeMutationPaths.push(`${method} ${url.pathname}`);
    }
    if (!url.pathname.includes(`/worlds/${UI_D_WORLD_ID}/`)) {
      await route.fallback();
      return;
    }
    requestedSocialPaths.push(`${method} ${url.pathname}`);
    if (url.pathname === `/api/backend/worlds/${UI_D_WORLD_ID}/owner-character`) {
      await json(route, uiDOwnerActor());
      return;
    }
    if (
      url.pathname === `/api/backend/worlds/${UI_D_WORLD_ID}/manual-social/feed` &&
      method === "GET"
    ) {
      await json(route, uiDManualFeed(feedItems));
      return;
    }
    if (
      url.pathname === `/api/backend/worlds/${UI_D_WORLD_ID}/manual-social/posts` &&
      method === "POST"
    ) {
      postRequestBodies.push(request.postDataJSON());
      postIdempotencyKeys.push(request.headers()["idempotency-key"]);
      if (postRequestBodies.length <= 2) {
        await json(route, { detail: "runtime_not_ready" }, 503);
        return;
      }
      feedItems = [postedRoot, rootPost, zeroReactionPost, existingReply];
      await json(route, uiDManualWrite(postedRoot, "post"));
      return;
    }
    if (
      url.pathname ===
        `/api/backend/worlds/${UI_D_WORLD_ID}/manual-social/posts/${UI_D_ROOT_POST_ID}` &&
      method === "GET"
    ) {
      await json(route, uiDManualFeed(detailItems));
      return;
    }
    if (
      url.pathname ===
        `/api/backend/worlds/${UI_D_WORLD_ID}/manual-social/posts/${UI_D_ROOT_POST_ID}/replies` &&
      method === "POST"
    ) {
      replyRequestBody = request.postDataJSON();
      replyIdempotencyKey = request.headers()["idempotency-key"];
      detailItems = [
        { ...rootPost, reply_count: 2 },
        existingReply,
        ownerReply,
      ];
      await json(route, uiDManualWrite(ownerReply));
      return;
    }
    await route.fallback();
  });

  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto(`/worlds/${UI_D_WORLD_ID}/feed`);

  const feedSurface = page.locator('[data-world-social-surface="feed"]');
  await expect(feedSurface).toBeVisible();
  await expect(feedSurface.locator('[data-social-stream="world"]')).toBeVisible();
  await expect(feedSurface.getByText("World Feed", { exact: true })).toHaveCSS(
    "color",
    "rgb(255, 107, 107)",
  );
  await expect(page.getByRole("button", { name: "글 쓰기" })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "닫기" })).toHaveCount(0);
  const composer = page.locator("#world-owner-composer");
  const titleInput = page.getByLabel("제목", { exact: true });
  const bodyInput = page.getByLabel("내용", { exact: true });
  const submitPost = page.getByRole("button", { name: "게시하기" });
  await expect(composer).toBeVisible();
  await expect(composer.getByRole("img", { name: "UI-D Owner 프로필 이미지" })).toBeVisible();
  await expect(composer.getByText("UI-D Owner", { exact: true })).toBeVisible();
  await expect(titleInput).toHaveAttribute(
    "placeholder",
    "오늘 이 World에 남길 이야기의 제목을 적어주세요",
  );
  await expect(bodyInput).toHaveAttribute(
    "placeholder",
    "내가 조종하는 앵무의 말로 이야기를 적어보세요",
  );
  await expect(submitPost).toBeDisabled();
  expect(await titleInput.evaluate((element) => document.activeElement === element)).toBe(false);
  expect(await bodyInput.evaluate((element) => document.activeElement === element)).toBe(false);
  for (const input of [titleInput, bodyInput]) {
    const inputId = await input.getAttribute("id");
    expect(inputId).toBeTruthy();
    const label = page.locator(`label[for="${inputId}"]`);
    await expect(label).toHaveCount(1);
    expect(
      await label.evaluate((element) => {
        const style = window.getComputedStyle(element);
        const rect = element.getBoundingClientRect();
        return style.position === "absolute" && rect.width <= 1 && rect.height <= 1;
      }),
    ).toBe(true);
  }

  await titleInput.fill("  공백을 정리한 제목  ");
  await bodyInput.fill("  첫 직접 게시글 내용  ");
  await expect(submitPost).toHaveCSS("background-color", "rgb(255, 107, 107)");
  await expect(submitPost).toHaveCSS("color", "rgb(255, 255, 255)");
  await titleInput.focus();
  await page.keyboard.press("Tab");
  await expect(bodyInput).toBeFocused();
  await page.keyboard.press("Tab");
  await expect(submitPost).toBeFocused();

  await submitPost.click();
  await expect.poll(() => postRequestBodies.length).toBe(1);
  await expect(page.getByText("로컬 엔진이 아직 준비되지 않았습니다.")).toBeVisible();
  await expect(titleInput).toHaveValue("  공백을 정리한 제목  ");
  await expect(bodyInput).toHaveValue("  첫 직접 게시글 내용  ");
  await expect(submitPost).toBeEnabled();
  await submitPost.click();
  await expect.poll(() => postRequestBodies.length).toBe(2);
  await expect(page.getByText("로컬 엔진이 아직 준비되지 않았습니다.")).toBeVisible();
  await expect(submitPost).toBeEnabled();
  await bodyInput.fill("  변경한 직접 게시글 내용  ");
  await submitPost.click();
  await expect.poll(() => postRequestBodies.length).toBe(3);
  await expect(page.getByText("게시글을 저장했습니다.", { exact: false })).toBeVisible();
  await expect(composer).toBeVisible();
  await expect(titleInput).toHaveValue("");
  await expect(bodyInput).toHaveValue("");
  expect(postRequestBodies).toEqual([
    { title: "공백을 정리한 제목", body: "첫 직접 게시글 내용" },
    { title: "공백을 정리한 제목", body: "첫 직접 게시글 내용" },
    { title: "공백을 정리한 제목", body: "변경한 직접 게시글 내용" },
  ]);
  expect(postIdempotencyKeys[0]).toMatch(/^owner-post-/);
  expect(postIdempotencyKeys[1]).toBe(postIdempotencyKeys[0]);
  expect(postIdempotencyKeys[2]).toMatch(/^owner-post-/);
  expect(postIdempotencyKeys[2]).not.toBe(postIdempotencyKeys[0]);

  const row = page.locator(`[data-social-post-row="${UI_D_ROOT_POST_ID}"]`);
  const zeroReactionRow = page.locator(
    '[data-social-post-row="post-ui-d-next-zero-reaction"]',
  );
  await expect(row).toHaveAttribute("data-variant", "feed");
  await expect(row).toHaveCSS("border-bottom-width", "1px");
  await expect(row).toHaveCSS("border-radius", "0px");
  await expect(row.getByRole("link", { name: "대꾸 1" })).toHaveAttribute(
    "href",
    new RegExp(`/worlds/${UI_D_WORLD_ID}/posts/${UI_D_ROOT_POST_ID}$`),
  );
  const positiveLike = row.getByLabel("좋아요 1", { exact: true });
  await expect(positiveLike).toHaveCount(1);
  await expect(positiveLike.locator("svg")).toHaveAttribute("fill", "currentColor");
  expect(await positiveLike.evaluate((element) => element.tagName)).toBe("SPAN");
  expect(await positiveLike.getAttribute("aria-pressed")).toBeNull();
  expect(await positiveLike.evaluate((element) => (element as HTMLElement).tabIndex)).toBe(-1);
  await expect(zeroReactionRow.getByRole("link", { name: "대꾸 0" })).toBeVisible();
  const zeroLike = zeroReactionRow.getByLabel("좋아요 0", { exact: true });
  await expect(zeroLike.locator("svg")).toHaveAttribute("fill", "none");
  expect(await zeroLike.evaluate((element) => element.tagName)).toBe("SPAN");
  await expect(row.getByRole("button", { name: /좋아요/ })).toHaveCount(0);
  await expect(zeroReactionRow.getByRole("button", { name: /좋아요/ })).toHaveCount(0);
  await expect(row.getByRole("link", { name: /좋아요/ })).toHaveCount(0);
  const expand = row.getByRole("button", { name: "더보기" });
  await expect(expand).toBeVisible();
  await expect(expand).toHaveCSS("color", "rgb(255, 107, 107)");
  await expect(
    page
      .locator('[data-social-post-row="post-ui-d-next-owner-new"]')
      .getByText("공백을 정리한 제목", { exact: true }),
  ).toBeInViewport();

  const feedUrl = page.url();
  await row.locator("p").evaluate((paragraph) => {
    const selection = window.getSelection();
    const range = document.createRange();
    range.selectNodeContents(paragraph);
    selection?.removeAllRanges();
    selection?.addRange(range);
  });
  await row.dispatchEvent("click", { button: 0 });
  expect(page.url()).toBe(feedUrl);
  await page.evaluate(() => window.getSelection()?.removeAllRanges());

  await expand.click();
  await expect(expand).toHaveCount(0);
  expect(page.url()).toBe(feedUrl);
  await row.focus();
  await expect(row).toBeFocused();
  await page.keyboard.press("Enter");

  await expect(page).toHaveURL(
    new RegExp(`/worlds/${UI_D_WORLD_ID}/posts/${UI_D_ROOT_POST_ID}$`),
  );
  await expect(page.locator('[data-world-social-surface="detail"]')).toBeVisible();
  await expect(page.getByRole("heading", { name: "게시글과 답글" })).toBeVisible();
  await expect(page.locator("#world-owner-composer")).toHaveCount(0);
  await expect(page.getByRole("button", { name: "게시하기" })).toHaveCount(0);
  await expect(
    page.locator(`[data-social-post-row="${UI_D_ROOT_POST_ID}"]`).getByLabel("대꾸 1"),
  ).toBeVisible();
  await expect(
    page.locator(`[data-social-post-row="${UI_D_ROOT_POST_ID}"]`).getByLabel("좋아요 1"),
  ).toBeVisible();
  await expect(
    page.locator('[data-social-post-row="reply-ui-d-next-existing"]').getByLabel("좋아요 0"),
  ).toBeVisible();
  await expect(page.getByRole("heading", { name: "대꾸 1" })).toBeVisible();
  await page.getByLabel("UI-D Autonomous의 게시글에 답글").fill("실제 scoped reply");
  await page.getByRole("button", { name: "답글 보내기" }).click();

  await expect(page.getByText("UI-D Owner reply arrived.", { exact: false })).toBeVisible();
  await expect(page.getByRole("heading", { name: "대꾸 2" })).toBeVisible();
  await expect(
    page.locator(`[data-social-post-row="${UI_D_ROOT_POST_ID}"]`).getByLabel("대꾸 2"),
  ).toBeVisible();
  expect(replyRequestBody).toEqual({ body: "실제 scoped reply" });
  expect(replyIdempotencyKey).toMatch(/^owner-reply-/);
  expect(requestedSocialPaths).toContain(
    `GET /api/backend/worlds/${UI_D_WORLD_ID}/manual-social/feed`,
  );
  expect(requestedSocialPaths).toContain(
    `GET /api/backend/worlds/${UI_D_WORLD_ID}/manual-social/posts/${UI_D_ROOT_POST_ID}`,
  );
  expect(requestedSocialPaths).toContain(
    `POST /api/backend/worlds/${UI_D_WORLD_ID}/manual-social/posts`,
  );
  expect(requestedSocialPaths).toContain(
    `POST /api/backend/worlds/${UI_D_WORLD_ID}/manual-social/posts/${UI_D_ROOT_POST_ID}/replies`,
  );
  expect(globalSocialPaths).toEqual([]);
  expect(feedCuePaths).toEqual([]);
  expect(likeMutationPaths).toEqual([]);
  expect(audit.providerCalls).toEqual([]);
});

test("UI-D Next World social errors distinguish 403, 404, 503, scope mismatch, and retry recovery", async ({
  page,
}) => {
  const world = uiDWorld();
  await installBackendFixture(page, {
    worldReads: { [world.world_id]: world },
  });
  const rootPost = uiDManualPost({
    body: "Recovered World-scoped body",
    id: UI_D_ROOT_POST_ID,
    title: "Recovered UI-D feed",
  });
  let responseMode: "403" | "404" | "503" | "scope" | "ready" | "empty" = "403";
  let feedRequests = 0;
  const globalSocialPaths: string[] = [];

  await page.route("**/api/backend/**", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    if (/^\/api\/backend\/(feed|posts)(\/|$)/.test(url.pathname)) {
      globalSocialPaths.push(`${request.method()} ${url.pathname}`);
    }
    if (url.pathname === `/api/backend/worlds/${UI_D_WORLD_ID}/owner-character`) {
      await json(route, uiDOwnerActor());
      return;
    }
    if (url.pathname !== `/api/backend/worlds/${UI_D_WORLD_ID}/manual-social/feed`) {
      await route.fallback();
      return;
    }
    feedRequests += 1;
    if (responseMode === "403" || responseMode === "404" || responseMode === "503") {
      await json(route, { detail: `ui_d_${responseMode}` }, Number(responseMode));
      return;
    }
    await json(
      route,
      uiDManualFeed(
        responseMode === "empty"
          ? []
          : [
              responseMode === "scope"
                ? uiDManualPost({
                    body: rootPost.body,
                    id: rootPost.id,
                    title: rootPost.title,
                    worldId: "world-foreign",
                  })
                : rootPost,
            ],
        responseMode === "scope" ? "world-foreign" : UI_D_WORLD_ID,
      ),
    );
  });

  await page.goto(`/worlds/${UI_D_WORLD_ID}/feed`);
  await expect(page.getByRole("heading", { name: "이 Feed를 볼 권한이 없어요" })).toBeVisible();
  await expect(page.getByRole("button", { name: "다시 시도" })).toHaveCount(0);
  await expect(page.locator("#world-owner-composer")).toBeVisible();
  await expect(page.getByRole("button", { name: "글 쓰기" })).toHaveCount(0);

  responseMode = "404";
  await page.reload();
  await expect(page.getByRole("heading", { name: "게시글을 찾을 수 없어요" })).toBeVisible();
  await expect(page.getByRole("button", { name: "다시 시도" })).toHaveCount(0);

  responseMode = "503";
  await page.reload();
  await expect(
    page.getByRole("heading", { name: "로컬 runtime에 연결할 수 없어요" }),
  ).toBeVisible();
  await expect(page.getByRole("button", { name: "다시 시도" })).toBeVisible();

  responseMode = "scope";
  await page.reload();
  await expect(page.getByRole("heading", { name: "World 경계를 확인했어요" })).toBeVisible();
  await expect(page.getByText("다른 World의 응답이 감지되어")).toBeVisible();

  responseMode = "ready";
  await page.getByRole("button", { name: "다시 시도" }).click();
  await expect(page.getByText("Recovered UI-D feed", { exact: true })).toBeVisible();
  responseMode = "empty";
  await page.reload();
  await expect(page.getByRole("heading", { name: "아직 공개된 게시글이 없어요" })).toBeVisible();
  await expect(page.locator("#world-owner-composer")).toBeVisible();
  await expect(page.getByRole("button", { name: "첫 글 쓰기" })).toHaveCount(0);
  await expect(
    page.getByRole("heading", { name: "아직 공개된 게시글이 없어요" }),
  ).toBeInViewport();
  expect(feedRequests).toBe(6);
  expect(globalSocialPaths).toEqual([]);
});

test("runtime outage is presented as degraded without blocking Device Home", async ({ page }) => {
  const audit = await installBackendFixture(page, {
    deviceWorlds: [WORLD_ALPHA],
    runtimeStatus: 503,
  });
  await page.goto("/");

  await expect(page.getByText("일부 기능 제한", { exact: true })).toBeVisible();
  await expect(page.getByRole("link", { name: "마법학교 World 열기" })).toBeVisible();
  expect(audit.writes).toEqual([]);
  expect(audit.providerCalls).toEqual([]);
});

test("Next Character dashboard presents production activity JSON as a compact safe summary", async ({
  page,
}) => {
  const audit = await installBackendFixture(page, {
    agents: [uiERecentActivityCharacter()],
  });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/agents");

  const character = page.locator(
    '[data-character-id="character-ui-e-recent-result"]',
  );
  const metrics = character.locator("[data-character-metrics]");
  const recent = character.locator("[data-character-recent-activity]");
  const resultLink = recent.getByRole("link", {
    name: "게시글 보기",
    exact: true,
  });

  await expect(recent).toHaveAttribute(
    "data-character-recent-activity",
    "recorded",
  );
  await expect(recent).toContainText("게시글 작성");
  await expect(recent).toContainText("지저귐을 남겼어요.");
  await expect(recent.locator("time")).toHaveAttribute(
    "datetime",
    "2026-08-29T23:15:00Z",
  );
  await expect(recent).toContainText("08.29 19:15");
  await expect(resultLink).toHaveAttribute(
    "href",
    "/posts/post-character-ui-e-authoritative",
  );
  await expect(resultLink).not.toHaveAttribute("aria-disabled", "true");
  await expect(
    recent.locator('[data-product-route-unavailable="true"]'),
  ).toHaveCount(0);

  const visibleText = await recent.innerText();
  for (const forbidden of [
    "{",
    '"message"',
    '"created_post_id"',
    '"topic_signature"',
    '"novelty_basis"',
    '"lore_chunk_ids"',
    '"retrieval_mode"',
    "post-character-ui-e-authoritative",
    "post-json-decoy",
  ]) {
    expect(visibleText).not.toContain(forbidden);
  }

  for (const viewport of [
    { width: 360, height: 800 },
    { width: 390, height: 844 },
    { width: 436, height: 880 },
  ]) {
    await page.setViewportSize(viewport);
    const [metricsBox, recentBox] = await Promise.all([
      metrics.boundingBox(),
      recent.boundingBox(),
    ]);
    expect(metricsBox).not.toBeNull();
    expect(recentBox).not.toBeNull();
    expect(Math.abs(recentBox!.x - metricsBox!.x)).toBeLessThanOrEqual(1);
    expect(
      Math.abs(
        recentBox!.x +
          recentBox!.width -
          (metricsBox!.x + metricsBox!.width),
      ),
    ).toBeLessThanOrEqual(1);
    const geometry = await recent.evaluate((node) => ({
      documentOverflow:
        document.documentElement.scrollWidth -
        document.documentElement.clientWidth,
      height: node.getBoundingClientRect().height,
      overflow: node.scrollWidth - node.clientWidth,
    }));
    expect(geometry.documentOverflow).toBe(0);
    expect(geometry.overflow).toBe(0);
    expect(geometry.height).toBeLessThanOrEqual(220);
  }

  await character
    .getByRole("button", { name: "최근 결과 앵무 자율활동 끄기" })
    .focus();
  await page.keyboard.press("Tab");
  await expect(resultLink).toBeFocused();
  expect(
    await resultLink.evaluate((node) => node.matches(":focus-visible")),
  ).toBe(true);

  expect(audit.writes).toEqual([]);
  expect(audit.providerCalls).toEqual([]);
});

test("Character recent activity presenter keeps every supported action and prototype-like unknown value fail-closed", () => {
  const mappedActions = [
    {
      actions: ["activated"],
      actionLabel: "자율활동 켜짐",
      headline: "자율활동이 켜졌어요.",
    },
    {
      actions: ["comment", "commented", "reply", "replied"],
      actionLabel: "대꾸 작성",
      headline: "대꾸를 남겼어요.",
      targetLabel: "대꾸한 글 보기",
    },
    {
      actions: ["complete_tick_rejected"],
      actionLabel: "활동 재검토",
      headline: "활동을 다시 고르고 있어요.",
    },
    {
      actions: ["created"],
      actionLabel: "앵무 생성",
      headline: "앵무가 만들어졌어요.",
    },
    {
      actions: ["credential_saved"],
      actionLabel: "연결 정보 저장",
      headline: "연결 정보를 안전하게 저장했어요.",
    },
    {
      actions: ["deactivated"],
      actionLabel: "자율활동 꺼짐",
      headline: "자율활동이 꺼졌어요.",
    },
    {
      actions: ["follow", "followed"],
      actionLabel: "팔로우",
      headline: "프로필을 팔로우했어요.",
    },
    {
      actions: ["like", "liked"],
      actionLabel: "좋아요",
      headline: "글에 좋아요를 눌렀어요.",
      targetLabel: "좋아요한 글 보기",
    },
    {
      actions: ["local_bot_rate_limited"],
      actionLabel: "외부 실행 제한",
      headline: "요청이 잠시 제한됐어요.",
    },
    {
      actions: ["local_key_issued"],
      actionLabel: "연결 키 발급",
      headline: "앵무 API key가 발급됐어요.",
    },
    {
      actions: ["local_key_revoked"],
      actionLabel: "연결 키 폐기",
      headline: "앵무 API key가 폐기됐어요.",
    },
    {
      actions: ["memory_note_refine_failed"],
      actionLabel: "기억 정리 보류",
      headline: "처음 저장한 기억을 유지했어요.",
    },
    {
      actions: ["observe", "observed"],
      actionLabel: "둘러보기",
      headline: "커뮤니티 흐름을 살펴봤어요.",
      targetLabel: "살펴본 글 보기",
    },
    {
      actions: ["persona_updated"],
      actionLabel: "페르소나 수정",
      headline: "페르소나 설정을 업데이트했어요.",
    },
    {
      actions: ["post", "post_created"],
      actionLabel: "게시글 작성",
      headline: "지저귐을 남겼어요.",
      targetLabel: "게시글 보기",
    },
    {
      actions: ["profile_updated"],
      actionLabel: "프로필 수정",
      headline: "프로필 정보를 업데이트했어요.",
    },
    {
      actions: ["quote", "quoted"],
      actionLabel: "인용",
      headline: "글을 인용했어요.",
      targetLabel: "인용한 글 보기",
    },
    {
      actions: ["repost", "reposted"],
      actionLabel: "리포스트",
      headline: "글을 리포스트했어요.",
      targetLabel: "리포스트한 글 보기",
    },
    {
      actions: ["skipped"],
      actionLabel: "쉬어감",
      headline: "이번 활동은 쉬어갔어요.",
    },
    {
      actions: ["state_saved"],
      actionLabel: "상태 저장",
      headline: "기분과 기억을 업데이트했어요.",
      targetLabel: "관련 글 보기",
    },
    {
      actions: ["tendency_analyzed"],
      actionLabel: "활동 성향 분석",
      headline: "활동 성향을 분석했어요.",
    },
    {
      actions: ["thread_viewed"],
      actionLabel: "대화 확인",
      headline: "대화 흐름을 확인했어요.",
      targetLabel: "확인한 글 보기",
    },
    {
      actions: ["tick_completed"],
      actionLabel: "활동 완료",
      headline: "이번 활동을 마무리했어요.",
      targetLabel: "관련 글 보기",
    },
    {
      actions: ["unfollow", "unfollowed"],
      actionLabel: "언팔로우",
      headline: "프로필 팔로우를 해제했어요.",
    },
  ] as const;
  const occurredAt = "2026-08-29T23:15:00Z";
  const targetPostId = "post/with?reserved";

  for (const expected of mappedActions) {
    for (const action of expected.actions) {
      const item = uiERecentActivityCharacter();
      item.recent_activity[0] = {
        ...item.recent_activity[0]!,
        action_type: action,
        created_at: occurredAt,
        result: "{broken",
        target_post_id: targetPostId,
      };

      const targetLabel = "targetLabel" in expected ? expected.targetLabel : null;
      expect(presentCharacterRecentActivity(item)).toEqual({
        actionLabel: expected.actionLabel,
        headline: expected.headline,
        occurredAt,
        state: "recorded",
        targetHref: targetLabel ? "/posts/post%2Fwith%3Freserved" : null,
        targetLabel,
      });
    }
  }

  for (const action of [
    "future_action_v2",
    "constructor",
    "toString",
    "valueOf",
    "__proto__",
  ]) {
    const item = uiERecentActivityCharacter();
    item.recent_activity[0] = {
      ...item.recent_activity[0]!,
      action_type: action,
      result: "raw result must stay hidden",
      target_post_id: targetPostId,
    };

    expect(presentCharacterRecentActivity(item)).toEqual({
      actionLabel: "활동",
      headline: "활동 기록이 업데이트됐어요.",
      occurredAt,
      state: "recorded",
      targetHref: null,
      targetLabel: null,
    });
  }
});

test("UI-E Device Home separates runtime state, World launchability, and retry", async ({ page }) => {
  const fixture: BackendFixture = {
    deviceWorlds: [
      WORLD_ALPHA,
      WORLD_PRIVATE,
      WORLD_DRAFT,
      WORLD_NOT_READY,
      WORLD_ARCHIVED,
    ],
    deviceWorldFailuresBeforeSuccess: 1,
    runtimeState: "starting",
  };
  const audit = await installBackendFixture(page, fixture);
  await page.goto("/");

  await expect(page.locator('[data-runtime-state="starting"]')).toContainText("시작 중");
  await expect(page.locator('section[role="alert"]')).toContainText(
    "Device Home을 열지 못했어요",
  );
  await page.getByRole("button", { name: "World 목록 다시 시도" }).click();

  await expect(
    page.getByRole("link", { name: /마법학교 World 열기\. 실행 가능\./ }),
  ).toBeVisible();
  await expect(page.locator('[data-world-launchability="launchable"]')).toContainText(
    "실행 가능",
  );

  const unavailableWorlds = [
    {
      badge: "비공개",
      description: "비공개 작업실 World는 비공개 상태라 Device Home에서 열 수 없습니다.",
      state: "world_private",
    },
    {
      badge: "공개 전",
      description: "초안 마을 World는 아직 공개되지 않아 Device Home에서 열 수 없습니다.",
      state: "world_not_published",
    },
    {
      badge: "준비 필요",
      description: "준비 중인 광장 World는 공개 준비가 완료되지 않아 Device Home에서 열 수 없습니다.",
      state: "world_not_ready",
    },
    {
      badge: "보관됨",
      description: "보관된 도서관 World는 보관되어 Device Home에서 열 수 없습니다.",
      state: "world_archived",
    },
  ] as const;

  for (const world of unavailableWorlds) {
    const item = page.getByRole("listitem", { name: world.description });
    await expect(item).toBeVisible();
    await expect(item.locator("a")).toHaveCount(0);
    await expect(
      page.locator(`[data-world-launchability="${world.state}"]`),
    ).toContainText(world.badge);
  }

  const runtimeCases = [
    ["ready", "healthy", "준비됨"],
    ["degraded", "degraded", "일부 기능 제한"],
    ["failed", "failed", "실행 실패"],
    ["recovery_required", "recovery_required", "복구 필요"],
  ] as const;
  for (const [backendState, productState, label] of runtimeCases) {
    fixture.runtimeState = backendState;
    await page.reload();
    await expect(page.locator(`[data-runtime-state="${productState}"]`)).toContainText(
      label,
    );
    await expect(
      page.getByRole("link", { name: /마법학교 World 열기\. 실행 가능\./ }),
    ).toBeVisible();
  }

  expect(
    audit.reads.filter((read) => read === "GET /api/backend/worlds/mine?surface=device_home"),
  ).toHaveLength(6);
  expect(audit.writes).toEqual([]);
  expect(audit.providerCalls).toEqual([]);
});

test("PWA is standalone, cache-free, and shares the canonical Home", async ({ page, request }) => {
  const audit = await installBackendFixture(page, { deviceWorlds: [WORLD_ALPHA] });
  const manifestResponse = await request.get("/manifest.webmanifest");
  expect(manifestResponse.ok()).toBeTruthy();
  const manifest = await manifestResponse.json();
  expect(manifest).toMatchObject({ display: "standalone", scope: "/", start_url: "/" });

  await page.goto("/");
  await page.evaluate(async () => {
    await navigator.serviceWorker.ready;
  });
  const cacheNames = await page.evaluate(() => caches.keys());
  expect(cacheNames).toEqual([]);
  const registration = await page.evaluate(async () => {
    const worker = await navigator.serviceWorker.getRegistration("/");
    return worker?.scope ?? null;
  });
  expect(registration).toBe(`${new URL(page.url()).origin}/`);
  await expect(page.locator('main[data-product-surface="device-home"]')).toBeVisible();
  expect(audit.writes).toEqual([]);
  expect(audit.providerCalls).toEqual([]);
});

test("legacy Messages keeps list, thread, retry, model, send, and delete parity", async ({
  page,
}) => {
  await installBackendFixture(page);

  const character = {
    profile_type: "character" as const,
    id: "character-p8-l-c",
    display_name: "구조 이동 앵무",
    handle: "p8_l_c",
    avatar_url: null,
    banner_url: null,
  };
  const requester = {
    profile_type: "user" as const,
    id: OWNER.id,
    display_name: OWNER.display_name,
    handle: "local_owner",
    avatar_url: null,
    banner_url: null,
  };
  let thread: MessageThreadRead = {
    id: "thread-p8-l-c",
    requester,
    character,
    selected_model: "gemini-2.5-flash-lite",
    last_message_at: "2026-09-01T00:01:00Z",
    created_at: "2026-09-01T00:00:00Z",
    latest_message: {
      id: 2,
      thread_id: "thread-p8-l-c",
      role: "assistant" as const,
      content: "답장을 만들지 못했어요.",
      model: "gemini-2.5-flash-lite",
      status: "error" as const,
      error_code: "model_busy",
      created_at: "2026-09-01T00:01:00Z",
    },
    messages: [
      {
        id: 1,
        thread_id: "thread-p8-l-c",
        role: "user" as const,
        content: "처음 질문",
        model: "gemini-2.5-flash-lite",
        status: "ok" as const,
        error_code: null,
        created_at: "2026-09-01T00:00:30Z",
      },
      {
        id: 2,
        thread_id: "thread-p8-l-c",
        role: "assistant" as const,
        content: "답장을 만들지 못했어요.",
        model: "gemini-2.5-flash-lite",
        status: "error" as const,
        error_code: "model_busy",
        created_at: "2026-09-01T00:01:00Z",
      },
    ],
    requester_world_character_id: null,
    responding_world_character_id: null,
    world_id: null,
    world_scope_status: "ambiguous",
  };
  let deleted = false;
  let releaseSend!: () => void;
  const sendGate = new Promise<void>((resolve) => {
    releaseSend = resolve;
  });
  const calls: Array<{ body: unknown; method: string; path: string }> = [];

  await page.route("**/api/backend/messages/**", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const method = request.method();
    const body = request.postData() ? request.postDataJSON() : null;
    calls.push({ body, method, path: url.pathname });

    if (url.pathname === "/api/backend/messages/threads" && method === "GET") {
      return json(route, {
        items: deleted ? [] : [thread],
        max_threads: 30,
      });
    }
    if (
      url.pathname === "/api/backend/messages/threads/thread-p8-l-c" &&
      method === "GET"
    ) {
      return json(route, thread);
    }
    if (
      url.pathname === "/api/backend/messages/threads/thread-p8-l-c" &&
      method === "PATCH"
    ) {
      thread = { ...thread, selected_model: body.selected_model };
      return json(route, thread);
    }
    if (
      url.pathname ===
        "/api/backend/messages/threads/thread-p8-l-c/messages/2/retry" &&
      method === "POST"
    ) {
      const assistantMessage = {
        ...thread.messages[1],
        content: "다시 만든 답장",
        error_code: null,
        status: "ok" as const,
      };
      thread = {
        ...thread,
        latest_message: assistantMessage,
        messages: [thread.messages[0], assistantMessage],
      };
      return json(route, {
        thread,
        user_message: thread.messages[0],
        assistant_message: assistantMessage,
      });
    }
    if (
      url.pathname ===
        "/api/backend/messages/threads/thread-p8-l-c/messages" &&
      method === "POST"
    ) {
      await sendGate;
      const userMessage = {
        id: 3,
        thread_id: thread.id,
        role: "user" as const,
        content: body.content,
        model: thread.selected_model,
        status: "ok" as const,
        error_code: null,
        created_at: "2026-09-01T00:02:00Z",
      };
      const assistantMessage = {
        id: 4,
        thread_id: thread.id,
        role: "assistant" as const,
        content: "새 질문에 대한 답장",
        model: thread.selected_model,
        status: "ok" as const,
        error_code: null,
        created_at: "2026-09-01T00:02:10Z",
      };
      thread = {
        ...thread,
        last_message_at: assistantMessage.created_at,
        latest_message: assistantMessage,
        messages: [...thread.messages, userMessage, assistantMessage],
      };
      return json(route, {
        thread,
        user_message: userMessage,
        assistant_message: assistantMessage,
      });
    }
    if (
      url.pathname === "/api/backend/messages/threads/thread-p8-l-c" &&
      method === "DELETE"
    ) {
      deleted = true;
      return route.fulfill({ status: 204 });
    }
    return json(
      route,
      { detail: `unexpected_messages_request:${url.pathname}` },
      404,
    );
  });

  await page.goto("/messages");
  await expect(page.getByRole("heading", { name: "쪽지함" })).toBeVisible();
  await expect(page.getByText("1/30", { exact: true })).toBeVisible();
  await expect(page.getByText("구조 이동 앵무", { exact: true })).toBeVisible();
  await page.locator('a[href="/messages/thread-p8-l-c"]').click();

  await expect(page).toHaveURL(/\/messages\/thread-p8-l-c$/);
  await expect(page.getByRole("heading", { name: "구조 이동 앵무" })).toBeVisible();
  await expect(page.getByText("이 이전 대화의 World를 고유하게 확인할 수 없어요.")).toBeVisible();
  await expect(page.getByText("처음 질문", { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "다시 시도" })).toHaveCount(1);

  await page.getByRole("button", { name: "다시 시도" }).click();
  await expect(page.getByText("다시 만든 답장", { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "다시 시도" })).toHaveCount(0);

  await page.getByRole("combobox", { name: "모델 선택" }).selectOption(
    "gemini-2.5-flash",
  );
  await expect(page.getByRole("combobox", { name: "모델 선택" })).toHaveValue(
    "gemini-2.5-flash",
  );

  await page.getByPlaceholder("쪽지를 입력하세요").fill("새 질문");
  await page.getByRole("button", { name: "보내기" }).click();
  await expect(page.getByText("새 질문", { exact: true })).toBeVisible();
  await expect(page.getByText("답장 중", { exact: true })).toBeVisible();
  releaseSend();
  await expect(page.getByText("새 질문에 대한 답장", { exact: true })).toBeVisible();
  await expect(page.getByText("답장 중", { exact: true })).toHaveCount(0);

  await page.getByRole("button", { name: "쪽지 내역 삭제" }).click();
  await expect(page).toHaveURL(/\/messages$/);
  await expect(
    page.getByText("아직 나눈 쪽지가 없습니다.", { exact: true }),
  ).toBeVisible();

  expect(calls.filter((call) => call.method !== "GET")).toEqual([
    {
      body: null,
      method: "POST",
      path: "/api/backend/messages/threads/thread-p8-l-c/messages/2/retry",
    },
    {
      body: { selected_model: "gemini-2.5-flash" },
      method: "PATCH",
      path: "/api/backend/messages/threads/thread-p8-l-c",
    },
    {
      body: { content: "새 질문" },
      method: "POST",
      path: "/api/backend/messages/threads/thread-p8-l-c/messages",
    },
    {
      body: null,
      method: "DELETE",
      path: "/api/backend/messages/threads/thread-p8-l-c",
    },
  ]);
  expect(
    calls.filter(
      (call) =>
        call.method === "GET" &&
        call.path === "/api/backend/messages/threads",
    ).length,
  ).toBeGreaterThanOrEqual(2);
  expect(
    calls.filter(
      (call) =>
        call.method === "GET" &&
        call.path === "/api/backend/messages/threads/thread-p8-l-c",
    ).length,
  ).toBeGreaterThanOrEqual(1);
});
