import { test, expect } from "@playwright/test";
import { readFileSync } from "node:fs";
import { worldLocalDate, nextWorldDateBoundary } from "../frontend/src/features/characters/utils/daily-plan-presentation";
import { installUiFixture, installMemoryUi, installLegacyImageUi } from "./world-ui-improvements-fixture";
import { FEED_WORLD, ownerId } from "./world-feed-fixture";
import { worldCharacterRoute, WORLD_AGENT } from "./world-character-management-fixture";

const fixture = (page: Parameters<typeof installUiFixture>[0], info: { project: { name: string; use: { baseURL?: string } } }, language: "ko" | "en" = "ko") =>
  installUiFixture(page, info.project.name === "static-export", String(info.project.use.baseURL), language);
const day = "2026-10-09T08:00:00Z";

for (const language of ["ko", "en"] as const) {
  test(`status-summary: six cards, four actual rows and independent original detail (${language})`, async ({ page }, info) => {
    await page.clock.install({ time: new Date(day) });
    await page.setViewportSize({ width: language === "ko" ? 390 : 960, height: 950 });
    const state = await fixture(page, info, language);
    await page.goto(`${worldCharacterRoute()}?view=status`);
    const panel = page.getByRole("tabpanel"), plan = panel.getByRole("region", { name: language === "ko" ? "오늘 하루 계획" : "Today's plan", exact: true });
    const topics = panel.getByRole("region", { name: language === "ko" ? "캐릭터 관심 주제" : "Character interests", exact: true });
    await expect(panel.locator(":scope > div > section")).toHaveCount(6);
    await expect(plan.locator("li")).toHaveCount(4);
    await expect(plan.locator("li").nth(1)).toContainText(language === "ko" ? "진행 중" : "In progress");
    await expect(plan.locator("li").nth(2)).toContainText(language === "ko" ? "예정" : "Planned");
    const details = plan.getByRole("button", { name: language === "ko" ? "계획 펼치기" : "Expand plan", exact: true });
    await details.nth(2).click();
    await expect(plan.locator("li").nth(2)).toContainText("Original afternoon seed");
    await expect(plan.locator("li").nth(2).getByRole("button").first()).toHaveAttribute("aria-expanded", "true");
    await expect(details.first()).toHaveAttribute("aria-expanded", "false");
    await details.first().focus(); await page.keyboard.press("Enter");
    const firstDetail = plan.locator("li").first().getByRole("button").first();
    await expect(firstDetail).toBeFocused(); await expect(firstDetail).toHaveAttribute("aria-expanded", "true");
    await page.keyboard.press("Space"); await expect(firstDetail).toHaveAttribute("aria-expanded", "false");
    await expect(topics.locator("li")).toHaveCount(6);
    await topics.getByRole("button", { name: language === "ko" ? "주제 펼치기" : "Expand topics", exact: true }).click();
    await expect(topics.locator("li")).toHaveCount(10);
    await topics.getByRole("button", { name: language === "ko" ? "주제 접기" : "Collapse topics", exact: true }).click();
    await expect(topics.locator("li")).toHaveCount(6);
    await expect(plan.getByRole("button", { name: language === "ko" ? "설정에서 보기" : "View in settings", exact: true })).toHaveCount(0);
    await expect(topics.getByRole("button", { name: language === "ko" ? "설정에서 보기" : "View in settings", exact: true })).toHaveCount(0);
    expect(state.writes).toEqual([]); expect(state.management.providerCalls).toEqual([]);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBe(true);
    await page.getByRole("tab", { name: language === "ko" ? "상태" : "Status", exact: true }).click();
    await page.locator('[data-device-scroll-owner="true"]').evaluate(node => node.scrollTop = 0);
    await page.screenshot({ path: info.outputPath(`status-${language}.png`), fullPage: true });
  });

  test(`world-relationships: owner and explicit center share one World shell (${language})`, async ({ page }, info) => {
    const state = await fixture(page, info, language);
    await page.setViewportSize({ width: language === "ko" ? 360 : 960, height: 900 });
    await page.goto(`/worlds/${FEED_WORLD}/relationships`);
    const graph = page.locator('[data-product-content="relationship-graph"]');
    await expect(graph).toContainText(`Center ${ownerId()}`);
    await expect(graph.getByRole("heading", { name: language === "ko" ? "이 World의 관계" : "Relationships in this World", exact: true })).toBeVisible();
    await expect(page.locator("main")).toHaveCount(1);
    const nav = page.getByRole("navigation");
    await expect(nav.getByRole("link", { name: language === "ko" ? "관계" : "Relationships", exact: true })).toHaveAttribute("aria-current", "page");
    await expect(graph.locator("path[marker-end]")).toHaveCount(1);
    await graph.getByRole("button", { name: language === "ko" ? "2단계까지 보기" : "Show up to two hops", exact: true }).click();
    await expect.poll(() => state.reads.some(path => path.includes("depth=2"))).toBe(true);
    await page.goto(`/characters/character-${WORLD_AGENT}/worlds/${FEED_WORLD}/relationship-graph?provider=ladybug`);
    await expect(graph).toContainText(`Center ${WORLD_AGENT}`);
    await page.reload(); await expect(graph).toContainText(`Center ${WORLD_AGENT}`);
    await page.goBack(); await expect(graph).toContainText(`Center ${ownerId()}`);
    await page.goForward(); await expect(graph).toContainText(`Center ${WORLD_AGENT}`);
    const viewport = graph.locator('[data-relationship-map-viewport]');
    await expect.poll(() => viewport.evaluate(node => node.scrollLeft)).toBeGreaterThan(0);
    await viewport.scrollIntoViewIfNeeded();
    const center = graph.locator('[data-relationship-center="true"]');
    const viewportBox = (await viewport.boundingBox())!, centerBox = (await center.boundingBox())!;
    expect(centerBox.x + centerBox.width / 2).toBeGreaterThan(viewportBox.x);
    expect(centerBox.x + centerBox.width / 2).toBeLessThan(viewportBox.x + viewportBox.width);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBe(true);
    expect(state.base.base.writes).toEqual([]); expect(state.writes).toEqual([]);
    await page.screenshot({ path: info.outputPath(`relationships-${language}.png`), fullPage: true });
    const evidence = graph.getByRole("link", { name: language === "ko" ? "근거 게시글 보기" : "View evidence post", exact: true });
    await expect(evidence).toHaveAttribute("href", new RegExp(`^/worlds/${FEED_WORLD}/posts/synthetic-evidence-post/?$`));
    await evidence.focus(); await expect(evidence).toBeFocused();
    await evidence.scrollIntoViewIfNeeded();
    const evidenceBox = (await evidence.boundingBox())!, footerBox = (await nav.boundingBox())!;
    expect(evidenceBox.y + evidenceBox.height).toBeLessThanOrEqual(footerBox.y);
    await page.screenshot({ path: info.outputPath(`relationship-evidence-${language}.png`), fullPage: true });
  });

  test(`embedding-card: saved notice, one read owner, dirty edits and explicit preparation (${language})`, async ({ page }, info) => {
    await fixture(page, info, language);
    const state = await installMemoryUi(page);
    await page.setViewportSize({ width: language === "ko" ? 390 : 960, height: 900 });
    await page.goto(`/memory?world=${FEED_WORLD}&subject=${WORLD_AGENT}`);
    const embedding = page.getByRole("region", { name: language === "ko" ? "임베딩 모델 API 키" : "Embedding model API key", exact: true });
    const storage = page.getByRole("region", { name: language === "ko" ? "기억 사용 중" : "Memory enabled", exact: true });
    await expect(embedding.getByLabel(language === "ko" ? "의미 검색 사용" : "Use semantic search", { exact: true })).toBeChecked();
    await embedding.getByLabel(language === "ko" ? "의미 검색 사용" : "Use semantic search", { exact: true }).focus();
    await expect(embedding.getByLabel(language === "ko" ? "의미 검색 사용" : "Use semantic search", { exact: true })).toBeFocused();
    await expect(storage).toContainText(language === "ko" ? "기억을 저장한 뒤 의미 검색 자료도 순서대로 준비해요." : "After memories are saved, their semantic search data is prepared in turn.");
    const names = await page.locator('section[aria-label]').allTextContents(); expect(names.length).toBeGreaterThan(0);
    const order = await page.locator('section[aria-labelledby] > header h2').allTextContents();
    expect(order.slice(0, 3)).toEqual(language === "ko" ? ["기억 사용 중", "임베딩 모델 API 키", "관계 정리"] : ["Memory enabled", "Embedding model API key", "Relationship review"]);
    expect(state.reads.filter(path => path.endsWith("/credentials/embedding"))).toHaveLength(1);
    await expect(storage.getByRole("button", { name: /임베딩|embedding/i })).toHaveCount(0);
    await embedding.getByLabel(language === "ko" ? "의미 검색 사용" : "Use semantic search", { exact: true }).uncheck();
    await expect(storage).toContainText(language === "ko" ? "기억을 저장한 뒤 의미 검색 자료도 순서대로 준비해요." : "After memories are saved, their semantic search data is prepared in turn.");
    await embedding.getByRole("button", { name: language === "ko" ? "의미 검색 설정 저장" : "Save semantic search settings", exact: true }).click();
    await expect(storage).toContainText(language === "ko" ? "키워드 검색 자료만 준비해요." : "only keyword search data");
    expect(state.writes.filter(path => path.endsWith("embedding-preparation"))).toHaveLength(0);
    await embedding.getByLabel(language === "ko" ? "의미 검색 사용" : "Use semantic search", { exact: true }).check();
    await embedding.getByRole("button", { name: language === "ko" ? "의미 검색 설정 저장" : "Save semantic search settings", exact: true }).click();
    await embedding.getByRole("button", { name: language === "ko" ? "검색 자료 준비 시작" : "Start preparing search data", exact: true }).click();
    expect(state.writes.filter(path => path.endsWith("embedding-preparation"))).toHaveLength(1);
    await page.evaluate(() => document.documentElement.style.fontSize = "200%");
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBe(true);
    await page.evaluate(() => { document.documentElement.style.fontSize = ""; document.querySelectorAll('[data-device-scroll-owner="true"]').forEach(node => node.scrollTop = 0); });
    await page.screenshot({ path: info.outputPath(`embedding-${language}.png`), fullPage: true });
  });

  test(`comfy-credentials: selected provider reuse and absent generic key DOM (${language})`, async ({ page }, info) => {
    const state = await fixture(page, info, language);
    await page.goto(`${worldCharacterRoute()}?view=settings`);
    const card = page.getByRole("region", { name: language === "ko" ? "SNS 게시글 이미지 생성" : "SNS post image generation", exact: true });
    const models = card.getByRole("combobox").first();
    await expect(card).toContainText("novel-fingerprint");
    await card.locator('input[type="password"]').first().fill("synthetic-unsaved-only");
    await models.selectOption("comfyui:workflow:");
    await expect(card.getByLabel(language === "ko" ? "새 이미지 API key" : "New image API key", { exact: true })).toHaveCount(0);
    await expect(card.getByRole("button", { name: language === "ko" ? "이미지 키 삭제" : "Delete image key", exact: true })).toHaveCount(0);
    await expect(card).not.toContainText("novel-fingerprint");
    await expect(card.locator('input[type="password"]')).toHaveCount(1);
    await models.selectOption("novelai:nai-diffusion-4-5-full:");
    await expect(card).toContainText("novel-fingerprint");
    await expect(card.locator('input[type="password"]').first()).toHaveValue("");
    expect(state.writes).toEqual([]); expect(state.management.writes).toEqual([]);
    await page.screenshot({ path: info.outputPath(`credentials-${language}.png`), fullPage: true });
  });
}

test("status-summary: 0/1/6/7/10 topics, partial failure, version conflict and World midnight", async ({ page }, info) => {
  await page.clock.install({ time: new Date("2026-10-09T14:59:58Z") });
  const state = await fixture(page, info);
  for (const count of [0, 1, 6, 7, 10]) {
    state.topics = Array.from({ length: count }, (_, i) => `Original topic ${i}`);
    await page.goto(`${worldCharacterRoute()}?view=status`);
    const topics = page.getByRole("tabpanel").getByRole("region", { name: "캐릭터 관심 주제", exact: true });
    await expect(topics.locator("li")).toHaveCount(Math.min(count, 6));
    if (count > 6) await expect(topics.getByRole("button", { name: "주제 펼치기", exact: true })).toBeVisible();
  }
  const plan = page.getByRole("tabpanel").getByRole("region", { name: "오늘 하루 계획", exact: true });
  await page.clock.runFor(4000);
  await expect(plan).toContainText("오늘 계획이 아닙니다.");
  expect(state.reads.filter(path => path.includes("activity-plan")).length).toBeGreaterThan(5);
  state.planDate = "2026-10-10"; state.plan!.local_date = "2026-10-10"; state.planVersion = 99;
  await page.reload(); await expect(plan).toContainText("확인 필요"); await expect(plan.locator("li")).toHaveCount(0);
  state.planVersion = 2; state.requestState = "failed";
  await plan.getByRole("button", { name: "다시 시도", exact: true }).click();
  await expect(plan).toContainText("기존의 유효한 오늘 일과");
  state.failure = 503; await page.evaluate(() => window.dispatchEvent(new Event("angmoo:desktop-runtime-config-changed")));
  await expect(plan.getByRole("alert")).toBeVisible();
  state.failure = 0; await plan.getByRole("button", { name: "다시 시도", exact: true }).click(); await expect(plan.locator("li")).toHaveCount(4);
  expect(state.writes).toEqual([]);
});

test("world-relationships: missing owner, explicit forbidden and canonical fallback remain distinct", async ({ page }, info) => {
  const state = await fixture(page, info); state.base.base.missingOwner = true;
  await page.goto(`/worlds/${FEED_WORLD}/relationships`);
  await expect(page.getByText("이 World의 내 프로필이 아직 연결되지 않았습니다. 관계 조회는 새 프로필을 만들지 않습니다.", { exact: true })).toBeVisible();
  expect(state.base.base.writes.filter(write => write.path.endsWith("ensure"))).toHaveLength(0);
  state.graphFailure = 403;
  await page.goto(`/characters/character-${WORLD_AGENT}/worlds/${FEED_WORLD}/relationship-graph`);
  await expect(page.getByText("이 캐릭터의 관계망을 열 수 없습니다. 권한과 World 참여 상태를 확인해주세요.", { exact: true })).toBeVisible();
  expect(state.reads.filter(path => path.includes("character-" + ownerId()))).toHaveLength(0);
  state.graphFailure = 0; state.graphSource = "canonical_fallback"; state.graphStatus = "unavailable";
  await page.reload(); await expect(page.locator('[data-relationship-graph-state="degraded"]')).toBeVisible();
  state.graphSource = "ladybug"; state.graphStatus = "healthy"; state.graphEmpty = true;
  await page.reload(); await expect(page.locator('[data-relationship-graph-state="empty"]')).toBeVisible();
});

for (const language of ["ko", "en"] as const) {
test(`creator-method: removed candidate and explicit external-draft recovery preserve inputs (${language})`, async ({ page }, info) => {
  await fixture(page, info, language);
  const catalog = JSON.parse(readFileSync(`../frontend/src/features/characters/locales/${language}.json`, "utf8"));
  const t = (key: string) => catalog[key] ?? key;
  const draft = { id: "external-draft", contract_version: 2, target_world_id: FEED_WORLD, revision: 4, source_kind: "external", status: "editing",
    provider: "google", model: "gemini-3.1-flash-lite", name: "Preserved name", handle: "preserved", one_liner: "Preserved intro",
    personality: "Preserved personality", speech_style: "Preserved speech", worldview: "Preserved description", character_background: "Preserved background",
    topic_preferences: "Preserved topics", safety_rules: "Preserved safety", avatar_temp_url: null, banner_temp_url: null, expires_at: "2026-10-10T00:00:00Z" };
  let writes = 0;
  await page.addInitScript(({ world }) => sessionStorage.setItem(`angmoo.creation.v2:${world}`, "external-draft"), { world: FEED_WORLD });
  const handler = async (route: import("@playwright/test").Route) => {
    if (!new URL(route.request().url()).pathname.endsWith("/agents/drafts/external-draft")) return route.fallback();
    if (route.request().method() === "PATCH") { const body = route.request().postDataJSON(); if (draft.source_kind === "external") expect(body.creation_method).toBe("direct"); expect(body.revision).toBe(draft.revision); expect(body.api_key).toBeUndefined(); draft.source_kind = "direct"; draft.revision++; writes++; }
    return route.fulfill({ json: draft });
  };
  await page.route("**/api/backend/**", handler); await page.route("http://127.0.0.1:8080/api/v1/**", handler);
  await page.goto(`/agents/new?worldId=${FEED_WORLD}`);
  await expect(page.getByRole("textbox", { name: t("이름"), exact: true })).toHaveValue("Preserved name");
  await page.getByRole("button", { name: t("만드는 방법 다시 선택"), exact: true }).click();
  await expect(page.getByRole("radio")).toHaveCount(3);
  await expect(page.getByRole("radio", { name: /외부|external/i })).toHaveCount(0);
  await page.getByRole("radio", { name: t("새 캐릭터 직접 만들기"), exact: true }).click();
  await expect(page.getByRole("radio", { name: t("새 캐릭터 직접 만들기"), exact: true })).toBeChecked();
  expect(writes).toBe(1); expect(draft.worldview).toBe("Preserved description");
  await page.getByRole("button", { name: t("저장하고 다음"), exact: true }).click();
  await expect(page.getByRole("textbox", { name: t("이름"), exact: true })).toHaveValue("Preserved name");
});
}

test("embedding-card: key absence, read failure and recovery cannot promise semantic preparation", async ({ page }, info) => {
  await fixture(page, info); const state = await installMemoryUi(page); state.hasKey = false;
  await page.goto(`/memory?world=${FEED_WORLD}&subject=${WORLD_AGENT}`);
  const storage = page.getByRole("region", { name: "기억 사용 중", exact: true });
  await expect(storage).toContainText("키워드 검색 자료만 준비해요.");
  state.failure = 503; await page.evaluate(() => window.dispatchEvent(new Event("angmoo:desktop-runtime-config-changed")));
  await expect(storage).toContainText("임베딩 설정 상태를 확인하지 못했어요.");
  state.failure = 0; state.hasKey = true;
  await page.getByRole("region", { name: "임베딩 모델 API 키", exact: true }).getByRole("button", { name: "다시 시도", exact: true }).click();
  await expect(storage).toContainText("기억을 저장한 뒤 의미 검색 자료도 순서대로 준비해요.");
  expect(state.writes).toEqual([]);
});

test("comfy-credentials: legacy screen reuses selected keys, clears unsaved provider key and saves keyless Comfy", async ({ page }, info) => {
  await fixture(page, info); const state = await installLegacyImageUi(page);
  await page.goto(`/agents/${WORLD_AGENT}?tab=settings`);
  const panel = page.getByRole("region", { name: "SNS 이미지 생성 설정", exact: true });
  const provider = panel.getByRole("combobox", { name: "이미지 서비스", exact: true });
  const key = panel.getByLabel("이미지 API 키", { exact: true });
  await expect(key).toHaveAttribute("placeholder", "선택된 서비스에 저장된 키가 있습니다");
  await provider.selectOption("openrouter");
  await expect(key).toHaveAttribute("placeholder", "선택된 서비스에 저장된 키가 있습니다");
  await key.fill("synthetic-unsaved");
  await panel.getByRole("combobox", { name: "이미지 모델", exact: true }).selectOption("google/gemini-3.1-flash-image");
  await expect(key).not.toHaveValue("");
  await provider.selectOption("comfyui");
  await expect(key).toHaveCount(0);
  await expect(panel.getByRole("button", { name: "이미지 키 삭제", exact: true })).toHaveCount(0);
  await expect(panel.locator('input[type="password"]')).toHaveCount(1);
  await provider.selectOption("openrouter"); await expect(key).toHaveValue("");
  await expect(key).toHaveAttribute("placeholder", "선택된 서비스에 저장된 키가 있습니다");
  await provider.selectOption("comfyui");
  await panel.getByLabel("불러온 API workflow JSON", { exact: true }).fill(JSON.stringify({ "9": { class_type: "SyntheticImage", inputs: { text: "fixed" } } }));
  await expect(panel.getByText("JSON 분석 완료", { exact: true })).toBeVisible();
  await panel.getByRole("button", { name: "설정 저장", exact: true }).click();
  await expect.poll(() => state.writes.length).toBe(1);
  expect(state.writes[0].api_key).toBeUndefined(); expect(state.writes[0].provider).toBe("comfyui");
});

test("status-summary: inactive and hidden reads stop and old actor responses do not leak", async ({ page }, info) => {
  const state = await fixture(page, info);
  await page.clock.install({ time: new Date(day) });
  await page.goto(`${worldCharacterRoute()}?view=status`);
  const plan = page.getByRole("tabpanel").getByRole("region", { name: "오늘 하루 계획", exact: true });
  await expect(plan.locator("li")).toHaveCount(4);
  // Settings intentionally owns its original preparation polling. Use Profile
  // to isolate whether the inactive Status summaries continue their own reads.
  await page.getByRole("tab", { name: "프로필", exact: true }).click();
  await expect(page.getByRole("tab", { name: "프로필", exact: true })).toHaveAttribute("aria-selected", "true");
  const reads = state.reads.filter(path => /activity-plan|recommendation-topics/.test(path)).length;
  await page.clock.runFor(26 * 3600 * 1000);
  expect(state.reads.filter(path => /activity-plan|recommendation-topics/.test(path))).toHaveLength(reads);
  await page.getByRole("tab", { name: "상태", exact: true }).click();
  await expect.poll(() => state.reads.filter(path => /activity-plan|recommendation-topics/.test(path)).length).toBeGreaterThan(reads);
  await page.evaluate(() => { Object.defineProperty(document, "visibilityState", { configurable: true, value: "hidden" }); document.dispatchEvent(new Event("visibilitychange")); });
  const hiddenReads = state.reads.length;
  await page.clock.runFor(26 * 3600 * 1000); expect(state.reads).toHaveLength(hiddenReads);
  state.delay = 600;
  await page.evaluate(() => { Object.defineProperty(document, "visibilityState", { configurable: true, value: "visible" }); document.dispatchEvent(new Event("visibilitychange")); });
  await expect.poll(() => state.reads.length).toBeGreaterThan(hiddenReads);
  await page.goto(`/worlds/${FEED_WORLD}/characters/${ownerId()}?view=status`);
  await expect(page.getByRole("tabpanel").getByRole("region", { name: "오늘 하루 계획", exact: true })).toHaveCount(0);
  expect(state.writes).toEqual([]);
});

test("embedding-card: dirty edits survive saved polling and runtime change clears old owner reads", async ({ page }, info) => {
  await fixture(page, info); const state = await installMemoryUi(page);
  await page.goto(`/memory?world=${FEED_WORLD}&subject=${WORLD_AGENT}`);
  const embedding = page.getByRole("region", { name: "임베딩 모델 API 키", exact: true });
  const toggle = embedding.getByLabel("의미 검색 사용", { exact: true });
  await expect(toggle).toBeChecked(); await toggle.uncheck();
  state.revision++;
  await expect.poll(() => state.reads.filter(path => path.endsWith("embedding-settings")).length).toBeGreaterThan(1);
  await expect(toggle).not.toBeChecked();
  await expect(page.getByRole("region", { name: "기억 사용 중", exact: true })).toContainText("기억을 저장한 뒤 의미 검색 자료도 순서대로 준비해요.");
  state.semantic = false; state.delay = 800;
  await page.evaluate(() => window.dispatchEvent(new Event("angmoo:desktop-runtime-config-changed")));
  await expect(toggle).not.toBeChecked();
  await expect(page.getByRole("region", { name: "기억 사용 중", exact: true })).toContainText("키워드 검색 자료만 준비해요.");
  expect(state.writes).toEqual([]);
});


test("status-summary: World dates and next midnight use server zone including DST", () => {
  const utc = new Date("2026-10-09T15:00:00Z");
  expect(worldLocalDate("Asia/Seoul", utc)).toBe("2026-10-10");
  expect(worldLocalDate("America/New_York", utc)).toBe("2026-10-09");
  expect(worldLocalDate("invalid/timezone", utc)).toBeNull();
  const next = nextWorldDateBoundary("America/New_York", Date.parse("2026-03-08T05:00:00Z"))!;
  const expected = Date.parse("2026-03-09T04:00:00Z");
  expect(next).toBeGreaterThanOrEqual(expected); expect(next).toBeLessThan(expected + 2100);
});

test("world-relationships: login recovery retains explicit URL and late center reads cannot replace it", async ({ page }, info) => {
  const state = await fixture(page, info);
  let authenticated = false;
  const auth = async (route: import("@playwright/test").Route) => {
    if (!new URL(route.request().url()).pathname.endsWith("/auth/me") || authenticated) return route.fallback();
    return route.fulfill({ status: 401, json: { detail: "synthetic_owner_required" } });
  };
  await page.route("**/api/backend/**", auth); await page.route("http://127.0.0.1:8080/api/v1/**", auth);
  const explicit = `/characters/character-${WORLD_AGENT}/worlds/${FEED_WORLD}/relationship-graph?provider=ladybug`;
  await page.goto(explicit);
  const recovery = page.getByRole("link", { name: "owner 연결", exact: true });
  await expect(recovery).toBeVisible();
  const recoveryUrl = new URL((await recovery.getAttribute("href"))!, "http://angmoo.local");
  expect(recoveryUrl.pathname.replace(/\/$/, "")).toBe("/login");
  expect(recoveryUrl.searchParams.get("returnTo")).toBe(explicit);
  expect(state.reads.filter(path => path.includes("relationship-graph"))).toEqual([]);
  authenticated = true;
  await page.goto(recoveryUrl.searchParams.get("returnTo")!);
  const graph = page.locator('[data-product-content="relationship-graph"]');
  await expect(graph).toContainText(`Center ${WORLD_AGENT}`);
  state.graphDelay = 600;
  await page.goto(`/worlds/${FEED_WORLD}/relationships`);
  await expect.poll(() => state.reads.some(path => path.includes(`character-${ownerId()}/worlds/`))).toBe(true);
  state.graphDelay = 0;
  await page.goto(explicit);
  await expect(graph).toContainText(`Center ${WORLD_AGENT}`);
  await page.waitForTimeout(700);
  await expect(graph).not.toContainText(`Center ${ownerId()}`);
  // The existing unauthenticated owner bootstrap attempts its local session;
  // graph reads must not create a profile, rebuild or provider work.
  expect(state.base.base.writes.map(write => write.path)).toEqual(["/auth/local/session"]);
  expect(state.writes).toEqual([]);
});

test("comfy-credentials: late metadata, read failure and provider deletion preserve isolation", async ({ page }, info) => {
  const state = await fixture(page, info);
  await page.goto(`${worldCharacterRoute()}?view=settings`);
  const card = page.getByRole("region", { name: "SNS 게시글 이미지 생성", exact: true });
  const model = card.getByRole("combobox").first();
  const save = card.getByRole("button", { name: "키와 모델 저장", exact: true });
  await expect(card).toContainText("novel-fingerprint");
  state.delay = 500;
  await model.selectOption("openrouter:openai/gpt-image-2.5-flare:");
  await expect.poll(() => state.reads.filter(path => path.endsWith("image-provider-key/openrouter")).length).toBeGreaterThan(0);
  await model.selectOption("novelai:nai-diffusion-4-5-full:");
  await expect(card).toContainText("novel-fingerprint");
  await page.waitForTimeout(600);
  await expect(card).not.toContainText("router-fingerprint");
  state.delay = 0; state.failure = 503;
  await model.selectOption("openrouter:openai/gpt-image-2.5-flare:");
  await expect(card.getByRole("alert")).toBeVisible(); await expect(save).toBeDisabled();
  expect(state.writes).toEqual([]);
  state.failure = 0;
  await card.getByRole("button", { name: "최신 설정 확인", exact: true }).click();
  await expect(card).toContainText("router-fingerprint");
  page.once("dialog", dialog => dialog.accept());
  await card.getByRole("button", { name: "이미지 키 삭제", exact: true }).click();
  await expect.poll(() => state.writes.length).toBe(1);
  await model.selectOption("comfyui:workflow:");
  await model.selectOption("openrouter:openai/gpt-image-2.5-flare:");
  await expect(card).toContainText("이 서비스의 API 키를 등록해 주세요.");
  await expect(card).not.toContainText("router-fingerprint");
  expect(state.selectedKeys.get("novelai")?.has_key).toBe(true);
  expect(state.selectedKeys.get("openrouter")?.has_key).toBe(false);
  expect(state.management.providerCalls).toEqual([]);
});
