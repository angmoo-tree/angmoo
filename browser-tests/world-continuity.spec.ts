import { expect, test } from "@playwright/test";
import { continuityAgentDetail } from "./continuity-fixture";
import { verifyMemoryRecovery } from "./memory-recovery-fixture";
import { installBackendFixture, json, uiDWorld, uiDOwnerActor, uiDManualPost, uiDManualFeed, UI_D_ROOT_POST_ID } from "./continuity-next-fixture";

test("memory: failed selection retry refreshes retained items and evidence", async ({ page }) => {
  const world = uiDWorld();
  await installBackendFixture(page, { deviceWorlds: [world] });
  await verifyMemoryRecovery(page, world.world_id);
});

test("continuity: nested evidence opens the exact later-page reply and its parent", async ({ page }) => {
  const world = uiDWorld();
  await installBackendFixture(page, { worldReads: { [world.world_id]: world } });
  const root = uiDManualPost({ id: UI_D_ROOT_POST_ID, title: "원문", body: "원 게시글", replyCount: 115 });
  const parent = uiDManualPost({ id: "reply-parent", title: "", body: "부모 답글", replyToPostId: root.id });
  const target = uiDManualPost({ id: "reply-target", title: "", body: "근거의 정확한 대댓글", replyToPostId: parent.id });
  await page.route("**/api/backend/**", async (route) => {
    const url = new URL(route.request().url());
    if (url.pathname.endsWith("/owner-character")) return json(route, uiDOwnerActor());
    if (url.pathname.includes("/manual-social/posts/")) {
      const targetId = url.pathname.split("/").at(-1);
      const firstPage = url.searchParams.get("offset") === "0" || targetId === parent.id;
      return json(route, { ...uiDManualFeed((firstPage ? [root, parent] : [root, target]).map((item) => ({...item, thread_root_post_id: root.id}))),
        root_post_id: root.id, target_post_id: targetId, page_offset: firstPage ? 0 : 100,
        next_offset: firstPage ? 50 : null });
    }
    return route.fallback();
  });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto(`/worlds/${world.world_id}/posts/${target.id}`);
  await expect(page.getByRole("heading", { name: "대꾸 115" })).toBeVisible();
  const evidence = page.getByRole("article", { name: "근거가 가리키는 답글" });
  await expect(evidence).toContainText("근거의 정확한 대댓글");
  await expect(evidence).toBeInViewport();
  expect(await evidence.evaluate((element) => element.scrollWidth <= element.clientWidth)).toBe(true);
  await page.getByRole("link", { name: /부모 답글 보기/ }).click();
  await expect(page).toHaveURL(new RegExp(`/posts/${parent.id}$`));
  await expect(page.getByRole("article", { name: "근거가 가리키는 답글" })).toContainText("부모 답글");
});


test("continuity: persona overflow stays editable with a field error and prevents saving", async ({ page }) => {
  await installBackendFixture(page);
  const agent = continuityAgentDetail("persona-limit-bird");
  let saved = 0;
  await page.route("**/api/backend/**", async (route) => {
    const url = new URL(route.request().url());
    if (url.pathname === "/api/backend/agents/persona-limit-bird") return json(route, agent);
    if (url.pathname.endsWith("/persona")) { saved++; return json(route, agent); }
    if (url.pathname.endsWith("/lore-sources")) return json(route, { items: [] });
    return route.fallback();
  });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/agents/persona-limit-bird?tab=settings");
  const personality = page.getByRole("textbox", { name: "성격", exact: true });
  await expect(personality).toBeVisible();
  await personality.fill("😀".repeat(6001));
  await expect(personality).toHaveValue("😀".repeat(6001));
  await expect(personality).toHaveAttribute("aria-invalid", "true");
  await expect(page.getByRole("alert").filter({ hasText: "1자 초과" })).toBeVisible();
  const form = personality.locator("xpath=ancestor::form");
  await form.locator('button[type="submit"]').click();
  expect(saved).toBe(0);
  await personality.fill("😀".repeat(6000));
  await expect(personality).not.toHaveAttribute("aria-invalid", "true");
  await form.locator('button[type="submit"]').click();
  await expect.poll(() => saved).toBe(1);
});


test("continuity: approved activity remains visible during optional generation and candidate rejection", async ({ page }) => {
  await installBackendFixture(page);
  const characterId = "continuity-bird", worldId = "continuity-world", entryId = "continuity-entry";
  const profile = { id: "approved-profile", world_character_id: entryId, status: "ready",
    visible_summary: "현재 승인된 프로필", core_interests: [], adjacent_interests: [], avoid_topics: [],
    discovery_openness: 0.5, search_keywords: [], action_profile: {}, provider: "fixture", model: "fixture",
    generated_at: "2026-09-08T00:00:00Z", approved_at: "2026-09-08T00:00:00Z" };
  const repertoire = { id: "approved-repertoire", world_character_id: entryId, status: "ready",
    candidates: Array.from({length: 40}, (_, index) => ({ id: `candidate-${index}`, repertoire_id: "approved-repertoire",
      ordinal: index % 10, daypart: ["dawn", "morning", "afternoon", "evening"][Math.floor(index / 10)],
      title: `일과 ${index}`, activity_seed: "기존 활동", activity_kind: "duty", social_mode: "solo", enabled: true })),
    provider: "fixture", model: "fixture", generated_at: profile.generated_at, approved_at: profile.approved_at };
  let setup = { world_character_id: entryId, world_id: worldId, character_id: characterId, state: "ready",
    autonomy_ready: true, autonomous_enabled: false, reused: false, can_retry_stage: null,
    can_approve: false, can_regenerate: true, can_reject: false, persona_changed: true, safe_reason_code: null,
    profile, repertoire, active_profile: profile, active_repertoire: repertoire };
  const writes: Array<Record<string, unknown>> = [];
  await page.route("**/api/backend/**", async (route) => {
    const url = new URL(route.request().url());
    if (url.pathname === `/api/backend/agents/${characterId}`) return json(route, continuityAgentDetail(characterId));
    if (url.pathname === `/api/backend/worlds/${worldId}`) return json(route, { id: worldId, name: "활동 유지 World", tagline: "fixture", timezone: "Asia/Seoul", roles: [], places: [] });
    if (url.pathname === `/api/backend/worlds/${worldId}/characters/${characterId}`) return json(route,
      { id: entryId, world_id: worldId, character_id: characterId, membership_id: "fixture", role_key: "no_specific_role", status: "active", autonomous_enabled: false, version: 1 });
    if (url.pathname.endsWith("/autonomy-setup/preflight")) return json(route, {
      world_character_id: entryId, world_id: worldId, character_id: characterId, provider: "fixture", model: "fixture",
      credential_ready: true, logical_call_count: 2, physical_request_count: 3, profile_max_output_tokens: 2048,
      repertoire_max_output_tokens: 12288, reused: false, safe_reason_code: null });
    if (url.pathname.endsWith("/autonomy-setup/generate")) {
      writes.push(route.request().postDataJSON());
      setup = { ...setup, can_approve: true, can_reject: true,
        profile: {...profile, id: "review-profile", status: "draft", visible_summary: "새 후보 프로필"},
        repertoire: {...repertoire, id: "review-repertoire", status: "draft"} };
      return json(route, setup);
    }
    if (url.pathname.endsWith("/autonomy-setup/reject")) {
      writes.push(route.request().postDataJSON());
      setup = { ...setup, can_approve: false, can_reject: false };
      return json(route, setup);
    }
    if (url.pathname.endsWith("/autonomy-setup")) return json(route, setup);
    return route.fallback();
  });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto(`/characters/${characterId}/worlds/${worldId}/autonomy-setup`);
  await expect(page.getByLabel("현재 사용하는 승인 결과")).toContainText("현재 승인된 프로필");
  const generate = page.getByRole("button", { name: "프로필·일과 다시 만들기" });
  await expect(generate).toBeDisabled();
  await page.getByRole("checkbox", { name: /캐릭터 키를 사용해 World 전용 프로필/ }).check();
  await generate.click();
  await expect(page.getByText("새 후보 프로필", { exact: true })).toBeVisible();
  await expect(page.getByLabel("현재 사용하는 승인 결과")).toContainText("현재 승인된 프로필");
  expect(writes[0].regenerate).toBe(true);
  await page.getByRole("button", { name: "후보 거절", exact: true }).click();
  await expect(page.getByRole("button", { name: "후보 거절", exact: true })).toHaveCount(0);
  expect(writes[1].profile_id).toBe("review-profile");
  expect(writes[1].repertoire_id).toBe("review-repertoire");
  await expect(page.getByLabel("현재 사용하는 승인 결과")).toContainText("현재 승인된 프로필");
  await generate.click();
  await expect.poll(() => writes.length).toBe(3);
  expect(writes[2].idempotency_key).not.toBe(writes[0].idempotency_key);
  await expect(page.getByLabel("현재 사용하는 승인 결과")).toContainText("현재 승인된 프로필");
  await page.route("**/autonomy-setup/generate", (route) => json(route, { detail: { code: "provider_failed" } }, 502));
  await generate.click();
  await expect(page.locator("#world-setup-generation-error")).toBeVisible();
  await expect(generate).toBeEnabled();
});
