/* Read-only browser verification of the new batch's real attached assets. */
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { createHash } from "node:crypto";
import { chromium } from "../../browser-tests/node_modules/@playwright/test/index.mjs";

const argument = (name, fallback) => { const index = process.argv.indexOf(name); return index >= 0 ? process.argv[index + 1] : fallback; };
async function main() {
  if (!process.argv.includes("--execute-authorized-plan")) {
    console.log(JSON.stringify({ mode: "dry_run", network_calls: 0, key_reads: 0 })); return;
  }
  const evidence = argument("--evidence");
  const privateRoot = argument("--private-root");
  if (!evidence || !privateRoot) throw new Error("retest_paths_required");
  const reportRoot = argument("--report-dir", evidence);
  const screenshotRoot = argument("--screenshots-dir", path.join(privateRoot, "ui"));
  if (!path.resolve(screenshotRoot).startsWith(path.resolve(privateRoot) + path.sep)) throw new Error("screenshots_must_be_private");
  fs.mkdirSync(reportRoot, { recursive: true });
  const api = `http://127.0.0.1:${argument("--api-port", "18388")}`;
  const origin = `http://127.0.0.1:${argument("--ui-port", "13000")}`;
  const surface = argument("--surface", "static");
  if (!["next", "static"].includes(surface)) throw new Error("surface_invalid");
  const transport = surface === "next" ? origin + "/api/backend" : api + "/api/v1";
  const results = JSON.parse(fs.readFileSync(path.join(evidence, "case-results.json"), "utf8")).results;
  const manifest = JSON.parse(fs.readFileSync(path.join(privateRoot, "manifest.json"), "utf8"));
  const counter = () => JSON.parse(fs.readFileSync(path.join(evidence, "request-counters.json"), "utf8"));
  const before = counter();
  const browser = await chromium.launch({ headless: true });
  const report = { surface: `actual ${surface} frontend and isolated backend`, user_check: "NOT_PERFORMED", images: [], status: "RUNNING", stage: "session" };
  try {
    const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
    // Observe the real Blob passed by the product to createObjectURL. Fetching
    // a blob URL again is subject to connect-src and is unnecessary for image
    // display; the probe does not change the Blob, response, URL or CSP.
    await context.addInitScript(() => {
      const records = new Map();
      window.__ANGMOO_MEDIA_REVIEW__ = records;
      const createUrl = URL.createObjectURL.bind(URL);
      const revokeUrl = URL.revokeObjectURL.bind(URL);
      URL.createObjectURL = blob => {
        const url = createUrl(blob);
        if (blob instanceof Blob) records.set(url, { blob_type: blob.type, byte_size: blob.size, revoked: false,
          hash: blob.arrayBuffer().then(bytes => crypto.subtle.digest("SHA-256", bytes))
            .then(hash => Array.from(new Uint8Array(hash), byte => byte.toString(16).padStart(2, "0")).join("")) });
        return url;
      };
      URL.revokeObjectURL = url => {
        const record = records.get(url);
        if (record) record.revoked = true;
        return revokeUrl(url);
      };
    });
    const session = await context.request.post(transport + "/auth/local/session",
      { headers: { Origin: origin, "x-angmoo-frontend-origin": origin } });
    assert.equal(session.status(), 200);
    if (surface === "static") await context.addInitScript(value => Object.assign(window, { __ANGMOO_RUNTIME_CONFIG__: {
      profile: "tauri-static", apiBaseUrl: value, graphProvider: "ladybug",
    } }), api);
    const page = await context.newPage();
    report.local_api_responses = [];
    report.local_api_failures = [];
    const localPath = requestUrl => {
      const parsed = new URL(requestUrl);
      return parsed.origin === api || parsed.origin === origin ? parsed.pathname : null;
    };
    page.on("response", response => {
      const pathname = localPath(response.url());
      if (pathname?.startsWith("/api/")) report.local_api_responses.push({ pathname, status: response.status() });
    });
    page.on("requestfailed", request => {
      const pathname = localPath(request.url());
      if (pathname?.startsWith("/api/")) report.local_api_failures.push({ pathname });
    });
    const verifyImage = async (image, result, response, phase) => {
      report.stage = result.id + "_" + phase + "_mime";
      assert.equal(response.headers()["content-type"], result.mime);
      report.stage = result.id + "_" + phase + "_decode";
      await image.waitFor({ state: "visible" });
      report.before_decode = await image.evaluate(img => ({ complete: img.complete, width: img.naturalWidth,
        height: img.naturalHeight, source_is_blob: img.src.startsWith("blob:") }));
      report.current_pathname = new URL(page.url()).pathname;
      report.response_metadata = { method: response.request().method(), from_service_worker: response.fromServiceWorker(),
        status: response.status(), content_length: response.headers()["content-length"] ?? null,
        content_encoding: response.headers()["content-encoding"] ?? null };
      await image.evaluate(img => img.decode());
      const actual = await image.evaluate(async img => {
        const record = window.__ANGMOO_MEDIA_REVIEW__.get(img.src);
        if (!record) throw new Error("displayed_blob_not_observed");
        return { width: img.naturalWidth, height: img.naturalHeight, blob_type: record.blob_type, byte_size: record.byte_size,
          source_is_blob: img.src.startsWith("blob:"), complete: img.complete, blob_revoked: record.revoked,
          content_hash: await record.hash };
      });
      report.last_observed_image = { case: result.id, phase, ...actual };
      report.stage = result.id + "_" + phase + "_geometry_and_blob";
      assert.equal(actual.width, result.width); assert.equal(actual.height, result.height);
      assert.equal(actual.blob_type, result.mime); assert.equal(actual.source_is_blob, true); assert.equal(actual.complete, true);
      assert.equal(actual.blob_revoked, false);
      assert.equal(actual.byte_size, result.byte_size); assert.equal(actual.content_hash, result.content_hash);
      report.stage = result.id + "_" + phase + "_response_hash";
      const http = await context.request.get(response.url());
      assert.equal(http.status(), 200); assert.equal(http.headers()["content-type"], result.mime);
      const content = await http.body();
      const hash = createHash("sha256").update(content).digest("hex");
      report.last_response = { method: response.request().method(), from_service_worker: response.fromServiceWorker(), byte_size: content.byteLength, content_hash: hash };
      assert.equal(hash, result.content_hash);
      return { ...actual, content_hash: hash };
    };
    for (const result of results) {
      assert.equal(result.status, "PASS");
      report.stage = result.id + "_content";
      const responsePromise = page.waitForResponse(response => response.url() === transport + `/media/assets/${result.asset_id}/content` && response.request().method() === "GET" && response.status() === 200);
      await page.goto(origin + `/worlds/${manifest.world_id}/posts/${result.post_id}`);
      const response = await responsePromise;
      const image = page.getByRole("img", { name: "AI가 생성한 게시글 이미지", exact: true });
      report.stage = result.id + "_render";
      const actual = await verifyImage(image, result, response, "initial");
      const reloadResponse = page.waitForResponse(response => response.url() === transport + `/media/assets/${result.asset_id}/content` && response.request().method() === "GET" && response.status() === 200);
      report.stage = result.id + "_reload";
      await page.reload();
      const reloaded = await verifyImage(image, result, await reloadResponse, "reload");
      fs.mkdirSync(screenshotRoot, { recursive: true });
      const screenshot = path.join(screenshotRoot, result.id + ".png");
      await page.screenshot({ path: screenshot, fullPage: true });
      report.images.push({ case: result.id, post_id: result.post_id, asset_id: result.asset_id, mime: result.mime,
        ...actual, reload: reloaded, private_screenshot: screenshot, status: "PASS" });
    }
    const after = counter();
    report.new_image_submissions = after.image_submissions - before.image_submissions;
    report.new_text_requests = after.text_requests - before.text_requests;
    assert.equal(report.new_image_submissions, 0); assert.equal(report.new_text_requests, 0);
    report.status = "PASS";
    report.stage = "complete";
  } catch (error) {
    report.status = "FAILED"; report.error_type = error.name;
    const safeValue = value => typeof value === "boolean" || typeof value === "number" ||
      (typeof value === "string" && (/^[0-9a-f]{64}$/.test(value) || /^image\/(png|jpeg|webp)$/.test(value))) ? value : null;
    if (error.name === "AssertionError") report.failed_assertion = { actual: safeValue(error.actual), expected: safeValue(error.expected) };
    report.decode_error = typeof error.message === "string" && error.message.includes("cannot be decoded");
    const firstLine = String(error.message).split("\n", 1)[0];
    report.error_summary = /^[A-Za-z0-9_ .:()/-]{1,200}$/.test(firstLine) ? firstLine : "playwright_operation_failed";
    throw error;
  } finally {
    const after = counter();
    report.new_image_submissions = after.image_submissions - before.image_submissions;
    report.new_text_requests = after.text_requests - before.text_requests;
    fs.writeFileSync(path.join(reportRoot, "ui-evidence.json"), JSON.stringify(report, null, 2));
    console.log(JSON.stringify({ status: report.status, images: report.images.length, new_image_submissions: report.new_image_submissions }));
    await browser.close();
  }
}
main().catch(error => { console.log(JSON.stringify({ status: "FAILED", error_type: error.name })); process.exitCode = 1; });
