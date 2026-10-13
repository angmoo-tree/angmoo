import { test, expect, type Page, type TestInfo } from "@playwright/test";
import { installIntegrationFixture } from "./home-activity-memory-fixture";
import { FEED_WORLD, OTHER_FEED_WORLD } from "./world-feed-fixture";
import { worldCharacterRoute, WORLD_AGENT } from "./world-character-management-fixture";

const fixture = (page: Page, info: TestInfo, language: "ko" | "en" = "ko") => installIntegrationFixture(page, info.project.name === "static-export", String(info.project.use.baseURL), language);
const basicRoute = `/characters/character-${WORLD_AGENT}/worlds/${FEED_WORLD}/autonomy-setup`;
const labels = (language: "ko" | "en") => language === "ko" ? {
  policy: "활동 설정", sns: "캐릭터 활동 API key", image: "SNS 게시글 이미지 생성", interval: "활동 간격 (분)", save: "설정 저장", on: "자율활동 켜기", off: "자율활동 끄기",
} : { policy: "Activity settings", sns: "Character activity API key", image: "SNS post image generation", interval: "Activity interval (minutes)", save: "Save settings", on: "Enable autonomous activity", off: "Turn autonomy off" };

for (const language of ["ko", "en"] as const) {
  test(`integration basic: saved policy, key-only eligibility, ON/OFF and draft World (${language})`, async ({ page }, info) => {
    const state = await fixture(page, info, language), l = labels(language);
    await page.setViewportSize({ width: language === "ko" ? 360 : 960, height: 900 });
    await page.goto(basicRoute); await page.reload();
    const card = page.getByRole("region", { name: l.policy, exact: true });
    await expect(card.getByRole("button", { name: l.on, exact: true })).toBeDisabled();
    await card.getByLabel(l.interval, { exact: true }).fill("45");
    await card.getByRole("button", { name: l.save, exact: true }).click();
    await expect(card).toContainText(language === "ko" ? "설정을 저장했어요." : "Settings saved.");
    const sns = page.getByRole("region", { name: l.sns, exact: true });
    await sns.locator('input[type="password"]').fill("synthetic-test-key-only");
    await expect(card.getByRole("button", { name: l.on, exact: true })).toBeDisabled();
    await sns.getByRole("button", { name: language === "ko" ? "모델 저장" : "Save model", exact: true }).click();
    await expect(card.getByRole("button", { name: l.on, exact: true })).toBeEnabled();
    await card.getByRole("button", { name: l.on, exact: true }).click();
    await expect(card.getByRole("button", { name: l.off, exact: true })).toBeEnabled();
    await card.getByRole("button", { name: l.off, exact: true }).click();
    await expect(card.getByRole("button", { name: l.on, exact: true })).toBeVisible();
    const image = page.getByRole("region", { name: l.image, exact: true });
    await expect(image.getByLabel(language === "ko" ? "새 게시글 자동 이미지 생성" : "Generate images automatically for new posts", { exact: true })).not.toBeChecked();
    state.draftWorld = true; await page.reload();
    await expect(card).toContainText(language === "ko" ? "World를 개시한 뒤 자율활동을 켤 수 있어요." : "Enable autonomous activity after publishing the World.");
    await expect(card.getByRole("button", { name: l.on, exact: true })).toBeDisabled();
    await card.getByLabel(l.interval, { exact: true }).fill("60");
    await card.getByRole("button", { name: l.save, exact: true }).click();
    await expect(card.getByLabel(l.interval, { exact: true })).toHaveValue("60");
    expect(state.ui.management.providerCalls).toEqual([]); expect(state.unexpected).toEqual([]);
    expect(state.ui.management.reads.some(path => /activity-plan|daily-preparation|recommendation-topics/.test(path))).toBe(false);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBe(true);
    await page.screenshot({ path: info.outputPath(`basic-settings-${language}.png`), fullPage: true });
  });

  test(`integration state: stored mood, original note, confirmed time, null and scope isolation (${language})`, async ({ page }, info) => {
    const state = await fixture(page, info, language);
    await page.setViewportSize({ width: language === "ko" ? 390 : 960, height: 900 });
    await page.goto(`${worldCharacterRoute()}?view=status`);
    const card = page.getByRole("tabpanel").getByRole("region", { name: "Synthetic Responder", exact: true });
    await expect(card).toContainText(language === "ko" ? "호기심" : "Curious");
    await expect(card).toContainText(state.note);
    await expect(card.locator('time[datetime="2026-10-09T08:01:00Z"]')).toBeVisible();
    await expect(card).not.toContainText("@synthetic_responder");
    const text = await card.innerText();
    expect(text.indexOf(state.note)).toBeLessThan(text.indexOf("Synthetic Responder"));
    const initialReads = state.reads.length; await page.waitForTimeout(1200); expect(state.reads.length).toBe(initialReads);
    state.runtimeKnown = false; await page.reload();
    await expect(card).toContainText(language === "ko" ? "아직 확인된 상태가 없습니다." : "No state has been confirmed yet.");
    await expect(card).not.toContainText(state.note);
    state.runtimeKnown = true; state.confirmedAt = null; state.runtimeDelay = 1500; state.note = "Old scope late note";
    await page.getByRole("tab", { name: language === "ko" ? "프로필" : "Profile", exact: true }).click();
    await page.getByRole("tab", { name: language === "ko" ? "상태" : "Status", exact: true }).click();
    state.runtimeDelay = 0; state.note = "New World scoped note";
    await page.goto(`${worldCharacterRoute(WORLD_AGENT, OTHER_FEED_WORLD)}?view=status`);
    await expect(card).toContainText("New World scoped note");
    await expect(card).toContainText(language === "ko" ? "미확인" : "Unverified");
    await page.waitForTimeout(1800); await expect(card).not.toContainText("Old scope late note");
    expect(state.writes).toEqual([]); expect(state.ui.management.providerCalls).toEqual([]); expect(state.unexpected).toEqual([]);
    await page.evaluate(() => { document.documentElement.style.fontSize = "200%"; });
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBe(true);
    await page.screenshot({ path: info.outputPath(`current-state-${language}.png`), fullPage: true });
  });
}

test("integration create: OFF registration, lost response recovery, sixth step, reload and skip", async ({ page }, info) => {
  const state = await fixture(page, info);
  await page.goto(`/agents/new?worldId=${FEED_WORLD}`);
  await page.getByRole("button", { name: "저장하고 다음", exact: true }).click();
  await page.getByRole("textbox", { name: "이름", exact: true }).fill("등록 시험 캐릭터");
  await page.getByRole("button", { name: "저장하고 다음", exact: true }).click();
  await page.getByRole("textbox", { name: "캐릭터 설명", exact: true }).fill("차분한 도서관에서 약속을 지키는 캐릭터입니다.");
  await page.getByRole("button", { name: "저장하고 다음", exact: true }).click();
  await page.getByRole("button", { name: "저장하고 다음", exact: true }).click();
  state.completeFailure = true;
  await page.getByRole("button", { name: "등록", exact: true }).click();
  await expect(page.getByRole("alert")).toBeVisible();
  await page.getByRole("button", { name: "등록 결과 확인", exact: true }).click();
  await expect(page.getByRole("list", { name: "생성 단계" }).getByRole("listitem")).toHaveCount(6);
  await expect(page.getByRole("region", { name: "활동 설정", exact: true })).toContainText("자율활동 OFF");
  expect(state.registrations).toBe(1); expect(state.completeCalls).toBe(2);
  await page.reload(); await expect(page.getByRole("button", { name: "건너뛰기", exact: true })).toBeVisible();
  expect(state.registrations).toBe(1); expect(state.completeCalls).toBe(3);
  await page.screenshot({ path: info.outputPath("registration-sixth-step.png"), fullPage: true });
  await page.getByRole("button", { name: "건너뛰기", exact: true }).click();
  await expect(page).toHaveURL(new RegExp(`/worlds/${FEED_WORLD}/characters/?$`));
  expect(state.writes.filter(row => /credentials|activity-settings|activate|image-policy/.test(row.path))).toEqual([]);
  expect(state.ui.management.providerCalls).toEqual([]); expect(state.unexpected).toEqual([]);
});

test("integration partial: saved policy survives key failure and dirty cancellation", async ({ page }, info) => {
  const state = await fixture(page, info);
  await page.goto(basicRoute);
  const card = page.getByRole("region", { name: "활동 설정", exact: true });
  await card.getByLabel("활동 간격 (분)", { exact: true }).fill("45");
  await card.getByRole("button", { name: "설정 저장", exact: true }).click();
  const sns = page.getByRole("region", { name: "캐릭터 활동 API key", exact: true }); state.snsFailure = 503;
  await sns.locator('input[type="password"]').fill("synthetic-rejected-key");
  await sns.getByRole("button", { name: "모델 저장", exact: true }).click();
  await expect(sns.getByRole("alert")).toBeVisible();
  await expect(card.getByLabel("활동 간격 (분)", { exact: true })).toHaveValue("45");
  const dialog = page.waitForEvent("dialog"); await page.getByRole("button", { name: "돌아가기", exact: true }).click({ noWaitAfter: true });
  await (await dialog).dismiss(); await expect(page).toHaveURL(new RegExp("autonomy-setup"));
  expect(state.registrations).toBe(0); expect(state.ui.management.providerCalls).toEqual([]); expect(state.unexpected).toEqual([]);
});

test("integration engine: character inheritance and V2 keep CAS and remove state/run UI", async ({ page }, info) => {
  const state = await fixture(page, info);
  await page.goto(`${worldCharacterRoute()}?view=settings`);
  const card = page.getByRole("region", { name: "활동 방식", exact: true });
  await expect(card).not.toContainText(state.note); await expect(card).not.toContainText("최근 실행");
  await expect(card.getByLabel("적용 범위", { exact: true })).toHaveCount(0);
  await card.getByLabel("사용할 방식", { exact: true }).selectOption("inherit");
  await card.getByRole("button", { name: "활동 방식 저장", exact: true }).click();
  await expect(card).toContainText("World 기본값");
  await card.getByLabel("사용할 방식", { exact: true }).selectOption("personalized_graph_v2");
  await card.getByRole("button", { name: "활동 방식 저장", exact: true }).click();
  await expect(card).toContainText("캐릭터 설정");
  expect(state.writes.map(row => row.body.engine)).toEqual([null, "personalized_graph_v2"]);
  expect(state.unexpected).toEqual([]);
});

test("integration home: icon links and World tabs remain without device footer", async ({ page }, info) => {
  const state = await fixture(page, info);
  await page.setViewportSize({ width: 360, height: 800 });
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Angmoo", exact: true })).toBeVisible();
  await expect(page.getByRole("navigation")).toHaveCount(0);
  await expect(page.getByRole("link", { name: /설정/ }).first()).toBeVisible();
  await expect(page.getByRole("link", { name: /Memory/ }).first()).toBeVisible();
  await expect(page.locator('[data-device-scroll-owner="true"]')).toHaveCount(1);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBe(true);
  await page.screenshot({ path: info.outputPath("home-no-footer.png"), fullPage: true });
  await page.goto(`${worldCharacterRoute()}?view=status`);
  await expect(page.getByRole("navigation").getByRole("link")).toHaveCount(5);
  expect(state.unexpected).toEqual([]);
});

test("integration editor: disjoint reconciliation, same-field conflict and runtime draft isolation", async ({ page }, info) => {
  const state = await fixture(page, info);
  await page.goto(basicRoute);
  const card = page.getByRole("region", { name: "활동 설정", exact: true });
  const interval = card.getByLabel("활동 간격 (분)", { exact: true });
  await interval.fill("45");
  const actor = state.ui.management.worlds.get(FEED_WORLD)!.find(row => row.profile.world_character_id === WORLD_AGENT)!;
  state.ui.management.settings.set(`${FEED_WORLD}:${WORLD_AGENT}`, {
    active_hours_start: "09:00", active_hours_end: "02:00", activity_interval_minutes: 30,
    max_posts_per_day: 30, max_comments_per_day: 30, allow_post: true, allow_reply: true, allow_like: false,
  });
  actor.revision++;
  const sns = page.getByRole("region", { name: "캐릭터 활동 API key", exact: true });
  await sns.locator('input[type="password"]').fill("synthetic-reconciliation-key");
  await sns.getByRole("button", { name: "모델 저장", exact: true }).click();
  await expect(interval).toHaveValue("45");
  await expect(card.getByLabel("좋아요", { exact: true })).not.toBeChecked();
  const saved = state.ui.management.settings.get(`${FEED_WORLD}:${WORLD_AGENT}`)!;
  state.ui.management.settings.set(`${FEED_WORLD}:${WORLD_AGENT}`, { ...saved, activity_interval_minutes: 60 }); actor.revision++;
  await card.getByRole("button", { name: "설정 저장", exact: true }).click();
  await expect(card.getByRole("alert")).toContainText("같은 항목이 다른 곳에서 변경되었어요.");
  await expect(interval).toHaveValue("45");
  expect(state.writes.filter(row => row.path.endsWith("activity-settings"))).toHaveLength(0);
  await card.getByRole("button", { name: "최신 값을 확인했어요. 내 입력 유지", exact: true }).click();
  await card.getByRole("button", { name: "설정 저장", exact: true }).click();
  await expect(card).toContainText("설정을 저장했어요.");
  expect(state.writes.filter(row => row.path.endsWith("activity-settings"))).toHaveLength(1);
  expect(state.ui.management.settings.get(`${FEED_WORLD}:${WORLD_AGENT}`)?.allow_like).toBe(false);
  await interval.fill("75");
  await page.evaluate(() => window.dispatchEvent(new Event("angmoo:desktop-runtime-config-changed")));
  await expect(interval).toHaveValue("45");
  expect(state.ui.management.providerCalls).toEqual([]); expect(state.unexpected).toEqual([]);
});

test("integration direct entry: home return and relationship header geometry", async ({ page }, info) => {
  const state = await fixture(page, info);
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/settings");
  await expect(page.getByRole("heading", { name: "설정", exact: true }).first()).toBeVisible();
  const home = page.locator('a[href="/"]').first();
  await expect(home).toBeVisible(); await home.focus(); await page.keyboard.press("Enter");
  await expect(page.getByRole("heading", { name: "Angmoo", exact: true })).toBeVisible();
  await page.goto(`/worlds/${FEED_WORLD}/relationships`);
  const header = page.locator('[data-product-content="relationship-graph"] > header');
  await expect(header.getByRole("heading", { name: "이 World의 관계", exact: true })).toBeVisible();
  const geometry = await header.evaluate(element => {
    const style = getComputedStyle(element), icon = element.firstElementChild!.getBoundingClientRect();
    return { padding: style.paddingLeft, gap: style.gap, icon: [icon.width, icon.height], paragraphs: element.querySelectorAll("p").length };
  });
  expect(geometry).toEqual({ padding: "20px", gap: "12px", icon: [48, 48], paragraphs: 1 });
  expect(state.unexpected).toEqual([]);
});
