import { readFileSync } from "node:fs";
import { join } from "node:path";

import { expect, test, type Page, type Route, type TestInfo } from "@playwright/test";

const FIXED_TIME = new Date("2026-08-31T11:00:00+09:00");
const FIXTURE_ORIGIN = "http://127.0.0.1:3302";
const STATIC_LAUNCH_TOKEN = "ui-f-visual-launch-token-000000000000";
const WORLD_ID = "world-ui-f-lumen";
const GRAPH_ROUTE =
  `/characters/character-ui-f-owner/worlds/${WORLD_ID}/relationship-graph`;

const fixture = JSON.parse(
  readFileSync(join(process.cwd(), "fixtures", "visual-corpus.json"), "utf8"),
) as {
  graph: {
    meta: Record<string, unknown>;
    [key: string]: unknown;
  };
};

type NetworkAudit = {
  blocked: string[];
  providerCalls: string[];
  writes: string[];
};

async function prepareProductSurface(
  page: Page,
  testInfo: TestInfo,
): Promise<NetworkAudit> {
  const baseURL = testInfo.project.use.baseURL;
  if (typeof baseURL !== "string") throw new Error("visual project requires baseURL");
  const productOrigin = new URL(baseURL).origin;
  const audit: NetworkAudit = { blocked: [], providerCalls: [], writes: [] };

  if (testInfo.project.name === "static-export") {
    await page.addInitScript(
      ({ apiBaseUrl, launchToken }) => {
        Object.assign(window, {
          __ANGMOO_RUNTIME_CONFIG__: {
            profile: "tauri-static",
            apiBaseUrl,
            graphProvider: "ladybug",
            launchToken,
          },
        });
      },
      { apiBaseUrl: FIXTURE_ORIGIN, launchToken: STATIC_LAUNCH_TOKEN },
    );
  }

  await page.clock.install({ time: FIXED_TIME });
  page.on("request", (request) => {
    const url = new URL(request.url());
    const method = request.method();
    if (!["GET", "HEAD", "OPTIONS"].includes(method)) {
      audit.writes.push(`${method} ${url.pathname}`);
    }
    if (/provider|gemini|openai|anthropic|generate|completion/i.test(url.pathname)) {
      audit.providerCalls.push(`${method} ${url.pathname}`);
    }
  });
  await page.route("**/*", async (route) => {
    const url = new URL(route.request().url());
    if (url.origin === productOrigin || url.origin === FIXTURE_ORIGIN) {
      await route.continue();
      return;
    }
    audit.blocked.push(route.request().url());
    await route.abort("blockedbyclient");
  });
  return audit;
}

async function settleVisualSurface(page: Page): Promise<void> {
  await page.evaluate(async () => {
    await document.fonts.ready;
    await Promise.all(
      Array.from(document.images).map((image) => {
        if (image.complete) return Promise.resolve();
        return new Promise<void>((resolve) => {
          image.addEventListener("load", () => resolve(), { once: true });
          image.addEventListener("error", () => resolve(), { once: true });
        });
      }),
    );
  });
  await expect
    .poll(() =>
      page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth),
    )
    .toBeLessThanOrEqual(1);
}

function expectReadOnlyFixture(audit: NetworkAudit): void {
  expect(audit.blocked).toEqual([]);
  expect(audit.providerCalls).toEqual([]);
  expect(audit.writes).toEqual([]);
}

async function fulfillJson(route: Route, body: unknown, status = 200): Promise<void> {
  await route.fulfill({ contentType: "application/json", json: body, status });
}

async function overrideApiRead(
  page: Page,
  pathSuffix: string,
  response: { body: unknown; status?: number },
): Promise<void> {
  await page.route("**/*", async (route) => {
    const url = new URL(route.request().url());
    const isProductProxy = url.pathname.startsWith("/api/backend/");
    const isStaticApi =
      url.origin === FIXTURE_ORIGIN && url.pathname.startsWith("/api/v1/");
    if (
      route.request().method() === "GET" &&
      (isProductProxy || isStaticApi) &&
      `${url.pathname}${url.search}`.includes(pathSuffix)
    ) {
      await fulfillJson(route, response.body, response.status ?? 200);
      return;
    }
    await route.fallback();
  });
}

test("UI-F captures compact and centered Device Home parity", async ({ page }, testInfo) => {
  const audit = await prepareProductSurface(page, testInfo);

  await page.setViewportSize({ width: 360, height: 800 });
  await page.goto("/");
  await expect(page.locator('main[data-product-surface="device-home"]')).toBeVisible();
  await expect(page.locator('[data-runtime-state="healthy"]')).toBeVisible();
  await expect(page.getByText("루멘 히어로 아카데미", { exact: true })).toBeVisible();
  await settleVisualSurface(page);
  await expect(page).toHaveScreenshot(["ui-f", "device-home-phone-360x800.png"]);

  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.reload();
  const device = page.locator('[data-product-shell="device"]');
  await expect(device).toBeVisible();
  const deviceBox = await device.boundingBox();
  expect(deviceBox).not.toBeNull();
  expect(Math.abs(deviceBox!.x + deviceBox!.width / 2 - 720)).toBeLessThanOrEqual(1);
  await settleVisualSurface(page);
  await expect(page).toHaveScreenshot(["ui-f", "device-home-centered-1440x1000.png"]);

  expectReadOnlyFixture(audit);
});

test("UI-F captures the global social media stream at the standard Phone size", async ({
  page,
}, testInfo) => {
  const audit = await prepareProductSurface(page, testInfo);
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/posts");

  const mediaPost = page.locator('[data-social-post-row="post-ui-f-media"]');
  await expect(mediaPost).toBeVisible();
  await expect(mediaPost.getByText("더보기", { exact: true })).toBeVisible();
  await expect(mediaPost.getByRole("img", { name: "노란 앵무 Angmoo 로고" })).toBeVisible();
  await expect(mediaPost.getByLabel("대꾸 2", { exact: true })).toBeVisible();
  await expect(mediaPost.getByLabel("좋아요 1", { exact: true })).toBeVisible();
  await expect(mediaPost.getByRole("button", { name: "게시글 메뉴" })).toHaveCount(0);
  await settleVisualSurface(page);
  await expect(page).toHaveScreenshot(["ui-f", "global-feed-media-phone-390x844.png"]);

  expectReadOnlyFixture(audit);
});

test("UI-F captures the persistent World composer and long Korean stream", async ({
  page,
}, testInfo) => {
  const audit = await prepareProductSurface(page, testInfo);
  await page.setViewportSize({ width: 436, height: 880 });
  await page.goto(`/worlds/${WORLD_ID}/feed`);

  await expect(page.locator('[data-world-social-surface="feed"]')).toBeVisible();
  await expect(page.locator("#world-owner-composer")).toBeVisible();
  await expect(page.getByLabel("제목", { exact: true })).toHaveAttribute(
    "placeholder",
    "오늘 이 World에 남길 이야기의 제목을 적어주세요",
  );
  await expect(page.locator('[data-social-post-row="world-post-ui-f-1"]')).toBeVisible();
  await settleVisualSurface(page);
  await expect(page).toHaveScreenshot(["ui-f", "world-feed-composer-phone-436x880.png"]);

  expectReadOnlyFixture(audit);
});

test("UI-F captures running, scheduled, and failed autonomy states", async ({
  page,
}, testInfo) => {
  const audit = await prepareProductSurface(page, testInfo);
  await page.setViewportSize({ width: 436, height: 880 });
  await page.goto("/agents");

  await expect(page.locator('[data-character-autonomy-state="running"]')).toBeVisible();
  await expect(page.locator('[data-character-autonomy-state="scheduled"]')).toBeVisible();
  await expect(page.locator('[data-character-autonomy-state="failed"]')).toBeVisible();
  await expect(page.locator('[data-character-recent-activity="recorded"]').first()).toBeVisible();
  await expect(page.getByText("내부 topic signature", { exact: false })).toHaveCount(0);
  await settleVisualSurface(page);
  await expect(page).toHaveScreenshot(["ui-f", "characters-autonomy-phone-436x880.png"]);

  expectReadOnlyFixture(audit);
});

test("UI-F captures populated and empty Creator Studio states", async ({ page }, testInfo) => {
  const audit = await prepareProductSurface(page, testInfo);
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/studio");

  await expect(page.locator('[data-product-shell="creator-studio"]')).toBeVisible();
  await expect(page.getByRole("heading", { name: "내 World" })).toBeVisible();
  await expect(page.getByText("루멘 히어로 아카데미", { exact: true })).toBeVisible();
  await settleVisualSurface(page);
  await expect(page).toHaveScreenshot(["ui-f", "creator-studio-populated-1440x900.png"]);

  await overrideApiRead(page, "worlds/mine?surface=creator_studio", {
    body: {
      schema_version: "local-world-surface-v1",
      surface: "creator_studio",
      items: [],
      next_cursor: null,
    },
  });
  await page.reload();
  await expect(page.getByRole("heading", { name: "아직 만든 World가 없습니다" })).toBeVisible();
  await settleVisualSurface(page);
  await expect(page).toHaveScreenshot(["ui-f", "creator-studio-empty-1440x900.png"]);

  expectReadOnlyFixture(audit);
});

test("UI-F captures ready and degraded Relationship Graph states", async ({
  page,
}, testInfo) => {
  const audit = await prepareProductSurface(page, testInfo);
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto(GRAPH_ROUTE);

  await expect(page.locator('[data-product-shell="relationship-graph"]')).toBeVisible();
  await expect(page.locator('[data-relationship-graph-state="ready"]')).toBeVisible();
  await expect(page.getByRole("heading", { name: "방향 관계 지도" })).toBeVisible();
  await settleVisualSurface(page);
  await expect(page).toHaveScreenshot(["ui-f", "relationship-graph-ready-1440x900.png"]);

  await overrideApiRead(page, "relationship-graph", {
    body: {
      ...fixture.graph,
      meta: {
        ...fixture.graph.meta,
        source: "canonical_fallback",
        graph_status: "unavailable",
        projection_lag_seconds: null,
        fallback_reason: "graph_provider_unavailable",
      },
    },
  });
  await page.reload();
  await expect(page.locator('[data-relationship-graph-state="degraded"]')).toBeVisible();
  await expect(page.getByText("Canonical DB 안전 대체", { exact: true })).toBeVisible();
  await settleVisualSurface(page);
  await expect(page).toHaveScreenshot(["ui-f", "relationship-graph-degraded-1440x900.png"]);

  expectReadOnlyFixture(audit);
});

test("UI-F captures runtime-offline truth without hiding launchability", async ({
  page,
}, testInfo) => {
  const audit = await prepareProductSurface(page, testInfo);
  await overrideApiRead(page, "runtime/status", {
    body: { detail: "runtime_unavailable" },
    status: 503,
  });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/");

  await expect(page.locator('[data-runtime-state="degraded"]')).toBeVisible();
  await expect(page.locator('[data-world-launchability="launchable"]')).toBeVisible();
  await settleVisualSurface(page);
  await expect(page).toHaveScreenshot(["ui-f", "device-home-runtime-offline-390x844.png"]);

  expectReadOnlyFixture(audit);
});

test("UI-F product surfaces keep focus, reduced motion, and 200 percent text reflow", async ({
  page,
}, testInfo) => {
  const audit = await prepareProductSurface(page, testInfo);
  await page.setViewportSize({ width: 360, height: 800 });
  await page.goto(`/worlds/${WORLD_ID}/feed`);

  const title = page.getByLabel("제목", { exact: true });
  await expect(title).toBeVisible();
  await title.focus();
  await expect(title).toBeFocused();
  expect(await title.evaluate((node) => node.matches(":focus-visible"))).toBe(true);
  const focusIndicator = await title.evaluate((node) => {
    const style = getComputedStyle(node);
    return {
      boxShadow: style.boxShadow,
      outlineStyle: style.outlineStyle,
      outlineWidth: Number.parseFloat(style.outlineWidth),
    };
  });
  expect(
    (focusIndicator.outlineStyle !== "none" && focusIndicator.outlineWidth >= 2) ||
      focusIndicator.boxShadow !== "none",
  ).toBe(true);

  const motion = await page.getByRole("button", { name: "게시하기" }).evaluate((node) => {
    const style = getComputedStyle(node);
    return { animationDuration: style.animationDuration, transitionDuration: style.transitionDuration };
  });
  for (const duration of [motion.animationDuration, motion.transitionDuration]) {
    const seconds = duration.endsWith("ms")
      ? Number.parseFloat(duration) / 1_000
      : Number.parseFloat(duration);
    expect(seconds).toBeLessThanOrEqual(0.000_01);
  }

  await page.evaluate(() => {
    document.documentElement.style.fontSize = "200%";
  });
  await expect
    .poll(() =>
      page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth),
    )
    .toBeLessThanOrEqual(1);
  await expect(page.locator("#world-owner-composer")).toBeVisible();

  expectReadOnlyFixture(audit);
});
