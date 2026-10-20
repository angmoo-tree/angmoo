import assert from "node:assert/strict";
import fs from "node:fs";
import vm from "node:vm";
import ts from "typescript";
const code = ts.transpileModule(fs.readFileSync(new URL("../src/features/chat/api/world-chat-client.ts", import.meta.url), "utf8"), {
  compilerOptions: {module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022},
}).outputText;
let scope = 1;
const calls = [];
const mod = {exports: {}};
const dependencies = {
  "@/config/generation-profiles": {},
  "@/lib/auth/browser-session": {
    captureAuthRequestScope: () => scope, isCurrentAuthRequestScope: value => value === scope,
    clearStoredUser() {}, notifyAuthChanged() {},
  },
  "@/lib/runtime/runtime-config": {runtimeFetch: (path, options) =>
    new Promise(resolve => calls.push({path, options, resolve}))},
};
vm.runInNewContext(`(function(module,exports,require){${code}\n})`, {Response, DOMException})(
  mod, mod.exports, name => { assert.ok(name in dependencies, name); return dependencies[name]; });
const prepare = mod.exports.prepareWorldChatSearch;
const response = (world = "world") => Response.json({
  schema_version: "memory-search-preparation.v1", world_id: world, thread_id: "thread",
  axes: {fts: {status: "preparing", reason: null}, vector: {status: "disabled", reason: null}},
}, {status: 202});
assert.equal(calls.length, 0, "import/prefetch does not prepare search");
const first = prepare("world", "thread");
assert.equal(prepare("world", "thread"), first, "duplicate mount shares pending admission");
assert.equal(calls.length, 1);
assert.equal(calls[0].options.method, "POST");
assert.equal(calls[0].options.body, "{}");
assert.ok(calls[0].path.endsWith("/memory-search/prepare"));
scope++;
const stale = assert.rejects(first, error => error.detail === "world_chat_scope_mismatch");
const second = prepare("world", "thread");
assert.notEqual(first, second);
calls[0].resolve(response());
await stale;
assert.equal(prepare("world", "thread"), second, "late cleanup cannot evict new auth scope");
calls[1].resolve(response());
assert.equal((await second).axes.fts.status, "preparing");
const invalid = prepare("world", "thread");
calls[2].resolve(response("other-world"));
await assert.rejects(invalid, error => error.detail === "world_chat_scope_mismatch");
assert.equal(calls.length, 3, "failed admission never retries or sends Chat messages");
console.log("chat_search_preparation_pass: demand-only POST, duplicate coalescing, auth/scope isolation, no retry");
