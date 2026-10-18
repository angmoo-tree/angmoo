import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import vm from "node:vm";
import { test } from "node:test";
import ts from "typescript";

const code = ts.transpileModule(readFileSync(new URL("../../src/features/characters/hooks/use-world-character-management.ts", import.meta.url), "utf8"), {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
}).outputText;
const turn = () => new Promise(resolve => setImmediate(resolve));
const deferred = () => { let resolve; const promise = new Promise(done => { resolve = done; }); return { promise, resolve }; };
const management = (revision, next) => ({ world_id: "world-a", world_character_id: "actor-a", can_manage: true,
  item: { revision, next_activity_at: next, profile: {}, settings: {}, capabilities: { can_edit_settings: true } } });
const saved = revision => ({ revision, profile: {}, settings: { active_hours_start: "12:00", active_hours_end: "03:00", activity_interval_minutes: 90 } });

// Exercise the actual shared hook with deterministic effect/transport scheduling.
// This harness proves lifecycle fences, not visual or native WebView rendering.
function fixture() {
  const cells = [], effects = [], requests = [], listeners = new Map();
  let index = 0, runtime = "browser";
  const same = (a, b) => a && b && a.length === b.length && a.every((v, i) => Object.is(v, b[i]));
  const react = {
    useState(initial) { const i = index++; if (!(i in cells)) cells[i] = typeof initial === "function" ? initial() : initial;
      return [cells[i], value => { cells[i] = typeof value === "function" ? value(cells[i]) : value; }]; },
    useRef(value) { const i = index++; return cells[i] ??= { current: value }; },
    useCallback(fn, deps) { const i = index++; if (!same(cells[i]?.deps, deps)) cells[i] = { fn, deps }; return cells[i].fn; },
    useEffect(fn, deps) { const i = index++; if (!same(cells[i]?.deps, deps)) {
      const previous = cells[i]; effects.push(() => { previous?.cleanup?.(); cells[i].cleanup = fn(); }); cells[i] = { deps }; } },
  };
  const scope = () => ({ userId: "owner", apiBaseUrl: runtime, launchToken: null });
  const exports = {};
  const modules = {
    react,
    "@/hooks/use-auth": { useAuth: () => ({ status: "authenticated", user: { id: "owner" } }) },
    "@/lib/auth/browser-session": { captureAuthRequestScope: scope, isCurrentAuthRequestScope: value => value.apiBaseUrl === runtime },
    "@/lib/http/api-request": { ApiRequestError: class extends Error {} },
    "@/lib/runtime/runtime-config": { DESKTOP_RUNTIME_CONFIG_CHANGED_EVENT: "runtime-changed" },
    "../api/world-character-management-client": {
      getWorldCharacterManagement: (_world, _actor, { signal }) => { const request = { ...deferred(), signal }; requests.push(request); return request.promise; },
      getWorldCharacterSettings: async () => saved(1),
    },
  };
  vm.runInNewContext(code, { exports, AbortController, queueMicrotask, window: {
    addEventListener: (key, fn) => listeners.set(key, fn), removeEventListener: key => listeners.delete(key),
  }, require: name => { assert.ok(modules[name], name); return modules[name]; } });
  function render() { index = 0; const hook = exports.useWorldCharacterManagement("world-a", "actor-a"); effects.splice(0).forEach(fn => fn()); return hook; }
  return { render, requests, switchRuntime() { runtime = "tauri"; listeners.get("runtime-changed")(); } };
}

async function ready() {
  const f = fixture(); f.render(); await turn();
  assert.equal(f.requests.length, 1); f.requests[0].resolve(management(1, "old-time")); await turn(); return f;
}

test("one saved command re-reads server next-time without a second command or optimistic time", async () => {
  const f = await ready(); const hook = f.render(); let writes = 0;
  await hook.mutate("settings-save", async () => { writes++; return saved(2); }, hook.acceptSettings);
  assert.equal(writes, 1); assert.equal(f.requests.length, 2);
  assert.equal(f.render().read.item.next_activity_at, "old-time");
  f.requests[1].resolve(management(2, "server-new-time")); await turn();
  assert.equal(f.render().read.item.next_activity_at, "server-new-time");
  assert.equal(f.render().settings.settings.activity_interval_minutes, 90);
});

test("an older post-save GET cannot overwrite a later saved schedule", async () => {
  const f = await ready(); let hook = f.render();
  await hook.mutate("settings-save", async () => saved(2), hook.acceptSettings);
  hook = f.render(); await hook.mutate("settings-save", async () => saved(3), hook.acceptSettings);
  assert.equal(f.requests.length, 3);
  f.requests[2].resolve(management(3, "latest")); await turn();
  f.requests[1].resolve(management(2, "obsolete")); await turn();
  assert.equal(f.render().read.item.next_activity_at, "latest");
});

test("runtime switch aborts the post-save read and the same hook reads the new runtime", async () => {
  const f = await ready(); const hook = f.render();
  await hook.mutate("settings-save", async () => saved(2), hook.acceptSettings);
  f.switchRuntime(); assert.equal(f.requests[1].signal.aborted, true);
  f.requests[1].resolve(management(2, "old-runtime")); await turn();
  assert.equal(f.render().read, null);
  f.requests[2].resolve(management(1, "new-runtime")); await turn();
  assert.equal(f.render().read.item.next_activity_at, "new-runtime");
});
