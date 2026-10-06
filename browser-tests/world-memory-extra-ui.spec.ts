import { expect, test, type Page } from "@playwright/test";
import { installWorldCharacterManagementFixture, syntheticWorldCharacter, worldCharacterRoute, WORLD_AGENT } from "./world-character-management-fixture";
import { FEED_WORLD } from "./world-feed-fixture";
import { memoryBatchFixture } from "./memory-batch-fixture";

for (const language of ["ko", "en"] as const) {
  for (const count of [1, 7, 20]) {
    test(`Relationship map retains every long name, direction and node (${language}, ${count})`, async ({page}, info) => {
      const owner = {id:"local-owner",email:null,display_name:"Local Owner",profile_setup_completed:true,is_admin:true,ui_language:language,ui_preference_revision:0,feed_content_filter:"all"};
      const nodes = Array.from({length:count}, (_, i) => ({world_character_id:`node-${i}`,character_id:`source-${i}`,display_name:`${i}·` + "긴이름 LongName 👨‍👩‍👦 ".repeat(7),is_center:i===0,avatar_url:null}));
      const edges = nodes.slice(1).flatMap((node,i) => [
        {relationship_state_id:`out-${i}`,actor_world_character_id:"node-0",target_world_character_id:node.world_character_id},
        {relationship_state_id:`in-${i}`,actor_world_character_id:node.world_character_id,target_world_character_id:"node-0"},
      ]).map(edge => ({...edge,relationship_label:"Original relationship ".repeat(10),perception:"Original perception",view_version:1,view_updated_at:null,reviewed_at:null,familiarity:1,affinity:2,trust:3,tension:0,interaction_count:5,relationship_version:1,last_event_id:null,last_event_at:null}));
      const writes: string[] = [];
      const graph = {world_id:"graph-world",center_world_character_id:"node-0",nodes,edges,evidence:[],meta:{template:"neighborhood",source:"ladybug",graph_status:"healthy",truncated:false,projection_lag_seconds:0,revalidated_node_count:count,revalidated_edge_count:edges.length,fallback_reason:null}};
      const isStatic=info.project.name === "static-export";
      if(isStatic) await page.addInitScript(() => Object.assign(window,{__ANGMOO_RUNTIME_CONFIG__:{profile:"tauri-static",apiBaseUrl:"http://127.0.0.1:8080",graphProvider:"ladybug",launchToken:"extra-fixture-token-0000000000000"}}));
      await page.route(isStatic ? "http://127.0.0.1:8080/api/v1/**" : "**/api/backend/**", async route => {
        const path=new URL(route.request().url()).pathname;
        if(route.request().method() !== "GET") writes.push(path);
        const data=path.endsWith("/auth/me") ? owner : path.endsWith("/relationship-graph") ? graph : path.endsWith("/relationship-review") ? {mode:"interpreted",configuration:{status:"scheduled",local_time:"02:00",timezone:"Asia/Seoul"},jobs:[],states:[],excluded_counts:{}} : {detail:"unexpected_fixture_request"};
        await route.fulfill({status:path.endsWith("/auth/me") || path.endsWith("/relationship-graph") || path.endsWith("/relationship-review") ? 200 : 404,json:data});
      });
      await page.goto("/characters/source-0/worlds/graph-world/relationship-graph");
      if(count === 1) {
        await expect(page.locator('[data-relationship-graph-state="empty"]')).toBeVisible();
        await expect(page.locator("[data-relationship-node]")).toHaveCount(0);
        expect(writes).toEqual([]);
        return;
      }
      const svg=page.locator("svg").filter({has:page.locator("[data-relationship-node]")});
      await expect(svg.locator("[data-relationship-node]")).toHaveCount(count);
      await expect(page.locator("[data-relationship-list-item]")).toHaveCount(edges.length);
      for(const width of [390,480,960,1440]) {
        await page.setViewportSize({width,height:1000});
        for(const zoom of [1,2]) {
          await page.evaluate(value => {document.documentElement.style.fontSize = `${value*16}px`;},zoom);
          expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth+1)).toBe(true);
          const bounds=await svg.evaluate(element => {
            const svg=element as SVGSVGElement, view=svg.viewBox.baseVal;
            return Array.from(svg.querySelectorAll<SVGGElement>("[data-relationship-node]")).map(node => {
              const b=node.getBBox();return {name:node.querySelector("text")!.textContent,x:b.x,y:b.y,width:b.width,height:b.height,inBounds:b.x>=0 && b.y>=0 && b.x+b.width<=view.width && b.y+b.height<=view.height};
            });
          });
          expect(bounds.every(value=>value.inBounds)).toBe(true);
          for (let i=0;i<bounds.length;i++) for(let j=i+1;j<bounds.length;j++) {
            const a=bounds[i],b=bounds[j];
            expect(a.x+a.width<=b.x || b.x+b.width<=a.x || a.y+a.height<=b.y || b.y+b.height<=a.y).toBe(true);
          }
          expect(bounds.map(value=>value.name)).toEqual([...nodes].sort((a,b)=>Number(b.is_center)-Number(a.is_center)||a.world_character_id.localeCompare(b.world_character_id)).map(node=>node.display_name));
        }
      }
      for(const edge of edges) {
        await expect(svg.locator(`[data-relationship-edge="${edge.relationship_state_id}"]`)).toHaveAttribute("data-relationship-from",edge.actor_world_character_id);
        await expect(svg.locator(`[data-relationship-edge="${edge.relationship_state_id}"]`)).toHaveAttribute("data-relationship-to",edge.target_world_character_id);
      }
      expect(writes).toEqual([]);
      await page.screenshot({path:info.outputPath(`graph-${language}-${count}.png`),fullPage:true});
    });
  }
}

function reviewBarrier() {
  let release!: () => void;
  const promise = new Promise<void>(resolve => { release = resolve; });
  return { promise, release };
}

async function installPrivateMemoryFixture(page: Page, isStatic: boolean, baseURL: string, language: "ko" | "en" = "ko") {
  const fixture = await installWorldCharacterManagementFixture(page, isStatic, baseURL, language);
  fixture.management.authOwner = language === "ko" ? "local-owner" : undefined;
  const state = { id: "private-memory", summary: "Original private memory", denied: false, reads: 0, completed: 0, writeCompleted: 0,
    barrier: null as Promise<void> | null, writeBarrier: null as Promise<void> | null, writes: [] as string[] };
  const scope = { world_id: FEED_WORLD, subject_world_character_id: WORLD_AGENT };
  const batch = memoryBatchFixture(FEED_WORLD, WORLD_AGENT, () => true);
  await page.route(isStatic ? "http://127.0.0.1:8080/api/v1/**" : "**/api/backend/**", async route => {
    const path = new URL(route.request().url()).pathname.replace(/^\/api\/(backend|v1)/, "");
    if (path === `/worlds/${FEED_WORLD}/world-characters`) return route.fulfill({ json: {
      schema_version: "world-character-profile-list-v1", world_id: FEED_WORLD, items: [syntheticWorldCharacter(WORLD_AGENT).profile],
    } });
    if (!path.startsWith(`/worlds/${FEED_WORLD}/world-characters/${WORLD_AGENT}/`)) return route.fallback();
    if (state.denied) return route.fulfill({ status: 403, json: { detail: "memory_scope_unavailable" } });
    if (route.request().method() !== "GET") state.writes.push(path);
    if (await batch(route)) return;
    if (path.endsWith("/memory/settings")) return route.fulfill({ json: {
      schema_version: "memory-setting-read.v1", scope, configured: true, enabled: true, retention_days: 180,
      provider_mode: "optional-configured", version: 1, capabilities: { read: "available", mutate: "available" },
    } });
    const item = { id: state.id, memory_kind: "AUTOBIOGRAPHICAL_EVENT", summary: state.summary, lifecycle: "active",
      formed_at: "2026-10-07T01:00:00Z", valid_from: "2026-10-07T01:00:00Z", valid_until: null, pinned: false,
      superseded_by_memory_id: null, retention_days: 180, related_character: null, version: 1 };
    if (path.endsWith("/memories")) {
      state.reads += 1;
      const data = { schema_version: "memory-item-list.v1", scope, memory_enabled: true, items: [item], next_cursor: null, capabilities: { read: "available", mutate: "available" } };
      if (state.barrier) await state.barrier;
      state.completed += 1;
      return route.fulfill({ json: data });
    }
    if (path.endsWith("/corrections") && route.request().method() === "POST") {
      state.id = "private-corrected"; state.summary = route.request().postDataJSON().summary;
      const response = { schema_version: "memory-item-mutation.v1", operation: "correct", outcome: "updated", scope,
        item: { ...item, id: state.id, summary: state.summary }, replaced_memory_id: item.id, projection_cleanup: "automatic_after_commit" };
      if (state.writeBarrier) await state.writeBarrier;
      state.writeCompleted += 1;
      return route.fulfill({ json: response });
    }
    if (path.includes("/memories/") && route.request().method() === "GET") return route.fulfill({ json: {
      ...item, schema_version: "memory-item-detail.v1", scope, memory_enabled: true, evidence: [], episode: null,
      provenance_summary: "Synthetic original evidence", capabilities: { read: "available", mutate: "available" },
    } });
    return route.fulfill({ status: 404, json: { detail: "unexpected_memory_fixture_request" } });
  });
  return { fixture, state };
}

test("I38: English activity hours and reused cards translate UI without changing policies", async ({ page }, info) => {
  const fixture = await installWorldCharacterManagementFixture(page, info.project.name === "static-export", String(info.project.use.baseURL), "en");
  await page.goto(`${worldCharacterRoute()}?view=settings`);
  const settings = page.locator("[data-world-character-settings-form]");
  const activity = settings.locator('[data-world-character-settings-card="activity"]');
  await expect(activity).toContainText("Set activity hours, allowed actions and writing limits.");
  await expect(activity).toContainText("Active daily from 09:00 until 02:00 the next day.");
  await activity.getByRole("button", { name: "Morning", exact: true }).click();
  await expect(activity).toContainText("Active daily from 06:00 until 14:00.");
  await activity.getByLabel("Activity ends", { exact: true }).selectOption("06:00");
  await expect(activity).toContainText("Activity start and end times must differ.");
  await expect(activity.getByRole("button", { name: "Save settings", exact: true })).toBeDisabled();
  await activity.getByLabel("Activity ends", { exact: true }).selectOption("00:30");
  await expect(activity).toContainText("The activity window can be up to 17 hours. The current selection is 18 hours 30 minutes.");
  await expect(activity.getByRole("button", { name: "Save settings", exact: true })).toBeDisabled();
  await expect(activity).not.toContainText(/[가-힣]/);
  const plan = settings.getByRole("region", { name: "Today's plan", exact: true });
  await expect(plan).toContainText("Today's plan is not prepared");
  await expect(plan).not.toContainText(/[가-힣]/);
  const runtime = settings.getByRole("region", { name: "Activity mode and current state", exact: true });
  await expect(runtime).toContainText("Activity mode informed by memories (V2)");
  await expect(runtime).not.toContainText(/[가-힣]/);
  expect(fixture.management.writes).toEqual([]);
  expect(fixture.management.providerCalls).toEqual([]);
});

for (const language of ["ko", "en"] as const) {
  test(`I41: Memory recovery uses its own purpose and localizes dynamic states (${language})`, async ({ page }, info) => {
    const { state } = await installPrivateMemoryFixture(page, info.project.name === "static-export", String(info.project.use.baseURL), language);
    const scope = { world_id: FEED_WORLD, subject_world_character_id: WORLD_AGENT };
    let saves = 0;
    await page.route("**/memory/batch-settings", async route => {
      if (route.request().method() === "PUT") {
        saves += 1;
        return route.fulfill({ status: 503, json: { detail: "synthetic-private-provider-response" } });
      }
      return route.fulfill({ json: { scope, version: 0, memory_enabled: true, ai_enabled: false,
        shutdown_enabled: true, schedule_enabled: false, local_time: "22:30", timezone: "Asia/Seoul", next_due_at: null,
        model_id: "gemini-3.1-flash-lite", thinking_level: "high", profile_version: 0, pending_count: 32,
        status: "attention", last_code: "memory_selection_auth_failed", last_completed_at: null,
        available_models: ["gemini-3.1-flash-lite", "gemini-3.5-flash-lite"], stored_count: 4, storage_limit: 100000,
        capacity_blocked: false, can_run: true, retryable: true, run_saved_count: null, run_pending_count: null } });
    });
    await page.goto(`/memory?world=${FEED_WORLD}&subject=${WORLD_AGENT}`);
    const shell = page.locator('[data-product-shell="memory"]');
    const card = shell.getByRole("region", { name: language === "ko" ? "기억·관계 정리" : "Memory and relationship consolidation", exact: true });
    await expect(card).toContainText(language === "ko" ? "기억 정리용 API 키와 이용 권한을 확인해 주세요." : "Check this character's memory consolidation API key and permissions.");
    await expect(card).not.toContainText(/쪽지용|채팅용|Chat API|Chat AI/);
    const memory = shell.getByRole("button").filter({ hasText: state.summary });
    await expect(memory).toContainText(language === "ko" ? "경험" : "Experience");
    await expect(memory).toContainText(language === "ko" ? "활성" : "Active");
    await card.getByRole("button", { name: language === "ko" ? "정리 설정 저장" : "Save consolidation settings", exact: true }).click();
    await expect(card).toContainText(language === "ko" ? "저장하지 못했어요. 이 캐릭터의 기억 정리용 API 키와 모델을 확인해 주세요." : "Could not save. Check this character's memory consolidation API key and model.");
    await expect(card).not.toContainText("synthetic-private-provider-response");
    expect(saves).toBe(1); expect(state.writes).toEqual([]);
    if (language === "en") await expect(card).not.toContainText(/[가-힣]/);
  });
}

test("I41: Memory owner change removes previous private memory and key drafts", async ({ page }, info) => {
  const { fixture, state } = await installPrivateMemoryFixture(page, info.project.name === "static-export", String(info.project.use.baseURL));
  await page.goto(`/memory?world=${FEED_WORLD}&subject=${WORLD_AGENT}`);
  const shell = page.locator('[data-product-shell="memory"]');
  await expect(shell).toContainText(state.summary);
  const secrets = shell.locator('input[type="password"]'); await expect(secrets).toHaveCount(2);
  await secrets.first().fill("private-retired-owner-draft");
  state.denied = true; fixture.management.authOwner = "different-owner";
  await page.evaluate(() => window.dispatchEvent(new Event("angmoo:auth-changed")));
  await expect.poll(() => page.evaluate(() => JSON.parse(sessionStorage.getItem("angmoo.user") || "{}").id)).toBe("different-owner");
  await expect(shell).not.toContainText("Original private memory");
  await expect(secrets).toHaveCount(0); expect(state.writes).toEqual([]);
});

test("I41: Memory runtime renewal clears loaded memory and key drafts before a new read", async ({ page }, info) => {
  const { state } = await installPrivateMemoryFixture(page, info.project.name === "static-export", String(info.project.use.baseURL));
  await page.goto(`/memory?world=${FEED_WORLD}&subject=${WORLD_AGENT}`);
  const shell = page.locator('[data-product-shell="memory"]');
  await expect(shell).toContainText(state.summary);
  const secrets = shell.locator('input[type="password"]'); await expect(secrets).toHaveCount(2);
  await secrets.first().fill("private-retired-runtime-draft");
  const fresh = reviewBarrier(); state.barrier = fresh.promise; state.summary = "Current runtime private memory";
  const previous = state.reads;
  await page.evaluate(() => {
    const config = (window as Window & { __ANGMOO_RUNTIME_CONFIG__?: { launchToken: string } }).__ANGMOO_RUNTIME_CONFIG__;
    if (config) config.launchToken = "renewed-memory-synthetic-token-0000000000";
    window.dispatchEvent(new Event("angmoo:desktop-runtime-config-changed"));
  });
  try {
    await expect.poll(() => state.reads).toBeGreaterThan(previous);
    await expect(shell).not.toContainText("Original private memory");
  } finally { state.barrier = null; fresh.release(); }
  await expect(shell).toContainText(state.summary); await expect(secrets).toHaveCount(2);
  await expect(secrets.first()).toHaveValue(""); expect(state.writes).toEqual([]);
});

test("I41: a late Memory list cannot replace the current runtime's private content", async ({ page }, info) => {
  const { state } = await installPrivateMemoryFixture(page, info.project.name === "static-export", String(info.project.use.baseURL));
  const stale = reviewBarrier(); state.barrier = stale.promise;
  await page.goto(`/memory?world=${FEED_WORLD}&subject=${WORLD_AGENT}`);
  await expect.poll(() => state.reads).toBeGreaterThan(0);
  state.barrier = null; state.summary = "Current runtime private memory";
  await page.evaluate(() => {
    const config = (window as Window & { __ANGMOO_RUNTIME_CONFIG__?: { launchToken: string } }).__ANGMOO_RUNTIME_CONFIG__;
    if (config) config.launchToken = "renewed-memory-synthetic-token-0000000000";
    window.dispatchEvent(new Event("angmoo:desktop-runtime-config-changed"));
  });
  const shell = page.locator('[data-product-shell="memory"]'); await expect(shell).toContainText(state.summary);
  stale.release(); await expect.poll(() => state.completed).toBeGreaterThanOrEqual(2);
  await expect(shell).toContainText(state.summary); await expect(shell).not.toContainText("Original private memory");
  expect(state.writes).toEqual([]);
});

test("I41: a late Memory correction cannot navigate back after leaving the screen", async ({ page }, info) => {
  const { state } = await installPrivateMemoryFixture(page, info.project.name === "static-export", String(info.project.use.baseURL));
  await page.goto(`/memory?world=${FEED_WORLD}&subject=${WORLD_AGENT}&memory=private-memory`);
  await expect(page.getByRole("heading", { name: state.summary, exact: true })).toBeVisible();
  await page.getByRole("button", { name: "정정", exact: true }).click();
  await page.getByLabel("정정할 기억 요약").fill("Canonical correction accepted before navigation");
  const pending = reviewBarrier(); state.writeBarrier = pending.promise;
  await page.getByRole("button", { name: "정정 저장", exact: true }).click();
  await expect.poll(() => state.writes.length).toBe(1);
  // Emulate external route activation while the busy modal owns pointer input.
  // Keep the modal's real cancel/close behavior intact.
  await page.getByRole("link", { name: "Device Home으로 돌아가기", exact: true }).evaluate(element => (element as HTMLAnchorElement).click());
  await expect.poll(() => new URL(page.url()).pathname).toBe("/");
  pending.release(); await expect.poll(() => state.writeCompleted).toBe(1);
  await page.evaluate(() => new Promise<void>(resolve => requestAnimationFrame(() => requestAnimationFrame(() => resolve()))));
  await expect(page).toHaveURL(/\/$/);
  await expect(page.locator('[data-product-shell="memory"]')).toHaveCount(0);
  expect(state.writes).toEqual([`/worlds/${FEED_WORLD}/world-characters/${WORLD_AGENT}/memories/private-memory/corrections`]);
});

async function installReviewFixture(page: Page, isStatic: boolean, language: "ko" | "en" = "ko") {
  const state = {
    owner: "review-owner-a" as string | null, period: "2026-10-07-owner-a",
    reviewReads: [] as string[], completed: [] as string[], writes: [] as string[],
    barrier: null as Promise<void> | null, reviewStatus: 200, authFailures: 0, bootstraps: 0,
    configuration: "scheduled", manualAvailable: true, jobStatus: "applied", errorCode: null as string | null,
    fallbackReason: null as string | null,
  };
  if (isStatic) await page.addInitScript(() => Object.assign(window, {
    __ANGMOO_RUNTIME_CONFIG__: { profile: "tauri-static", apiBaseUrl: "http://127.0.0.1:8080", graphProvider: "ladybug", launchToken: "review-synthetic-token-0000000000000" },
  }));
  await page.route(isStatic ? "http://127.0.0.1:8080/api/v1/**" : "**/api/backend/**", async route => {
    const path = new URL(route.request().url()).pathname;
    const user = { id: state.owner, email: null, display_name: "Review Owner", profile_setup_completed: true, is_admin: true, ui_language: language, ui_preference_revision: 0, feed_content_filter: "all" };
    let status = 200;
    let data: unknown;
    if (path.endsWith("/auth/me")) {
      status = state.owner && state.authFailures === 0 ? 200 : 401;
      if (state.authFailures) state.authFailures -= 1;
      data = status === 200 ? user : { detail: "not_authenticated" };
    } else if (path.endsWith("/auth/local/session")) {
      state.bootstraps += 1;
      status = state.owner ? 200 : 401;
      data = state.owner ? { user, profile_setup_required: false } : { detail: "not_authenticated" };
    } else if (path.endsWith("/relationship-graph")) {
      data = { world_id: "review-world", center_world_character_id: "review-actor", nodes: [
        { world_character_id: "review-actor", character_id: "review-source", display_name: "Original Actor", is_center: true, avatar_url: null },
        { world_character_id: "review-target", character_id: "review-target-source", display_name: "Original Target", is_center: false, avatar_url: null },
      ], edges: [{ relationship_state_id: "review-edge", actor_world_character_id: "review-actor", target_world_character_id: "review-target", relationship_label: "Authored original label", perception: "Authored original perception", familiarity: 3, affinity: 2, trust: 1, tension: 0, interaction_count: 4, relationship_version: 5, last_event_id: null, last_event_at: null }], evidence: [],
      meta: { template: "neighborhood", source: state.fallbackReason ? "canonical_fallback" : "ladybug", graph_status: state.fallbackReason ? "unavailable" : "healthy", truncated: false, projection_lag_seconds: 0, revalidated_node_count: 2, revalidated_edge_count: 1, fallback_reason: state.fallbackReason } };
    } else if (path.endsWith("/relationship-review")) {
      const period = state.period, wait = state.barrier;
      status = state.reviewStatus;
      data = status === 200 ? { mode: "interpreted", configuration: { status: state.configuration, manual_available: state.manualAvailable, local_time: "02:00", timezone: "Asia/Seoul" },
        jobs: [{ id: period, target_id: "review-target", period, phase: "direct", status: state.jobStatus, memory_count: 1, error_code: state.errorCode }], states: [], excluded_counts: {} } : { detail: "synthetic_review_failure" };
      state.reviewReads.push(period);
      if (wait) await wait;
      state.completed.push(period);
    } else {
      status = 404; data = { detail: "unexpected_fixture_request" };
    }
    if (route.request().method() !== "GET" && !path.endsWith("/auth/local/session")) state.writes.push(path);
    await route.fulfill({ status, json: data });
  });
  return state;
}

function reviewCard(page: Page, language: "ko" | "en" = "ko") {
  return page.locator("section").filter({ has: page.getByRole("heading", { name: language === "ko" ? "하루 관계 정리" : "Daily relationship review", exact: true }) }).last();
}

async function openReview(page: Page, language: "ko" | "en" = "ko") {
  const card = reviewCard(page, language);
  await expect(card.locator("details").first()).toBeVisible();
  await card.locator("summary").first().click();
  return card;
}

test("R-T10: same route review is cleared and reloaded for a different owner", async ({ page }, info) => {
  const state = await installReviewFixture(page, info.project.name === "static-export");
  await page.goto("/characters/review-source/worlds/review-world/relationship-graph");
  const card = await openReview(page);
  await expect(card).toContainText(state.period);
  const next = reviewBarrier(); state.owner = "review-owner-b"; state.period = "2026-10-07-owner-b"; state.barrier = next.promise;
  await page.evaluate(() => window.dispatchEvent(new Event("angmoo:auth-changed")));
  try {
    await expect.poll(() => state.reviewReads.includes("2026-10-07-owner-b")).toBe(true);
    await expect(card).not.toContainText("2026-10-07-owner-a");
  } finally { state.barrier = null; next.release(); }
  await openReview(page); await expect(card).toContainText("2026-10-07-owner-b");
  expect(state.writes).toEqual([]);
});

for (const staleStatus of [200, 503]) {
  test(`R-T10: runtime renewal rejects a late review response (${staleStatus})`, async ({ page }, info) => {
    const state = await installReviewFixture(page, info.project.name === "static-export");
    const stale = reviewBarrier(); state.barrier = stale.promise; state.reviewStatus = staleStatus;
    await page.goto("/characters/review-source/worlds/review-world/relationship-graph");
    await expect.poll(() => state.reviewReads.length).toBeGreaterThan(0);
    const current = reviewBarrier(); state.barrier = current.promise; state.period = "2026-10-07-current-runtime"; state.reviewStatus = 200;
    await page.evaluate(() => {
      const config = (window as Window & { __ANGMOO_RUNTIME_CONFIG__?: { launchToken: string } }).__ANGMOO_RUNTIME_CONFIG__;
      if (config) config.launchToken = "renewed-review-synthetic-token-0000000000";
      window.dispatchEvent(new Event("angmoo:desktop-runtime-config-changed"));
    });
    try { await expect.poll(() => state.reviewReads.includes(state.period)).toBe(true); }
    finally { state.barrier = null; current.release(); }
    const card = await openReview(page); await expect(card).toContainText(state.period);
    stale.release();
    await expect.poll(() => state.completed.includes("2026-10-07-owner-a")).toBe(true);
    await expect(card).toContainText(state.period); await expect(card).not.toContainText("2026-10-07-owner-a");
    await expect(card.getByRole("alert")).toHaveCount(0); expect(state.writes).toEqual([]);
  });
}

test("R-T10: a renewed session with the same owner reloads the private review", async ({ page }, info) => {
  const state = await installReviewFixture(page, info.project.name === "static-export");
  await page.goto("/characters/review-source/worlds/review-world/relationship-graph");
  await openReview(page); await expect(reviewCard(page)).toContainText(state.period);
  const next = reviewBarrier(); state.period = "2026-10-07-renewed-session"; state.barrier = next.promise; state.authFailures = 1;
  await page.evaluate(() => window.dispatchEvent(new Event("angmoo:auth-changed")));
  try {
    await expect.poll(() => state.reviewReads.includes(state.period)).toBe(true);
    await expect(reviewCard(page)).not.toContainText("2026-10-07-owner-a");
  } finally { state.barrier = null; next.release(); }
  await openReview(page); await expect(reviewCard(page)).toContainText(state.period); expect(state.writes).toEqual([]);
  expect(state.bootstraps).toBe(1);
});

test("R-T10: logout removes the review and a late response cannot restore it", async ({ page }, info) => {
  const state = await installReviewFixture(page, info.project.name === "static-export");
  const pending = reviewBarrier(); state.barrier = pending.promise;
  await page.goto("/characters/review-source/worlds/review-world/relationship-graph");
  await expect.poll(() => state.reviewReads.length).toBeGreaterThan(0);
  state.owner = null;
  await page.evaluate(() => { sessionStorage.removeItem("angmoo.user"); window.dispatchEvent(new Event("angmoo:auth-changed")); });
  await expect(reviewCard(page)).toHaveCount(0);
  pending.release(); await expect.poll(() => state.completed.length).toBeGreaterThan(0);
  await expect(reviewCard(page)).toHaveCount(0); await expect(page.getByText("2026-10-07-owner-a")).toHaveCount(0);
  expect(state.writes).toEqual([]); expect(state.bootstraps).toBe(1);
  expect(await page.evaluate(() => sessionStorage.getItem("angmoo.user"))).toBeNull();
});

test("R-T10: a late private review from the previous owner cannot replace the current result", async ({ page }, info) => {
  const state = await installReviewFixture(page, info.project.name === "static-export");
  const stale = reviewBarrier(); state.barrier = stale.promise;
  await page.goto("/characters/review-source/worlds/review-world/relationship-graph");
  await expect.poll(() => state.reviewReads.length).toBeGreaterThan(0);
  state.owner = "review-owner-b"; state.period = "2026-10-07-owner-b"; state.barrier = null;
  await page.evaluate(() => window.dispatchEvent(new Event("angmoo:auth-changed")));
  await expect.poll(() => state.reviewReads.includes(state.period)).toBe(true);
  const card = await openReview(page); await expect(card).toContainText(state.period);
  stale.release(); await expect.poll(() => state.completed.includes("2026-10-07-owner-a")).toBe(true);
  await expect(card).toContainText(state.period); await expect(card).not.toContainText("2026-10-07-owner-a");
  expect(state.writes).toEqual([]);
});

for (const language of ["ko", "en"] as const) {
  for (const known of [true, false]) {
    test(`R-C08/R-T11: review and fallback errors use safe localized labels (${language}, ${known})`, async ({ page }, info) => {
      const state = await installReviewFixture(page, info.project.name === "static-export", language);
      state.jobStatus = "failed";
      state.errorCode = known ? "relationship_review_profile_changed" : "provider-secret-http://synthetic.invalid/private-error";
      state.fallbackReason = known ? "schema_not_ready" : "synthetic-internal-fallback";
      if (!known) { state.configuration = "synthetic-internal-configuration"; state.jobStatus = "synthetic-internal-job"; }
      await page.goto("/characters/review-source/worlds/review-world/relationship-graph");
      const card = await openReview(page, language);
      await expect(card).not.toContainText(state.errorCode);
      await expect(page.locator("main")).not.toContainText(state.fallbackReason);
      if (known) await expect(card).toContainText(language === "ko" ? "설정이 변경되어 다시 확인이 필요해요." : "Settings changed. Another check is required.");
      else {
        await expect(card).not.toContainText(state.configuration); await expect(card).not.toContainText(state.jobStatus);
        await expect(card).toContainText(language === "ko" ? "정리 상태를 확인해주세요." : "Check the review status.");
      }
      if (language === "en") {
        await expect(page.locator("main")).not.toContainText("사유:");
        await expect(page.getByText("Graph temporarily unavailable", { exact: true }).first()).toBeVisible();
        await expect(card).not.toContainText(/[가-힣]/);
      }
      await expect(page.locator("main")).toContainText("Authored original label");
      expect(state.writes).toEqual([]);
    });
  }
  test(`R-T03/R-T14: missing consolidation configuration shows its actual state (${language})`, async ({ page }, info) => {
    const state = await installReviewFixture(page, info.project.name === "static-export", language);
    state.configuration = "consolidation_configuration_required"; state.manualAvailable = false;
    await page.goto("/characters/review-source/worlds/review-world/relationship-graph");
    const card = await openReview(page, language);
    await expect(card).toContainText(language === "ko" ? "기억 정리용 API 키·모델 설정 필요" : "Configure the memory consolidation API key and model");
    await expect(card).not.toContainText(language === "ko" ? "예약 시간과 관계없이 실행" : "regardless of the scheduled time");
    await expect(card).toContainText(state.period); expect(state.writes).toEqual([]);
  });
}
