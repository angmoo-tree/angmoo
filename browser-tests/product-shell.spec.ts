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

  await page.keyboard.press("Tab");
  await expect(page.getByRole("link", { name: "설정 열기" })).toBeFocused();
  await page.keyboard.press("Tab");
  await expect(page.getByRole("link", { name: "Creator Studio 열기" })).toBeFocused();
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
  await expect(page.getByText("전체 커뮤니티 Feed와 구분됩니다")).toBeVisible();

  await page.goto("/worlds/world-foreign");
  await expect(page.getByRole("heading", { name: "이 World 앱을 열 수 없어요" })).toBeVisible();
  await expect(page.getByText(WORLD_ALPHA.name, { exact: true })).toHaveCount(0);
  await expect(page.locator('main[data-product-surface="world-app"]')).toHaveCount(0);
  expect(audit.writes).toEqual([]);
  expect(audit.providerCalls).toEqual([]);
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
