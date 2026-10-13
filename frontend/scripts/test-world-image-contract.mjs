import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import vm from "node:vm";
import { fileURLToPath } from "node:url";
import ts from "typescript";

const root = fileURLToPath(new URL("../src/", import.meta.url));
const calls = [];
const context = vm.createContext({
  URL, Headers, Response, Event, console,
  process: { env: {} },
  window: { location: { origin: "http://tauri.localhost" }, dispatchEvent() {} },
  fetch: async (url, init) => { calls.push({ url, init }); return new Response("{}", { status: 200 }); },
});
const cache = new Map();
function load(name) {
  if (cache.has(name)) return cache.get(name).exports;
  const moduleRecord = { exports: {} }; cache.set(name, moduleRecord);
  const source = fs.readFileSync(path.join(root, name), "utf8");
  const code = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 } }).outputText;
  const require = name => {
    assert.equal(name, "@/lib/runtime/runtime-config");
    return load("lib/runtime/runtime-config.ts");
  };
  vm.runInContext(`(function(module,exports,require){${code}\n})`, context, { filename: name })(moduleRecord, moduleRecord.exports, require);
  return moduleRecord.exports;
}
const runtime = load("lib/runtime/runtime-config.ts");
const safe = load("lib/media/safe-media-url.ts").safeSameOriginMediaUrl;
const api = load("features/worlds/api/worlds.ts");
const source = "/media/worlds/world-fixture/icon-existing.webp";
assert.equal(safe(source), source);
assert.equal(runtime.resolveRuntimeMediaUrl(source), "/api/backend/worlds/world-fixture/media/icon-existing.webp");
assert.equal(runtime.resolveRuntimeMediaUrl(source + "?v=1"), "/api/backend/worlds/world-fixture/media/icon-existing.webp?v=1");
assert.equal(runtime.resolveRuntimeMediaUrl("/media/characters/a/avatar.webp"), "/media/characters/a/avatar.webp");
assert.equal(runtime.resolveRuntimeMediaUrl("/api/v1/media/assets/asset-a/content"), "/api/backend/media/assets/asset-a/content");
assert.equal(safe("https://elsewhere.test/image.webp"), null);
assert.equal(safe("//elsewhere.test/image.webp"), null);
assert.equal(safe("blob:fixture", { allowBlob: true }), "blob:fixture");

for (const kind of ["avatar", "banner"]) {
  calls.length = 0;
  const original = { version: 7, media_type: kind, content_type: "image/webp", data_base64: "synthetic-image",
    filename: `${kind}.webp`, other_component_metadata: "not-an-api-field" };
  await api.uploadMyProfileMedia("world-fixture", original);
  const call = calls.at(-1), body = JSON.parse(call.init.body);
  assert.equal(call.url, "/api/backend/worlds/world-fixture/my-profile/media");
  assert.deepEqual(Object.keys(body).sort(), ["content_type", "data_base64", "media_type", "version"]);
  assert.equal(body.media_type, kind); assert.equal(body.version, 7);
  assert.equal(original.filename, `${kind}.webp`);
}

context.process.env.NEXT_PUBLIC_ANGMOO_FRONTEND_PROFILE = "tauri-static";
context.window.__ANGMOO_RUNTIME_CONFIG__ = { apiBaseUrl: "http://127.0.0.1:8080", profile: "tauri-static", graphProvider: "ladybug", launchToken: "synthetic-world-media-launch-token-0001" };
assert.equal(safe(source), source);
assert.equal(runtime.resolveRuntimeMediaUrl(source), "http://127.0.0.1:8080/api/v1/worlds/world-fixture/media/icon-existing.webp");
assert.equal(runtime.resolveRuntimeMediaUrl("/media/posts/p/photo.webp"), "http://127.0.0.1:8080/media/posts/p/photo.webp");
calls.length = 0;
await runtime.runtimeFetch(runtime.resolveRuntimeMediaUrl(source), { cache: "no-store" });
let call = calls.at(-1);
assert.equal(call.init.credentials, "include");
assert.equal(call.init.headers.get("X-Angmoo-Launcher-Token"), context.window.__ANGMOO_RUNTIME_CONFIG__.launchToken);
assert.equal(call.init.headers.get("X-Angmoo-Frontend-Origin"), "http://tauri.localhost");
runtime.installDesktopRuntimeConfig("http://127.0.0.1:8181", "synthetic-new-world-media-launch-token-0002", "ladybug");
assert.equal(runtime.resolveRuntimeMediaUrl(source), "http://127.0.0.1:8181/api/v1/worlds/world-fixture/media/icon-existing.webp");
await runtime.runtimeFetch(runtime.resolveRuntimeMediaUrl(source));
call = calls.at(-1);
assert.equal(call.init.headers.get("X-Angmoo-Launcher-Token"), context.window.__ANGMOO_RUNTIME_CONFIG__.launchToken);
console.log("World media Next/static URL, scoped token and exact profile payload contracts passed.");
