import { test, expect } from "@playwright/test";
import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import { guardExternalInput } from "./photo-input-fixture";
import { installIntegrationFixture } from "./home-activity-memory-fixture";
import { installUiFixture, installLegacyImageUi } from "./world-ui-improvements-fixture";
import { continuityAgentDetail } from "./continuity-fixture";
import { FEED_WORLD } from "./world-feed-fixture";
import { WORLD_AGENT, worldCharacterRoute } from "./world-character-management-fixture";

const jpeg = readFileSync("fixtures/photos/normal.jpg");
const hash = (buffer: Buffer) => createHash("sha256").update(buffer).digest("hex");
const document = { spec:"chara_card_v2", spec_version:"2.0", data:{name:"Input card", description:"Original persona", personality:"Quiet", scenario:"", first_mes:"Hello", mes_example:"", creator_notes:"Keep original", system_prompt:"", post_history_instructions:"", alternate_greetings:[], tags:[], creator:"fixture", character_version:"1", extensions:{fixture:"unchanged"}} };
const json = Buffer.from(JSON.stringify(document));
function cardPng() {
  const image = readFileSync("../backend/tests/image_integration/fixtures/pixels.png");
  const data = Buffer.from(`chara\0${json.toString("base64")}`), kind = Buffer.from("tEXt");
  let crc = 0xffffffff;
  for (const byte of Buffer.concat([kind, data])) { crc ^= byte; for (let bit=0; bit<8; bit++) crc = (crc >>> 1) ^ ((crc & 1) ? 0xedb88320 : 0); }
  const size = Buffer.alloc(4), sum = Buffer.alloc(4); size.writeUInt32BE(data.length); sum.writeUInt32BE((crc ^ 0xffffffff) >>> 0);
  return Buffer.concat([image.subarray(0,-12), size,kind,data,sum,image.subarray(-12)]);
}

for (const language of ["ko", "en"] as const) {
  for (const format of ["json", "png"] as const) test(`card ${format} preserves exact metadata and reads before draft creation ${language}`, async ({page}, info) => {
    await guardExternalInput(page);
    const state = await installIntegrationFixture(page, info.project.name === "static-export", String(info.project.use.baseURL), language);
    const buffer = format === "json" ? json : cardPng(); let imported: Buffer | null = null, preview = buffer;
    const handler = async (route: any) => {
      const path = new URL(route.request().url()).pathname;
      if (path.endsWith("/agents/drafts/integration-draft/media/avatar")) return route.fulfill({body:preview,contentType:preview === buffer ? "image/png" : "image/webp"});
      if (path.endsWith("/agents/drafts/integration-draft/media") && route.request().method() === "POST") {
        preview = Buffer.from(route.request().postDataJSON().data_base64,"base64"); state.draft!.revision++;
        return route.fulfill({json:state.draft});
      }
      if (!path.endsWith("/agents/drafts/integration-draft/card")) return route.fallback();
      const body = route.request().postDataJSON(); expect(body.revision).toBe(state.draft!.revision);
      imported = Buffer.from(body.data_base64,"base64");
      Object.assign(state.draft!, {source_kind:"card", name:"Input card", worldview:"Original persona", revision:state.draft!.revision+1});
      if (format === "png") state.draft!.avatar_temp_url = "/api/v1/agents/drafts/integration-draft/media/avatar";
      return route.fulfill({json:{draft:state.draft,card_version:2,review:[],raw_only:["first_mes"],metadata_selection:format === "png" ? {keyword:"chara",same_keyword_count:1} : null}});
    };
    await page.route("**/api/backend/**",handler); await page.route("http://127.0.0.1:8080/api/v1/**",handler);
    await page.goto(`/agents/new?worldId=${FEED_WORLD}`); await page.locator('input[value="card"]').check();
    const input = page.locator('input[accept=".png,.json"]');
    await page.evaluate(() => { (window as any).inputProof.fail = true; });
    await input.setInputFiles({name:`card.${format}`,mimeType:format === "png" ? "image/png" : "application/json", buffer});
    await expect(page.getByText(language === "ko" ? "파일을 읽지 못했어요. 다시 선택해 주세요." : "The file could not be read. Select it again.", {exact:true})).toBeVisible();
    expect(state.draft).toBeNull(); expect(state.writes).toEqual([]); expect(imported).toBeNull();
    await page.evaluate(() => { (window as any).inputProof.fail = false; });
    await input.setInputFiles({name:`card.${format}`,mimeType:format === "png" ? "image/png" : "application/json",buffer});
    await expect(page.getByRole("textbox",{name:language === "ko" ? "이름" : "Name",exact:true})).toHaveValue("Input card");
    expect(hash(imported!)).toBe(hash(buffer)); expect(await page.evaluate(() => (window as any).inputProof.reads)).toBe(2);
    if (format === "png") {
      const next = page.getByRole("button",{name:language === "ko" ? "저장하고 다음" : "Save and continue",exact:true});
      await next.click(); await next.click();
      const image = page.locator('img[src^="blob:"]'); await expect(image).toHaveCount(1);
      const initial = await image.getAttribute("src");
      const id = await page.getByRole("button",{name:language === "ko" ? "아바타 업로드" : "Upload avatar",exact:true}).evaluate(element => element.nextElementSibling!.id);
      await page.locator(`[id="${id}"]`).setInputFiles({name:"replacement.jpg",mimeType:"image/jpeg",buffer:jpeg});
      await page.getByRole("dialog").getByRole("button",{name:language === "ko" ? "저장" : "Save",exact:true}).click();
      await expect(image).not.toHaveAttribute("src",initial!);
      expect(hash(imported!)).toBe(hash(buffer)); expect(state.draft!.worldview).toBe("Original persona");
    }
    expect(state.ui.management.providerCalls).toEqual([]);
  });

  for (const scope of ["character", "world_character"] as const) test(`reference ${scope} keeps its 10 MiB policy and owned bytes ${language}`, async ({page},info) => {
    await guardExternalInput(page);
    const state = await installUiFixture(page, info.project.name === "static-export", String(info.project.use.baseURL), language);
    if (scope === "character") await installLegacyImageUi(page);
    const writes: any[] = []; const forbidden: string[] = [];
    const handler = async (route: any) => {
      const path = new URL(route.request().url()).pathname.replace(/^\/api\/(backend|v1)/, "");
      if (path === "/media/assets" && route.request().method() === "POST") {
        writes.push(route.request().postDataJSON());
        return route.fulfill({json:{id:"reference-fixture",url:"/api/v1/media/assets/reference-fixture/content",allowed:true}});
      }
      if (path === "/media/assets/reference-fixture/content") return route.fulfill({contentType:"image/jpeg",body:jpeg});
      if (/preflight|image-generation/.test(path)) { forbidden.push(path); return route.fulfill({status:500}); }
      return route.fallback();
    };
    await page.route("**/api/backend/**",handler); await page.route("http://127.0.0.1:8080/api/v1/**",handler);
    await page.goto(scope === "character" ? `/agents/${WORLD_AGENT}?tab=settings` : `${worldCharacterRoute()}?view=settings`);
    const input = page.getByLabel(language === "ko" ? "첨부 이미지 선택" : "Select image attachment",{exact:true});
    await expect(input).toBeAttached();
    await page.evaluate(() => { (window as any).inputProof.fail = true; });
    await input.setInputFiles({name:"reference.jpg",mimeType:"image/jpeg",buffer:jpeg});
    await expect(page.getByText(language === "ko" ? "사진을 읽지 못했어요. 사진 목록에서 다시 선택해 주세요." : "The photo could not be read. Select it again from your photos.",{exact:true})).toBeVisible();
    expect(writes).toHaveLength(0);
    await page.evaluate(() => { (window as any).inputProof.fail = false; });
    await input.setInputFiles({name:"reference.jpg",mimeType:"image/jpeg",buffer:jpeg});
    await expect.poll(() => writes.length).toBe(1);
    expect(writes[0]).toMatchObject({scope_kind:scope, scope_id:WORLD_AGENT,content_type:"image/jpeg"});
    expect(hash(Buffer.from(writes[0].data_base64,"base64"))).toBe(hash(jpeg));
    await input.setInputFiles({name:"too-large.png",mimeType:"image/png",buffer:Buffer.alloc(10*1024*1024+1)});
    await expect(page.getByText(language === "ko" ? "10MB 이하의 PNG, JPG 또는 WebP 이미지를 선택해 주세요." : "Choose a PNG, JPG or WebP image up to 10 MB.",{exact:true})).toBeVisible();
    expect(writes).toHaveLength(1); expect(forbidden).toEqual([]); expect(state.management.providerCalls).toEqual([]);
  });
}

// Run only on a second isolated build with the existing experimental feature flag enabled.
for (const language of ["ko", "en"] as const) test(`conditional user seed input reads before metadata and preserves server contract ${language}`, async ({page},info) => {
  test.skip(process.env.ANGMOO_PHOTO_SEED_CHECK !== "1", "Conditional input is tested in the separate feature-enabled build.");
  await guardExternalInput(page);
  await installUiFixture(page, info.project.name === "static-export", String(info.project.use.baseURL), language);
  await installLegacyImageUi(page);
  const detail = continuityAgentDetail(WORLD_AGENT); detail.image_settings.image_key_mode = "user";
  const writes: any[] = [];
  const handler = async (route:any) => {
    const path = new URL(route.request().url()).pathname.replace(/^\/api\/(backend|v1)/, "");
    if (path === `/agents/${WORLD_AGENT}`) return route.fulfill({json:detail});
    if (path.endsWith("/image-settings/seed")) { writes.push(route.request().postDataJSON()); return route.fulfill({json:{...detail.image_settings,seed_image_url:"/api/v1/media/assets/seed/content"}}); }
    if (path.endsWith("/media/assets/seed/content")) return route.fulfill({contentType:"image/jpeg",body:jpeg});
    return route.fallback();
  };
  await page.route("**/api/backend/**",handler); await page.route("http://127.0.0.1:8080/api/v1/**",handler);
  await page.goto(`/agents/${WORLD_AGENT}?tab=settings`);
  const input = page.getByLabel(language === "ko" ? "시드 이미지 업로드" : "Upload seed image");
  await expect(input).toBeAttached();
  await page.evaluate(() => { (window as any).inputProof.fail = true; });
  await input.setInputFiles({name:"seed.jpg",mimeType:"image/jpeg",buffer:jpeg});
  await expect(page.getByText(language === "ko" ? "사진을 읽지 못했어요. 사진 목록에서 다시 선택해 주세요." : "The photo could not be read. Select it again from your photos.",{exact:true})).toBeVisible(); expect(writes).toEqual([]);
  await page.evaluate(() => { (window as any).inputProof.fail = false; });
  await input.setInputFiles({name:"seed.jpg",mimeType:"image/jpeg",buffer:jpeg});
  await expect.poll(() => writes.length).toBe(1);
  expect(hash(Buffer.from(writes[0].data_base64,"base64"))).toBe(hash(jpeg));
  expect(writes[0]).toMatchObject({filename:"seed.jpg",content_type:"image/jpeg"});
  await expect(page.getByRole("img", {name:language === "ko" ? "시드 이미지" : "Seed image",exact:true})).toBeVisible();
});
