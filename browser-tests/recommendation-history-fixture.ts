import { expect, test, type Page } from "@playwright/test";
import { staticAgentDetail } from "./agent-detail-fixture";

const worldId = "history-world", wcId = "history-wc", characterId = "history-character";
const base = {
  world_id: worldId, world_character_id: wcId, state: "ready", topics: [],
  key_world_character_id: wcId, model: "fixture", thinking_level: "high",
  last_code: null, approval_required: false,
  recent_feed: [{ post_id: "legacy", title: "과거 관찰은 표시 금지", lane: null, action: "comment" }],
};

function history() {
  return [{ delivery_id: "one", recorded_at: "2026-09-19T00:07:46Z",
    recorded_post_count: 5, visible_post_count: 5, unavailable_post_count: 0, is_partial: false,
    posts: [
      { post_id: "one", title: "실제 전달된 축구 글", lane: "latest", sources: ["latest"], selected_action: "comment", result_state: "succeeded" },
      { post_id: "two", title: "선택한 글", lane: "interest", sources: ["interest"], selected_action: "comment", result_state: "selected" },
      { post_id: "three", title: "지나간 글", lane: "explore", sources: ["explore"], selected_action: null, result_state: "no_action" },
      { post_id: "four", title: "실패한 글", lane: "relation", sources: ["relation"], selected_action: "comment", result_state: "failed" },
      { post_id: "five", title: "결과 없는 글", lane: null, sources: [], selected_action: null, result_state: "unrecorded" },
    ] },
    { delivery_id: "two", recorded_at: "2026-09-18T00:07:46Z", recorded_post_count: 1,
      visible_post_count: 0, unavailable_post_count: 1, is_partial: false, posts: [] }];
}

export function recommendationHistoryTests(staticMode: boolean, bootstrap: (page: Page) => Promise<void> = async () => {}) {
  const prefix = staticMode ? "/api/v1" : "/api/backend";
  async function setup(page: Page) {
    await bootstrap(page);
    const methods: string[] = [];
    const state: { body: object; status: number; defer?: Promise<void>; reads: number } = {
      body: { ...base, recent_deliveries: [] }, status: 200, reads: 0,
    };
    await page.route(`**${prefix}/**`, async route => {
      const url = new URL(route.request().url());
      if (url.pathname === `${prefix}/agents/${characterId}`) {
        const agent = staticAgentDetail(characterId);
        return route.fulfill({ json: { ...agent, activity_profile_readiness: {
          ...agent.activity_profile_readiness, world_id: worldId, world_character_id: wcId,
        } } });
      }
      if (url.pathname === `${prefix}/worlds/${worldId}/recommendation-topics`) {
        methods.push(route.request().method()); state.reads++;
        const { body, status, defer } = state;
        if (defer) await defer;
        await route.fulfill({ json: body, status }).catch(() => {}); // Aborted prior refresh is expected.
        return;
      }
      return route.fallback();
    });
    await page.goto(`/agents/${characterId}?tab=settings`);
    return { state, methods };
  }

  test("character topics remain scoped and refresh without retired Feed history", async ({ page }, testInfo) => {
    const { state, methods } = await setup(page);
    const panel = page.getByRole("region", { name: "캐릭터 관심 주제", exact: true });
    await expect(panel.getByText("등록된 주제가 없습니다.", { exact: true })).toBeVisible();
    state.body = { ...base, topics: [{ id: "topic-one", name: "실제 준비된 축구 주제", scope: "world" }],
      recent_deliveries: history() };
    await panel.getByRole("button", { name: "상태 새로고침", exact: true }).click();
    await expect(panel.getByText("실제 준비된 축구 주제", { exact: true })).toBeVisible();
    await expect(page.getByLabel("최근 전달된 Feed", { exact: true })).toHaveCount(0);
    await expect(page.getByText("과거 관찰은 표시 금지")).toHaveCount(0);
    await expect(page.getByText("실제 전달된 축구 글", { exact: true })).toHaveCount(0);
    await page.setViewportSize({ width: 360, height: 800 });
    expect(await panel.evaluate(node => node.scrollWidth <= node.clientWidth + 1)).toBe(true);
    await page.screenshot({ path: testInfo.outputPath("recommendation-topics-mobile.png") });
    expect(methods.length).toBeGreaterThanOrEqual(2);
    expect(methods.every(method => method === "GET")).toBe(true);
  });

  test("topic readiness stays distinct from historical Feed execution results", async ({ page }, testInfo) => {
    const { state, methods } = await setup(page);
    const panel = page.getByRole("region", { name: "캐릭터 관심 주제", exact: true });
    const refresh = panel.getByRole("button", { name: "상태 새로고침", exact: true });
    for (const [value, label] of [["pending", "주제 준비 전"], ["running", "주제 만드는 중"],
      ["failed", "주제 생성 실패 · 이전 결과 유지"], ["stale", "설정 변경됨 · 기존 주제 사용 중"]]) {
      state.body = { ...base, state: value, recent_deliveries: history() };
      await refresh.click();
      await expect(panel.getByText(label, { exact: true })).toBeVisible();
      await expect(page.getByRole("region", { name: "Feed 실행 상태", exact: true })).toHaveCount(0);
    }
    expect(methods.every(method => method === "GET")).toBe(true);
    await page.screenshot({ path: testInfo.outputPath("topic-readiness.png") });
  });

  test("topic refresh rejects failed and late responses without legacy Feed fallback", async ({ page }) => {
    const { state, methods } = await setup(page);
    const panel = page.getByRole("region", { name: "캐릭터 관심 주제", exact: true });
    const refresh = panel.getByRole("button", { name: "상태 새로고침", exact: true });
    state.status = 502;
    await refresh.click();
    await expect(panel.getByRole("alert")).toBeVisible();
    state.status = 200; state.body = base;
    await refresh.click();
    await expect(panel.getByText("주제 준비됨", { exact: true })).toBeVisible();
    let release!: () => void;
    state.defer = new Promise<void>(resolve => { release = resolve; });
    const before = state.reads;
    await refresh.click();
    await expect.poll(() => state.reads).toBeGreaterThan(before);
    state.defer = undefined;
    state.body = { ...base, topics: [{ id: "latest-topic", name: "최신 주제만 표시", scope: "world" }] };
    await refresh.click();
    await expect(panel.getByText("최신 주제만 표시", { exact: true })).toBeVisible();
    release();
    await expect(panel.getByText("최신 주제만 표시", { exact: true })).toBeVisible();
    await expect(page.getByText("과거 관찰은 표시 금지")).toHaveCount(0);
    expect(methods.every(method => method === "GET")).toBe(true);
  });
}
