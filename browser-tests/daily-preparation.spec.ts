import { expect, test } from "@playwright/test";
import { continuityAgentDetail } from "./continuity-fixture";
import { installBackendFixture, json } from "./continuity-next-fixture";

const staticShell = process.env.ANGMOO_DAILY_STATIC === "1";
test("daily preparation keeps registration free and exposes explicit recovery", async ({ page }, testInfo) => {
  if (staticShell) await page.addInitScript(() => Object.assign(window, { __ANGMOO_RUNTIME_CONFIG__: {
    profile: "tauri-static", apiBaseUrl: "http://127.0.0.1:8080", graphProvider: "ladybug", launchToken: "daily-fixture-token-0000000000000",
  } }));
  else await installBackendFixture(page);
  const characterId = "daily-bird", worldId = "daily-world", actorId = "daily-actor";
  let agent = { ...continuityAgentDetail(characterId), credential: { id: "fixture", enabled: true, provider: "google", model: "gemini-3.1-flash-lite" },
    activity_profile_readiness: { ready: false, source: "legacy_tendency" } };
  let runtimeMode = "legacy_resident_v1";
  let generated = false;
  const writes: string[] = [];
  const plan = { id: "plan", version: 1, local_date: "2026-09-28", items: ["dawn", "morning", "afternoon", "evening"].map((part, i) => ({
    id: part, daypart: part, title: ["가볍게 쉬기", "책 정리", "산책", "독서"][i], activity_seed: "현재 시간에 맞춰 천천히 진행", status: i < 2 ? "skipped" : "planned",
  })) };
  await page.route(staticShell ? "http://127.0.0.1:8080/api/v1/**" : "**/api/backend/**", async route => {
    const path = new URL(route.request().url()).pathname.replace(/^\/api\/(backend|v1)/, "");
    const method = route.request().method();
    if (method !== "GET") writes.push(`${method} ${path}`);
    if (path === "/auth/me") return json(route, { id: "owner", display_name: "Owner", profile_setup_completed: true, is_admin: true, feed_content_filter: "all" });
    if (path === `/agents/${characterId}`) return json(route, agent);
    if (path === `/worlds/${worldId}`) return json(route, { id: worldId, name: "SNS", timezone: "Asia/Seoul", roles: [], status: "published" });
    if (path === `/worlds/${worldId}/characters/${characterId}`) return json(route, { id: actorId, world_id: worldId, character_id: characterId, role_key: "no_specific_role", status: "active", activity_runtime_mode: runtimeMode });
    if (path.endsWith("/activity-runtime-mode")) {
      expect(method).toBe("PATCH");
      runtimeMode = route.request().postDataJSON().activity_runtime_mode;
      agent = { ...agent, activity_profile_readiness: { ready: true, source: "daily_preparation" } };
      return json(route, { activity_runtime_mode: runtimeMode, autonomous_enabled: false });
    }
    if (path.endsWith("/autonomy-setup")) return json(route, { preparation_contract: "daily-plan-v1", autonomy_ready: true, state: "ready", active_profile: null, active_repertoire: null });
    if (path.endsWith("/daily-preparation")) {
      if (method === "POST") { expect(route.request().postDataJSON().request_id).toBeTruthy(); generated = true; }
      return json(route, { world_character_id: actorId, local_date: "2026-09-28", plan_state: generated ? "ready" : "failed", topic_state: "ready", plan_id: generated ? "plan" : null,
        plan_version: generated ? 1 : null, request_state: generated ? "ready" : "failed", reason_code: generated ? null : "preparation_attempts_exhausted", attempt_count: 4 });
    }
    if (path.endsWith("/activity-plan")) return generated ? json(route, plan) : json(route, { detail: "not_found" }, 404);
    if (path.endsWith("/activate") || path.endsWith("/deactivate")) { agent = { ...agent, settings: { ...agent.settings, auto_enabled: path.endsWith("/activate") } }; return json(route, agent); }
    if (path.includes("recommendation-topics")) return json(route, { state: "ready", topics: [{ id: "books", name: "독서", scope: "common" }], recent_deliveries: [], recent_feed: [], approval_required: false });
    if (path.includes("personalized") || path.includes("activity-state")) return json(route, { effective_mode: "personalized_graph_v2", effective_source: "global", character_override: null, state: null, runs: [] });
    if (staticShell) return json(route, {});
    return route.fallback();
  });
  await page.setViewportSize({ width: 430, height: 900 });
  await page.goto(`/characters/${characterId}/worlds/${worldId}/autonomy-setup`);
  await expect(page.getByRole("heading", { name: "오늘 하루 계획" })).toBeVisible();
  await expect(page.getByText("2026-09-28 · 오늘 일과 생성 실패")).toBeVisible();
  expect(writes).toEqual([]);
  await expect(page.getByRole("button", { name: "자율활동 시작", exact: true })).toBeDisabled();
  await page.getByRole("button", { name: "일과 활동 방식 사용", exact: true }).click();
  await expect(page.getByRole("button", { name: "자율활동 시작", exact: true })).toBeEnabled();
  expect(writes).toEqual([`PATCH /characters/${characterId}/worlds/${worldId}/activity-runtime-mode`]);
  await expect(page.getByText("World 커뮤니티 프로필", { exact: true })).toHaveCount(0);
  await page.getByRole("button", { name: "오늘 일과 다시 만들기", exact: true }).click();
  await expect(page.getByText("2026-09-28 · 오늘 일과 준비됨")).toBeVisible();
  await expect(page.getByRole("heading", { name: "새벽 · 00:00–06:00" })).toBeVisible();
  await expect(page.getByText("시간이 지나 실행하지 않음")).toHaveCount(2);
  await expect(page.getByRole("button", { name: "자율활동 시작", exact: true })).toBeVisible();
  expect(writes.filter(value => value.endsWith("/daily-preparation"))).toHaveLength(1);
  expect(writes.some(value => /preflight|generate|approve/.test(value))).toBe(false);
  await page.screenshot({ path: testInfo.outputPath("daily-preparation.png"), fullPage: true });
});
