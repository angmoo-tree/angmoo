import { expect, test } from "@playwright/test";

const backend = process.env.ANGMOO_CHARACTER_FIXTURE_API ?? "http://127.0.0.1:3356";
const A = "config-world-a", B = "config-world-b", ROLE_A = "config-role-a", ROLE_B = "config-role-b";
const basisKind = process.env.ANGMOO_CHARACTER_BASIS_KIND ?? "legacy_transition";
const evidenceName = (mode: string) => basisKind === "creation" ? `${mode}-creation` : mode;
type State = {
  characters: { id: string; name: string; personality: string; avatar_url: string | null }[];
  snapshots: { id: string; source_character_id: string; kind: string; digest: string; payload: { settings: { personality: string } } }[];
  origins: { character_id: string; snapshot_id: string }[];
  roles: { id: string; world_id: string; character_id: string; control_mode: string; autonomous_enabled: boolean; revision: number }[];
  configs: { id: string; profile: { display_name: string; intro: string; avatar_url: string | null }; settings: { personality: string } }[];
  runs: { id: string; character_id: string; status: string; input_snapshot: Record<string, unknown>; gateway_result: Record<string, unknown> }[];
};

test(`T102/T110/T118: actual API preserves ${basisKind} basis, independent edits, import and admitted input`, async ({ page, request }, info) => {
  await expect.poll(async () => (await request.get(`${backend}/__fixture__/health`).catch(() => null))?.ok(), { timeout: 90_000 }).toBe(true);
  const base = String(info.project.use.baseURL), origin = new URL(base).origin;
  const writes: { path: string; body: unknown }[] = [], unexpected: string[] = [], providerCalls: string[] = [];
  const headers = { "x-angmoo-frontend-origin": origin, Origin: origin };
  const state = async () => (await (await request.get(`${backend}/__fixture__/state`)).json()) as State;
  const before = await state();
  const basis = before.snapshots.find(row => row.source_character_id === "config-actor-a")!;
  expect(basis.kind).toBe(basisKind);
  expect(basis.payload.settings.personality).toBe("Original persona");
  const originalB = before.configs.find(row => row.id === ROLE_B)!;
  await page.route("**/*", async route => {
    const url = new URL(route.request().url());
    if (/^\/api\/(backend|v1)\//.test(url.pathname) || url.pathname.startsWith("/media/")) {
      const path = url.pathname.replace(/^\/api\/(backend|v1)/, "/api/v1");
      if (/generate|completion|preflight/.test(path)) { providerCalls.push(path); await route.abort("blockedbyclient"); return; }
      const method = route.request().method();
      if (!["GET", "HEAD"].includes(method)) writes.push({ path, body: route.request().postData() ? route.request().postDataJSON() : null });
      const response = await route.fetch({ url: `${backend}${path}${url.search}`,
        headers: { ...route.request().headers(), ...headers, "sec-fetch-site": "same-origin" } });
      if (response.status() >= 400) unexpected.push(`${path}:${response.status()}`);
      await route.fulfill({ response }); return;
    }
    await (url.origin === origin ? route.fallback() : route.abort("blockedbyclient"));
  });
  if (info.project.name === "static-export") await page.addInitScript(api => Object.assign(window, {
    __ANGMOO_RUNTIME_CONFIG__: { profile: "tauri-static", apiBaseUrl: api, graphProvider: "ladybug", launchToken: "fixture-static-token-0000000000" },
  }), backend);

  await page.goto(`/worlds/${A}/characters/${ROLE_A}?view=settings`);
  const settings = page.locator("[data-world-character-settings-form]");
  await expect(settings.locator('textarea[name="personality"]')).toHaveValue("Original persona");
  await settings.locator('textarea[name="personality"]').fill("Only World A persona");
  await settings.getByRole("button", { name: "설정 저장", exact: true }).click();
  await expect(settings.getByRole("status")).toHaveText("이 World의 설정을 저장했어요.");
  const afterA = await state();
  expect(afterA.configs.find(row => row.id === ROLE_A)!.settings.personality).toBe("Only World A persona");
  expect(afterA.configs.find(row => row.id === ROLE_B)).toEqual(originalB);
  expect(afterA.snapshots.find(row => row.id === basis.id)).toEqual(basis);
  expect(afterA.characters.find(row => row.id === "config-actor-a")!.personality).toBe("Original persona");

  await page.goto(`/agents/new?worldId=${B}&mode=copy`);
  await expect(page.getByText("새 World는 최초 생성 기준 또는 기존 캐릭터의 전환 기준으로 시작하며, 이후 수정은 이 World에만 적용됩니다.", { exact: true })).toBeVisible();
  await page.screenshot({ path: `../artifacts/world-character-configuration-api-20261005/${evidenceName(info.project.name)}-copy-basis-notice.png`, fullPage: true });
  await page.getByLabel("설정을 복사할 캐릭터", { exact: true }).selectOption("config-actor-a");
  await page.getByRole("button", { name: "저장하고 다음", exact: true }).click();
  await page.getByRole("textbox", { name: "이름", exact: true }).fill("Imported Bram");
  await page.getByLabel("핸들", { exact: true }).fill("imported_bram");
  await page.getByRole("button", { name: "저장하고 다음", exact: true }).click();
  await expect(page.getByLabel("성격", { exact: true })).toHaveValue("Original persona");
  await page.getByRole("button", { name: "저장하고 다음", exact: true }).click();
  await page.getByRole("button", { name: "저장하고 다음", exact: true }).click();
  await page.getByRole("button", { name: "자율활동 OFF로 등록", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Imported Bram 등록 완료", exact: true })).toBeVisible();
  const imported = await state();
  const copied = imported.roles.find(row => row.world_id === B && !before.roles.some(old => old.id === row.id))!;
  expect(copied.character_id).not.toBe("config-actor-a");
  expect(copied.autonomous_enabled).toBe(false);
  expect(imported.origins.find(row => row.character_id === copied.character_id)!.snapshot_id).toBe(basis.id);
  expect(imported.configs.find(row => row.id === copied.id)!.settings.personality).toBe("Original persona");
  expect(imported.configs.find(row => row.id === ROLE_B)).toEqual(originalB);
  expect(writes.some(write => /\/drafts\/[^/]+\/copy-settings$/.test(write.path))).toBe(true);
  expect(writes.some(write => /\/drafts\/[^/]+\/complete$/.test(write.path))).toBe(true);

  await page.goto(`/worlds/${B}/characters/${copied.id}?view=settings`);
  await expect(settings.locator('textarea[name="personality"]')).toHaveValue("Original persona");
  await settings.locator('textarea[name="personality"]').fill("Only World B persona");
  await settings.getByRole("button", { name: "설정 저장", exact: true }).click();
  await expect(settings.getByRole("status")).toHaveText("이 World의 설정을 저장했어요.");
  // Keyless registration stays OFF; the controlled fixture supplies a synthetic
  // credential/readiness record before exercising the real admission path.
  expect((await request.post(`${backend}/__fixture__/prepare/${copied.character_id}`)).ok()).toBe(true);
  await page.goto(`/worlds/${A}/characters`);
  await page.locator(`[data-world-character-id="${ROLE_A}"]`).getByRole("button", { name: /자율활동 켜기$/ }).click();
  await expect(page.locator(`[data-world-character-id="${ROLE_A}"]`)).toHaveAttribute("data-character-autonomy-state", "on");
  await expect.poll(async () => (await state()).roles.find(row => row.id === ROLE_A)!.autonomous_enabled).toBe(true);
  await page.goto(`/worlds/${B}/characters`);
  await page.locator(`[data-world-character-id="${copied.id}"]`).getByRole("button", { name: /자율활동 켜기$/ }).click();
  await expect(page.locator(`[data-world-character-id="${copied.id}"]`)).toHaveAttribute("data-character-autonomy-state", "on");
  await expect.poll(async () => (await state()).roles.filter(row => [ROLE_A, copied.id].includes(row.id)).every(row => row.autonomous_enabled)).toBe(true);
  const bothOn = await state();
  expect(bothOn.roles.find(row => row.id === ROLE_A)!.autonomous_enabled).toBe(true);
  expect(bothOn.roles.find(row => row.id === copied.id)!.autonomous_enabled).toBe(true);
  await page.goto(`/worlds/${A}/characters`);
  await page.locator(`[data-world-character-id="${ROLE_A}"]`).getByRole("button", { name: /자율활동 끄기$/ }).click();
  await expect(page.locator(`[data-world-character-id="${ROLE_A}"]`)).toHaveAttribute("data-character-autonomy-state", "off");
  await expect.poll(async () => (await state()).roles.find(row => row.id === ROLE_A)!.autonomous_enabled).toBe(false);
  const afterOff = await state();
  expect(afterOff.roles.find(row => row.id === ROLE_A)!.autonomous_enabled).toBe(false);
  expect(afterOff.roles.find(row => row.id === copied.id)!.autonomous_enabled).toBe(true);
  await page.goto(`/worlds/${B}/characters/${copied.id}?view=status`);
  await page.getByRole("button", { name: "지금 한 번 활동", exact: true }).click();
  await expect(page.getByText("이 World의 활동이 완료되었어요.", { exact: true })).toBeVisible();
  await page.screenshot({ path: `../artifacts/world-character-configuration-api-20261005/${evidenceName(info.project.name)}-admitted-world-run.png`, fullPage: true });
  const afterRun = await state();
  const run = afterRun.runs.find(row => row.character_id === copied.character_id)!;
  expect(run.status).toBe("completed");
  expect(JSON.stringify(run.input_snapshot)).toContain("Only World B persona");
  expect(JSON.stringify(run.input_snapshot)).toContain(copied.id);
  expect(JSON.stringify(run.input_snapshot)).not.toContain("Only World A persona");
  expect(run.gateway_result.provider_call_count).toBe(0);
  expect(run.gateway_result.public_write_count).toBe(0);
  expect(afterRun.roles.find(row => row.id === ROLE_A)!.autonomous_enabled).toBe(false);
  expect(afterRun.roles.find(row => row.id === copied.id)!.autonomous_enabled).toBe(true);
  expect(afterRun.snapshots.find(row => row.id === basis.id)).toEqual(basis);
  const outsider = await request.get(`${backend}/api/v1/worlds/${A}/world-characters/${ROLE_A}/settings`, { headers: { ...headers, "x-fixture-user": "outsider" } });
  expect(outsider.status()).toBe(403);
  const unsafe = await request.patch(`${backend}/api/v1/worlds/${A}/world-characters/${ROLE_A}/profile`, {
    headers: { ...headers, Origin: "https://untrusted.invalid" }, data: { expected_revision: 1, intro: "forbidden" },
  });
  expect(unsafe.status()).toBe(403);
  expect(providerCalls).toEqual([]);
  expect(unexpected).toEqual([]);
});

test("T64/T76/T88: actual World profile media, user profile, canonical graph avatars and Chat entry", async ({ page, request }, info) => {
  await expect.poll(async () => (await request.get(`${backend}/__fixture__/health`).catch(() => null))?.ok(), { timeout: 90_000 }).toBe(true);
  const base = String(info.project.use.baseURL), origin = new URL(base).origin;
  const headers = { "x-angmoo-frontend-origin": origin, Origin: origin };
  const state = async () => (await (await request.get(`${backend}/__fixture__/state`)).json()) as State;
  const before = await state(), user = before.roles.find(role => role.world_id === A && role.control_mode === "owner_controlled")!;
  const beforeB = before.configs.filter(config => before.roles.some(role => role.id === config.id && role.world_id === B));
  const errors: string[] = [], graphReads: Record<string, unknown>[] = [], writes: string[] = [];
  const chatThreads: { responding: { avatar_url: string | null }; requester: { display_name: string } }[] = [];
  const profileWrites: { path: string; body: Record<string, unknown> }[] = [];
  await page.route("**/*", async route => {
    const url = new URL(route.request().url());
    if (/^\/api\/(backend|v1)\//.test(url.pathname) || url.pathname.startsWith("/media/")) {
      const path = url.pathname.replace(/^\/api\/(backend|v1)/, "/api/v1");
      if (/generate|completion|preflight/.test(path)) { errors.push(`provider:${path}`); await route.abort("blockedbyclient"); return; }
      if (!["GET", "HEAD"].includes(route.request().method())) writes.push(path);
      if (path.endsWith("/profile") && route.request().method() === "PATCH") profileWrites.push({ path, body: route.request().postDataJSON() });
      const response = await route.fetch({ url: `${backend}${path}${url.search}`, headers: { ...route.request().headers(), ...headers, "sec-fetch-site": "same-origin" } });
      if (response.status() >= 400) errors.push(`${path}:${response.status()}`);
      if (path.endsWith("/relationship-graph") && response.ok()) graphReads.push(await response.json());
      if (path.endsWith("/chat/threads") && route.request().method() === "POST" && response.ok()) chatThreads.push((await response.json()).thread);
      await route.fulfill({ response }); return;
    }
    await (url.origin === origin ? route.fallback() : route.abort("blockedbyclient"));
  });
  if (info.project.name === "static-export") await page.addInitScript(api => Object.assign(window, {
    __ANGMOO_RUNTIME_CONFIG__: { profile: "tauri-static", apiBaseUrl: api, graphProvider: "ladybug", launchToken: "fixture-static-token-0000000000" },
  }), backend);

  await page.goto(`/worlds/${A}/characters/${ROLE_A}`);
  const profile = page.locator('[data-world-character-surface="profile"]');
  await expect(profile.locator('[data-profile-action="relationships"]')).toBeVisible();
  await profile.locator('[data-profile-action="edit"]').click();
  const editor = page.locator("[data-world-character-profile-editor]");
  // A synthetic browser-owned image passes the existing cropper and actual
  // scoped file/CAS storage. No user asset, generated image, or upload DTO mock.
  const png = await page.evaluate(() => {
    const canvas = document.createElement("canvas"); canvas.width = canvas.height = 64;
    const ctx = canvas.getContext("2d")!; ctx.fillStyle = "#72bdac"; ctx.fillRect(0, 0, 64, 64);
    ctx.fillStyle = "#19342d"; ctx.beginPath(); ctx.arc(32, 32, 17, 0, Math.PI * 2); ctx.fill();
    return canvas.toDataURL("image/png").split(",")[1];
  });
  await editor.locator('input[type="file"]').last().setInputFiles({ name: "synthetic-profile.png", mimeType: "image/png", buffer: Buffer.from(png, "base64") });
  await expect(page.getByRole("heading", { name: "아바타 자르기", exact: true })).toBeVisible();
  await page.getByRole("button", { name: "저장", exact: true }).click();
  await expect(page.getByRole("heading", { name: "아바타 자르기", exact: true })).toHaveCount(0);
  await editor.locator('textarea[name="intro"]').fill("Only World A profile introduction");
  await editor.getByRole("button", { name: "프로필 저장", exact: true }).click();
  await expect(editor).toBeHidden();
  await expect(profile).toContainText("Only World A profile introduction");
  await expect(profile.locator("img")).toBeVisible();
  await expect.poll(() => profile.locator("img").evaluate(image => (image as HTMLImageElement).naturalWidth)).toBeGreaterThan(0);
  const afterProfile = await state(), aProfile = afterProfile.configs.find(config => config.id === ROLE_A)!.profile;
  expect(aProfile.avatar_url).toMatch(/^\/media\/characters\/config-actor-a\/avatar-/);
  expect(afterProfile.characters.find(character => character.id === "config-actor-a")!.avatar_url).toBeNull();
  expect(afterProfile.configs.filter(config => before.roles.some(role => role.id === config.id && role.world_id === B))).toEqual(beforeB);
  expect(afterProfile.snapshots).toEqual(before.snapshots);
  await profile.locator('[data-profile-action="relationships"]').click();
  await expect(page).toHaveURL(new RegExp(`/characters/config-actor-a/worlds/${A}/relationship-graph/?$`));
  const graph = page.locator('[data-product-content="relationship-graph"]');
  await expect(graph.locator("[data-relationship-node]")).toHaveCount(2);
  await expect(graph.locator(`[data-relationship-node="${ROLE_A}"] img`)).toBeVisible();
  await expect.poll(() => graph.locator(`[data-relationship-node="${ROLE_A}"] img`).evaluate(image => (image as HTMLImageElement).naturalWidth)).toBeGreaterThan(0);
  await expect(graph.locator(`[data-relationship-node="${user.id}"]`)).toContainText("사");
  await expect(graph.locator("path[marker-end]")).toHaveCount(1);
  expect(graphReads.length).toBeGreaterThan(0);
  // React's development effect replay can issue a second read. Validate every
  // actual response rather than treating harmless repeat GETs as mutations.
  for (const response of graphReads) {
    const graphRead = response as { meta: { source: string }; nodes: { world_character_id: string; avatar_url: string | null }[] };
    expect(graphRead.meta.source).toBe("canonical_fallback");
    expect(graphRead.nodes.find(node => node.world_character_id === ROLE_A)!.avatar_url).toBe(aProfile.avatar_url);
  }
  await page.setViewportSize({ width: 960, height: 1660 });
  await graph.locator(`[data-relationship-node="${ROLE_A}"]`).scrollIntoViewIfNeeded();
  await expect(graph.locator(`[data-relationship-node="${ROLE_A}"] img`)).toBeInViewport();
  await page.screenshot({ path: `../artifacts/world-character-configuration-api-20261005/${evidenceName(info.project.name)}-actual-avatar-graph.png`, fullPage: true });

  await page.goto(`/worlds/${A}/characters/${user.id}`);
  await profile.locator('[data-profile-action="edit"]').click();
  await editor.locator('textarea[name="intro"]').fill("Only World A user introduction");
  await editor.getByRole("button", { name: "프로필 저장", exact: true }).click();
  await expect(editor).toBeHidden(); await expect(profile).toContainText("Only World A user introduction");
  await expect(page.locator("[data-world-character-management]").getByRole("button", { name: "지금 한 번 활동", exact: true })).toHaveCount(0);
  await page.goto(`/worlds/${A}/characters/${ROLE_A}`);
  await expect(profile.locator('[data-profile-action="mail"]')).toBeEnabled();
  await profile.locator('[data-profile-action="mail"]').click();
  await expect(page).toHaveURL(new RegExp(`/worlds/${A}/chat/[^/]+/?$`));
  await expect(page.locator('[data-world-chat-surface="thread"]')).toBeVisible();
  expect(chatThreads).toHaveLength(1);
  expect(chatThreads[0].responding.avatar_url).toBe(aProfile.avatar_url);
  expect(writes.some(path => path.endsWith(`/${ROLE_A}/profile/media`))).toBe(true);
  expect(writes.some(path => path.endsWith(`/${user.id}/profile`))).toBe(true);
  expect(Object.keys(profileWrites.find(write => write.path.endsWith(`/${user.id}/profile`))!.body).sort()).toEqual(["expected_revision", "intro"]);
  expect(writes.some(path => path.endsWith("/chat/threads"))).toBe(true);
  const after = await state(); expect(after.snapshots).toEqual(before.snapshots);
  expect(after.configs.filter(config => before.roles.some(role => role.id === config.id && role.world_id === B))).toEqual(beforeB);
  expect(errors).toEqual([]);
});
