import { expect, test, type Page } from "@playwright/test";
import { staticAgentDetail } from "./agent-detail-fixture";

export function personalizedActivityTests(staticMode: boolean, bootstrap: (page: Page) => Promise<void> = async () => {}) {
  test("personalized activity preserves old runs and shows combined stages in server order", async ({ page }) => {
    await bootstrap(page);
    const prefix = staticMode ? "/api/v1" : "/api/backend";
    const worldId = "activity-world", actorId = "activity-actor", characterId = "activity-character";
    const state = { status: 200, stage: "DecisionDraft", version: 2 };
    const path = { status: "completed", public_action_count: 1, selected_count: null, recall_count: null, state_status: null, reason: null };
    await page.route(`**${prefix}/**`, async route => {
      const pathname = new URL(route.request().url()).pathname;
      if (pathname === `${prefix}/agents/${characterId}`) return route.fulfill({ json: staticAgentDetail(characterId) });
      if (pathname === `${prefix}/worlds/${worldId}`) return route.fulfill({ json: { id: worldId, name: "활동 검증 공간", tagline: "합성 자료", timezone: "Asia/Seoul", roles: [] } });
      if (pathname === `${prefix}/worlds/${worldId}/characters/${characterId}`) return route.fulfill({ json: { id: actorId, world_id: worldId, character_id: characterId, role_key: null } });
      if (pathname === `${prefix}/world-characters/${actorId}/autonomy-setup`) return route.fulfill({ json: { state: "not_started", autonomy_ready: false } });
      if (pathname.endsWith(`/world-characters/${actorId}/autonomy-setup/preflight`)) return route.fulfill({ json: { profile_max_output_tokens: 0, repertoire_max_output_tokens: 0, credential_ready: false } });
      if (pathname === `${prefix}/worlds/${worldId}/world-characters/${actorId}/activity-runtime`) return route.fulfill({ status: state.status, json: state.status === 200 ? {
        world_id: worldId, world_character_id: actorId, autonomous_enabled: false, control_mode: "autonomous",
        effective: { engine: "personalized_graph_v2", source: "default", version: 0 },
        policies: Object.fromEntries(["character", "world", "global"].map(key => [key, { engine: null, version: 0 }])),
        current_state: { known: false }, runs: [{ activity_id: "run", engine: "personalized_graph_v2", status: "waiting", stage: state.stage,
          contract_version: state.version, execution_order: state.version === 2 ? ["inbox", "feed", "routine"] : ["inbox", "routine", "feed"],
          started_at: "2026-09-25T03:00:00Z", public_action_count: null,
          paths: { inbox: path, routine: path, feed: { ...path, status: "no_action", public_action_count: 0, reason: "feed_target_stale" } } }],
      } : { detail: "fixture_unavailable" } });
      return route.fallback();
    });
    await page.goto(`/characters/${characterId}/worlds/${worldId}/autonomy-setup`);
    const panel = page.getByRole("region", { name: "개인화 활동 방식과 현재 상태" });
    await expect(panel.getByText("반응을 정하고 글 작성 중", { exact: true })).toBeVisible();
    await expect(panel.getByText(/선택한 글을 더 이상 사용할 수 없어/)).toBeVisible();
    const paths = panel.locator("p").filter({ hasText: /선택 미기록/ });
    await expect(paths).toHaveCount(3);
    expect(await paths.allTextContents()).toEqual([expect.stringContaining("받은 대화"), expect.stringContaining("피드"), expect.stringContaining("일과")]);
    state.version = 1; state.stage = "ActionPlanner";
    await panel.getByRole("button", { name: "상태 새로고침" }).click();
    await expect(panel.getByText("반응 판단 중", { exact: true })).toBeVisible();
    expect(await paths.allTextContents()).toEqual([expect.stringContaining("받은 대화"), expect.stringContaining("일과"), expect.stringContaining("피드")]);
    state.stage = "future-stage";
    await panel.getByRole("button", { name: "상태 새로고침" }).click();
    await expect(panel.getByText("활동 진행 중", { exact: true })).toBeVisible();
    state.status = 503;
    await panel.getByRole("button", { name: "상태 새로고침" }).click();
    await expect(panel.getByRole("alert")).toBeVisible();
  });
}
