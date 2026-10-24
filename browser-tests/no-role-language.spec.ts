import { test, expect } from "@playwright/test";
import { installUiFixture } from "./world-ui-improvements-fixture";
import { FEED_WORLD } from "./world-feed-fixture";
import { WORLD_AGENT, worldCharacterRoute } from "./world-character-management-fixture";
import { installIntroductionFixture } from "./world-introduction-fixture";
import { studio } from "./photo-studio-fixture";

for (const language of ["ko", "en"] as const) {
  for (const stored of ["No role", "역할 없음"]) {
    test(`profile renders stored role unchanged ${stored} ${language}`, async ({page}, info) => {
      const ui = await installUiFixture(page, info.project.name === "static-export", String(info.project.use.baseURL), language);
      const item = ui.management.worlds.get(FEED_WORLD)!.find(row => row.profile.world_character_id === WORLD_AGENT)!;
      Object.assign(item.profile, {role_key:"no_specific_role", role_name:stored});
      await page.goto(worldCharacterRoute());
      await expect(page.getByText(stored, {exact:true})).toBeVisible();
      Object.assign(item.profile, {role_key:"ordinary", role_name:stored}); await page.reload();
      await expect(page.getByText(stored, {exact:true})).toBeVisible();
      Object.assign(item.profile, {role_key:null, role_name:null}); await page.reload();
      await expect(page.getByText(language === "ko" ? "역할 정보를 확인할 수 없어요." : "Role information is unavailable.", {exact:true})).toBeVisible();
      expect(ui.management.writes).toEqual([]); expect(ui.management.providerCalls).toEqual([]);
    });
    test(`World introduction retains stored role name description and user prose ${stored} ${language}`, async ({page},info) => {
      const fixture = await installIntroductionFixture(page,info,language);
      const world = fixture.state.worlds.get(FEED_WORLD)!;
      const description = stored === "No role" ? "A character with no specific World role." : "별도의 World 역할을 지정하지 않은 캐릭터";
      world.roles = [{key:"no_specific_role",name:stored,description,responsibilities:[],allowed_activity_scope:[],autonomous_allowed:true},
        {key:"ordinary",name:stored,description:"Preserved custom role",responsibilities:["Original responsibility"],allowed_activity_scope:[],autonomous_allowed:true}];
      const original = JSON.stringify(world);
      await page.goto(`/worlds/${FEED_WORLD}`);
      const intro = page.locator("[data-world-introduction]");
      const expand = intro.getByRole("button",{expanded:false});
      await expect(expand).toBeVisible(); await expand.click();
      await expect(intro.getByRole("heading",{name:stored,exact:true})).toHaveCount(2);
      await expect(intro.getByText(description,{exact:true})).toBeVisible();
      await expect(intro.getByText("Original responsibility",{exact:true})).toBeVisible();
      await expect(intro.getByText(world.tagline,{exact:true})).toBeVisible();
      const reads = [...fixture.state.reads];
      for (const nextLanguage of [language === "ko" ? "en" : "ko", language] as const) {
        // Simulate the same owner's saved preference notification, using the
        // real AuthProvider and i18n update path; World responses stay unchanged.
        fixture.base.base.language = nextLanguage;
        await page.evaluate(() => window.dispatchEvent(new Event("angmoo:auth-changed")));
        await expect(page.locator("html")).toHaveAttribute("lang",nextLanguage);
        await expect(intro.getByRole("button",{name:nextLanguage === "ko" ? "접기" : "Show less",exact:true})).toHaveAttribute("aria-expanded","true");
        await expect(intro.getByRole("heading",{name:stored,exact:true})).toHaveCount(2);
        await expect(intro.getByText(description,{exact:true})).toBeVisible();
        expect(fixture.state.reads).toEqual(reads);
      }
      expect(JSON.stringify(world)).toBe(original); expect(fixture.state.writes).toEqual([]);
      expect(fixture.base.base.providerCalls).toEqual([]);
    });
  }
  test(`Studio uses stored role once and synthesizes English fallback only when absent ${language}`, async ({page},info) => {
    const fixture = await studio(page,info.project.name === "static-export",String(info.project.use.baseURL),language);
    const handler = async (route:any) => new URL(route.request().url()).pathname.endsWith("/character-candidates")
      ? route.fulfill({json:{schema_version:"studio-character-candidates-v1",world_id:FEED_WORLD,items:[]}}) : route.fallback();
    await page.route("**/api/backend/**",handler); await page.route("http://127.0.0.1:8080/api/v1/**",handler);
    await page.goto(`/studio/worlds/${FEED_WORLD}?createdCharacterId=fixture-candidate`);
    const selector = page.getByRole("combobox",{name:language === "ko" ? "World 역할" : "World role",exact:true});
    await expect(selector.locator("option")).toHaveText(["No role"]);
    fixture.world.roles = [{key:"no_specific_role",name:"역할 없음",description:"별도의 World 역할을 지정하지 않은 캐릭터",responsibilities:[],allowed_activity_scope:[],autonomous_allowed:true}];
    await page.reload(); await expect(selector.locator("option")).toHaveText(["역할 없음"]);
    expect(fixture.writes).toEqual([]); expect(fixture.base.ui.management.providerCalls).toEqual([]);
  });
}
