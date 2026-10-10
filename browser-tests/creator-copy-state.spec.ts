import { verifyCreatorResponsive } from "./creator-copy-responsive";
import { expect, test, type Page } from "@playwright/test";
import { readFileSync } from "node:fs";
import { installIntegrationFixture } from "./home-activity-memory-fixture";
import { FEED_WORLD } from "./world-feed-fixture";

async function routes(page: Page, handler: (route: any) => Promise<any>) {
  await page.route("**/api/backend/**", handler);
  await page.route("http://127.0.0.1:8080/api/v1/**", handler);
}
for (const language of ["ko", "en"] as const) {
  const en = language === "en";
  const catalog = Object.assign({}, ...["worlds", "creator-studio", "world-packages"].map(feature =>
    JSON.parse(readFileSync(`../frontend/src/features/${feature}/locales/${language}.json`, "utf8"))));
  const t = (key: string) => catalog[key] ?? key;
  test(`studio enum groups, user text and empty/error states ${language}`, async ({ page }, info) => {
    await installIntegrationFixture(page, info.project.name === "static-export", String(info.project.use.baseURL), language);
    let items: any[] = [
      { world_id: "live", name: "User P2 CORE", tagline: "User private owner", status: "published", visibility: "public", readiness_status: "publish_ready", membership_role: "owner", launchable: true },
      { world_id: "draft", name: "Draft", tagline: "", status: "draft", visibility: "unlisted", readiness_status: "stale", membership_role: "editor", launchable: false },
      { world_id: "private", name: "Private", tagline: "", status: "published", visibility: "private", readiness_status: "publish_ready", membership_role: "member", launchable: false },
      { world_id: "archived", name: "Archived", tagline: "", status: "archived", visibility: "unknown_enum", readiness_status: "unknown_enum", membership_role: "unknown_enum", launchable: false },
    ];
    let failure = false;
    await routes(page, async route => {
      const url = new URL(route.request().url());
      if (url.pathname.endsWith("/worlds/mine") && url.searchParams.get("surface") === "creator_studio")
        return route.fulfill({ status: failure ? 503 : 200, json: failure ? { detail: "internal_secret_reason" } : { schema_version: "local-world-surface-v1", surface: "creator_studio", items } });
      return route.fallback();
    });
    await page.goto("/studio");
    await expect(page.getByRole("heading").first()).toBeVisible(); await verifyCreatorResponsive(page);
    for (const key of ["공개한 World", "작성 중", "비공개", "보관됨"]) await expect(page.getByRole("heading", { name: t(key), exact: true, level: 2 })).toBeVisible();
    await expect(page.getByRole("heading", { name: "User P2 CORE", exact: true })).toBeVisible();
    await expect(page.getByText("User private owner", { exact: true })).toBeVisible();
    await expect(page.getByRole("link", { name: t("World 열기"), exact: true })).toHaveCount(1);
    await expect(page.getByText("unknown_enum", { exact: true })).toHaveCount(0);
    items = []; await page.reload(); await expect(page.getByRole("heading", { name: t("아직 만든 World가 없어요."), exact: true })).toBeVisible();
    failure = true; await page.reload(); await expect(page.getByText(t("Creator Studio를 열지 못했어요."), { exact: true })).toBeVisible();
    await expect(page.getByText("internal_secret_reason", { exact: true })).toHaveCount(0);
  });
  test(`new World empty draft, image guard and field error ${language}`, async ({ page }, info) => {
    await installIntegrationFixture(page, info.project.name === "static-export", String(info.project.use.baseURL), language);
    const writes: any[] = [];
    await routes(page, async route => {
      if (new URL(route.request().url()).pathname.replace(/^\/api\/(backend|v1)/, "") === "/worlds" && route.request().method() === "POST") {
        writes.push(route.request().postDataJSON());
        return route.fulfill({ status: 422, json: { detail: [{ type: "missing", loc: ["body", "internal_field"], msg: "private validator detail" }] } });
      }
      return route.fallback();
    });
    await page.goto("/studio/worlds/new");
    await expect(page.getByRole("heading", { name: t("새 World 만들기"), exact: true })).toBeVisible();
    const save = page.getByRole("button", { name: t("초안 저장"), exact: true });
    await expect(save).toBeDisabled(); await verifyCreatorResponsive(page);
    await expect(page.getByLabel(t("아이콘 선택"), { exact: true })).toBeDisabled();
    await expect(page.getByLabel(t("배너 선택"), { exact: true })).toBeDisabled();
    const form = page.locator("section").filter({ has: page.getByRole("heading", { name: t("필수 세계관 설정"), exact: true }) }).last();
    const name = form.getByLabel(new RegExp(`^${t("World 이름")}`)); await name.fill("Only a draft name");
    await expect(save).toBeEnabled(); await save.click();
    await expect(page.getByText(t("입력값과 형식을 확인해 주세요."), { exact: true })).toBeVisible(); await expect(name).toHaveValue("Only a draft name");
    expect(writes).toHaveLength(1); expect(writes[0].name).toBe("Only a draft name");
    await expect(page.getByText(/private validator detail|internal_field/, { exact: true })).toHaveCount(0);
    await expect(page.getByLabel(t("아이콘 선택"), { exact: true })).toBeDisabled();
  });
  test(`package preview, digest approval, cancel, blocking and success ${language}`, async ({ page }, info) => {
    await installIntegrationFixture(page, info.project.name === "static-export", String(info.project.use.baseURL), language);
    let blocked = false, stageError = false, stageNumber = 0;
    const writes: { method: string; headers: Record<string,string>; body: any }[] = [];
    const digest = "d".repeat(64), token = "synthetic-preview-token";
    await routes(page, async route => {
      const request = route.request(), path = new URL(request.url()).pathname;
      if (path.endsWith("/world-package-imports/stage")) {
        stageNumber++;
        if (stageError) return route.fulfill({ status: 422, json: { detail: "manifest_invalid" } });
        return route.fulfill({ json: { preview_token: token, preview: {
          operation_id: "synthetic-op", content_digest: digest, archive_digest: "a".repeat(64), world_name: "User P2 CORE", world_tagline: "Preserved author text",
          schema_version: "world-package-preview-v1", state: "prepared", package_id: "private-id", package_version: 1,
          producer_name: "fixture", producer_version: "private-version", min_reader_version: "private-min-reader", world_contract_version: "private-contract",
          trust_state: "checksum_verified_unsigned", license: { expression: "CC0-1.0", attribution: "User attribution", source_url: null, license_text_path: null },
          character_names: ["Actor"], character_settings: [{ name: "Actor", description: "User P2 body", character_background: "User CORE background" }],
          place_count: 1, role_count: 1, rule_count: 0, glossary_count: 0, asset_count: 1, asset_bytes: 1024, total_decoded_pixels: 1024,
          excluded_owner_controlled_characters: 1, excluded_runtime_records: 1, normalized_assets: [], expires_at: "2026-10-11T00:00:00Z",
          collision_plan: { planned_world_slug: "private-planned-slug", characters: [], duplicate_state: "already_imported", commit_allowed_by_default: false },
          warnings: ["author_signature_not_available", "unknown_warning"], blocking_issues: blocked ? ["unknown_blocking"] : [],
        } } });
      }
      if (/\/world-package-imports\/synthetic-op(\/commit)?$/.test(path)) {
        writes.push({ method: request.method(), headers: request.headers(), body: request.method() === "POST" ? request.postDataJSON() : null });
        return route.fulfill({ status: request.method() === "DELETE" ? 204 : 200, ...(request.method() === "DELETE" ? {} : { json: { import_id: "synthetic-import", imported_world_id: FEED_WORLD, device_home_world_id: FEED_WORLD, replayed: false } }) });
      }
      return route.fallback();
    });
    await page.goto("/studio/import");
    await expect(page.getByRole("heading").first()).toBeVisible(); await verifyCreatorResponsive(page);
    const input = page.locator('input[type="file"][accept*="angmoo-world"]');
    const file = { name: "synthetic.angmoo-world", mimeType: "application/zip", buffer: Buffer.from("synthetic test staging response") };
    await input.setInputFiles(file);
    const commit = page.getByRole("button", { name: t("World 가져오기"), exact: true }); await expect(commit).toBeDisabled();
    await expect(page.getByRole("heading", { name: "User P2 CORE", exact: true })).toBeVisible();
    await expect(page.getByText(t("파일 내용 확인 완료 · 제작자 미확인"), { exact: true })).toBeVisible();
    await page.getByText(t("가져올 캐릭터 설정 확인"), { exact: true }).click(); await expect(page.getByText("User P2 body", { exact: true })).toBeVisible();
    for (const privateValue of [digest, "private-planned-slug", "unknown_warning", "private-contract"]) await expect(page.getByText(privateValue, { exact: true })).toHaveCount(0);
    await page.getByRole("button", { name: t("가져오기 취소"), exact: true }).click(); await expect(commit).toHaveCount(0);
    expect(writes[0]).toMatchObject({ method: "DELETE", headers: { "x-world-package-preview-token": token } });
    blocked = true; await input.setInputFiles(file); await expect(page.getByRole("checkbox")).toBeDisabled(); await expect(commit).toBeDisabled();
    await page.getByRole("button", { name: t("가져오기 취소"), exact: true }).click();
    blocked = false; stageError = true; await input.setInputFiles(file); await expect(page.locator('[data-ui-primitive="inline-error"]')).toBeVisible();
    await expect(page.getByText("manifest_invalid", { exact: true })).toHaveCount(0);
    stageError = false; await input.setInputFiles(file); await page.getByRole("checkbox").check(); await expect(commit).toBeEnabled(); await commit.click();
    await expect(page.getByRole("heading", { name: t("World를 가져왔어요."), exact: true })).toBeVisible();
    expect(writes.at(-1)).toMatchObject({ method: "POST", headers: { "x-world-package-preview-token": token }, body: { expected_content_digest: digest, duplicate_strategy: "independent_copy" } });
    expect(stageNumber).toBe(4);
  });
  test(`directory and embedded relationship use the same computed header ${language}`, async ({ page }, info) => {
    await installIntegrationFixture(page, info.project.name === "static-export", String(info.project.use.baseURL), language);
    const styles = async (heading: any) => heading.evaluate((element: HTMLElement) => {
      const header = element.parentElement!.parentElement!, css = getComputedStyle(element);
      const icon = header.firstElementChild!, small = element.parentElement!.querySelector("span")!;
      return { title: [css.fontSize, css.fontWeight, css.lineHeight, css.marginTop], icon: [getComputedStyle(icon).width, getComputedStyle(icon).borderRadius, getComputedStyle(icon).backgroundColor], small: [getComputedStyle(small).fontSize, getComputedStyle(small).fontWeight] };
    });
    for (const width of [480, 1024, 1440]) {
      await page.setViewportSize({ width, height: 900 }); await page.goto(`/worlds/${FEED_WORLD}/characters`);
      const directory = page.locator('[data-world-character-surface="list"] header h2'); await expect(directory).toBeVisible();
      const expected = await styles(directory); expect(expected.title[1]).toBe("400");
      await page.goto(`/worlds/${FEED_WORLD}/relationships`);
      const relation = page.getByRole("heading", { name: en ? "Relationships in this World" : "이 World의 관계", exact: true });
      await expect(relation).toBeVisible(); expect(await styles(relation)).toEqual(expected);
    }
  });
}
