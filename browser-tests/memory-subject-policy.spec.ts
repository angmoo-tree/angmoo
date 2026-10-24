import { test, expect } from "@playwright/test";
import { installUiFixture, installMemoryUi } from "./world-ui-improvements-fixture";
import { FEED_WORLD, OTHER_FEED_WORLD, ownerId } from "./world-feed-fixture";
import { WORLD_AGENT, syntheticWorldCharacter } from "./world-character-management-fixture";

for (const language of ["ko", "en"] as const) {
  test(`Memory selects only AI by type and blocks owner URLs and empty World ${language}`, async ({page}, info) => {
    const ui = await installUiFixture(page, info.project.name === "static-export", String(info.project.use.baseURL), language);
    const memory = await installMemoryUi(page);
    const owner = syntheticWorldCharacter(ownerId(FEED_WORLD)).profile;
    owner.display_name = "Renamed human";
    const ai = syntheticWorldCharacter(WORLD_AGENT, FEED_WORLD, false).profile; ai.display_name = "User";
    let onlyOwner = false; const denied: string[] = [];
    const handler = async (route: any) => {
      const path = new URL(route.request().url()).pathname;
      if (path.endsWith(`/worlds/${FEED_WORLD}/world-characters`)) return route.fulfill({json:{schema_version:"world-character-profile-list-v1",world_id:FEED_WORLD,items:onlyOwner ? [owner] : [owner, ai]}});
      if (path.includes(`/world-characters/${owner.world_character_id}/`) && /memory|memories|embedding/.test(path)) { denied.push(path); return route.fulfill({status:500}); }
      return route.fallback();
    };
    await page.route("**/api/backend/**", handler); await page.route("http://127.0.0.1:8080/api/v1/**", handler);
    await page.goto(`/memory?world=${FEED_WORLD}`);
    const selector = page.getByRole("combobox", {name:language === "ko" ? "기억하는 Character" : "Remembering character",exact:true});
    await expect(selector).toHaveValue(WORLD_AGENT);
    await expect(selector.locator("option")).toHaveText(["User"]);
    await expect.poll(() => memory.reads.some(path => path.endsWith("/memories"))).toBe(true);
    await page.goto(`/memory?world=${FEED_WORLD}&subject=${owner.world_character_id}&memory=old-memory`);
    await expect(page.getByText(language === "ko" ? "기억을 관리할 캐릭터를 선택해 주세요." : "Choose a character to manage their memories.", {exact:true}).last()).toBeVisible();
    await expect(selector).toHaveValue(""); await expect(page).not.toHaveURL(/memory=old-memory/);
    await page.reload(); await expect(selector).toHaveValue("");
    await selector.selectOption(WORLD_AGENT); await expect(selector).toHaveValue(WORLD_AGENT);
    onlyOwner = true; await page.goto(`/memory?world=${FEED_WORLD}`);
    await expect(page.getByText(language === "ko" ? "기억을 관리할 캐릭터가 없어요." : "There are no characters whose memories you can manage.", {exact:true})).toBeVisible();
    await expect(selector).toBeDisabled();
    expect(denied).toEqual([]); expect(memory.writes).toEqual([]); expect(ui.management.providerCalls).toEqual([]);
    await page.screenshot({path:info.outputPath(`memory-empty-${language}.png`)});
  });

  test(`Memory preserves user speech as AI evidence and discards old World reads ${language}`, async ({page},info) => {
    const ui = await installUiFixture(page,info.project.name === "static-export",String(info.project.use.baseURL),language);
    await installMemoryUi(page);
    await installMemoryUi(page,OTHER_FEED_WORLD,"other-ai");
    const scope = {world_id:FEED_WORLD,subject_world_character_id:WORLD_AGENT}, capabilities = {read:"available",mutate:"available"};
    const item = {id:"ai-user-memory",memory_kind:"AUTOBIOGRAPHICAL_EVENT",summary:"AI remembers the user",lifecycle:"active",formed_at:"2026-10-24T01:00:00Z",valid_from:"2026-10-24T01:00:00Z",valid_until:null,pinned:false,superseded_by_memory_id:null,retention_days:180,related_character:null,version:1};
    let delayed = false, release!: () => void, captured = 0;
    const barrier = new Promise<void>(resolve => {release=resolve;});
    const handler = async (route:any) => {
      const path = new URL(route.request().url()).pathname;
      if (!path.includes(`/worlds/${FEED_WORLD}/world-characters/${WORLD_AGENT}/`)) return route.fallback();
      if (path.endsWith("/memories")) {
        if (delayed) { captured++; await barrier; }
        try { return await route.fulfill({json:{schema_version:"memory-item-list.v1",scope,memory_enabled:true,items:[item],next_cursor:null,capabilities}}); } catch { return; }
      }
      if (path.endsWith(`/memories/${item.id}`)) return route.fulfill({json:{...item,schema_version:"memory-item-detail.v1",scope,capabilities,evidence:[{source_kind:"CHAT_MESSAGE",source_label:"User",source_created_at:item.formed_at,availability:"available",excerpt:"User: My original words remain here.",related_character:null,canonical_href:null}],provenance_summary:"1 source"}});
      return route.fallback();
    };
    await page.route("**/api/backend/**",handler); await page.route("http://127.0.0.1:8080/api/v1/**",handler);
    await page.goto(`/memory?world=${FEED_WORLD}&subject=${WORLD_AGENT}&memory=${item.id}`);
    await expect(page.getByText("User: My original words remain here.",{exact:true})).toBeVisible();
    const world = page.getByRole("combobox",{name:"World",exact:true});
    await world.selectOption(OTHER_FEED_WORLD);
    await expect(page.getByText("User: My original words remain here.",{exact:true})).toHaveCount(0);
    delayed = true; await world.selectOption(FEED_WORLD); await expect.poll(() => captured).toBeGreaterThan(0);
    await world.selectOption(OTHER_FEED_WORLD); release();
    await expect(page.getByRole("combobox",{name:language === "ko" ? "기억하는 Character" : "Remembering character",exact:true})).toHaveValue("other-ai");
    await expect(page.getByText(item.summary,{exact:true})).toHaveCount(0);
    await page.evaluate(() => window.dispatchEvent(new Event("angmoo:desktop-runtime-config-changed")));
    await expect(page.getByText(item.summary,{exact:true})).toHaveCount(0);
    expect(ui.management.writes).toEqual([]); expect(ui.management.providerCalls).toEqual([]);
  });

}
