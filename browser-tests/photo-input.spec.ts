import { test, expect } from "@playwright/test";
import { guardExternalInput } from "./photo-input-fixture";
import { readFileSync } from "node:fs";
import { installIntegrationFixture } from "./home-activity-memory-fixture";
import { installWorldFeedFixture, feedRoute, FEED_WORLD } from "./world-feed-fixture";

const photo = (name = "normal.jpg") => ({ name, mimeType: "image/jpeg", buffer: readFileSync("fixtures/photos/normal.jpg") });

for (const language of ["ko", "en"] as const) {
  test(`selected file read once before metadata, real Worker transfer and read error ${language}`, async ({page}, info) => {
    await guardExternalInput(page);
    const state = await installWorldFeedFixture(page, info.project.name === "static-export", String(info.project.use.baseURL), language);
    await page.goto(feedRoute());
    const input = page.locator('input[type="file"][accept*="heic"]');
    await input.setInputFiles(photo());
    await expect.poll(() => state.writes.filter(row => row.path === "/media/assets").length).toBe(1);
    const title = page.getByLabel(language === "ko" ? "제목" : "Title", {exact:true}); await title.fill("Preserved input");
    await page.evaluate(() => { (window as any).inputProof.fail = true; });
    await input.setInputFiles(photo());
    await expect(page.locator('[data-ui-primitive="inline-error"]')).toContainText(language === "ko" ? "사진을 읽지 못했어요." : "The photo could not be read.");
    await expect(page.getByRole("link", {name:language === "ko" ? "이미지 인식 설정 열기" : "Open image recognition settings"})).toHaveCount(0);
    await expect(title).toHaveValue("Preserved input");
    expect(state.writes.filter(row => row.path === "/media/assets")).toHaveLength(1);
    expect(await page.evaluate(() => (window as any).inputProof)).toMatchObject({reads:2, transfers:1, terminated:1});
  });

  test(`creation avatar and banner same URL refresh, saved GET failure and read-only retry ${language}`, async ({page}, info) => {
    await guardExternalInput(page);
    const state = await installIntegrationFixture(page, info.project.name === "static-export", String(info.project.use.baseURL), language);
    const images = new Map<string, Buffer>(); let uploads = 0, gets = 0, failGet = false, failUpload = false;
    const readsByKind = {avatar: 0, banner: 0};
    const handler = async (route: any) => {
      const path = new URL(route.request().url()).pathname.replace(/^\/api\/(backend|v1)/, "");
      if (path === "/agents/drafts/integration-draft/media" && route.request().method() === "POST") {
        uploads++; const body = route.request().postDataJSON();
        if (failUpload) return route.fulfill({status:409,json:{detail:"draft_revision_conflict"}});
        images.set(body.media_type, Buffer.from(body.data_base64, "base64"));
        state.draft![`${body.media_type as "avatar"|"banner"}_temp_url`] = `/api/v1/agents/drafts/integration-draft/media/${body.media_type}`;
        state.draft!.revision++;
        return route.fulfill({json: state.draft});
      }
      if (/^\/agents\/drafts\/integration-draft\/media\/(avatar|banner)$/.test(path)) {
        readsByKind[path.split("/").at(-1)! as "avatar" | "banner"]++;
        gets++; const bytes = images.get(path.split("/").at(-1)!);
        return failGet ? route.fulfill({status:503}) : route.fulfill({contentType:"image/webp",body:bytes});
      }
      return route.fallback();
    };
    await page.route("**/api/backend/**", handler); await page.route("http://127.0.0.1:8080/api/v1/**", handler);
    await page.goto(`/agents/new?worldId=${FEED_WORLD}`);
    const next = page.getByRole("button", {name:language === "ko" ? "저장하고 다음" : "Save and continue",exact:true});
    await next.click(); await page.getByRole("textbox", {name:language === "ko" ? "이름" : "Name",exact:true}).fill("Preserved name");
    await next.click(); await page.getByRole("textbox", {name:language === "ko" ? "캐릭터 설명" : "Character description",exact:true}).fill("Preserved persona"); await next.click();
    const colored = async (color: string) => ({ name:"solid.png", mimeType:"image/png", buffer: Buffer.from(await page.evaluate(color => {
      const canvas = document.createElement("canvas"); canvas.width = 128; canvas.height = 128;
      const context = canvas.getContext("2d")!; context.fillStyle = color; context.fillRect(0,0,128,128);
      return canvas.toDataURL("image/png").split(",")[1];
    }, color), "base64") });
    const red = await colored("#ff0000"), green = await colored("#00ff00");
    for (const kind of ["avatar", "banner"] as const) {
      const label = language === "ko" ? kind === "avatar" ? "아바타 업로드" : "배너 업로드" : kind === "avatar" ? "Upload avatar" : "Upload banner";
      const inputId = await page.getByRole("button", {name:label,exact:true}).evaluate(element => (element.nextElementSibling as HTMLInputElement).id);
      const input = page.locator(`[id="${inputId}"]`);
      await input.setInputFiles(red);
      const dialog = page.getByRole("dialog"); await expect(dialog).toBeVisible();
      await dialog.getByRole("button", {name:language === "ko" ? "저장" : "Save",exact:true}).click();
      await expect(dialog).toHaveCount(0);
      await expect.poll(() => gets).toBeGreaterThan(0);
      await expect(page.locator('img[src^="blob:"]')).toHaveCount(kind === "avatar" ? 1 : 2);
      const before = await page.locator('img[src^="blob:"]').evaluateAll(nodes => nodes.map(node => (node as HTMLImageElement).src));
      const currentImage = page.locator('img[src^="blob:"]').first();
      const pixel = () => currentImage.evaluate((image: HTMLImageElement) => {
        const canvas = document.createElement("canvas"); canvas.width = canvas.height = 1;
        const context = canvas.getContext("2d")!; context.drawImage(image,0,0,1,1); return Array.from(context.getImageData(0,0,1,1).data);
      });
      // Crop output is lossy WebP: verify the displayed color within codec rounding.
      await expect.poll(async () => { const [r,g,b,a] = await pixel(); return r >= 250 && g <= 4 && b <= 4 && a === 255; }).toBe(true);
      const otherGets = readsByKind[kind === "avatar" ? "banner" : "avatar"];
      failGet = true; const count = uploads;
      await input.setInputFiles(green); await dialog.getByRole("button", {name:language === "ko" ? "저장" : "Save",exact:true}).click();
      const previewFailure = page.getByRole("alert").filter({hasText:language === "ko" ? "이미지는 저장했지만" : "The image was saved"});
      await expect(previewFailure).toBeVisible();
      expect(uploads).toBe(count + 1);
      expect(await page.locator('img[src^="blob:"]').evaluateAll(nodes => nodes.map(node => (node as HTMLImageElement).src))).toEqual(before);
      failGet = false;
      await page.getByRole("button", {name:language === "ko" ? `${kind === "avatar" ? "아바타" : "배너"} 미리보기 다시 불러오기` : `Reload ${kind === "avatar" ? "Avatar" : "Banner"} preview`,exact:true}).click();
      await expect(previewFailure).toHaveCount(0);
      await expect.poll(() => page.locator('img[src^="blob:"]').evaluateAll(nodes => nodes.map(node => (node as HTMLImageElement).src))).not.toEqual(before);
      await expect.poll(async () => { const [r,g,b,a] = await pixel(); return r <= 4 && g >= 250 && b <= 4 && a === 255; }).toBe(true);
      expect(readsByKind[kind === "avatar" ? "banner" : "avatar"]).toBe(otherGets);
      const revoked = await page.evaluate(() => (window as any).inputProof.revoked as string[]);
      expect(before.some(url => revoked.includes(url))).toBe(true);
      expect(uploads).toBe(count + 1);
      const good = await currentImage.getAttribute("src"), goodGets = gets;
      failUpload = true;
      await input.setInputFiles(red); await dialog.getByRole("button", {name:language === "ko" ? "저장" : "Save",exact:true}).click();
      await expect.poll(() => uploads).toBe(count + 2);
      await expect(dialog).toBeVisible();
      await expect(dialog.getByRole("button",{name:language === "ko" ? "저장" : "Save",exact:true})).toBeEnabled();
      expect(gets).toBe(goodGets); expect(await currentImage.getAttribute("src")).toBe(good);
      await dialog.getByRole("button",{name:language === "ko" ? "취소" : "Cancel",exact:true}).click(); failUpload = false;
    }
    expect(state.draft!.name).toBe("Preserved name"); expect(state.draft!.worldview).toBe("Preserved persona");
    expect(state.ui.management.providerCalls).toEqual([]);
    await page.screenshot({path:info.outputPath(`saved-preview-${language}.png`)});
  });
}
