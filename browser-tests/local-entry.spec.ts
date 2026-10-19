import { test, expect, type Page } from "@playwright/test";
import { installLocalContent } from "./fixtures/local-entry-content";

async function configure(page: Page, isStatic: boolean) {
  if (isStatic) await page.addInitScript(() => Object.assign(window, {
    __ANGMOO_RUNTIME_CONFIG__: { profile: "tauri-static", apiBaseUrl: "http://127.0.0.1:3492", graphProvider: "ladybug", launchToken: "synthetic-desktop-launch-token-000000000000" },
  }));
}
const state = async () => (await fetch("http://127.0.0.1:3492/_test/state")).json();
test.beforeEach(async () => { await fetch("http://127.0.0.1:3492/_test/reset", { method: "POST" }); });

for (const locale of ["en-US", "ko-KR", "ja-JP"]) test(`first entry, expiry and explicit stop: ${locale}`, async ({ browser, baseURL }, info) => {
  const context = await browser.newContext({ locale, timezoneId: "America/New_York" });
  const page = await context.newPage();
  await configure(page, info.project.name === "static");
  const errors: string[] = [];
  page.on("pageerror", error => errors.push(error.message));
  await page.goto(baseURL!);
  await expect(page.getByRole("link", { name: /SNS World/ })).toBeVisible();
  expect(new URL(page.url()).pathname).toBe("/");
  expect(await page.locator('[data-local-owner-state="unavailable"]').count()).toBe(0);
  let data = await state();
  expect(data.users).toHaveLength(1); expect(data.worlds).toHaveLength(1);
  expect(data.users[0].name).toBe(locale === "ko-KR" ? "사용자" : "User");
  expect(data.worlds[0].language).toBe(locale === "ko-KR" ? "ko" : "en");
  expect(data.worlds[0].timezone).toBe("America/New_York");
  const original = data.users[0].id;
  await page.screenshot({ path: `../artifacts/local-entry-browser/${info.project.name}-${locale}-home.png` });
  await page.getByRole("link", { name: /SNS World/ }).click();
  await expect.poll(async () => (await state()).profiles.length).toBe(1);
  expect((await state()).profiles[0].name).toBe(locale === "ko-KR" ? "사용자" : "User");
  expect(new URL(page.url()).pathname).toContain(`/worlds/${data.worlds[0].id}/feed`);
  await page.goto(baseURL!);
  await expect(page.getByRole("link", { name: /SNS World/ })).toBeVisible();
  // Independent tabs use one persistent connection; the server remains canonical.
  const other = await context.newPage(); await configure(other, info.project.name === "static");
  await other.goto(baseURL!); await expect(other.getByRole("link", { name: /SNS World/ })).toBeVisible();
  data = await state(); expect(data.clients).toHaveLength(1); expect(data.users).toHaveLength(1);
  await fetch("http://127.0.0.1:3492/_test/expire", { method: "POST" });
  await page.reload(); await expect(page.getByRole("link", { name: /SNS World/ })).toBeVisible();
  expect((await state()).users[0].id).toBe(original);
  await page.goto(`${baseURL}/settings`);
  if (locale === "en-US") {
    await page.getByRole("textbox", { name: /Account name/ }).fill("Synthetic owner");
    await page.getByRole("button", { name: "Save account name", exact: true }).click();
    await expect.poll(async () => (await state()).users[0].name).toBe("Synthetic owner");
    await page.getByLabel("Name this Angmoo (optional)").fill("Synthetic installation");
    await page.getByRole("button", { name: "Save installation name", exact: true }).click();
    await expect.poll(async () => (await state()).installation_label).toBe("Synthetic installation");
    await page.getByRole("button", { name: /한국어|Korean/, exact: true }).click();
    await expect(page.getByRole("button", { name: /세션.*종료|세션 끝내기/ })).toBeVisible();
    expect((await state()).profiles[0].name).toBe("User");
    expect((await state()).users[0].name).toBe("Synthetic owner");
  }
  await expect(page.getByRole("button", { name: /End.*session|세션.*종료|세션 끝내기/i })).toBeVisible();
  await page.getByRole("button", { name: /End.*session|세션.*종료|세션 끝내기/i }).click();
  await expect(page.locator('[data-local-owner-state="stopped"]')).toBeVisible();
  await expect(other.locator('[data-local-owner-state="stopped"]')).toBeVisible();
  await page.reload(); await expect(page.locator('[data-local-owner-state="stopped"]')).toBeVisible();
  data = await state(); expect(data.users[0].id).toBe(original); expect(data.worlds).toHaveLength(1);
  const writes = data.requests.filter((r: { path: string; method: string }) => r.method === "POST" && r.path.endsWith("/session")).length;
  await other.reload(); await expect(other.locator('[data-local-owner-state="stopped"]')).toBeVisible();
  expect((await state()).requests.filter((r: { path: string; method: string }) => r.method === "POST" && r.path.endsWith("/session")).length).toBe(writes);
  await page.getByRole("button", { name: /Continue|다시 시작하기/ }).click();
  await expect(page.getByRole("link", { name: /SNS World/ })).toBeVisible();
  expect(new URL(page.url()).pathname).toBe("/");
  expect((await state()).users[0].id).toBe(original);
  expect(errors).toEqual([]);
  await context.close();
});

test("late issue and late stop cookies respect server generations", async ({ page, baseURL }, info) => {
  const isStatic = info.project.name === "static";
  await configure(page, isStatic); await page.goto(baseURL!);
  await expect(page.getByRole("link", { name: /SNS World/ })).toBeVisible();
  const endpoint = isStatic ? "http://127.0.0.1:3492/api/v1" : `${baseURL}/api/backend`;
  const call = (path: string, body?: unknown) => page.evaluate(async ({ endpoint, path, body, isStatic }) => {
    const response = await fetch(endpoint + path, { method: body ? "POST" : "GET", credentials: "include",
      headers: { "Content-Type": "application/json", ...(isStatic ? { "X-Angmoo-Launcher-Token": "synthetic-desktop-launch-token-000000000000", "X-Angmoo-Frontend-Origin": window.location.origin } : {}) },
      ...(body ? { body: JSON.stringify(body) } : {}) });
    return { status: response.status, data: await response.json() };
  }, { endpoint, path, body, isStatic });
  const hold = async (operation: string) => { await fetch(`http://127.0.0.1:3492/_test/hold/${operation}`, { method: "POST" }); };
  const release = async () => { await fetch("http://127.0.0.1:3492/_test/release", { method: "POST" }); };
  const original = (await state()).users[0].id;
  await hold("issue");
  const issued = call("/auth/local/session", (await state()).client_request);
  await expect.poll(async () => (await state()).gate_entered).toBe(true);
  expect((await call("/auth/local/client/stop", (await state()).client_request)).status).toBe(200);
  await release(); expect((await issued).status).toBe(200);
  expect((await call("/auth/me")).status).toBe(401); // late cookie is real but invalid
  expect((await call("/auth/local/client/resume", (await state()).client_request)).status).toBe(200);
  await hold("stop");
  const stopped = call("/auth/local/client/stop", (await state()).client_request);
  await expect.poll(async () => (await state()).gate_entered).toBe(true);
  expect((await call("/auth/local/client/resume", (await state()).client_request)).status).toBe(200);
  await release(); expect((await stopped).status).toBe(200);
  // Old deletion may clear the new cookie, but it cannot revert the resume.
  expect((await state()).clients[0].state).toBe("active");
  expect((await call("/auth/local/session", (await state()).client_request)).status).toBe(200);
  expect((await call("/auth/me")).data.id).toBe(original);
});

test("automatic entry connects real PNG registration and sequential activity/key settings", async ({ page, baseURL }, info) => {
  test.setTimeout(120_000);
  await configure(page, info.project.name === "static");
  await page.goto(baseURL!); await expect(page.getByRole("link", { name: /SNS World/ })).toBeVisible();
  const world = (await state()).worlds[0].id;
  await page.getByRole("link", { name: /SNS World/ }).click();
  await expect.poll(async () => (await state()).profiles.length).toBe(1);
  await page.goto(`${baseURL}/agents/new?worldId=${world}`);
  await page.getByRole("radio", { name: "Import SillyTavern character card", exact: true }).check();
  const card = Buffer.from(await (await fetch("http://127.0.0.1:3492/_test/card")).arrayBuffer());
  await page.getByLabel("Character card PNG or JSON", { exact: true }).setInputFiles({ name: "synthetic.png", mimeType: "image/png", buffer: card });
  await expect(page.getByRole("textbox", { name: "Name", exact: true })).toHaveValue("Synthetic Ian");
  for (let step=0; step<3; step++) await page.getByRole("button", { name: "Save and continue", exact: true }).click();
  await page.getByRole("button", { name: "Register", exact: true }).click();
  await expect.poll(async () => (await state()).registrations.length).toBe(1);
  await expect(page.getByRole("heading", { name: /Synthetic Ian/ }).first()).toBeVisible();
  const activity = page.getByRole("region", { name: "Activity settings", exact: true });
  const credential = page.getByRole("region", { name: "Character activity API key", exact: true });
  await expect(credential.getByLabel("New API key", { exact: true })).toBeVisible();
  await credential.getByLabel("New API key", { exact: true }).fill("synthetic-browser-key-not-a-real-credential");
  const interval = activity.locator('[name="activity_interval_minutes"]');
  await interval.fill(String(Number(await interval.inputValue()) + 30));
  await activity.getByRole("button", { name: "Save settings", exact: true }).click();
  await expect(activity.getByText("Settings saved.", { exact: true })).toBeVisible();
  await expect(credential.getByLabel("New API key", { exact: true })).toHaveValue("synthetic-browser-key-not-a-real-credential");
  await credential.getByRole("button", { name: "Save model", exact: true }).click();
  await expect(credential.getByText("Settings saved.", { exact: true })).toBeVisible();
  await expect(credential.getByRole("status").filter({ hasText: "API key saved" })).toBeVisible();
  const saved = await state();
  expect(saved.credentials).toEqual([{ purpose: "sns", revision: 1, has_key: true }]);
  expect(saved.requests.filter((r: { status: number }) => r.status === 500)).toEqual([]);
  expect(saved.registrations[0].autonomous_enabled).toBe(false);
  // A committed write with a lost response is not replayed or called successful.
  let loseNextWrite = true;
  await page.route("**/credentials/sns", async route => {
    if (route.request().method() === "PUT" && loseNextWrite) {
      loseNextWrite = false;
      const response = await route.fetch(); expect(response.status()).toBe(200);
      await route.abort("connectionreset"); return;
    }
    await route.fallback();
  });
  await credential.getByLabel("New API key", { exact: true }).fill("synthetic-replacement-with-lost-response");
  await credential.getByRole("button", { name: "Save model", exact: true }).click();
  await expect(credential.getByRole("alert")).toContainText(/could not be confirmed|Settings have changed/);
  await expect(credential.getByText("Settings saved.", { exact: true })).toHaveCount(0);
  await credential.getByRole("button", { name: "Reload settings", exact: true }).click();
  await expect(credential.getByLabel("New API key", { exact: true })).toHaveValue("synthetic-replacement-with-lost-response");
  expect((await state()).requests.filter((r: { path: string; method: string }) => r.path.endsWith("/credentials/sns") && r.method === "PUT")).toHaveLength(2);
  await credential.getByRole("button", { name: "Reviewed latest settings. Keep my inputs", exact: true }).click();
  // A deliberate blank model save preserves the key already committed by the server.
  await credential.getByLabel("New API key", { exact: true }).fill("");
  await credential.getByRole("button", { name: "Save model", exact: true }).click();
  await expect(credential.getByText("Settings saved.", { exact: true })).toBeVisible();
  saved.credentials = (await state()).credentials;
  await page.screenshot({ path: `../artifacts/local-entry-browser/${info.project.name}-registered-settings.png`, fullPage: true });
  await page.getByRole("button", { name: "Completed", exact: true }).click();
  const content = await installLocalContent(page, { owner: saved.users[0].id, world, profile: saved.profiles[0].id,
    character: saved.registrations[0].character_id, actor: saved.registrations[0].world_character_id });
  await page.goto(`${baseURL}/worlds/${world}/feed`);
  await expect(page.getByText("Pine trail plan", { exact: true })).toBeVisible();
  await page.goto(`${baseURL}/worlds/${world}/chat/${content.threadId}`);
  await page.getByPlaceholder("Write a message").fill("Good, remember our pine trail plan.");
  await page.getByRole("button", { name: /Send message|Send$/ }).click();
  await expect(page.getByText("I remember our plan to walk the pine trail.", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "View 2 evidence items", exact: true }).click();
  const dialog = page.locator("[data-world-chat-evidence-dialog]");
  await expect(dialog.getByRole("heading", { name: "Evidence for this response", exact: true })).toBeVisible();
  await expect(dialog).toContainText("Synthetic Ian");
  await expect(dialog).toContainText(content.text);
  await expect(dialog).not.toContainText("오늘 SNS 활동");
  await expect(dialog).not.toContainText("행동 주체");
  await page.keyboard.press("Escape");
  expect(content.fixture).toEqual({ sends: 1, streams: 1, evidenceReads: 1 });
  await page.goto(`${baseURL}/settings`);
  await page.getByRole("button", { name: /End.*session/i }).click();
  await expect(page.locator('[data-local-owner-state="stopped"]')).toBeVisible();
  await page.reload(); await expect(page.locator('[data-local-owner-state="stopped"]')).toBeVisible();
  await page.getByRole("button", { name: "Continue", exact: true }).click();
  await expect(page.getByRole("link", { name: /SNS World/ })).toBeVisible();
  expect(new URL(page.url()).pathname).toBe("/");
  expect((await state()).registrations).toEqual(saved.registrations);
  expect((await state()).credentials).toEqual(saved.credentials);
});
