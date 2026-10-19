// Product components, translations and compiled CSS. Only network/runtime hooks
// are replaced; all inputs and images are synthetic and remain local.
import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { mkdir, readFile, readdir, writeFile } from "node:fs/promises";
import { createServer } from "node:http";
import { once } from "node:events";
import path from "node:path";
import { fileURLToPath } from "node:url";
const root = fileURLToPath(new URL("..", import.meta.url));
const require = createRequire(new URL("../package.json", import.meta.url));
const { webpack } = require("next/dist/compiled/webpack/webpack");
if (!process.env.ANGMOO_BROWSER_TEST_MODULES) throw new Error("ANGMOO_BROWSER_TEST_MODULES required");
const { chromium } = createRequire(path.join(process.env.ANGMOO_BROWSER_TEST_MODULES, "_test.cjs"))("playwright");
const output = path.resolve(root, "../../.task-output", `profile-evidence-browser-${Date.now()}`);
await mkdir(output, { recursive: true });
await writeFile(path.join(output, "ts.cjs"), `const ts=require(${JSON.stringify(require.resolve("typescript"))}); module.exports=s=>ts.transpileModule(s,{compilerOptions:{jsx:ts.JsxEmit.ReactJSX,module:ts.ModuleKind.ESNext,target:ts.ScriptTarget.ES2022}}).outputText;`);
const cssLoader = source => `const style=document.createElement("style");style.textContent=${JSON.stringify(source)};document.head.append(style);export default ${JSON.stringify(Object.fromEntries([...source.matchAll(/\.([A-Za-z][\w-]*)/g)].map(m => [m[1],m[1]])))}`;
await writeFile(path.join(output, "css.cjs"), `module.exports=${cssLoader.toString()}`);
const hooks = path.join(output, "hooks.js");
await writeFile(hooks, `export const useProductLeaveGuard=()=>()=>{};
export const captureAuthRequestScope=()=>window.fixture.scope; export const isCurrentAuthRequestScope=s=>s===window.fixture.scope;
export const usePrivateMediaUrl=v=>v; export const useRuntimeMediaUrl=v=>v;
export const useUiDateFormatter=()=>v=>v; export const getWorldChatEvidence=async()=>window.fixture.evidence;`);
const aliases = Object.fromEntries(["hooks/use-product-leave-guard", "hooks/use-private-media-url", "hooks/use-runtime-media-url", "hooks/use-ui-date-formatter", "lib/auth/browser-session", "features/memory/api/memory-client"].map(key => [`@/${key}`, hooks]));
const compiler = webpack({ mode: "development", devtool: false, context: root, entry: path.join(root, "scripts/fixtures/profile-evidence-browser.tsx"),
  plugins: [new webpack.DefinePlugin({ "process.env": JSON.stringify({ NODE_ENV: "development" }) })],
  output: { path: output, filename: "bundle.js" }, resolve: { extensions: [".tsx", ".ts", ".js"], alias: { ...aliases, "@": path.join(root, "src") }, modules: [path.join(root, "node_modules"), "node_modules"] },
  module: { rules: [{ test: /\.tsx?$/, use: path.join(output, "ts.cjs") }, { test: /\.css$/, use: path.join(output, "css.cjs") }] } });
await new Promise((resolve, reject) => compiler.run((e, s) => e || s.hasErrors() ? reject(e ?? new Error(s.toString({ all: false, errors: true }))) : resolve()));
await new Promise(resolve => compiler.close(resolve));
const bundle = await readFile(path.join(output, "bundle.js"));
const cssDir = path.join(root, ".next-local-stability/static/css");
const css = (await Promise.all((await readdir(cssDir)).filter(p => p.endsWith(".css")).map(p => readFile(path.join(cssDir, p), "utf8")))).join("\n");
const server = createServer((req, res) => {
  if (req.url === "/bundle.js") { res.setHeader("content-type", "text/javascript; charset=utf-8"); res.end(bundle); }
  else if (req.url === "/style.css") { res.setHeader("content-type", "text/css"); res.end(css); }
  else if (req.url === "/media/avatar.svg") { res.setHeader("content-type", "image/svg+xml"); res.end('<svg xmlns="http://www.w3.org/2000/svg" width="200" height="200"><rect width="200" height="200" fill="#a7d8f0"/><circle cx="100" cy="90" r="55" fill="#a52a2a"/></svg>'); }
  else { res.setHeader("content-type", "text/html; charset=utf-8"); res.end('<!doctype html><html lang="en"><meta charset="utf-8"><link rel="stylesheet" href="/style.css"><div id="root"></div><script src="/bundle.js"></script></html>'); }
});
server.listen(0, "127.0.0.1"); await once(server, "listening");
const browser = await chromium.launch({ channel: "msedge", headless: true });
const page = await browser.newPage({ viewport: { width: 800, height: 900 } });
const errors = []; page.on("pageerror", error => errors.push(error.message));
const measures = [];
try {
  await page.goto(`http://127.0.0.1:${server.address().port}`); await page.getByText("Upload avatar", { exact: true }).waitFor();
  for (const language of ["en", "ko"]) for (const zoom of [1, 1.25, 1.5]) for (const avatar of [true, false]) {
    await page.evaluate(({ language, zoom, avatar }) => { fixture.i18n.changeLanguage(language); fixture.set({ avatar, banner: !avatar, overlay: !avatar }); document.body.style.zoom = String(zoom); }, { language, zoom, avatar });
    const measure = await page.locator('[class*="top-[-54px]"]').evaluate(frame => {
      const avatar = frame.firstElementChild, outer = frame.getBoundingClientRect(), inner = avatar.getBoundingClientRect();
      const css = getComputedStyle(frame); return { width: outer.width, height: outer.height, avatar: inner.height, display: css.display,
        extra: (outer.height-inner.height)/Number(document.body.style.zoom)-parseFloat(css.borderTopWidth)-parseFloat(css.borderBottomWidth) };
    });
    assert.equal(measure.display, "flex"); assert.ok(Math.abs(measure.extra) < 1, JSON.stringify(measure)); measures.push({ language, zoom, avatar, ...measure });
  }
  // Demonstrate the old line-box gap without editing the component.
  await page.evaluate(() => fixture.set({ avatar: true, overlay: false }));
  await page.locator('[class*="top-[-54px]"] img').waitFor();
  const originalGap = await page.locator('[class*="top-[-54px]"]').evaluate(frame => {
    frame.style.display = "block"; const value = (frame.getBoundingClientRect().height-frame.firstElementChild.getBoundingClientRect().height)/1.5-parseFloat(getComputedStyle(frame).borderTopWidth)-parseFloat(getComputedStyle(frame).borderBottomWidth); frame.style.display = ""; return value;
  });
  assert.ok(originalGap > 2, `expected baseline gap, got ${originalGap}`);
  await page.evaluate(() => { document.body.style.zoom = "1"; fixture.set({ avatar: true, overlay: false }); });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.screenshot({ path: path.join(output, "profile-ko-small.png"), fullPage: true });
  await page.evaluate(() => { fixture.i18n.changeLanguage("en"); fixture.set({ evidence: true }); });
  await page.getByRole("dialog").waitFor(); await page.getByText("Today's SNS activity", { exact: true }).first().waitFor();
  const english = await page.getByRole("dialog").innerText();
  assert.ok(english.includes("SNS activity type: posts_authored")); assert.ok(english.includes("Actor: Ian"));
  assert.ok(english.includes("<img src=x")); assert.ok(english.includes("과거 원문 그대로"));
  assert.equal(await page.evaluate(() => Boolean(window.injected)), false);
  assert.equal(await page.getByRole("dialog").locator("img").count(), 0);
  const validation = await page.evaluate(() => [fixture.displaySegmentsMatch(fixture.item),
    fixture.displaySegmentsMatch({ ...fixture.item, excerpt: "different" }),
    fixture.displaySegmentsMatch({ ...fixture.item, display_segments: [{ key: "invented", text: fixture.item.excerpt }] }),
    fixture.displaySegmentsMatch({ ...fixture.item, availability: "deleted" })]);
  assert.deepEqual(validation, [true, false, false, false]);
  await page.screenshot({ path: path.join(output, "evidence-en-small.png"), fullPage: true });
  await page.evaluate(() => fixture.i18n.changeLanguage("ko"));
  await page.getByText("오늘 SNS 활동", { exact: true }).first().waitFor();
  assert.ok((await page.getByRole("dialog").innerText()).includes("행동 주체: Ian"));
  await page.keyboard.press("Escape"); await page.getByRole("dialog").waitFor({ state: "hidden" });
  await page.evaluate(() => { fixture.i18n.changeLanguage("en"); fixture.set({ overlay: false }); });
  const png = await page.evaluate(() => { const canvas = document.createElement("canvas"); canvas.width = canvas.height = 32;
    canvas.getContext("2d").fillRect(0, 0, 32, 32); return canvas.toDataURL("image/png").split(",")[1]; });
  const upload = page.locator('input[type="file"]').last();
  const choose = () => upload.setInputFiles({ name: "synthetic.png", mimeType: "image/png", buffer: Buffer.from(png, "base64") });
  await choose(); await page.getByRole("dialog").waitFor();
  await page.getByRole("dialog").getByRole("button", { name: "Cancel", exact: true }).click();
  assert.equal(await page.evaluate(() => fixture.uploads), 0);
  await choose(); await page.getByRole("dialog").waitFor();
  await page.getByRole("dialog").getByRole("button", { name: "Save", exact: true }).click();
  await page.getByRole("dialog").waitFor({ state: "hidden" });
  assert.equal(await page.evaluate(() => fixture.uploads), 1);
  // A delayed decode from the previous owner/runtime cannot open an old cropper.
  await page.evaluate(() => { const original = window.createImageBitmap;
    window.createImageBitmap = async (...args) => { const bitmap = await original(...args);
      await new Promise(resolve => fixture.releaseDecode = resolve); return bitmap; }; });
  await choose(); await page.waitForFunction(() => Boolean(fixture.releaseDecode));
  await page.evaluate(() => { fixture.scope++; fixture.releaseDecode(); });
  await page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))));
  assert.equal(await page.getByRole("dialog").count(), 0);
  assert.equal(await page.evaluate(() => fixture.uploads), 1);
  assert.deepEqual(errors, []);
  await writeFile(path.join(output, "measurements.json"), JSON.stringify({ originalGap, measures }, null, 2));
  console.log(`profile_evidence_browser_pass: 12 layout cases; baseline gap=${originalGap}; crop cancel/apply, stale decode, ko/en, literal safety, legacy, strict parser, dialog keyboard; evidence=${output}`);
} catch (error) { console.error({ errors, body: (await page.locator("body").innerText()).slice(0, 1600) }); throw error; }
finally { await browser.close(); await new Promise(resolve => server.close(resolve)); }
