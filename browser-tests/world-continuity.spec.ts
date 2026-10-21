import { selectedOwnerRead } from "./fixtures/owner-selection.mjs";
import { expect, test } from "@playwright/test";
import { continuityAgentDetail } from "./continuity-fixture";
import { installIntegrationFixture } from "./home-activity-memory-fixture";
import { WORLD_AGENT } from "./world-character-management-fixture";
import { FEED_WORLD } from "./world-feed-fixture";
import { verifyMemoryRecovery } from "./memory-recovery-fixture";
import { installBackendFixture, json, uiDWorld, uiDOwnerActor, uiDManualPost, uiDManualThread, UI_D_ROOT_POST_ID } from "./continuity-next-fixture";

test("memory: failed save retries the same request and refreshes retained items and evidence", async ({ page }) => {
  const world = uiDWorld();
  await installBackendFixture(page, { deviceWorlds: [world] });
  await verifyMemoryRecovery(page, world.world_id);
});

test("continuity: nested evidence opens the exact later-page reply and its parent", async ({ page }) => {
  const world = uiDWorld();
  await installBackendFixture(page, { worldReads: { [world.world_id]: world } });
  const root = uiDManualPost({ id: UI_D_ROOT_POST_ID, title: "원문", body: "원 게시글", replyCount: 115 });
  const parent = uiDManualPost({ id: "reply-parent", title: "", body: "부모 답글", replyToPostId: root.id });
  const target = uiDManualPost({ id: "reply-target", title: "", body: "근거의 정확한 대댓글", replyToPostId: parent.id, replyCount: 115 });
  const child = uiDManualPost({ id: "reply-child-later-page", title: "", body: "대댓글의 마지막 페이지 답글", replyToPostId: target.id });
  await page.route("**/api/backend/**", async (route) => {
    const url = new URL(route.request().url());
    if (url.pathname.endsWith("/owner-character/selection")) return json(route, selectedOwnerRead(uiDOwnerActor()));
    if (url.pathname.includes("/manual-social/posts/")) {
      const targetId = url.pathname.split("/").at(-1);
      if (targetId === parent.id) return json(route, uiDManualThread(parent, [target], { rootId: root.id }));
      const firstPage = url.searchParams.get("offset") === "0";
      return json(route, uiDManualThread(target, firstPage ? [] : [child], {
        rootId: root.id, pageOffset: firstPage ? 0 : 100, nextOffset: firstPage ? 50 : null,
      }));
    }
    return route.fallback();
  });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto(`/worlds/${world.world_id}/posts/${target.id}`);
  await expect(page.getByRole("heading", { name: "답글 115" })).toBeVisible();
  const evidence = page.locator(`[data-social-post-row="${target.id}"]`);
  await expect(evidence).toContainText("근거의 정확한 대댓글");
  await expect(evidence).toBeInViewport();
  expect(await evidence.evaluate((element) => element.scrollWidth <= element.clientWidth)).toBe(true);
  await expect(page.locator(`[data-social-post-row="${child.id}"]`)).toContainText(child.body);
  await page.getByRole("link", { name: /부모 게시글 보기/ }).first().click();
  await expect(page).toHaveURL(new RegExp(`/posts/${parent.id}$`));
  await expect(page.locator(`[data-social-post-row="${parent.id}"]`)).toContainText("부모 답글");
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


test("continuity: World activity settings preserve saved policy on provider and transport failure", async ({ page }, info) => {
  const state = await installIntegrationFixture(page, false, String(info.project.use.baseURL), "ko");
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/characters/character-" + WORLD_AGENT + "/worlds/" + FEED_WORLD + "/autonomy-setup");
  const card = page.getByRole("region", { name: "활동 설정", exact: true });
  await expect(card.getByLabel("활동 간격 (분)", { exact: true })).toHaveValue("30");
  await card.getByLabel("활동 간격 (분)", { exact: true }).fill("45");
  state.policyFailure = 502;
  await card.getByRole("button", { name: "설정 저장", exact: true }).click();
  await expect(card.getByRole("alert")).toBeVisible();
  await expect(card.getByLabel("활동 간격 (분)", { exact: true })).toHaveValue("45");
  state.policyFailure = 0;
  await card.getByRole("button", { name: "설정 저장", exact: true }).click();
  await expect(card).toContainText("설정을 저장했어요.");
  await page.reload();
  await expect(card.getByLabel("활동 간격 (분)", { exact: true })).toHaveValue("45");
  const sns = page.getByRole("region", { name: "캐릭터 활동 API key", exact: true });
  state.snsFailure = 502;
  await sns.locator('input[type="password"]').fill("synthetic-key-only");
  await sns.getByRole("button", { name: "모델 저장", exact: true }).click();
  await expect(sns.getByRole("alert")).toBeVisible();
  await expect(card.getByLabel("활동 간격 (분)", { exact: true })).toHaveValue("45");
  await expect(card.getByRole("button", { name: "자율활동 켜기", exact: true })).toBeDisabled();
  expect(state.ui.management.providerCalls).toEqual([]);
  expect(state.unexpected).toEqual([]);
});


test("retrieval diagnostics: bounded basic view and opt-in details on narrow screen", async ({ page }) => {
  const world = uiDWorld();
  await installBackendFixture(page, { worldReads: { [world.world_id]: world } });
  const worldId = world.world_id, threadId = "diagnostic-thread";
  const worldThread = {
    id: threadId,
    world_id: worldId,
    requester: {
      world_character_id: "wc-p8-l-d-owner",
      character_id: "character-p8-l-d-owner",
      display_name: "사용자 앵무",
      handle: "owner_bird",
      avatar_url: null,
      banner_url: null,
      role_key: "student",
      control_mode: "owner_controlled",
      profile_capability: "available",
    },
    responding: {
      world_character_id: "wc-p8-l-d-friend",
      character_id: "character-p8-l-d-friend",
      display_name: "친구 앵무",
      handle: "friend_bird",
      avatar_url: null,
      banner_url: null,
      role_key: "mentor",
      control_mode: "autonomous",
      profile_capability: "available",
    },
    selected_model: "gemini-3.1-flash-lite",
    selected_thinking_level: "high",
    default_thinking_level: "high",
    default_model: "gemini-3.1-flash-lite",
    model_binding_mode: "default",
    last_message_at: "2026-09-01T03:04:00Z",
    created_at: "2026-09-01T03:00:00Z",
    latest_message: {
      id: 2,
      thread_id: threadId,
      role: "assistant",
      content: "World 경계를 기억하고 있어요.",
      model: "gemini-2.5-flash-lite",
      status: "ok",
      error_code: null,
      created_at: "2026-09-01T03:04:00Z",
    },
    messages: [
      {
        id: 1,
        thread_id: threadId,
        role: "user",
        content: "여기는 어느 World야?",
        model: "gemini-2.5-flash-lite",
        status: "ok",
        error_code: null,
        created_at: "2026-09-01T03:03:00Z",
      },
      {
        id: 2,
        thread_id: threadId,
        role: "assistant",
        content: "World 경계를 기억하고 있어요.",
        model: "gemini-2.5-flash-lite",
        status: "ok",
        error_code: null,
        created_at: "2026-09-01T03:04:00Z",
      },
    ],
    evidence_summaries: [],
  };

  let enabled = false;
  await page.route("**/api/backend/**", async route => {
    const url = new URL(route.request().url());
    if (url.pathname.endsWith("/diagnostics/capture")) {
      enabled = route.request().postDataJSON().enabled;
      return json(route, { enabled, remaining: enabled ? 10 : 0, expires_at: null });
    }
    if (url.pathname.endsWith("/diagnostics")) return json(route, {
      world_id: worldId, thread_id: threadId, request_id: "fixture-request", request_state: "committed",
      status: "available", record: { version: "chat-retrieval-diagnostics.v1", omitted_events: 0,
        events: [{ event: "router", route: "CANONICAL" }, { event: "step", executed: false, skipped: true, reason: "canonical_dependency_empty" }, { event: "crg_input", items: 0 }] },
      capture: { enabled, remaining: enabled ? 9 : 0, expires_at: null },
      details: enabled ? [{ search_text: "synthetic private query" }] : null,
    });
    if (url.pathname.endsWith(`/threads/${threadId}`)) return json(route, worldThread);
    if (url.pathname.endsWith("/requests/latest")) return json(route, { response_request: null });
    return route.fallback();
  });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto(`/worlds/${worldId}/chat/${threadId}`);
  await page.getByRole("button", { name: "기억과 진단 보기", exact: true }).click();
  await expect(page.getByRole("dialog", { name: "기억과 진단", exact: true })).toBeVisible();
  await page.getByText("검색 진단 · 문제 해결", { exact: true }).click();
  await expect(page.getByText("답변 생성에 근거 전달", { exact: true })).toBeVisible();
  await expect(page.getByText("앞 단계 결과가 없어 건너뜀", { exact: true })).toBeVisible();
  await expect(page.getByText("synthetic private query")).toHaveCount(0);
  await page.getByRole("button", { name: "현재 대화의 상세 진단 켜기", exact: true }).click();
  await page.getByText("수집한 검색 조건 보기", { exact: true }).click();
  await expect(page.getByText(/synthetic private query/)).toBeVisible();
  await page.getByRole("button", { name: "상세 진단 끄고 기록 지우기", exact: true }).click();
  await expect(page.getByText(/synthetic private query/)).toHaveCount(0);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
});
