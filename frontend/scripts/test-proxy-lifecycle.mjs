import assert from "node:assert/strict";
import fs from "node:fs";
import vm from "node:vm";
import path from "node:path";
import { fileURLToPath } from "node:url";
import ts from "typescript";

const root = fileURLToPath(new URL("../src/lib/server/", import.meta.url));
const logs = [];
let fetchCalls = 0;
let fetchImpl;
const context = vm.createContext({
  console: { info: value => logs.push(value), warn: value => logs.push(value) },
  fetch: (...args) => { fetchCalls++; return fetchImpl(...args); },
  Headers, Response, URL, AbortController, ReadableStream, TextDecoder, Error,
  performance, process, DOMException, crypto,
});
const cache = new Map();
function load(name) {
  if (name === "server-only") return {};
  const filename = path.resolve(root, name + ".ts");
  if (cache.has(filename)) return cache.get(filename).exports;
  const loadedModule = { exports: {} }; cache.set(filename, loadedModule);
  const code = ts.transpileModule(fs.readFileSync(filename, "utf8"), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
  }).outputText;
  vm.runInContext(`(function(module,exports,require){${code}\n})`, context, { filename })(loadedModule, loadedModule.exports, load);
  return loadedModule.exports;
}
const { proxyBackend } = load("backend");
const { isRequestCancellation, proxyConnectionCode } = load("proxy-lifecycle");
assert.equal(proxyConnectionCode({cause: {code: "UND_ERR_SOCKET"}}), "UND_ERR_SOCKET");
assert.equal(proxyConnectionCode({code: "secret-text"}), "unknown");
const cyclic = {}; cyclic.cause = cyclic;
assert.equal(proxyConnectionCode(cyclic), "unknown");
assert.equal(proxyConnectionCode(new Proxy({}, {getOwnPropertyDescriptor() {throw new Error("private");}})), "unknown");
assert.equal(proxyConnectionCode({get cause() { throw new Error("getter must not run"); }}), "unknown");
assert.equal(proxyConnectionCode({cause:{cause:{cause:{cause:{code:"ECONNRESET"}}}}}), "unknown");
const aborted = new AbortController();
const reason = new Error("private reason"); reason.name = "ResponseAborted";
aborted.abort(reason);
assert.equal(isRequestCancellation(reason, aborted.signal), true);
assert.equal(isRequestCancellation(Object.assign(new Error("unrelated"), { name: "ResponseAborted" }), aborted.signal), false);
assert.equal((await proxyBackend("/private?secret", { signal: aborted.signal })).status, 499);
assert.equal(fetchCalls, 0);

fetchImpl = async () => { throw new TypeError("private upstream failure"); };
assert.equal((await proxyBackend("/private")).status, 502);
fetchImpl = async () => { throw new TypeError("private upstream failure", {cause: {code: "UND_ERR_SOCKET"}}); };
assert.equal((await proxyBackend("/private")).status, 502);
assert.equal(logs.at(-1).connection_code, "UND_ERR_SOCKET");
assert.match(logs.at(-1).request_id, /^[0-9a-f-]{36}$/);
for (const status of [204, 205, 304, 409, 503]) {
  fetchImpl = async () => new Response(status < 400 ? null : '{"detail":"expected"}', {
    status, headers: { "cache-control": "no-store", "retry-after": "3", "set-cookie": "angmoo_browser_session=opaque; HttpOnly" },
  });
  const result = await proxyBackend("/private");
  assert.equal(result.status, status);
  assert.equal(result.headers.get("retry-after"), "3");
  assert.ok(result.headers.get("set-cookie").startsWith("angmoo_browser_session="));
  assert.equal(await result.text(), status < 400 ? "" : '{"detail":"expected"}');
}
fetchImpl = async () => new Response("x".repeat(65537), { status: 400 });
assert.equal((await (await proxyBackend("/private")).text()).includes("Backend request failed"), true);

let cancelCount = 0, pullCount = 0;
fetchImpl = async () => new Response(new ReadableStream({
  pull(controller) { pullCount++; controller.enqueue(new Uint8Array([1, 2])); },
  cancel() { cancelCount++; },
}, { highWaterMark: 0 }));
const streaming = await proxyBackend("/private");
assert.equal(pullCount, 0, "proxy must not eagerly buffer the response");
const reader = streaming.body.getReader();
assert.deepEqual((await reader.read()).value, new Uint8Array([1, 2]));
await reader.cancel();
assert.equal(cancelCount, 1);

fetchImpl = async () => new Response(new ReadableStream({
  start(controller) { controller.enqueue(new TextEncoder().encode('{"partial":true}\n')); },
  pull(controller) { controller.error(new Error("independent upstream stream failure")); },
}));
const broken = await proxyBackend("/private");
await assert.rejects(broken.text(), /independent upstream/);
const live = new AbortController();
fetchImpl = (_url, init) => new Promise((_resolve, reject) => init.signal.addEventListener("abort", () => reject(init.signal.reason), { once: true }));
const pending = proxyBackend("/private", { signal: live.signal });
live.abort(reason);
assert.equal((await pending).status, 499);
assert.ok(!JSON.stringify(logs).includes("private"));
assert.equal(logs.filter(log => log.phase === "response_stream" && log.outcome === "failed").length, 1);
console.log("proxy_lifecycle_pass: cancellation identity, no dispatch, status/cookies, bounds, backpressure, cancel, stream failure, safe diagnostics");
