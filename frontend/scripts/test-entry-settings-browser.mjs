// Isolated Chromium, actual React controls and cross-tab IndexedDB; synthetic API only.
import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import { createServer } from "node:http";
import { once } from "node:events";
import path from "node:path";
import { fileURLToPath } from "node:url";

const root = fileURLToPath(new URL("..", import.meta.url));
const require = createRequire(new URL("../package.json", import.meta.url));
const { webpack } = require("next/dist/compiled/webpack/webpack");
const runtime = process.env.ANGMOO_BROWSER_TEST_MODULES;
if (!runtime) throw new Error("Set ANGMOO_BROWSER_TEST_MODULES to the available Playwright node_modules directory");
const { chromium } = createRequire(path.join(runtime, "_test.cjs"))("playwright");
const output = path.resolve(root, "../../.task-output", `entry-settings-browser-${Date.now()}`);
await mkdir(output, { recursive: true });
const loader = path.join(output, "typescript-loader.cjs");
await writeFile(loader, `const ts = require(${JSON.stringify(require.resolve("typescript"))}); module.exports = function(source) { return ts.transpileModule(source, {compilerOptions:{jsx:ts.JsxEmit.ReactJSX,module:ts.ModuleKind.ESNext,target:ts.ScriptTarget.ES2022}}).outputText; };`);
await writeFile(path.join(output, "css-loader.cjs"), 'module.exports = source => "export default " + JSON.stringify(Object.fromEntries([...source.matchAll(/\\.([A-Za-z][\\w-]*)/g)].map(m => [m[1],m[1]])))');
const hooks = path.join(output, "hooks.js");
await writeFile(hooks, 'export const useAuthRuntimeIdentity = value => value; export const useProductLeaveGuard = () => () => {}; export const captureAuthRequestScope = () => 1; export const isCurrentAuthRequestScope = () => true;');
const apiMock = path.join(output, "api.js");
await writeFile(apiMock, 'export const apiRequest = (path, options) => window.fixtureAPI(path, options);');
const compiler = webpack({ mode: "development", devtool: false, context: root,
  entry: path.join(root, "scripts/fixtures/credential-browser.tsx"), output: { path: output, filename: "bundle.js" },
  resolve: { extensions: [".tsx", ".ts", ".js"], alias: {
    "@/hooks/use-auth-runtime-identity": hooks, "@/hooks/use-product-leave-guard": hooks,
    "@/lib/auth/browser-session": hooks, "@/lib/http/api-request": apiMock,
    "@": path.join(root, "src") }, modules: [path.join(root, "node_modules"), "node_modules"] },
  module: { rules: [{ test: /\.tsx?$/, use: loader }, { test: /\.css$/, use: path.join(output, "css-loader.cjs") }] },
});
await new Promise((resolve, reject) => compiler.run((error, stats) => error || stats.hasErrors() ? reject(error ?? new Error(stats.toString({ all: false, errors: true }))) : resolve()));
await new Promise(resolve => compiler.close(resolve));
const bundle = await readFile(path.join(output, "bundle.js"));
const server = createServer((req, res) => {
  if (req.url === "/bundle.js") { res.setHeader("content-type", "text/javascript; charset=utf-8"); res.end(bundle); }
  else { res.setHeader("content-type", "text/html; charset=utf-8"); res.end('<!doctype html><meta charset="utf-8"><div id="root"></div><script src="/bundle.js"></script>'); }
});
server.listen(0, "127.0.0.1"); await once(server, "listening");
const browser = await chromium.launch({ channel: process.env.ANGMOO_BROWSER_TEST_CHANNEL ?? "msedge", headless: true });
const context = await browser.newContext(); const page = await context.newPage();
const errors = []; page.on("pageerror", error => errors.push(error.message));
const base = `http://127.0.0.1:${server.address().port}`;
try {
  await page.goto(base); await page.getByRole("button", { name: "Save", exact: true }).waitFor();
  const key = page.getByLabel("New API key"), model = page.getByLabel("Model");
  await key.fill("synthetic-secret"); await model.selectOption("google:model-b:high");
  await page.evaluate(() => { fixture.metadata.configuration_revision = 2; fixture.refresh(); });
  await page.waitForFunction(() => !document.querySelector('button')?.disabled);
  await page.getByRole("button", { name: "Save", exact: true }).click();
  await page.getByText("Saved", { exact: true }).waitFor();
  const written = await page.evaluate(() => fixture.writes[0]);
  assert.equal(written.expected_configuration_revision, 2); assert.equal(written.api_key, "synthetic-secret"); assert.equal(written.model, "model-b");
  await key.fill("second-synthetic");
  await page.evaluate(() => { fixture.metadata = { ...fixture.metadata, revision: 3, model: "model-a" }; fixture.refresh(); });
  await page.getByText("Settings changed", { exact: false }).first().waitFor();
  assert.equal(await key.inputValue(), "second-synthetic"); assert.equal(await model.inputValue(), "google:model-b:high");
  assert.equal(await page.getByRole("button", { name: "Save", exact: true }).isDisabled(), true);
  await page.getByRole("button", { name: "Review and keep inputs" }).click();
  await page.evaluate(() => fixture.failure = "unknown");
  await page.getByRole("button", { name: "Save", exact: true }).click();
  await page.getByText("Result unknown", { exact: false }).waitFor();
  await page.getByRole("button", { name: "Reload", exact: true }).click();
  assert.equal(await key.inputValue(), "second-synthetic");
  assert.equal(await page.evaluate(() => fixture.writes.length), 2, "read must not retry mutation");
  await page.evaluate(() => fixture.failure = "load"); await page.getByRole("button", { name: "Reload", exact: true }).click();
  await page.getByText("Load failed", { exact: false }).waitFor();
  assert.equal(await page.getByText("private", { exact: false }).count(), 0);
  if (!process.argv.includes("--settings-only")) {
  const other = await context.newPage(); await other.goto(base);
  await other.waitForFunction(() => Boolean(window.fixture));
  const states = await Promise.all([page, other].map(p => p.evaluate(() => fixture.store.read("installation-a"))));
  assert.equal(states[0].clientId, states[1].clientId);
  await page.evaluate(() => fixture.store.update("installation-a", state => ({ ...state, intent: "stopped", generation: state.generation+1 })));
  await other.waitForFunction(() => fixture.changed > 0);
  await other.reload(); await other.waitForFunction(() => Boolean(window.fixture));
  assert.equal((await other.evaluate(() => fixture.store.read("installation-a"))).intent, "stopped");
  assert.equal((await other.evaluate(() => fixture.store.read("installation-b"))).intent, "active");
  }
  assert.deepEqual(errors, []);
  await page.screenshot({ path: path.join(output, "credential-error.png"), fullPage: true });
  for (const locale of ["en", "ko"]) {
    await page.goto(`${base}?vision=${locale}`);
    const checkbox = page.getByRole("checkbox");
    await checkbox.waitFor();
    assert.equal(await checkbox.isDisabled(), true);
    const saveName = locale === "ko" ? "인식 설정 저장" : "Save analysis settings";
    await page.evaluate(() => { vision.status = "error"; vision.refresh(); });
    await page.getByRole("alert").waitFor();
    await page.getByRole("button", {name: locale === "ko" ? "다시 불러오기" : "Reload", exact: true}).click();
    assert.equal(await page.evaluate(() => vision.reloads), 1);
    await page.evaluate(() => { vision.status = "missing"; vision.refresh(); });
    assert.equal(await checkbox.isDisabled(), true);
    await page.evaluate(() => { vision.status = "saved"; vision.refresh(); });
    await page.waitForFunction(() => !document.querySelector('input[type="checkbox"]').disabled);
    assert.equal(await checkbox.isChecked(), false, "saving a key must not enable vision");
    await checkbox.check();
    // Key deleted in another tab after this page admitted the toggle.
    await page.evaluate(() => vision.fail = true);
    await page.getByRole("button", {name: saveName, exact: true}).click();
    await page.getByRole("alert").waitFor();
    assert.equal(await checkbox.isChecked(), true, "422 must preserve the draft");
    assert.equal(await page.evaluate(() => vision.updates.length), 1);
    await page.evaluate(() => { vision.status = "missing"; vision.fail = false; vision.refresh(); });
    await checkbox.uncheck();
    await page.getByRole("button", {name: saveName, exact: true}).click();
    await page.waitForFunction(() => vision.updates.length === 2);
    assert.equal(await page.evaluate(() => vision.updates[1].vision_enabled), false);
    await page.screenshot({path: path.join(output, `vision-${locale}.png`)});
  }
  assert.deepEqual(errors, []);
  console.log("entry_settings_browser_pass: configuration refresh, draft preservation, conflict, unknown result, read-only recovery, bilingual vision prerequisites and safe OFF");
  console.log(`evidence=${output}`);
} finally { await context.close(); await browser.close(); await new Promise(resolve => server.close(resolve)); }
