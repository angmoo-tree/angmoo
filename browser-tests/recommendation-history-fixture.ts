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

  test("recommendation history uses completed rounds and refresh is read-only", async ({ page }, testInfo) => {
    const { state, methods } = await setup(page);
    const panel = page.getByLabel("최근 전달된 Feed", { exact: true });
    await expect(panel.getByText("아직 전달된 글이 없습니다.", { exact: true })).toBeVisible();
    await expect(page.getByText("과거 관찰은 표시 금지")).toHaveCount(0);
    state.body = { ...base, recent_deliveries: history() };
    await page.getByRole("button", { name: "상태 새로고침", exact: true }).click();
    await expect(panel.getByText("최신글 · 댓글 작성 완료", { exact: true })).toBeVisible();
    await expect(panel.getByText("관심사 · 댓글 선택 · 실행 결과 확인 불가", { exact: true })).toBeVisible();
    await expect(panel.getByText("탐색 · 읽고 지나감", { exact: true })).toBeVisible();
    await expect(panel.getByText("관계 · 댓글 처리 실패", { exact: true })).toBeVisible();
    await expect(panel.getByText("출처 기록 없음 · 전달됨 · 반응 결과 확인 불가", { exact: true })).toBeVisible();
    await expect(panel.locator("details")).toHaveCount(2);
    await expect(panel.locator("details").nth(1)).not.toHaveAttribute("open", "");
    const summary = panel.locator("summary").nth(1);
    await summary.focus(); await page.keyboard.press("Enter");
    await expect(panel.getByText("현재 표시할 수 있는 글이 없습니다.")).toBeVisible();
    await page.setViewportSize({ width: 360, height: 800 });
    await panel.scrollIntoViewIfNeeded();
    expect(await summary.evaluate(node => node.getBoundingClientRect().height)).toBeGreaterThanOrEqual(44);
    expect(await panel.evaluate(node => node.scrollWidth <= node.clientWidth)).toBe(true);
    // Element screenshots scroll behind the existing sticky Agent header. Capture
    // the real viewport after placing the history heading below that header.
    await panel.evaluate(node => {
      const owner = node.closest<HTMLElement>('[data-device-scroll-owner="true"]');
      const header = node.closest("section.min-h-screen")?.querySelector(".sticky");
      if (owner && header) owner.scrollTop -= header.getBoundingClientRect().bottom + 8 - node.getBoundingClientRect().top;
    });
    await page.screenshot({ path: testInfo.outputPath("recommendation-history-mobile.png") });
    expect(methods.length).toBeGreaterThanOrEqual(2);
    expect(methods.every(method => method === "GET")).toBe(true);
  });

  test("recommendation history handles failed old and late responses without legacy fallback", async ({ page }) => {
    const { state, methods } = await setup(page);
    const panel = page.getByLabel("최근 전달된 Feed", { exact: true });
    const refresh = page.getByRole("button", { name: "상태 새로고침", exact: true });
    await expect(panel.getByText("아직 전달된 글이 없습니다.", { exact: true })).toBeVisible();
    state.status = 503;
    await refresh.click();
    await expect(panel.getByRole("alert")).toBeVisible();
    await expect(panel.getByText("아직 전달된 글이 없습니다.", { exact: true })).toHaveCount(0);
    state.status = 200; state.body = base;
    await refresh.click();
    await expect(panel.getByText(/앱과 서버 버전을 확인/)).toBeVisible();
    await expect(page.getByText("과거 관찰은 표시 금지")).toHaveCount(0);
    let release!: () => void;
    state.defer = new Promise<void>(resolve => { release = resolve; });
    const before = state.reads;
    await refresh.click();
    await expect.poll(() => state.reads).toBeGreaterThan(before);
    await expect(panel.getByText("전달 이력 확인 중")).toBeVisible();
    state.defer = undefined; state.body = { ...base, recent_deliveries: history() };
    await refresh.click();
    await expect(panel.getByText("실제 전달된 축구 글", { exact: true })).toBeVisible();
    release();
    await expect(panel.getByText("실제 전달된 축구 글", { exact: true })).toBeVisible();
    expect(methods.every(method => method === "GET")).toBe(true);
  });
}
