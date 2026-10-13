import { expect, test, type Page, type Route } from "@playwright/test";
import { uiDWorld } from "../continuity-next-fixture";

type GraphPhase =
  | "ready"
  | "empty"
  | "degraded"
  | "unavailable"
  | "provider-error";

const OWNER = {
  id: "local-owner",
  email: null,
  display_name: "Local Owner",
  display_name_updated_at: null,
  display_name_change_available_at: null,
  profile_setup_completed: true,
  feed_content_filter: "all",
  is_admin: true,
  ui_language: "ko",
  ui_preference_revision: 0,
};

export function graphRead(phase: Exclude<GraphPhase, "provider-error">) {
  const hasRelationship = phase !== "empty";
  return {
    world_id: "world-ui-e-graph",
    center_world_character_id: "wc-ui-e-center",
    nodes: [
      {
        world_character_id: "wc-ui-e-center",
        character_id: "character-ui-e-center",
        display_name: "중심 앵무",
        is_center: true,
      },
      ...(hasRelationship
        ? [
            {
              world_character_id: "wc-ui-e-peer",
              character_id: "character-ui-e-peer",
              display_name: "친구 앵무",
              is_center: false,
            },
          ]
        : []),
    ],
    edges: hasRelationship
      ? [
          {
            relationship_state_id: "relationship-ui-e",
            actor_world_character_id: "wc-ui-e-center",
            target_world_character_id: "wc-ui-e-peer",
            relationship_label: "의견이 달라도 서로 믿으며 함께 성장하는 오랜 동료",
            perception: "경쟁심도 느끼지만 중요한 순간에는 믿고 의지할 수 있는 상대다. ".repeat(4),
            view_version: 2,
            view_updated_at: "2026-09-22T00:00:00Z",
            reviewed_at: "2026-09-22T00:00:00Z",
            familiarity: 3,
            affinity: 2,
            trust: 1,
            tension: 0,
            interaction_count: 4,
            relationship_version: 2,
            last_event_id: "event-ui-e",
            last_event_at: "2026-08-30T01:00:00Z",
          },
        ]
      : [],
    evidence: [],
    meta: {
      template: "neighborhood",
      source: phase === "degraded" ? "canonical_fallback" : "ladybug",
      graph_status:
        phase === "degraded" || phase === "unavailable"
          ? "unavailable"
          : "healthy",
      truncated: false,
      projection_lag_seconds: phase === "ready" || phase === "empty" ? 0 : null,
      revalidated_node_count: hasRelationship ? 2 : 1,
      revalidated_edge_count: hasRelationship ? 1 : 0,
      fallback_reason:
        phase === "degraded" ? "graph_provider_unavailable" : null,
    },
  };
}

async function json(route: Route, body: unknown, status = 200) {
  await route.fulfill({
    body: JSON.stringify(body),
    contentType: "application/json",
    status,
  });
}

export async function installGraphFixture(
  page: Page,
  getPhase: () => GraphPhase,
  requestedProviders: Array<string | null>,
) {
  const staticShell = (await page.evaluate(() => Boolean((window as any).__ANGMOO_RUNTIME_CONFIG__))) || process.env.ANGMOO_GRAPH_STATIC === "1";
  if (process.env.ANGMOO_GRAPH_STATIC === "1") await page.addInitScript(() => Object.assign(window,{__ANGMOO_RUNTIME_CONFIG__:{profile:"tauri-static",apiBaseUrl:"http://127.0.0.1:8080",graphProvider:"ladybug",launchToken:"graph-fixture-token-0000000000000"}}));
  await page.route(staticShell ? "http://127.0.0.1:8080/api/v1/**" : "**/api/backend/**", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    if (url.pathname.endsWith("/auth/me")) {
      await json(route, OWNER);
      return;
    }
    if (url.pathname.endsWith("/worlds/mine/world-ui-e-graph")) {
      await json(route, { schema_version: "local-world-app-v1", surface: "world_app",
        world: uiDWorld("world-ui-e-graph") });
      return;
    }
    if (url.pathname.endsWith("/relationship-review")) {
      await json(route, {mode:"interpreted",activated_at:"2026-09-22T00:00:00Z",
        configuration:{status:"scheduled",local_time:"02:00",timezone:"Asia/Seoul"},
        jobs:[],states:[],excluded_counts:{}});
      return;
    }
    if (url.pathname.endsWith("/relationship-graph")) {
      requestedProviders.push(url.searchParams.get("provider"));
      const phase = getPhase();
      if (phase === "provider-error") {
        await json(route, { detail: "graph_provider_unavailable" }, 503);
        return;
      }
      await json(route, graphRead(phase));
      return;
    }
    await json(route, { detail: `unexpected_graph_request:${url.pathname}` }, 404);
  });
}

test("UI-E Relationship Graph keeps ready, empty, degraded, and unavailable distinct", async ({
  page,
}) => {
  let phase: GraphPhase = "ready";
  const requestedProviders: Array<string | null> = [];
  await installGraphFixture(page, () => phase, requestedProviders);
  await page.setViewportSize({ width: 1440, height: 900 });

  const route =
    "/characters/character-ui-e-center/worlds/world-ui-e-graph/relationship-graph";
  await page.goto(route);

  await expect(page.locator('[data-product-content="relationship-graph"]')).toBeVisible();
  await expect(page.locator('main[data-product-surface="world-app"]')).toHaveAttribute("data-world-id", "world-ui-e-graph");
  await expect(page.locator('[data-relationship-graph-state="ready"]')).toBeVisible();
  await expect(page.getByText("LadybugDB 검증 결과", { exact: true })).toBeVisible();
  await expect(page.getByRole("heading", { name: "방향 관계 지도" })).toBeVisible();

  phase = "empty";
  await page.reload();
  await expect(page.locator('[data-relationship-graph-state="empty"]')).toBeVisible();
  await expect(page.getByRole("heading", { name: "아직 관계 근거가 없습니다" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "방향 관계 지도" })).toHaveCount(0);
  await expect(page.locator('[data-relationship-graph-state="ready"]')).toHaveCount(0);

  phase = "degraded";
  await page.reload();
  await expect(page.locator('[data-relationship-graph-state="degraded"]')).toBeVisible();
  await expect(page.getByText("Canonical DB 안전 대체", { exact: true })).toBeVisible();
  await expect(page.getByRole("heading", { name: "방향 관계 지도" })).toBeVisible();
  await expect(page.locator('[data-relationship-graph-state="ready"]')).toHaveCount(0);

  phase = "unavailable";
  await page.reload();
  await expect(page.locator('[data-relationship-graph-state="unavailable"]')).toBeVisible();
  await expect(page.getByRole("heading", { name: "관계망을 사용할 수 없습니다" })).toBeVisible();
  await expect(page.getByText("안전한 대체 관계 데이터가 없어 그래프를 표시하지 않습니다.")).toBeVisible();
  await expect(page.getByRole("heading", { name: "방향 관계 지도" })).toHaveCount(0);
  await expect(page.getByText("LadybugDB 검증 결과", { exact: true })).toHaveCount(0);

  phase = "ready";
  await page.getByRole("button", { name: "다시 시도" }).click();
  await expect(page.locator('[data-relationship-graph-state="ready"]')).toBeVisible();
  await expect(page.locator('[data-relationship-graph-state="unavailable"]')).toHaveCount(0);

  expect(requestedProviders.length).toBeGreaterThanOrEqual(5);
  expect(new Set(requestedProviders)).toEqual(new Set(["ladybug"]));
});

test("UI-E Relationship Graph never presents a provider outage as healthy", async ({
  page,
}) => {
  let phase: GraphPhase = "provider-error";
  const requestedProviders: Array<string | null> = [];
  await installGraphFixture(page, () => phase, requestedProviders);

  await page.goto(
    "/characters/character-ui-e-center/worlds/world-ui-e-graph/relationship-graph",
  );
  await expect(page.locator('[data-relationship-graph-state="failed"]')).toBeVisible();
  await expect(page.getByText("LadybugDB 관계망을 지금 사용할 수 없습니다.", { exact: false })).toBeVisible();
  await expect(page.locator('[data-relationship-graph-state="ready"]')).toHaveCount(0);
  await expect(page.getByRole("heading", { name: "방향 관계 지도" })).toHaveCount(0);

  phase = "ready";
  await page.getByRole("button", { name: "다시 시도" }).click();
  await expect(page.locator('[data-relationship-graph-state="ready"]')).toBeVisible();
  expect(new Set(requestedProviders)).toEqual(new Set(["ladybug"]));
});


test("RI relationship labels, perception and daily status remain readable at 200 percent", async ({page}) => {
  const mutations: string[] = [];
  page.on("request", request => { if (request.url().includes("/api/backend/") && request.method() !== "GET") mutations.push(request.method()); });
  await installGraphFixture(page, () => "ready", []);
  await page.goto("/characters/character-ui-e-center/worlds/world-ui-e-graph/relationship-graph");
  await expect(page.getByRole("heading", {name:"하루 관계 정리",exact:true})).toBeVisible();
  await expect(page.getByText("의견이 달라도 서로 믿으며 함께 성장하는 오랜 동료", {exact:true}).last()).toBeVisible();
  await page.locator("body").evaluate(element => { element.style.zoom="2"; });
  const summary = page.locator("summary").filter({hasText:"인식"});
  await summary.focus();
  await page.keyboard.press("Enter");
  await expect(page.getByText("경쟁심도 느끼지만 중요한 순간에는 믿고 의지할 수 있는 상대다.", {exact:false}).last()).toBeVisible();
  await page.reload();
  await expect(page.getByText("아직 관계 정리 기록이 없습니다.", {exact:false})).toBeVisible();
  expect(mutations).toEqual([]);
});
