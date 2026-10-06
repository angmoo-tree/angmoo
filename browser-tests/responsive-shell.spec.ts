import { expect, test, type Page } from "@playwright/test";
import { VISUAL_ENVIRONMENT } from "./fixtures/visual-environment.mjs";

const world = "world-ui-f-lumen";
const graph = `/characters/character-ui-f-owner/worlds/${world}/relationship-graph?provider=ladybug`;
const routes = ["/", "/agents", "/agents/new", "/agents/character-ui-f-mango", "/settings", "/login?returnTo=%2F", "/posts", "/posts/post-ui-f-main", `/worlds/${world}`, `/worlds/${world}/feed`, `/worlds/${world}/chat`, `/worlds/${world}/chat/thread-ui-f-main`, `/worlds/${world}/characters`, `/worlds/${world}/characters/wc-ui-f-mango`, `/worlds/${world}/relationships`, `/worlds/${world}/posts/post-ui-f-main`, `/characters/character-ui-f-mango/worlds/${world}/autonomy-setup`, "/memory", `/memory?world=${world}&subject=wc-ui-f-mango`, "/memory-explorer", "/studio", "/studio/import", "/studio/worlds/new", `/studio/worlds/${world}`, "/worlds/new", `/worlds/${world}/creator`, graph];

test.beforeEach(async ({ page }, info) => {
  const origin = new URL(String(info.project.use.baseURL)).origin;
  await page.route("**/*", route => [origin, "http://127.0.0.1:3302"].includes(new URL(route.request().url()).origin) ? route.fallback() : route.abort("blockedbyclient"));
  if (info.project.name === "static-export") await page.addInitScript(() => {
    Object.assign(window, { __ANGMOO_RUNTIME_CONFIG__: { profile: "tauri-static", apiBaseUrl: "http://127.0.0.1:3302", graphProvider: "ladybug", launchToken: "responsive-synthetic-only-token-000000000000" } });
  });
});

async function native(page: Page, kind = "phone") {
  await page.addInitScript(({ kind }) => {
    const commands: { command: string; args?: Record<string, unknown> }[] = [];
    Object.assign(window, { __NAVTEST__: commands, __ANGMOO_DESKTOP_WINDOW__: { kind, route: "/" }, __TAURI__: { core: { invoke: async (command: string, args?: Record<string, unknown>) => {
      commands.push({ command, args });
      if (command === "desktop_runtime_status") return { phase: "ready", apiBaseUrl: "http://127.0.0.1:3302", graphProvider: "ladybug", launchToken: "responsive-synthetic-only-token-000000000000" };
      if (command === "desktop_shutdown_status") return { phase: "RUNNING", deferred: false };
      return args?.route;
    } } } });
  }, { kind });
}

const address = (page: Page) => page.getByRole("textbox", { name: "Angmoo 내부 경로" });
async function enter(page: Page, route: string) { await address(page).fill(route); await address(page).press("Enter"); }
async function assertGeometry(page: Page, maximum: number) {
  const frame = page.locator('[data-product-viewport-body] [data-product-shell="device"], [data-product-viewport-body] [data-product-shell="memory"], [data-product-viewport-body] [data-product-shell="creator-studio"], [data-product-viewport-body] [data-product-shell="relationship-graph"]').first();
  await expect(frame).toBeVisible();
  const geometry = await frame.evaluate(frame => {
    const body = frame.closest('[data-product-viewport-body]')!;
    const rect = frame.getBoundingClientRect(), b = body.getBoundingClientRect();
    return { width: rect.width, left: rect.left, viewport: window.innerWidth, overflow: document.documentElement.scrollWidth - document.documentElement.clientWidth, bottom: b.bottom, height: window.innerHeight, border: getComputedStyle(frame).borderTopWidth, radius: getComputedStyle(frame).borderRadius };
  });
  expect(geometry.overflow).toBe(0);
  expect(geometry.width).toBe(Math.min(geometry.viewport, maximum));
  expect(Math.abs(geometry.left - (geometry.viewport - geometry.width) / 2)).toBeLessThanOrEqual(1);
  expect(geometry.bottom).toBeLessThanOrEqual(geometry.height + 1);
  if (maximum === 960) { expect(geometry.border).toBe("0px"); expect(geometry.radius).toBe("0px"); }
}

for (const route of routes) test(`direct and reload ${route}`, async ({ page }) => {
  await page.goto(route);
  await expect(page.locator('[data-product-viewport]')).toBeVisible();
  await expect(page.getByText("지원하지 않는 Angmoo 경로입니다.", { exact: true })).toHaveCount(0);
  await expect(page.locator("main").first()).toBeVisible();
  await page.reload();
  await expect(page.locator("main").first()).toBeVisible();
  expect(await page.locator('[data-desktop-navigation]').count()).toBe(0);
});

test("general viewport fills up to 960 with one scroll owner at all supported sizes", async ({ page }, info) => {
  await page.goto("/agents");
  for (const width of [320, 360, 390, 480, 768, 960, 1024, 1280, 1920]) for (const height of [600, 800, 850, 1080]) {
    await page.setViewportSize({ width, height }); await assertGeometry(page, 960);
    expect(await page.locator('[data-device-scroll-owner="true"]').count()).toBe(1);
  }
  await page.screenshot({ path: info.outputPath("general-wide.png") });
});

for (const route of ["/memory", "/studio", graph]) test(`workspace reflow ${route}`, async ({ page }, info) => {
  await page.goto(route);
  for (const width of [320, 480, 768, 960, 1440, 1920]) { await page.setViewportSize({ width, height: 850 }); await assertGeometry(page, 1440); }
  await page.screenshot({ path: info.outputPath("workspace-wide.png") });
});

test("browser fake native uses real history, truncates forward tail, and reloads the current deep route", async ({ page }) => {
  await native(page); const writes: string[] = [];
  page.on("request", request => { if (request.method() === "POST" && !/environment|default-space\/ensure|auth\/local/.test(request.url())) writes.push(request.url()); });
  await page.goto("/agents"); await expect(address(page)).toHaveValue("/agents");
  await expect(page.getByRole("button", { name: "뒤로", exact: true })).toBeDisabled();
  await enter(page, "/settings"); await expect(page).toHaveURL(/\/settings$/); await expect(address(page)).toHaveValue("/settings");
  await enter(page, "/posts"); await expect(address(page)).toHaveValue("/posts");
  await page.getByRole("button", { name: "뒤로", exact: true }).click(); await expect(address(page)).toHaveValue("/settings");
  await expect(page.getByRole("button", { name: "앞으로", exact: true })).toBeEnabled();
  await enter(page, "/agents"); await expect(address(page)).toHaveValue("/agents");
  await expect(page.getByRole("button", { name: "앞으로", exact: true })).toBeDisabled();
  await enter(page, `/worlds/${world}/posts/post-ui-f-main?returnTo=%2Fposts`); await expect(address(page)).toHaveValue(`/worlds/${world}/posts/post-ui-f-main?returnTo=%2Fposts`);
  await page.getByRole("button", { name: "현재 화면 새로고침" }).click();
  await expect(address(page)).toHaveValue(`/worlds/${world}/posts/post-ui-f-main?returnTo=%2Fposts`);
  expect(writes).toEqual([]);
});

test("address draft Escape, IME, invalid inputs and canonical aliases do not leak external documents", async ({ page }) => {
  await native(page); await page.goto("/agents");
  for (const invalid of ["https://example.com", "//example.com", "/../settings", "/%2e%2e/settings", "/agents/a%2fb", "/agents/%zz", "/unsupported", "/settings?api_key=secret", "/settings?%61pi_key=secret", "/settings?__angmoo_window_route=/", "/worlds/%6eew/feed"]) {
    await enter(page, invalid); await expect(page.locator("#desktop-navigation-error")).toContainText("경로를 열 수 없습니다"); await expect(page).toHaveURL(/\/agents$/);
  }
  await address(page).press("Escape"); await expect(address(page)).toHaveValue("/agents");
  await address(page).fill("/settings");
  await address(page).dispatchEvent("keydown", { key: "Enter", isComposing: true }); await expect(page).toHaveURL(/\/agents$/);
  await address(page).press("Escape");
  await enter(page, "/worlds/new");
  const commands = await page.evaluate(() => (window as unknown as { __NAVTEST__: { command: string; args?: Record<string, unknown> }[] }).__NAVTEST__);
  expect(commands.filter(row => row.command === "open_product_window").at(-1)?.args).toEqual({ kind: "studio", route: "/studio/worlds/new" });
  await expect(page).toHaveURL(/\/agents$/);
});

test("unknown history metadata or unavailable storage leaves both traversal buttons disabled", async ({ page }) => {
  await native(page); await page.goto("/agents"); await enter(page, "/settings");
  await page.evaluate(() => { sessionStorage.setItem("angmoo.product-history.v1", "broken"); window.dispatchEvent(new Event("angmoo:desktop-route")); });
  await expect(page.getByRole("button", { name: "뒤로", exact: true })).toBeDisabled();
  await expect(page.getByRole("button", { name: "앞으로", exact: true })).toBeDisabled();
  await page.reload(); await expect(address(page)).toHaveValue("/settings");
  await expect(page.getByRole("button", { name: "뒤로", exact: true })).toBeDisabled();
});

test("replace preserves router state and rejected push retains the real forward tail", async ({ page }) => {
  await native(page); await page.goto("/agents"); await enter(page, "/settings");
  await expect(address(page)).toHaveValue("/settings");
  await enter(page, "/posts"); await expect(address(page)).toHaveValue("/posts");
  await page.getByRole("button", { name: "뒤로", exact: true }).click(); await expect(address(page)).toHaveValue("/settings");
  const before = await page.evaluate(() => ({ session: sessionStorage.getItem("angmoo.product-history.v1"), entry: history.state.__angmooProductHistory }));
  const after = await page.evaluate(() => {
    history.replaceState({ ...history.state, fixtureRouterState: "preserved" }, "", location.href);
    let rejected = false;
    try { history.pushState(history.state, "", "https://example.org/forbidden"); } catch { rejected = true; }
    return { rejected, session: sessionStorage.getItem("angmoo.product-history.v1"), entry: history.state.__angmooProductHistory, state: history.state.fixtureRouterState };
  });
  expect(after).toEqual({ ...before, rejected: true, state: "preserved" });
  await expect(page.getByRole("button", { name: "앞으로", exact: true })).toBeEnabled();
  await page.getByRole("button", { name: "앞으로", exact: true }).click(); await expect(address(page)).toHaveValue("/posts");
});

test("blocked session storage keeps destination recovery while disabling traversal", async ({ page }) => {
  await native(page);
  await page.addInitScript(() => { const original = Storage.prototype.setItem; Storage.prototype.setItem = function(key, value) { if (key === "angmoo.product-history.v1") throw new DOMException("fixture storage denied", "SecurityError"); return original.call(this, key, value); }; });
  await page.goto("/agents"); await enter(page, "/settings");
  await expect(address(page)).toHaveValue("/settings");
  await expect(page.getByRole("button", { name: "뒤로", exact: true })).toBeDisabled();
  await expect(page.getByRole("button", { name: "앞으로", exact: true })).toBeDisabled();
  await page.getByRole("button", { name: "Device Home으로 이동" }).click(); await expect(address(page)).toHaveValue("/");
});

test("native direct profile entry keeps World destination recovery without invented back history", async ({ page }) => {
  await native(page);
  await page.route("**/world-characters/wc-responsive-cold", route => route.fulfill({ json: {
    schema_version: "world-character-profile-v1", world_id: world, world_character_id: "wc-responsive-cold",
    character_id: "character-responsive-cold", display_name: "Synthetic cold profile", handle: null,
    avatar_url: null, banner_url: null, intro: "", role_key: null, control_mode: "autonomous",
    status: "active", profile_capability: "available",
  } }));
  await page.goto(`/worlds/${world}/characters/wc-responsive-cold`);
  await expect(page.getByRole("heading", { name: "Synthetic cold profile" })).toBeVisible();
  await expect(page.getByRole("button", { name: "뒤로", exact: true })).toBeDisabled();
  await page.getByRole("button", { name: "이전 화면으로", exact: true }).click();
  await expect(address(page)).toHaveValue(`/worlds/${world}/characters`);
  await expect(page.getByRole("button", { name: "뒤로", exact: true })).toBeDisabled();
});

test("keyboard navigation leaves textarea and visible modal input ownership intact", async ({ page }) => {
  await native(page); await page.goto("/agents");
  const before = await page.evaluate(() => {
    const textarea = document.createElement("textarea"); textarea.id = "fixture-textarea"; document.body.append(textarea); textarea.focus();
    textarea.dispatchEvent(new KeyboardEvent("keydown", { key: "l", ctrlKey: true, bubbles: true, cancelable: true }));
    return document.activeElement?.id;
  });
  expect(before).toBe("fixture-textarea");
  const modal = await page.evaluate(() => {
    document.getElementById("fixture-textarea")?.remove();
    const dialog = document.createElement("div"); dialog.setAttribute("role", "dialog"); dialog.setAttribute("aria-modal", "true"); dialog.id = "fixture-modal";
    const input = document.createElement("input"); input.id = "fixture-modal-input"; dialog.append(input); document.body.append(dialog); input.focus();
    input.dispatchEvent(new KeyboardEvent("keydown", { key: "l", ctrlKey: true, bubbles: true, cancelable: true }));
    return document.activeElement?.id;
  });
  expect(modal).toBe("fixture-modal-input");
});

test("native toolbar sizing, keyboard and child Home retain the source window", async ({ page }, info) => {
  await native(page, "memory"); await page.goto(`/memory?world=${world}`);
  for (const width of [320, 480, 1920]) {
    await page.setViewportSize({ width, height: 480 });
    for (const button of await page.locator('[data-desktop-navigation] button').all()) { const box = await button.boundingBox(); expect(box!.width).toBeGreaterThanOrEqual(44); expect(box!.height).toBeGreaterThanOrEqual(44); }
    await assertGeometry(page, 1440);
  }
  await expect(page.getByRole("link", { name: "Device Home으로 돌아가기" })).toHaveCount(0);
  // Chrome owns real Ctrl+L even in a renderer mock. Actual WebView keys are
  // tested separately in the contributor native smoke.
  await page.evaluate(() => window.dispatchEvent(new KeyboardEvent("keydown", { key: "l", ctrlKey: true, cancelable: true })));
  await expect(address(page)).toBeFocused();
  await address(page).press("Escape");
  await page.getByRole("button", { name: "Device Home으로 이동" }).click();
  await expect(page).toHaveURL(new RegExp(`/memory\\?world=${world}$`));
  const commands = await page.evaluate(() => (window as unknown as { __NAVTEST__: { command: string; args?: Record<string, unknown> }[] }).__NAVTEST__);
  expect(commands.filter(row => row.command === "open_product_window").at(-1)?.args).toEqual({ kind: "phone", route: "/" });
  expect(commands.some(row => /skip_memory_shutdown|retry_desktop_runtime|close_product_window/.test(row.command))).toBe(false);
  await page.screenshot({ path: info.outputPath("native-renderer-toolbar.png") });
});

test("dirty World input can cancel toolbar navigation and reload without losing text", async ({ page }) => {
  await native(page, "studio"); await page.goto("/studio/worlds/new");
  const field = page.getByRole("textbox", { name: /^World 이름/ });
  await field.fill("unsaved synthetic world");
  const dialogs: string[] = [];
  page.on("dialog", async dialog => { dialogs.push(dialog.type()); await dialog.dismiss(); });
  await enter(page, "/studio"); await expect(field).toHaveValue("unsaved synthetic world");
  await page.getByRole("button", { name: "현재 화면 새로고침" }).click(); await expect(field).toHaveValue("unsaved synthetic world");
  expect(dialogs).toEqual(["confirm", "confirm"]);
});

test("a failed cross-window request keeps the source route and real history", async ({ page }) => {
  await native(page); await page.goto("/agents");
  await page.evaluate(() => {
    const original = window.__TAURI__!.core!.invoke!;
    window.__TAURI__!.core!.invoke = async (command, args) => { if (command === "open_product_window") throw new Error("synthetic child open failure"); return original(command, args); };
  });
  const historyBefore = await page.evaluate(() => ({ length: history.length, state: JSON.stringify(history.state) }));
  await enter(page, "/memory");
  await expect(page.locator("#desktop-navigation-error")).toBeVisible();
  await expect(page).toHaveURL(/\/agents$/);
  expect(await page.evaluate(() => ({ length: history.length, state: JSON.stringify(history.state) }))).toEqual(historyBefore);
});

test("Korean and English native labels remain accessible at 200 percent", async ({ page }) => {
  await native(page);
  await page.route("**/auth/me", route => route.fulfill({ json: { id: "responsive-owner", display_name: "A deliberately long synthetic English owner name", profile_setup_completed: true, ui_language: "en", ui_preference_revision: 1, feed_content_filter: "all" } }));
  await page.route("**/auth/local/environment", route => route.fulfill({ json: { ...VISUAL_ENVIRONMENT, preferred_language: "en-US" } }));
  await page.goto("/agents"); await expect(page.getByRole("navigation", { name: "Angmoo navigation" })).toBeVisible();
  await page.evaluate(() => { document.documentElement.style.zoom = "2"; });
  await expect(page.getByRole("button", { name: "Reload current page" })).toBeVisible();
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow).toBeLessThanOrEqual(1);
});
