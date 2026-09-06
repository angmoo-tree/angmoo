import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import vm from "node:vm";
import { execFileSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import ts from "typescript";

const root = fileURLToPath(new URL("../../", import.meta.url));
const baseline = "de1abed71db6ea00b31b455ad9673b12619bf5f0";
function harness(historical, kind) {
  const requests = [], events = [], cache = new Map();
  let response = {status: 200, text: '{"items":[],"ok":true}'};
  const runtimeFetch = async (url, options) => {
    requests.push([url, options]);
    return {ok: response.status >= 200 && response.status < 300, status: response.status, text: async () => response.text};
  };
  function load(name) {
    if (cache.has(name)) return cache.get(name).exports;
    const source = historical
      ? execFileSync("git", ["show", `${baseline}:${name}`], {cwd: root, encoding: "utf8"})
      : fs.readFileSync(path.join(root, name), "utf8");
    const loadedModule = {exports: {}}; cache.set(name, loadedModule);
    const require = spec => {
      if (["@/shared/runtime/public", "@/lib/runtime/runtime-config"].includes(spec)) return {runtimeFetch};
      if (["@/shared/auth/public", "@/lib/auth/browser-session"].includes(spec)) return {
        clearStoredUser: () => events.push("clear"), notifyAuthChanged: () => events.push("auth"),
      };
      if (spec === "@/shared/ui/public") return {};
      const target = spec.startsWith("@/") ? "frontend/src/" + spec.slice(2)
        : path.posix.normalize(path.posix.join(path.posix.dirname(name), spec));
      return load(target + ".ts");
    };
    const code = ts.transpileModule(source, {compilerOptions: {module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022}}).outputText;
    vm.runInNewContext(code, {module: loadedModule, exports: loadedModule.exports, require, URLSearchParams}, {filename: name});
    return loadedModule.exports;
  }
  const entries = {
    community: historical ? "lib/community" : "features/social/api/community",
    actor: historical ? "features/social/api/social-agent-client" : "features/characters/api/feed-actor",
    transport: historical ? "features/social/api/social-feed-client" : "lib/http/social-request",
  };
  return {api: load("frontend/src/" + entries[kind] + ".ts"), requests, events, setResponse: value => {response = value;}};
}
const plain = value => JSON.parse(JSON.stringify(value));
const options = {limit: 7, cursor: "cursor/+", content: "reposts", target_type: "character", target_id: "target/id", reason: "other", details: "fixture"};
function args(name) {
  if (["listFeed", "listFollowingFeed", "listNotifications", "followProfile", "getFollowStatus", "unfollowProfile", "createPost"].includes(name)) return [options];
  if (name === "searchNest") return ["query 한글 &", 7, 3];
  if (name === "giveAgentFeedCue") return ["character/id", "fixture", {manualRun: true}];
  if (name.includes("ProfileFeed") || name.includes("ProfileConnections")) return ["owner/id", "following", options];
  return ["entity/id", options, "character/id"];
}
for (const [kind, count] of [["community", 27], ["actor", 4]]) {
  const names = Object.keys(harness(false, kind).api);
  assert.equal(names.length, count);
  for (const name of names) {
    const a = harness(true, kind), b = harness(false, kind);
    assert.deepEqual(plain(await b.api[name](...args(name))), plain(await a.api[name](...args(name))), name);
    assert.equal(a.requests.length, 1, name + " must issue one request");
    assert.deepEqual(plain(b.requests), plain(a.requests), name + " request payload and options");
    assert.deepEqual(b.events, a.events, name + " auth event order");
  }
}
for (const response of [
  {status: 200, text: "malformed"}, {status: 204, text: ""},
  {status: 401, text: '{"detail":"fixture"}'}, {status: 422, text: '{"detail":[{"msg":"fixture"}]}'},
  {status: 503, text: "unavailable"},
]) {
  for (const anonymous of [false, true]) {
    const a = harness(true, "transport"), b = harness(false, "transport");
    const outcome = async h => {
      h.setResponse(response);
      try {return {value: await h.api.requestSocialApi("/fixture", {anonymous, clearAuthOnUnauthorized: true})};}
      catch (error) {return {error: error.name + ":" + error.message};}
    };
    assert.deepEqual(plain(await outcome(b)), plain(await outcome(a)));
    assert.deepEqual(b.events, a.events);
    assert.deepEqual(plain(b.requests), plain(a.requests));
  }
}
console.log("Social parity passed: 27 Social + 4 Character endpoint requests, 10 transport/auth/error cases.");
