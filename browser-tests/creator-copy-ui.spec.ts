import { verifyCreatorResponsive } from "./creator-copy-responsive";
import { expect, test, type Page } from "@playwright/test";
import { readFileSync, writeFileSync } from "node:fs";
import { installIntegrationFixture } from "./home-activity-memory-fixture";
import { FEED_WORLD } from "./world-feed-fixture";
import { WORLD_AGENT } from "./world-character-management-fixture";

async function studio(page: Page, staticShell: boolean, baseURL: string, language: "ko" | "en") {
  const base = await installIntegrationFixture(page, staticShell, baseURL, language);
  const world = { id: FEED_WORLD, slug: "fixture-world", name: "Draft World", tagline: "A small synthetic town",
    setting_description: "A small town where synthetic characters exchange stories.", daily_life_description: "Characters read and share their ordinary days.",
    genre_tags: ["Everyday"], tone_tags: [], timezone: "Asia/Seoul", language: "ko", visibility: "private", join_policy: "private",
    additional_generation_guidance: "", places: [], roles: [], daypart_profiles: [], rules: [], glossary: [], banner_media_id: null as string | null, icon_media_id: null as string | null,
    banner_alt_text: "", status: "draft", definition_version: 1, row_version: 1, contract_version: "world-v1", contract_hash: "a".repeat(64),
    readiness_status: "publish_ready", created_at: "2026-10-10T00:00:00Z", updated_at: "2026-10-10T00:00:00Z", archived_at: null };
  const context = () => ({ world, membership_role: "owner", readiness: { world_id: world.id, definition_version: 1, row_version: world.row_version,
    contract_version: "world-v1", contract_hash: world.contract_hash, required_fields: {}, optional_setting_count: 0, quality_tier: "CORE", issues: [], ready_for_publish: true, evaluated_at: world.updated_at } });
  const state = { world, base, writes: [] as { path: string; body: any }[], imageFailure: 0 };
  const handler = async (route: any) => {
    const request = route.request(), path = new URL(request.url()).pathname.replace(/^\/api\/(backend|v1)/, ""), method = request.method();
    if (path === `/worlds/${FEED_WORLD}/creator-context`) return route.fulfill({ json: context() });
    if (path === `/worlds/${FEED_WORLD}/readiness` || path === `/worlds/${FEED_WORLD}/validate`) return route.fulfill({ json: context().readiness });
    if ([`/worlds/${FEED_WORLD}`, `/worlds/${FEED_WORLD}/icon`, `/worlds/${FEED_WORLD}/banner`].includes(path) && method !== "GET") {
      const body = request.postDataJSON(); state.writes.push({ path, body }); expect(body.row_version).toBe(world.row_version);
      if (/\/(icon|banner)$/.test(path)) {
        if (state.imageFailure) return route.fulfill({ status: state.imageFailure, json: { detail: "world_row_version_conflict" } });
        const kind = path.endsWith("/icon") ? "icon" : "banner";
        world[`${kind}_media_id`] = method === "DELETE" ? null : `/api/v1/media/assets/synthetic-${kind}/content`;
        world.row_version++;
        return route.fulfill({ json: context() });
      }
      Object.assign(world, body, { row_version: world.row_version + 1 }); return route.fulfill({ json: context() });
    }
    return route.fallback();
  };
  await page.route("**/api/backend/**", handler); await page.route("http://127.0.0.1:8080/api/v1/**", handler);
  return state;
}

for (const language of ["ko", "en"] as const) {
  const en = language === "en";
  const catalog = { ...JSON.parse(readFileSync(`../frontend/src/features/worlds/locales/${language}.json`, "utf8")), ...JSON.parse(readFileSync(`../frontend/src/features/characters/locales/${language}.json`, "utf8")) };
  const t = (key: string) => catalog[key] ?? key;
  test(`single column preview preserves banner and draft controls ${language}`, async ({ page }, info) => {
    const state = await studio(page, info.project.name !== "next", String(info.project.use.baseURL), language);
    await page.goto(`/studio/worlds/${FEED_WORLD}`);
    const previews = page.locator("[data-world-image-previews]"); await expect(previews).toBeVisible();
    const form = page.locator("section").filter({ has: page.getByRole("heading", { name: t("필수 세계관 설정"), exact: true }) }).last();
    await form.getByLabel(new RegExp(`^${t("World 이름")}`)).fill("Very long World name ".repeat(4));
    await form.getByLabel(new RegExp(`^${t("한 줄 소개")}`)).fill("A long introduction with ordinary spaces ".repeat(5));
    await form.getByLabel(new RegExp(`^${t("장르 태그")}`)).fill("Everyday,Adventure,Mystery"); await form.getByLabel(new RegExp(`^${t("장르 태그")}`)).blur();
    for (const width of [360, 390, 768, 1440, 768]) {
      await page.setViewportSize({ width, height: 900 });
      const boxes = await previews.evaluate(element => [element, ...element.children].map(node => { const box = node.getBoundingClientRect(); return { x: box.x, y: box.y, width: box.width, bottom: box.bottom }; }));
      expect(boxes[2].y).toBeGreaterThanOrEqual(boxes[1].bottom + 20);
      expect(Math.abs(boxes[2].width - boxes[0].width)).toBeLessThanOrEqual(2);
      expect(Math.abs(boxes[2].x - boxes[0].x)).toBeLessThanOrEqual(1);
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBe(true);
      const banner = previews.locator("[data-world-banner]"); await expect(banner).toHaveAttribute("data-world-banner", "default");
      const box = (await banner.boundingBox())!; expect(Math.abs(box.height - Math.min(280, Math.max(160, width * .27)))).toBeLessThanOrEqual(2);
      await expect(banner.locator("img")).toHaveAttribute("src", /world-default-banner\.svg/);
      await expect(previews.getByText("Adventure", { exact: true })).toBeVisible();
      await previews.scrollIntoViewIfNeeded(); await page.screenshot({ path: info.outputPath(`column-${language}-${width}.png`) });
    }
    await expect(previews.getByRole("button", { name: t("아이콘 업로드"), exact: true })).toBeEnabled(); await expect(previews.getByRole("button", { name: t("배너 업로드"), exact: true })).toBeEnabled();
    expect(state.writes).toEqual([]);
  });
  test(`single column preview registered and failed banner ${language}`, async ({ page }, info) => {
    const state = await studio(page, info.project.name !== "next", String(info.project.use.baseURL), language);
    state.world.banner_media_id = "/api/v1/media/assets/synthetic-banner/content";
    const image = Buffer.from(await page.evaluate(() => { const canvas = document.createElement("canvas"); canvas.width = 16; canvas.height = 8; const ctx = canvas.getContext("2d")!; ctx.fillStyle = "#809e92"; ctx.fillRect(0, 0, 16, 8); return canvas.toDataURL("image/png").split(",")[1]; }), "base64");
    await page.route("**/media/assets/synthetic-banner/content", route => route.fulfill({ contentType: "image/png", body: image }));
    await page.goto(`/studio/worlds/${FEED_WORLD}`);
    const previews = page.locator("[data-world-image-previews]");
    const banner = previews.locator("[data-world-banner]");
    await expect(banner).toHaveAttribute("data-world-banner", "registered");
    for (const width of [360, 390, 768, 1440]) {
      await page.setViewportSize({ width, height: 900 });
      const boxes = await previews.evaluate(element => [element, ...element.children].map(node => { const box = node.getBoundingClientRect(); return { y: box.y, width: box.width, bottom: box.bottom }; }));
      expect(boxes[2].y).toBeGreaterThanOrEqual(boxes[1].bottom + 20);
      expect(Math.abs(boxes[2].width - boxes[0].width)).toBeLessThanOrEqual(2);
      await expect(banner.locator("img")).toHaveCSS("object-fit", "cover");
    }
    state.world.banner_media_id = "/api/v1/media/assets/failed-banner/content";
    await page.route("**/media/assets/failed-banner/content", route => route.fulfill({ status: 404 }));
    await page.reload();
    await expect(banner).toHaveAttribute("data-world-banner", "default");
    await expect(banner.locator("img")).toHaveAttribute("src", /world-default-banner\.svg/);
    expect(state.writes).toEqual([]);
  });
  test(`World crop file size boundaries ${language}`, async ({ page }, info) => {
    const state = await studio(page, info.project.name !== "next", String(info.project.use.baseURL), language);
    await page.goto(`/studio/worlds/${FEED_WORLD}`);
    const input = page.getByLabel(t("아이콘 업로드"), { exact: true }), dialog = page.getByRole("dialog");
    function photo(size: number) {
      const image = readFileSync("fixtures/photos/normal.jpg"), comments: Buffer[] = []; let extra = size - image.length;
      while (extra) { const length = Math.min(extra, 65537), part = Buffer.alloc(length); part[0] = 255; part[1] = 254; part.writeUInt16BE(length - 2, 2); comments.push(part); extra -= length; }
      return Buffer.concat([image.subarray(0, 2), ...comments, image.subarray(2)]);
    }
    for (const size of [5242879, 5242880]) {
      await input.setInputFiles({ name: "bounded.jpg", mimeType: "image/jpeg", buffer: photo(size) });
      await expect(dialog).toBeVisible(); expect(state.writes).toEqual([]);
      await dialog.getByRole("button", { name: en ? "Cancel" : "취소", exact: true }).click();
      await expect(dialog).toHaveCount(0);
    }
    await input.setInputFiles({ name: "too-large.jpg", mimeType: "image/jpeg", buffer: photo(5242881) });
    await expect(page.getByText(t("이미지는 5MB 이하로 선택해주세요."), { exact: true })).toBeVisible();
    await expect(dialog).toHaveCount(0); expect(state.writes).toEqual([]);
  });
  test(`package export keeps confirmations, preview and delivery ${language}`, async ({ page }, info) => {
    await studio(page, info.project.name !== "next", String(info.project.use.baseURL), language);
    const strings = JSON.parse(readFileSync(`../frontend/src/features/world-packages/locales/${language}.json`, "utf8"));
    const pt = (key: string) => strings[key] ?? key;
    const writes: { path: string; body: unknown; token?: string }[] = [];
    const preview = { source_world_id: FEED_WORLD, package_id: "internal-package-id", package_version: 765432,
      seed_digest: "d".repeat(64), recommended_filename: "synthetic.angmoo-world", included_autonomous_characters: 2,
      excluded_owner_controlled_characters: 1, included_assets: 2, excluded_external_assets: 1,
      warnings: ["internal_warning_code"], license: { expression: "CC-BY-4.0", attribution: "Original Author", source_url: null, license_text_path: null } };
    const handler = async (route: any) => {
      const request = route.request(), path = new URL(request.url()).pathname.replace(/^\/api\/(backend|v1)/, "");
      if (path === `/worlds/${FEED_WORLD}/package-exports/preview`) {
        writes.push({ path, body: request.postDataJSON() }); return route.fulfill({ json: preview });
      }
      if (path === `/worlds/${FEED_WORLD}/package-exports`) {
        writes.push({ path, body: request.postDataJSON() });
        return route.fulfill({ json: { operation_id: "synthetic-export", download_token: "synthetic-download-token",
          download_path: "/api/v1/world-package-exports/synthetic-export/download", expires_at: "2026-10-11T00:00:00Z",
          preview, manifest_digest: "m".repeat(64), archive_digest: "a".repeat(64), archive_bytes: 16, replayed_request: false } });
      }
      if (path === "/world-package-exports/synthetic-export/download") {
        writes.push({ path, body: null, token: request.headers()["x-world-package-download-token"] });
        return route.fulfill({ body: Buffer.from("synthetic-export"), contentType: "application/octet-stream" });
      }
      return route.fallback();
    };
    await page.route("**/api/backend/**", handler); await page.route("http://127.0.0.1:8080/api/v1/**", handler);
    await page.goto(`/studio/worlds/${FEED_WORLD}`);
    const panel = page.locator("section").filter({ has: page.getByRole("heading", { name: pt("Package 내보내기"), exact: true }) }).last();
    const inspect = panel.getByRole("button", { name: pt("포함 내용 확인"), exact: true });
    const download = panel.getByRole("button", { name: pt("Package 다운로드"), exact: true });
    await expect(inspect).toBeDisabled(); await expect(download).toBeDisabled();
    for (const checkbox of await panel.getByRole("checkbox").all()) await checkbox.check();
    await panel.getByLabel(pt("저작자 표시"), { exact: true }).fill("Original Author");
    expect(writes).toEqual([]); await inspect.click(); await expect(download).toBeEnabled();
    await expect(panel).not.toContainText("765432"); await expect(panel).not.toContainText("internal_warning_code");
    expect(writes[0].body).toMatchObject({ confirm_export_rights: true, confirm_license: true, confirm_exclusions: true, attribution: "Original Author" });
    await panel.getByLabel(pt("저작자 표시"), { exact: true }).fill("Changed Author");
    await expect(download).toBeDisabled(); await inspect.click();
    const delivered = page.waitForEvent("download"); await download.click();
    expect((await delivered).suggestedFilename()).toBe("synthetic.angmoo-world");
    await expect(panel.getByRole("status")).toContainText(pt("World 패키지를 내보냈어요. ({{size}})").replace("{{size}}", "16 B"));
    expect(writes.at(-1)).toMatchObject({ path: "/world-package-exports/synthetic-export/download", token: "synthetic-download-token" });
  });
  test(`studio draft metadata eight combinations and readiness ${language}`, async ({ page }, info) => {
    const state = await studio(page, info.project.name !== "next", String(info.project.use.baseURL), language);
    await page.goto(`/studio/worlds/${FEED_WORLD}`);
    const previews = page.locator("[data-world-image-previews]"); await expect(previews).toBeVisible();
    const form = page.locator("section").filter({ has: page.getByRole("heading", { name: t("필수 세계관 설정"), exact: true }) }).last();
    const name = form.getByLabel(new RegExp(`^${t("World 이름")}`));
    const intro = form.getByLabel(new RegExp(`^${t("한 줄 소개")}`));
    const tags = form.getByLabel(new RegExp(`^${t("장르 태그")}`));
    for (let mask = 0; mask < 8; mask++) {
      await name.fill(mask & 1 ? "Visible name" : "  "); await intro.fill(mask & 2 ? "Visible introduction" : "  ");
      await tags.fill(mask & 4 ? "Visible tag" : ""); await tags.blur();
      await expect(previews.locator("h4")).toHaveCount(mask & 1 ? 1 : 0);
      await expect(previews.getByText("Visible introduction", { exact: true })).toHaveCount(mask & 2 ? 1 : 0);
      await expect(previews.getByText("Visible tag", { exact: true })).toHaveCount(mask & 4 ? 1 : 0);
    }
    await page.getByRole("button", { name: t("공개 준비 확인"), exact: true }).click();
    expect(state.writes).toEqual([]);
    await expect(page.getByText(en ? "0 optional sections completed" : "선택 항목 0개 작성됨", { exact: true })).toBeVisible();
    for (const width of [480, 1024, 1440]) {
      await page.setViewportSize({ width, height: 900 }); expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBe(true);
      await previews.scrollIntoViewIfNeeded();
      await page.screenshot({ path: info.outputPath(`studio-${language}-${width}.png`) });
    }
  });

  test(`world crop cancel, dimensions, conflict retention and latest revision ${language}`, async ({ page }, info) => {
    const state = await studio(page, info.project.name !== "next", String(info.project.use.baseURL), language);
    await page.goto(`/studio/worlds/${FEED_WORLD}`);
    const original = readFileSync("fixtures/photos/normal.jpg");
    const inputs = [page.getByLabel(t("아이콘 업로드"), { exact: true }), page.getByLabel(t("배너 업로드"), { exact: true })];
    const beforeUrl = page.url();
    const originalName = "Unsaved World name";
    const name = page.getByLabel(new RegExp(`^${t("World 이름")}`)); await name.fill(originalName);
    const chooserPromise = page.waitForEvent("filechooser");
    const upload = page.getByRole("button", { name: t("아이콘 업로드"), exact: true });
    await upload.focus(); await page.keyboard.press("Enter");
    const chooser = await chooserPromise;
    await chooser.setFiles({ name: "crop.jpg", mimeType: "image/jpeg", buffer: original });
    const dialog = page.getByRole("dialog");
    await expect(dialog).toBeVisible(); expect(state.writes).toEqual([]);
    expect(page.url()).toBe(beforeUrl); await expect(name).toHaveValue(originalName);
    await dialog.getByRole("button", { name: en ? "Cancel" : "취소", exact: true }).click();
    await expect(dialog).toHaveCount(0); expect(state.writes).toEqual([]);
    for (const [index, kind, width, height] of [[0, "icon", 768, 768], [1, "banner", 1024, 384]] as const) {
      await inputs[index].setInputFiles({ name: "crop.jpg", mimeType: "image/jpeg", buffer: original }); await expect(dialog).toBeVisible();
      const slider = dialog.getByLabel(t("확대"), { exact: true }); await slider.fill("2");
      const preview = await dialog.locator("canvas").evaluate((canvas: HTMLCanvasElement) => [...canvas.getContext("2d")!.getImageData(20,20,1,1).data]);
      state.imageFailure = 409; await dialog.getByRole("button", { name: en ? "Apply" : "적용", exact: true }).click();
      await expect(dialog.getByRole("alert")).toBeVisible(); await expect(slider).toHaveValue("2"); await expect(dialog).toBeVisible();
      state.imageFailure = 0; await dialog.getByRole("button", { name: t("현재 이미지 상태 새로고침"), exact: true }).click();
      await expect(dialog.getByRole("alert")).toHaveCount(0); await expect(slider).toHaveValue("2");
      await dialog.getByRole("button", { name: en ? "Apply" : "적용", exact: true }).click(); await expect(dialog).toHaveCount(0);
      const body = state.writes.at(-1)!.body; expect(body.content_type).toBe("image/webp");
      const pixels = await page.evaluate(async ({ data, mime }) => { const bytes = Uint8Array.from(atob(data), x => x.charCodeAt(0)); const image = await createImageBitmap(new Blob([bytes], { type: mime }));
        const canvas = document.createElement("canvas"); canvas.width=image.width; canvas.height=image.height; const c=canvas.getContext("2d")!; c.drawImage(image,0,0);
        const result={width:image.width,height:image.height,corner:[...c.getImageData(20,20,1,1).data]}; image.close(); return result; }, { data: body.data_base64, mime: body.content_type });
      expect(pixels).toMatchObject({ width, height }); expect(Math.abs(pixels.corner[0] - preview[0])).toBeLessThan(10);
      expect(state.writes.at(-1)!.path).toBe(`/worlds/${FEED_WORLD}/${kind}`);
      writeFileSync(info.outputPath(`${kind}.webp`), Buffer.from(body.data_base64, "base64"));
    }
    expect(page.url()).toBe(beforeUrl); await expect(name).toHaveValue(originalName);
    expect(state.writes).toHaveLength(4);
    await inputs[0].setInputFiles({ name: "too-large.jpg", mimeType: "image/jpeg", buffer: Buffer.alloc(5 * 1024 * 1024 + 1) });
    await expect(dialog).toHaveCount(0); expect(state.writes).toHaveLength(4);
  });

  test(`World image transport failure and removal preserve unsaved definition ${language}`, async ({ page }, info) => {
    const state = await studio(page, info.project.name !== "next", String(info.project.use.baseURL), language);
    state.world.icon_media_id = "/api/v1/media/assets/synthetic-icon/content";
    state.world.banner_media_id = "/api/v1/media/assets/synthetic-banner/content";
    await page.route("**/media/assets/synthetic-*/content", route => route.fulfill({ contentType: "image/jpeg", body: readFileSync("fixtures/photos/normal.jpg") }));
    await page.goto(`/studio/worlds/${FEED_WORLD}`);
    const beforeUrl = page.url(), previews = page.locator("[data-world-image-previews]");
    const form = page.locator("section").filter({ has: page.getByRole("heading", { name: t("필수 세계관 설정"), exact: true }) }).last();
    const name = form.getByLabel(new RegExp(`^${t("World 이름")}`));
    const intro = form.getByLabel(new RegExp(`^${t("한 줄 소개")}`));
    await name.fill("Retained unsaved name"); await intro.fill("Retained unsaved introduction");
    await page.getByLabel(t("아이콘 업로드"), { exact: true }).setInputFiles("fixtures/photos/normal.jpg");
    const dialog = page.getByRole("dialog"), apply = dialog.getByRole("button", { name: en ? "Apply" : "적용", exact: true });
    await expect(dialog).toBeVisible(); await dialog.getByLabel(t("확대"), { exact: true }).fill("2");
    state.imageFailure = 500; await apply.click();
    await expect(dialog.getByRole("alert")).toBeVisible(); await expect(dialog.getByLabel(t("확대"), { exact: true })).toHaveValue("2");
    await expect(previews.getByRole("button", { name: t("아이콘 제거"), exact: true })).toBeVisible();
    await expect(name).toHaveValue("Retained unsaved name"); await expect(intro).toHaveValue("Retained unsaved introduction");
    await dialog.getByRole("button", { name: en ? "Cancel" : "취소", exact: true }).click();
    state.imageFailure = 0;
    for (const kind of ["icon", "banner"] as const) {
      const remove = previews.getByRole("button", { name: t(kind === "icon" ? "아이콘 제거" : "배너 제거"), exact: true });
      await remove.click(); await expect(remove).toHaveCount(0);
      expect(state.writes.at(-1)).toMatchObject({ path: `/worlds/${FEED_WORLD}/${kind}`, body: { row_version: kind === "icon" ? 1 : 2 } });
      await expect(name).toHaveValue("Retained unsaved name"); await expect(intro).toHaveValue("Retained unsaved introduction");
      expect(page.url()).toBe(beforeUrl);
    }
    await expect(previews.locator("[data-world-banner]")).toHaveAttribute("data-world-banner", "default");
    expect(state.writes).toHaveLength(3); // Failed apply and two image-only removals; no draft write.
  });

  test(`World image pending apply cannot leak across runtime scope ${language}`, async ({ page }, info) => {
    const state = await studio(page, info.project.name !== "next", String(info.project.use.baseURL), language);
    const requests: string[] = []; let release!: () => void;
    const blocked = new Promise<void>(resolve => { release = resolve; });
    const handler = async (route: any) => {
      const path = new URL(route.request().url()).pathname.replace(/^\/api\/(backend|v1)/, "");
      if (path !== `/worlds/${FEED_WORLD}/icon` || route.request().method() !== "POST") return route.fallback();
      requests.push(path); await blocked;
      try { await route.fulfill({ json: { world: { ...state.world, icon_media_id: "/api/v1/media/assets/late-scope/content", row_version: 999 }, membership_role: "owner", readiness: null } }); }
      catch { /* The abandoned request may already be aborted by the component. */ }
    };
    await page.route("**/api/backend/**", handler); await page.route("http://127.0.0.1:8080/api/v1/**", handler);
    await page.goto(`/studio/worlds/${FEED_WORLD}`);
    await page.getByLabel(t("아이콘 업로드"), { exact: true }).setInputFiles("fixtures/photos/normal.jpg");
    const dialog = page.getByRole("dialog"); await expect(dialog).toBeVisible();
    await dialog.getByRole("button", { name: en ? "Apply" : "적용", exact: true }).click();
    await expect.poll(() => requests.length).toBe(1);
    await page.evaluate(() => window.dispatchEvent(new Event("angmoo:desktop-runtime-config-changed")));
    await expect(dialog).toHaveCount(0);
    const previews = page.locator("[data-world-image-previews]"); await expect(previews).toBeVisible();
    release();
    await expect(previews.getByRole("button", { name: t("아이콘 업로드"), exact: true })).toBeEnabled();
    await expect(previews.getByRole("button", { name: t("아이콘 제거"), exact: true })).toHaveCount(0);
    await expect(page.getByText(t("이미지를 저장했어요."), { exact: true })).toHaveCount(0);
    expect(state.writes).toEqual([]);
  });

  for (const mode of ["off", "on", "blocked", "failure"] as const) test(`creation completion actions ${mode} ${language}`, async ({ page }, info) => {
    const state = await installIntegrationFixture(page, info.project.name !== "next", String(info.project.use.baseURL), language);
    state.draft = { id: "integration-draft", revision: 1, contract_version: 2, target_world_id: FEED_WORLD, source_kind: "direct", status: "completed", provider: "google", model: "gemini-3.1-flash-lite", thinking_level: "high", key_fingerprint: null,
      name: "Registered synthetic character", handle: "registered", one_liner: "", worldview: "Synthetic description", personality: "", speech_style: "", character_background: "", topic_preferences: "", safety_rules: "", image_style: "", appearance_prompt: "", avatar_temp_url: null, banner_temp_url: null, persona_enhance_available_at: null, media_generation_available_at: null, expires_at: "2026-10-11T00:00:00Z", created_at: "2026-10-10T00:00:00Z", updated_at: "2026-10-10T00:00:00Z" };
    state.ui.management.credentials.set(`${FEED_WORLD}:${WORLD_AGENT}:sns`, { purpose: "sns", provider: "google", model: "gemini-3.1-flash-lite", thinking_level: "high", has_key: mode !== "blocked", revision: 1, fingerprint: "synthetic" });
    state.ui.management.worlds.get(FEED_WORLD)!.find(row => row.profile.world_character_id === WORLD_AGENT)!.autonomous_enabled = mode === "on";
    state.ui.management.failure = mode === "failure" ? 409 : 0;
    await page.addInitScript(({ world }) => sessionStorage.setItem(`angmoo.creation.v2:${world}`, "integration-draft"), { world: FEED_WORLD });
    await page.goto(`/agents/new?worldId=${FEED_WORLD}`);
    const enable = page.getByRole("button", { name: en ? "Enable autonomous activity and finish" : "자율활동을 켜고 완료", exact: true });
    await expect(enable).toBeVisible(); await verifyCreatorResponsive(page);
    const region = page.getByRole("region", { name: en ? "Activity settings" : "활동 설정", exact: true });
    await expect(region.getByRole("button", { name: /자율활동 (켜기|끄기)|Turn (on|off) autonomous activity/ })).toHaveCount(0);
    const bottom = page.getByRole("button", { name: en ? "Skip" : "건너뛰기", exact: true }); await expect(bottom).toBeVisible();
    const positions = await page.getByRole("button").allTextContents();
    expect(positions.indexOf(en ? "Completed" : "완료")).toBeLessThan(positions.indexOf(en ? "Enable autonomous activity and finish" : "자율활동을 켜고 완료"));
    expect(positions.indexOf(en ? "Enable autonomous activity and finish" : "자율활동을 켜고 완료")).toBeLessThan(positions.indexOf(en ? "Skip" : "건너뛰기"));
    if (mode === "blocked") { await expect(enable).toBeDisabled(); await bottom.click(); }
    else { await expect(enable).toBeEnabled(); await enable.click(); }
    if (mode === "failure") {
      await expect(page).toHaveURL(/agents\/new/); await expect(region.getByRole("alert")).toBeVisible();
      expect(state.ui.management.writes.filter(row => row.path.endsWith("/activate"))).toHaveLength(1);
      await bottom.click();
    }
    await expect(page).toHaveURL(new RegExp(`/worlds/${FEED_WORLD}/characters/?$`));
    expect(state.ui.management.writes.filter(row => row.path.endsWith("/activate"))).toHaveLength(mode === "off" || mode === "failure" ? 1 : 0);
    expect(state.ui.management.writes.filter(row => row.path.endsWith("/deactivate") || /credentials|activity-settings|image-policy/.test(row.path))).toEqual([]);
    expect(state.registrations).toBe(0);
  });
}
