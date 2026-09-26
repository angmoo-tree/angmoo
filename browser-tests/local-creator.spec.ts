import { expect, test, type Page } from "@playwright/test";

const staticShell = process.env.ANGMOO_CREATOR_STATIC === "1";
const owner = { id: "owner", display_name: "Owner", email: null, profile_setup_completed: true,
  feed_content_filter: "all", is_admin: false, display_name_updated_at: null, display_name_change_available_at: null };

async function fixture(page: Page) {
  const writes: { path: string; body: any }[] = [];
  let draft: any = null;
  const world = { id: "world-test", slug: "world-test", name: "검증 World", tagline: "일상을 나누는 곳",
    setting_description: "친구들과 이야기를 나누는 작은 마을의 SNS입니다.", daily_life_description: "서로의 일상을 나누고 차를 마시며 쉬는 공간입니다.",
    genre_tags: ["일상"], tone_tags: ["편안함"], timezone: "Asia/Seoul", language: "ko", visibility: "private", join_policy: "private",
    additional_generation_guidance: "", places: [], roles: [], daypart_profiles: [], rules: [{key:"legacy",rule_kind:"allow",description:"보존 규칙"}], glossary: [],
    banner_media_id: null, icon_media_id: null, banner_alt_text: "", status: "published", definition_version: 1, row_version: 1,
    contract_version: "world-v1", contract_hash: "a".repeat(64), readiness_status: "publish_ready", created_at: "2026-09-27T00:00:00Z", updated_at: "2026-09-27T00:00:00Z", archived_at: null };
  let identity: any = { schema_version: "owner-controlled-world-character-v1", world_character_id: "owner-wc", world_id: world.id, character_id: "owner-character",
    control_mode: "owner_controlled", status: "active", autonomous_enabled: false, version: 1,
    profile: { display_name: "사용자", handle: "owner-local", intro: "", avatar_url: null, banner_url: null, role_key: null, preferred_address: "이전 호칭", interests: [], background: "보존 배경" } };
  const context = () => ({ world, membership_role: "owner", readiness: { world_id: world.id, definition_version: 1, row_version: world.row_version,
    contract_version: "world-v1", contract_hash: world.contract_hash, required_fields: {}, optional_setting_count: 0, quality_tier: "CORE", issues: [], ready_for_publish: true, evaluated_at: world.updated_at } });
  if (staticShell) await page.addInitScript(() => Object.assign(window, { __ANGMOO_RUNTIME_CONFIG__: {
    profile: "tauri-static", apiBaseUrl: "http://127.0.0.1:8080", graphProvider: "ladybug", launchToken: "creator-fixture-token-0000000000000",
  } }));
  await page.route(staticShell ? "http://127.0.0.1:8080/api/v1/**" : "**/api/backend/**", async route => {
    const path = new URL(route.request().url()).pathname.replace(/^\/api\/(backend|v1)/, "");
    const method = route.request().method();
    const body = route.request().postDataJSON();
    const reply = (json: unknown, status = 200) => route.fulfill({ status, contentType: "application/json", json });
    if (path === "/auth/me") return reply(owner);
    if (path === "/agents" && method === "GET") return reply([{ character: { id: "source", name: "복사 원본", execution_mode: "llm" } }]);
    if (method !== "GET") writes.push({ path, body });
    if (path === "/worlds/world-test/creator-context") return reply(context());
    if (path === "/worlds/world-test/characters") return reply({schema_version:"studio-world-character-list-v1",world_id:world.id,items:[]});
    if (path === "/worlds/world-test/my-profile/ensure") return reply(identity);
    if (path === "/worlds/world-test/my-profile" && method === "PATCH") {
      expect(body.version).toBe(identity.version);
      identity = {...identity,version:identity.version+1,profile:{...identity.profile,...body}};
      return reply(identity);
    }
    if (path === "/worlds/world-test" && method === "PATCH") {
      expect(body.rules).toBeUndefined(); expect(body.visibility).toBeUndefined();
      Object.assign(world,body,{row_version:world.row_version+1}); return reply(context());
    }
    if (path === "/agents/drafts" && method === "POST") {
      expect(body.api_key).toBeUndefined();
      draft = { id: "draft", revision: 1, contract_version: 2, target_world_id: body.target_world_id ?? "sns",
        source_kind: body.execution_mode === "local" ? "external" : "direct", status: "editing", provider: "google", model: "gemini-3.1-flash-lite",
        name: "", handle: null, one_liner: "", personality: "", speech_style: "", worldview: "", topic_preferences: "", safety_rules: "",
        avatar_temp_url: null, banner_temp_url: null, expires_at: "2026-10-10T00:00:00Z" };
      return reply(draft);
    }
    if (path === "/agents/drafts/draft" && method === "GET") return reply(draft);
    if (path === "/agents/drafts/draft" && method === "PATCH") {
      expect(body.revision).toBe(draft.revision); draft = { ...draft, ...body, revision: draft.revision + 1 }; return reply(draft);
    }
    if (path === "/agents/drafts/draft/card") {
      expect(body.revision).toBe(draft.revision);
      draft = { ...draft, revision: draft.revision + 1, source_kind: "card", name: "Seraphina", personality: "", worldview: "원본 설명" };
      return reply({ draft, card_version: 3, review: ["personality_required_review_description", "v3_common_fields_only"], raw_only: ["system_prompt"] });
    }
    if (path === "/agents/drafts/draft/copy-settings") {
      expect(body.character_id).toBe("source"); draft = { ...draft, revision: draft.revision + 1, source_kind: "copy", name: "복사 원본", personality: "차분함" }; return reply(draft);
    }
    if (path === "/agents/drafts/draft/card-source") return reply({ document: { data: { name: "Seraphina", system_prompt: "원본 전용 지침" } } });
    if (path === "/agents/drafts/draft/complete") {
      expect(body.revision).toBe(draft.revision); draft.status = "completed";
      return reply({ character: { id: "registered", name: draft.name, execution_mode: "llm" } });
    }
    return reply({ detail: `unexpected:${method}:${path}` }, 404);
  });
  return { writes, getDraft: () => draft };
}

for (const viewport of [{width:360,height:800},{width:390,height:844},{width:436,height:880},{width:1440,height:1000}]) {
  test(`keyless registration ${viewport.width}`, async ({ page }) => {
    await page.setViewportSize(viewport);
    const state = await fixture(page);
    await page.goto("/agents/new");
    await expect(page.getByRole("heading", { name: "앵무 만들기" })).toBeVisible();
    await expect(page.getByLabel("API 키", { exact: true })).toHaveCount(0);
    await page.getByRole("button", { name: "저장하고 다음" }).click();
    await page.getByRole("textbox", { name: "이름", exact: true }).fill("테스트 앵무");
    await page.getByRole("button", { name: "저장하고 다음" }).click();
    await page.getByRole("textbox", { name: "성격", exact: true }).fill("차분하고 다정합니다.");
    await page.getByRole("button", { name: "저장하고 다음" }).click();
    await page.getByRole("button", { name: "저장하고 다음" }).click();
    await page.getByRole("button", { name: "자율활동 OFF로 등록" }).click();
    await expect(page.getByRole("heading", { name: "테스트 앵무 등록 완료" })).toBeVisible();
    expect(state.getDraft().target_world_id).toBe("sns");
    expect(state.writes.some(row => /generate|enhance|credential|setup|activate/.test(row.path))).toBe(false);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  });
}

test("card review, manual correction, refresh and World target", async ({ page }) => {
  const state = await fixture(page);
  await page.goto("/agents/new?worldId=world-test");
  await page.getByLabel("만드는 방법", { exact: true }).selectOption("card");
  await page.getByLabel("캐릭터 카드 PNG 또는 JSON", { exact: true }).setInputFiles({ name: "card.json", mimeType: "application/json", buffer: Buffer.from("{}") });
  await expect(page.getByRole("textbox", { name: "이름", exact: true })).toHaveValue("Seraphina");
  await page.getByText("카드 원본과 반영 범위 확인", { exact: true }).click();
  await page.getByRole("button", { name: "원문 보기" }).click();
  await expect(page.getByText(/원본 전용 지침/)).toBeVisible();
  await page.getByRole("button", { name: "저장하고 다음" }).click();
  await page.getByRole("textbox", { name: "성격", exact: true }).fill("사용자가 수정한 성격");
  await page.getByRole("button", { name: "초안 저장" }).click();
  await expect.poll(() => state.getDraft().personality).toBe("사용자가 수정한 성격");
  await page.reload();
  await expect(page.getByRole("textbox", { name: "이름", exact: true })).toHaveValue("Seraphina");
  expect(state.getDraft().target_world_id).toBe("world-test");
  expect(state.writes.some(row => /generate|enhance/.test(row.path))).toBe(false);
});

test("World management edits the same profile and preserves hidden settings", async ({ page }, info) => {
  const state = await fixture(page);
  await page.setViewportSize({width:1440,height:900});
  await page.goto("/studio/worlds/world-test");
  const profile = page.getByRole("region", {name:"내 프로필 편집"});
  await expect(profile.getByRole("textbox", {name:"이름",exact:true})).toHaveValue("사용자");
  await expect(profile.getByLabel("불리고 싶은 이름")).toHaveCount(0);
  await expect(page.getByLabel("공개 범위", {exact:true})).toHaveCount(0);
  await profile.getByRole("textbox", {name:"이름",exact:true}).fill("새 이름");
  await profile.getByRole("button", {name:"프로필 저장",exact:true}).click();
  await expect(profile.getByText(/기존 글·대화·관계는 그대로/)).toBeVisible();
  const patch = state.writes.find(row => row.path === "/worlds/world-test/my-profile");
  expect(Object.keys(patch!.body).sort()).toEqual(["display_name","handle","intro","version"]);
  expect(state.writes.some(row => /replacement|credential|activate|generate/.test(row.path))).toBe(false);
  await profile.screenshot({path: info.outputPath("my-profile.png")});
});

test("creation guide remains usable at two hundred percent browser CSS zoom", async ({ page }, info) => {
  await fixture(page);
  await page.setViewportSize({width:1440,height:1000});
  await page.goto("/agents/new");
  await expect(page.getByRole("heading", {name:"앵무 만들기"})).toBeVisible();
  await page.evaluate(() => { document.body.style.zoom = "2"; });
  await page.getByRole("button", {name:"저장하고 다음"}).click();
  await expect(page.getByRole("textbox", {name:"이름",exact:true})).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.screenshot({path:info.outputPath("creation-zoom.png"),fullPage:true});
});

test("settings copy uses same guide and preserves return destination", async ({ page }) => {
  const state = await fixture(page);
  await page.setViewportSize({width:1440,height:900});
  await page.goto("/agents/new?worldId=world-test&mode=copy&returnTo=%2Fstudio%2Fworlds%2Fworld-test");
  await page.getByLabel("설정을 복사할 캐릭터", { exact: true }).selectOption("source");
  await page.getByRole("button", { name: "저장하고 다음" }).click();
  await expect(page.getByRole("textbox", { name: "이름", exact: true })).toHaveValue("복사 원본");
  expect(state.getDraft().source_kind).toBe("copy");
  await page.keyboard.press("Tab");
  await expect(page.locator(":focus")).toBeVisible();
});


test("same World selection opens existing profile without creating a draft", async ({ page }) => {
  const state = await fixture(page);
  await page.route("**/worlds/world-test/characters?surface=studio", route => route.fulfill({json:{
    schema_version:"studio-world-character-list-v1",world_id:"world-test",
    items:[{character_id:"source",world_character_id:"source-wc"}],
  }}));
  await page.goto("/agents/new?worldId=world-test&mode=copy");
  await page.getByLabel("설정을 복사할 캐릭터", {exact:true}).selectOption("source");
  await page.getByRole("button", {name:"저장하고 다음"}).click();
  await expect(page).toHaveURL(/worlds\/world-test\/characters\/source-wc/);
  expect(state.writes.filter(item=>item.path.startsWith("/agents/drafts"))).toHaveLength(0);
});


test("legacy draft resumes only after explicit adoption without key setup", async ({ page }) => {
  const state = await fixture(page);
  await page.addInitScript(() => sessionStorage.setItem("angmoo.agentCreationDraftId","legacy"));
  const legacy = {id:"legacy",contract_version:1,revision:1,target_world_id:null,source_kind:"direct",status:"editing",
    name:"이전 초안",handle:null,one_liner:"보존 소개",personality:"친절함",speech_style:"",worldview:"",topic_preferences:"",safety_rules:""};
  let adopted = false;
  await page.route("**/agents/drafts/legacy", route=>route.fulfill({json:legacy}));
  await page.route("**/agents/drafts/legacy/adopt", route=>{
    adopted = true;
    expect(route.request().postDataJSON()).toEqual({revision:1,target_world_id:"world-test"});
    return route.fulfill({json:{...legacy,contract_version:2,revision:2,target_world_id:"world-test"}});
  });
  await page.goto("/agents/new?worldId=world-test");
  await expect(page.getByRole("button",{name:"이전 초안 이어가기"})).toBeVisible();
  expect(adopted).toBe(false);
  await page.getByRole("button",{name:"이전 초안 이어가기"}).click();
  await expect(page.getByRole("textbox",{name:"이름",exact:true})).toHaveValue("이전 초안");
  expect(adopted).toBe(true);
  expect(state.writes.some(row=>/generate|enhance|credential|setup/.test(row.path))).toBe(false);
});
