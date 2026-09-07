import { expect, test } from "@playwright/test";

const token = "static-route-probe-token-000000000000";
test.beforeEach(async ({page}) => {
  await page.addInitScript(({token}) => Object.assign(window, {
    __ANGMOO_RUNTIME_CONFIG__: {profile: "tauri-static", apiBaseUrl: "http://127.0.0.1:8080", graphProvider: "ladybug", launchToken: token},
  }), {token});
  await page.route("http://127.0.0.1:8080/api/v1/**", async route => {
    expect(route.request().headers()["x-angmoo-launcher-token"]).toBe(token);
    const path = new URL(route.request().url()).pathname;
    await route.fulfill({status: path.endsWith("/auth/me") ? 200 : 503, json: path.endsWith("/auth/me")
      ? {id: "lifecycle-owner", email: null, display_name: "Owner", profile_setup_completed: true, feed_content_filter: "all", is_admin: false}
      : {detail: "fixture_unavailable"}});
  });
});

test("Memory scope switch ignores an older pending Character response", async ({page}) => {
  let release!: () => void;
  const held = new Promise<void>(resolve => {release = resolve;});
  let oldStarted = false;
  let oldFinished = false;
  const calls: string[] = [];
  await page.route("http://127.0.0.1:8080/api/v1/worlds/**", async route => {
    const path = new URL(route.request().url()).pathname;
    calls.push(path);
    if (path.endsWith("/mine")) return route.fulfill({json: {
      schema_version: "local-world-surface-v1", surface: "device_home",
      items: ["a", "b"].map(id => ({world_id: id, name: `World ${id}`, launchable: true})), next_cursor: null,
    }});
    if (path.endsWith("/world-characters")) {
      const world = path.split("/")[4];
      if (world === "a") {oldStarted = true; await held;}
      await route.fulfill({json: {schema_version: "world-character-profile-list-v1", world_id: world,
        items: [{schema_version: "world-character-profile-v1", world_id: world, world_character_id: `wc-${world}`, character_id: `c-${world}`, display_name: `Bird ${world}`, handle: `bird_${world}`, avatar_url: null, banner_url: null, intro: "", role_key: "resident", control_mode: "autonomous", status: "active", profile_capability: "available"}],
      }});
      if (world === "a") oldFinished = true;
      return;
    }
    const scope = {world_id: "b", subject_world_character_id: "wc-b"};
    if (path.endsWith("/memory/settings")) return route.fulfill({json: {schema_version: "memory-setting-read.v1", scope, configured: true, enabled: true, retention_days: 180, provider_mode: "none", version: 1, capabilities: {read: "available", mutate: "available"}}});
    if (path.endsWith("/memories")) return route.fulfill({json: {schema_version: "memory-item-list.v1", scope, memory_enabled: true, items: [], next_cursor: null}});
    return route.fulfill({status: 503, json: {detail: "fixture_unavailable"}});
  });
  await page.goto("/memory?world=a");
  await expect.poll(() => oldStarted).toBe(true);
  await page.getByRole("combobox", {name: "World", exact: true}).selectOption("b");
  await expect(page.getByRole("combobox", {name: "기억하는 Character", exact: true})).toHaveValue("wc-b");
  release();
  await expect.poll(() => oldFinished).toBe(true);
  await expect(page.getByRole("combobox", {name: "World", exact: true})).toHaveValue("b");
  await expect(page.getByRole("combobox", {name: "기억하는 Character", exact: true})).toHaveValue("wc-b");
  await expect(page.getByText("Bird a", {exact: true})).toHaveCount(0);
  await expect(page).toHaveURL(/world=b/);
  expect(calls.some(path => path.includes("/a/world-characters/wc-a/"))).toBe(false);
});

test("Memory child close uses only the window command and restarted host status clears closing UI", async ({page}) => {
  await page.addInitScript(({token}) => {
    const state = {phase: "RUNNING", deferred: false, commands: [] as string[]};
    Object.assign(window, {__LIFECYCLE__: state, __ANGMOO_DESKTOP_WINDOW__: {kind: "memory", route: "/memory"},
      __TAURI__: {core: {invoke: async (command: string) => {
        state.commands.push(command);
        if (command === "desktop_runtime_status") return {phase: "ready", apiBaseUrl: "http://127.0.0.1:8080", launchToken: token, graphProvider: "ladybug"};
        if (command === "desktop_shutdown_status") return {phase: state.phase, deferred: state.deferred};
        return undefined;
      }}},
    });
  }, {token});
  await page.goto("/memory");
  await page.getByRole("button", {name: "Angmoo 창 닫기", exact: true}).click();
  const commands = await page.evaluate(() => (window as unknown as {__LIFECYCLE__: {commands: string[]}}).__LIFECYCLE__.commands);
  expect(commands.filter(command => command === "close_product_window")).toHaveLength(1);
  expect(commands.filter(command => /shutdown|quit|exit/.test(command) && command !== "desktop_shutdown_status")).toEqual([]);
  const dialog = page.getByRole("dialog", {name: "끄는 중…"});
  await expect(dialog).toHaveCount(0);
  await page.evaluate(() => Object.assign((window as unknown as {__LIFECYCLE__: object}).__LIFECYCLE__, {phase: "CONSOLIDATING", deferred: true}));
  await expect(dialog).toBeVisible();
  await expect(dialog.getByRole("status")).toContainText("다음 실행에서 이어집니다");
  await page.reload();
  await expect(page.getByRole("button", {name: "Angmoo 창 닫기", exact: true})).toBeVisible();
  await expect(dialog).toHaveCount(0);
});
