import { verifyCreatorResponsive } from "./creator-copy-responsive";
import { test, expect } from "@playwright/test";
import { readFileSync, writeFileSync, mkdirSync } from "node:fs";
import { createHash } from "node:crypto";
import { installWorldFeedFixture, feedRoute } from "./world-feed-fixture";
import { installIntegrationFixture } from "./home-activity-memory-fixture";
import { FEED_WORLD } from "./world-feed-fixture";
import { installSocialChatFixture, chatRoute } from "./world-social-chat-fixture";
import { checkPhotoDimensions } from "../frontend/src/features/media/utils/photo-header";

const photoArtifacts = process.env.ANGMOO_BROWSER_PHOTO_ARTIFACTS ?? "../artifacts/creator-copy-media-20261010";
mkdirSync(photoArtifacts, { recursive: true });

function paddedJpeg(size: number) {
  const image = readFileSync("fixtures/photos/normal.jpg"), comments = []; let extra = size - image.length;
  while (extra) { const total = Math.min(extra, 65537), part = Buffer.alloc(total); part[0]=255; part[1]=254; part.writeUInt16BE(total-2,2); comments.push(part); extra-=total; }
  return Buffer.concat([image.subarray(0,2), ...comments, image.subarray(2)]);
}

test("EXIF mirror survives browser preparation and final attachment", async ({ page }, info) => {
  const state = await installWorldFeedFixture(page, info.project.name === "static-export", String(info.project.use.baseURL), "ko");
  await page.goto(feedRoute());
  const source = Buffer.from(await page.evaluate(async () => {
    const canvas = document.createElement("canvas"); canvas.width = 320; canvas.height = 240;
    const context = canvas.getContext("2d")!;
    context.fillStyle = "red"; context.fillRect(0, 0, 160, 240);
    context.fillStyle = "blue"; context.fillRect(160, 0, 160, 240);
    const blob = await new Promise<Blob>(resolve => canvas.toBlob(value => resolve(value!), "image/jpeg", .95));
    return [...new Uint8Array(await blob.arrayBuffer())];
  }));
  const tiff = Buffer.from("49492a0008000000010012010300010000000200000000000000", "hex");
  const exif = Buffer.concat([Buffer.from("Exif\0\0"), tiff]);
  const marker = Buffer.from([255, 225, 0, exif.length + 2]);
  const original = Buffer.concat([source.subarray(0, 2), marker, exif, source.subarray(2)]);
  await page.locator('input[type="file"][accept*="heic"]').setInputFiles({ name: "mirror.jpg", mimeType: "image/jpeg", buffer: original });
  await expect.poll(() => state.writes.filter(write => write.path === "/media/assets").length).toBe(1);
  const body = state.writes.find(write => write.path === "/media/assets")!.body!;
  const bytes = Buffer.from(String(body.data_base64), "base64");
  const pixels = await page.evaluate(async ({ data, mime }) => {
    const content = Uint8Array.from(atob(data), x => x.charCodeAt(0));
    const image = await createImageBitmap(new Blob([content], { type: mime }));
    const canvas = document.createElement("canvas"); canvas.width = image.width; canvas.height = image.height;
    const context = canvas.getContext("2d")!; context.drawImage(image, 0, 0);
    const result = { width: image.width, height: image.height, left: [...context.getImageData(10, 10, 1, 1).data] };
    image.close(); return result;
  }, { data: String(body.data_base64), mime: String(body.content_type) });
  expect(pixels).toMatchObject({ width: 320, height: 240 }); expect(pixels.left[2]).toBeGreaterThan(230);
  writeFileSync(`${photoArtifacts}/prepared-${info.project.name}-mirror.jpg`, bytes);
});

test("resized transparent PNG retains its format and alpha", async ({ page }, info) => {
  const state = await installWorldFeedFixture(page, info.project.name === "static-export", String(info.project.use.baseURL), "ko");
  await page.goto(feedRoute());
  const original = Buffer.from(await page.evaluate(async () => {
    const canvas = document.createElement("canvas"); canvas.width = 5000; canvas.height = 3500;
    const context = canvas.getContext("2d")!; context.fillStyle = "rgba(255, 0, 0, .25)"; context.fillRect(0, 0, 5000, 3500);
    const blob = await new Promise<Blob>(resolve => canvas.toBlob(value => resolve(value!), "image/png"));
    return [...new Uint8Array(await blob.arrayBuffer())];
  }));
  await page.locator('input[type="file"][accept*="heic"]').setInputFiles({ name: "resized-alpha.png", mimeType: "image/png", buffer: original });
  await expect.poll(() => state.writes.filter(row => row.path === "/media/assets").length).toBe(1);
  const body = state.writes.find(row => row.path === "/media/assets")!.body!;
  expect(body.content_type).toBe("image/png");
  const bytes = Buffer.from(String(body.data_base64), "base64"); expect(bytes.length).toBeLessThanOrEqual(10485760);
  const geometry = await page.evaluate(async ({ data, mime }) => {
    const bitmap = await createImageBitmap(new Blob([Uint8Array.from(atob(data), x => x.charCodeAt(0))], { type: mime }));
    const canvas = document.createElement("canvas"); canvas.width = bitmap.width; canvas.height = bitmap.height;
    const context = canvas.getContext("2d")!; context.drawImage(bitmap, 0, 0);
    const result = { width: bitmap.width, height: bitmap.height, alpha: context.getImageData(10, 10, 1, 1).data[3] };
    bitmap.close(); return result;
  }, { data: String(body.data_base64), mime: String(body.content_type) });
  expect(geometry).toEqual({ width: 4096, height: 2867, alpha: 64 });
  writeFileSync(`${photoArtifacts}/prepared-${info.project.name}-resized-alpha.png`, bytes);
});

for (const language of ["ko", "en"] as const) {
  for (const filename of ["normal.jpg", "primary.heic", "large.jpg", "orientation6.jpg", "alpha.png"]) {
    test(`actual photo codec and attachment copy ${filename} ${language}`, async ({ page }, info) => {
      const staticShell = info.project.name === "static-export";
      const state = await installWorldFeedFixture(page, staticShell, String(info.project.use.baseURL), language);
      await page.goto(feedRoute());
      const original = readFileSync(`fixtures/photos/${filename}`), before = createHash("sha256").update(original).digest("hex");
      await page.locator('input[type="file"][accept*="heic"]').setInputFiles({ name: filename, mimeType: filename.endsWith("heic") ? "image/heic" : filename.endsWith("png") ? "image/png" : "image/jpeg", buffer: original });
      await expect.poll(() => state.writes.filter(write => write.path === "/media/assets").length, { timeout: 45000 }).toBe(1);
      const body = state.writes.find(write => write.path === "/media/assets")!.body!;
      const bytes = Buffer.from(String(body.data_base64), "base64");
      expect(bytes.length).toBeLessThanOrEqual(10485760);
      const pixels = await page.evaluate(async ({ base64, mime }) => {
        const data = Uint8Array.from(atob(base64), c => c.charCodeAt(0));
        const bitmap = await createImageBitmap(new Blob([data], { type: mime }));
        const canvas = document.createElement("canvas"); canvas.width = bitmap.width; canvas.height = bitmap.height;
        const context = canvas.getContext("2d")!; context.drawImage(bitmap, 0, 0);
        const result = { width: bitmap.width, height: bitmap.height, corner: [...context.getImageData(10, 10, 1, 1).data] }; bitmap.close(); return result;
      }, { base64: String(body.data_base64), mime: String(body.content_type) });
      expect(pixels.width).toBeLessThanOrEqual(4096); expect(pixels.height).toBeLessThanOrEqual(4096);
      if (filename === "primary.heic") { expect(body.content_type).toBe("image/jpeg"); expect(pixels.width).toBe(320); expect(pixels.corner[0]).toBeGreaterThan(230); }
      if (filename === "orientation6.jpg") { expect(pixels.width).toBe(240); expect(pixels.height).toBe(320); }
      if (filename === "large.jpg") { expect(body.content_type).toBe("image/jpeg"); expect(pixels.width).toBe(4096); expect(pixels.height).toBe(2731); }
      if (["normal.jpg", "alpha.png"].includes(filename)) expect(bytes.equals(original)).toBe(true);
      if (filename === "alpha.png") expect(pixels.corner[3]).toBe(64);
      if (filename === "normal.jpg") await verifyCreatorResponsive(page);
      writeFileSync(`${photoArtifacts}/prepared-${info.project.name}-${filename}`, bytes);
      expect(createHash("sha256").update(original).digest("hex")).toBe(before);
      await expect(page.locator('img[alt]').filter({ visible: true }).first()).toBeVisible();
      console.log("PHOTO", language, filename, body.content_type, bytes.length, pixels);
      await page.screenshot({ path: `${photoArtifacts}/${info.project.name}-${language}-${filename}.png`, fullPage: true });
    });
  }
  test(`photo limits and preserved text ${language}`, async ({ page }, info) => {
    const state = await installWorldFeedFixture(page, info.project.name === "static-export", String(info.project.use.baseURL), language);
    await page.goto(feedRoute());
    const title = page.getByLabel(language === "ko" ? "제목" : "Title", { exact: true }); await title.fill("Preserved text");
    const input = page.locator('input[type="file"][accept*="heic"]');
    await input.setInputFiles({ name: "too-large.jpg", mimeType: "image/jpeg", buffer: Buffer.alloc(20 * 1024 * 1024 + 1) });
    await expect(page.locator('[data-ui-primitive="inline-error"]')).toContainText("20");
    expect(state.writes.filter(write => write.path === "/media/assets")).toHaveLength(0);
    await input.setInputFiles({ name: "broken.jpg", mimeType: "image/jpeg", buffer: Buffer.from("this is not a JPEG file") });
    await expect(page.locator('[data-ui-primitive="inline-error"]')).toBeVisible();
    await expect(title).toHaveValue("Preserved text");
    expect(state.writes.filter(write => write.path === "/media/assets")).toHaveLength(0);
  });
  test(`home font and explicit navigation ${language}`, async ({ page }, info) => {
    const external: string[] = [];
    await page.route(/^https?:\/\/(?!127\.0\.0\.1:)/, route => { external.push(route.request().url()); return route.abort(); });
    await installIntegrationFixture(page, info.project.name === "static-export", String(info.project.use.baseURL), language);
    await page.goto("/");
    const brand = page.getByRole("heading", { name: "Angmoo", exact: true }); await expect(brand).toBeVisible();
    expect(await brand.evaluate(async element => { await document.fonts.ready; const css = getComputedStyle(element); return { color: css.color, weight: css.fontWeight, loaded: document.fonts.check('700 22px "AngmooQuicksand"'), actualFace: Array.from(document.fonts).some(face => face.family.replaceAll('"', '') === "AngmooQuicksand" && face.status === "loaded"), family: css.fontFamily }; })).toMatchObject({ color: "rgb(255, 107, 107)", weight: "700", loaded: true, actualFace: true });
    await expect(page.getByText("LOCAL DEVICE", { exact: true })).toHaveCount(0); await verifyCreatorResponsive(page);
    for (const route of ["/settings", `/agents/new?worldId=${FEED_WORLD}`]) {
      await page.goto(route); await expect(page.locator('[data-ui-primitive="bottom-navigation"]')).toHaveCount(0);
      await expect(page.locator('[data-product-shell="device"] > div > footer')).toHaveCount(0); await verifyCreatorResponsive(page);
    }
    expect(external).toEqual([]);
  });

  test(`photo early geometry and animation rejection ${language}`, async ({ page }, info) => {
    const state = await installWorldFeedFixture(page, info.project.name === "static-export", String(info.project.use.baseURL), language);
    await page.goto(feedRoute()); const input = page.locator('input[type="file"][accept*="heic"]');
    const alpha = readFileSync("fixtures/photos/alpha.png");
    const tooWide = Buffer.from(alpha); tooWide.writeUInt32BE(16385,16);
    const tooMany = Buffer.from(alpha); tooMany.writeUInt32BE(8001,16); tooMany.writeUInt32BE(8000,20);
    const animation = Buffer.alloc(20); animation.writeUInt32BE(8,0); animation.write("acTL",4);
    const animated = Buffer.concat([alpha.subarray(0,33), animation, alpha.subarray(33)]);
    expect(() => checkPhotoDimensions(8000, 8000)).not.toThrow();
    expect(() => checkPhotoDimensions(8001, 8000)).toThrow("photo_dimensions");
    const catalog = JSON.parse(readFileSync(`../frontend/src/features/media/locales/${language}.json`, "utf8"));
    for (const [index, bytes] of [tooWide, tooMany, animated].entries()) {
      await input.setInputFiles({ name: "bounded.png", mimeType: "image/png", buffer: bytes });
      const message = index === 2 ? "움직이는 이미지나 동영상은 첨부할 수 없어요. 사진 한 장을 선택해주세요." : "사진 해상도가 너무 커요. 16,384px 이하, 전체 64메가픽셀 이하로 선택해주세요.";
      await expect(page.locator('[data-ui-primitive="inline-error"]')).toContainText(catalog[message]);
      expect(state.writes.filter(row => row.path === "/media/assets")).toHaveLength(0);
    }
  });

  test(`photo cancellation supersession and worker timeout preserve old attachment ${language}`, async ({ page }, info) => {
    await page.addInitScript(() => {
      const NativeWorker = window.Worker;
      Object.assign(window, { photoWork: { created: 0, terminated: 0 } });
      const work = (window as any).photoWork;
      window.Worker = class {
        constructor(url: string | URL, options?: WorkerOptions) {
          work.created++;
          if (work.created === 1 || work.created >= 5) return new NativeWorker(url, options);
          return { onmessage: null, onerror: null, postMessage() {}, terminate() { work.terminated++; } } as unknown as Worker;
        }
      } as typeof Worker;
    });
    const state = await installWorldFeedFixture(page, info.project.name === "static-export", String(info.project.use.baseURL), language);
    await page.goto(feedRoute()); const input = page.locator('input[type="file"][accept*="heic"]');
    const file = { name: "normal.jpg", mimeType: "image/jpeg", buffer: readFileSync("fixtures/photos/normal.jpg") };
    await input.setInputFiles(file); await expect.poll(() => state.writes.filter(row => row.path === "/media/assets").length).toBe(1);
    const title = page.getByLabel(language === "ko" ? "제목" : "Title", { exact: true }); await title.fill("Preserved text");
    await input.setInputFiles(file); await page.getByRole("button", { name: language === "ko" ? "사진 준비 취소" : "Cancel photo preparation", exact: true }).click();
    await expect.poll(() => page.evaluate(() => (window as any).photoWork.terminated)).toBe(1);
    expect(state.writes.filter(row => row.path === "/media/assets")).toHaveLength(1);
    await page.clock.install(); await input.setInputFiles(file); await input.setInputFiles(file);
    await expect.poll(() => page.evaluate(() => (window as any).photoWork.terminated)).toBe(2);
    await page.clock.fastForward(30001);
    await expect(page.locator('[data-ui-primitive="inline-error"]')).toBeVisible();
    await expect(title).toHaveValue("Preserved text");
    expect(state.writes.filter(row => row.path === "/media/assets")).toHaveLength(1);
    expect(state.writes.filter(row => row.method === "DELETE")).toHaveLength(0);
    await page.clock.resume(); await input.setInputFiles(file);
    await expect.poll(() => state.writes.filter(row => row.path === "/media/assets").length).toBe(2);
    await expect.poll(() => state.writes.filter(row => row.method === "DELETE").length).toBe(1);
    await expect(title).toHaveValue("Preserved text");
  });

  test(`source and final byte boundaries without gratuitous encoding ${language}`, async ({ page }, info) => {
    const state = await installWorldFeedFixture(page, info.project.name === "static-export", String(info.project.use.baseURL), language);
    await page.goto(feedRoute()); const input = page.locator('input[type="file"][accept*="heic"]');
    for (const size of [10485759, 10485760, 10485761, 20971519, 20971520]) {
      const previous = state.writes.filter(row => row.path === "/media/assets").length;
      await input.setInputFiles({ name: "bounded.jpg", mimeType: "image/jpeg", buffer: paddedJpeg(size) });
      await expect.poll(() => state.writes.filter(row => row.path === "/media/assets").length, { timeout: 45000 }).toBe(previous+1);
      const bytes = Buffer.from(String(state.writes.filter(row => row.path === "/media/assets").at(-1)!.body!.data_base64), "base64");
      expect(bytes.length).toBeLessThanOrEqual(10485760); if (size <= 10485760) expect(bytes.length).toBe(size); else expect(bytes.length).toBeLessThan(size);
    }
  });

  test(`chat photo preflight keeps its real asset gate ${language}`, async ({ page }, info) => {
    const state = await installSocialChatFixture(page, info.project.name === "static-export", String(info.project.use.baseURL), language);
    let allowed=false; const proofs: string[]=[];
    const handler = async (route: any) => { const path=new URL(route.request().url()).pathname;
      if (/\/media\/assets\/[^/]+\/preflight$/.test(path)) { proofs.push(path); return route.fulfill({json:{allowed,reason:allowed?null:"interpretation_disabled"}}); } return route.fallback(); };
    await page.route("**/api/backend/**",handler); await page.route("http://127.0.0.1:8080/api/v1/**",handler);
    await page.goto(chatRoute());
    const input=page.locator('input[type="file"][accept*="heic"]'), send=page.getByRole("button",{name:language==="ko"?"메시지 보내기":"Send message",exact:true});
    const file={name:"primary.heic",mimeType:"image/heic",buffer:readFileSync("fixtures/photos/primary.heic")};
    await input.setInputFiles(file); await expect.poll(()=>proofs.length).toBe(1); await expect(send).toBeDisabled();
    expect(proofs[0]).toContain("/draft-1/preflight"); expect(state.writes.filter(row=>row.path.endsWith("/messages"))).toEqual([]);
    allowed=true; await input.setInputFiles(file); await expect.poll(()=>proofs.length).toBe(2); await expect(send).toBeEnabled();
    await send.click(); await expect.poll(()=>state.writes.filter(row=>row.path.endsWith("/messages")).length).toBe(1);
    expect(state.writes.find(row=>row.path.endsWith("/messages"))!.data.attachment_asset_id).toBe("draft-2");
  });
}
