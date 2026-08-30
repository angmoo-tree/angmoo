import { expect, test, type Page, type Route } from "@playwright/test";

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

type BackendFixture = {
  deviceWorlds?: WorldFixture[];
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
    if (url.pathname === "/api/backend/worlds/mine") {
      const surface = url.searchParams.get("surface");
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
  replyToPostId = null,
  title,
  worldId = UI_D_WORLD_ID,
}: {
  authorName?: string;
  body: string;
  canOwnerReply?: boolean;
  id: string;
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
    title,
    body,
    post_type: replyToPostId ? "reply" : "text",
    reply_to_post_id: replyToPostId,
    created_at: "2026-08-30T01:00:00Z",
    can_owner_reply: canOwnerReply,
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

function uiDManualWrite(post: ReturnType<typeof uiDManualPost>) {
  return {
    schema_version: "owner-manual-social-v1",
    operation: "reply",
    replayed: false,
    post,
    delivery: {
      provider_call_count: 0,
      inbox_candidate_id: "inbox-ui-d-reply",
      inbox_status: "pending",
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
    await expect(navigation.locator('a[href="/agents"]')).toHaveAttribute(
      "aria-current",
      "page",
    );

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
    title: "UI-D World root",
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
  let detailItems = [rootPost, existingReply];
  let replyRequestBody: unknown = null;
  let replyIdempotencyKey: string | undefined;
  const requestedSocialPaths: string[] = [];
  const globalSocialPaths: string[] = [];

  await page.route("**/api/backend/**", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const method = request.method();
    if (/^\/api\/backend\/(feed|posts)(\/|$)/.test(url.pathname)) {
      globalSocialPaths.push(`${method} ${url.pathname}`);
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
      await json(route, uiDManualFeed([rootPost, existingReply]));
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
      detailItems = [rootPost, existingReply, ownerReply];
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
  const composerToggle = page.getByRole("button", { name: "글 쓰기" });
  await expect(composerToggle).toHaveAttribute("aria-expanded", "false");
  await expect(page.locator("#world-owner-composer")).toHaveCount(0);
  await composerToggle.click();
  await expect(page.getByRole("button", { name: "닫기" })).toHaveAttribute(
    "aria-expanded",
    "true",
  );
  await expect(page.locator("#world-owner-composer")).toBeVisible();
  await expect(page.getByLabel("제목")).toBeFocused();
  await page.getByRole("button", { name: "닫기" }).click();

  const row = page.locator(`[data-social-post-row="${UI_D_ROOT_POST_ID}"]`);
  await expect(row).toHaveAttribute("data-variant", "feed");
  await expect(row).toHaveCSS("border-bottom-width", "1px");
  await expect(row).toHaveCSS("border-radius", "0px");
  const expand = row.getByRole("button", { name: "더보기" });
  await expect(expand).toBeVisible();

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
  await expect(page.getByRole("heading", { name: "대꾸 1" })).toBeVisible();
  await page.getByLabel("UI-D Autonomous의 게시글에 답글").fill("실제 scoped reply");
  await page.getByRole("button", { name: "답글 보내기" }).click();

  await expect(page.getByText("UI-D Owner reply arrived.", { exact: false })).toBeVisible();
  await expect(page.getByRole("heading", { name: "대꾸 2" })).toBeVisible();
  expect(replyRequestBody).toEqual({ body: "실제 scoped reply" });
  expect(replyIdempotencyKey).toMatch(/^owner-reply-/);
  expect(requestedSocialPaths).toContain(
    `GET /api/backend/worlds/${UI_D_WORLD_ID}/manual-social/feed`,
  );
  expect(requestedSocialPaths).toContain(
    `GET /api/backend/worlds/${UI_D_WORLD_ID}/manual-social/posts/${UI_D_ROOT_POST_ID}`,
  );
  expect(requestedSocialPaths).toContain(
    `POST /api/backend/worlds/${UI_D_WORLD_ID}/manual-social/posts/${UI_D_ROOT_POST_ID}/replies`,
  );
  expect(globalSocialPaths).toEqual([]);
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
  let responseMode: "403" | "404" | "503" | "scope" | "ready" = "403";
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
        [
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
  expect(feedRequests).toBe(5);
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
