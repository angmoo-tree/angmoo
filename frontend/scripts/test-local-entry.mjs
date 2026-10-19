import assert from "node:assert/strict";
import fs from "node:fs";
import vm from "node:vm";
import { fileURLToPath } from "node:url";
import ts from "typescript";

class ApiRequestError extends Error { constructor(status, code) { super(code); this.status = status; this.code = code; } }
const filename = fileURLToPath(new URL("../src/features/identity/controllers/local-entry-controller.ts", import.meta.url));
const code = ts.transpileModule(fs.readFileSync(filename, "utf8"), { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 } }).outputText;
const loadedModule = { exports: {} };
vm.runInNewContext(`(function(module,exports,require){${code}\n})`, { Error, Promise, console })(loadedModule, loadedModule.exports, spec => {
  if (spec.endsWith("browser-session")) return { isAuthError: error => error?.status === 401 };
  if (spec.endsWith("error-contract")) return { ApiRequestError };
  throw new Error(spec);
});
const { createLocalEntryController } = loadedModule.exports;
const deferred = () => { let resolve; const promise = new Promise(done => { resolve = done; }); return { promise, resolve }; };
function fixture() {
  let local, server = { generation: 0, state: "active" }, owner = null, token = false, bound = false;
  const calls = [];
  let queue = Promise.resolve();
  const bootstrap = () => ({ protocol: 2, installation_id: "installation", local_label: null,
    state: owner ? "claimed" : "unclaimed", automatic_prepare_allowed: !owner, candidates: [],
    owner, client_connection: bound ? { ...server, protocol: 2, installation_id: "installation", client_instance_id: "synthetic-client" } : null });
  const check = data => {
    if (server.generation !== data.expected_generation) throw new ApiRequestError(409, "local_client_revision_conflict");
  };
  const deps = { language: () => "en-US", store: {
    read: async () => local ??= { clientId: "synthetic-client", generation: 0, intent: "active" },
    update: async (_installation, change) => local = change(local),
    serialize: async (_installation, work) => { const current = queue.then(work); queue = current.catch(() => {}); return current; },
  }, api: {
    bootstrap: async () => bootstrap(),
    challenge: async () => { calls.push("challenge"); return {}; },
    status: async () => ({ ...server }),
    currentUser: async () => { if (!token) throw new ApiRequestError(401, "expired"); return owner; },
    prepare: async (data, language) => {
      check(data); assert.equal(server.state, "active"); assert.equal(language, "en-US");
      calls.push("prepare"); owner ??= { id: "one-owner", display_name: "User" }; token = bound = true; return { user: owner };
    },
    issue: async data => { check(data); assert.equal(server.state, "active"); calls.push("issue"); token = bound = true; return { user: owner }; },
    stop: async data => { check(data); calls.push("stop"); server = { generation: server.generation + 1, state: "stopped" }; token = false; return { ...server }; },
    resume: async data => { check(data); assert.equal(server.state, "stopped"); calls.push("resume"); server = { generation: server.generation + 1, state: "active" }; token = true; return { user: owner }; },
  } };
  return { deps, calls, expire: () => { token = false; }, local: () => local, server: () => server };
}
{
  const f = fixture(), controller = createLocalEntryController(f.deps);
  await Promise.all([controller.refresh(), controller.refresh()]);
  assert.equal(controller.getSnapshot().phase, "authenticated");
  assert.equal(f.calls.filter(c => c === "prepare").length, 1);
  await controller.refresh(); assert.equal(f.calls.includes("issue"), false);
  f.expire(); await controller.refresh(); assert.equal(f.calls.filter(c => c === "issue").length, 1);
  await controller.stop(); assert.equal(controller.getSnapshot().phase, "stopped");
  const reloaded = createLocalEntryController(f.deps); await reloaded.refresh();
  assert.equal(reloaded.getSnapshot().phase, "stopped");
  await reloaded.resume(); assert.equal(reloaded.getSnapshot().phase, "authenticated");
  assert.equal(reloaded.getSnapshot().user.id, "one-owner");
  assert.equal(f.calls.filter(c => c === "prepare").length, 1);
}
{
  const f = fixture(), first = createLocalEntryController(f.deps), second = createLocalEntryController(f.deps);
  await first.refresh(); await second.refresh();
  await first.stop(); await second.refresh();
  assert.equal(second.getSnapshot().phase, "stopped");
  assert.equal(f.calls.filter(c => c === "prepare").length, 1);
}
{
  const f = fixture(), controller = createLocalEntryController(f.deps);
  await controller.refresh();
  const committed = f.deps.api.stop;
  f.deps.api.stop = async data => { await committed(data); throw new TypeError("lost stop response"); };
  await controller.stop(); assert.equal(controller.getSnapshot().phase, "end_unconfirmed");
  await controller.refresh(); assert.equal(controller.getSnapshot().phase, "stopped");
  assert.equal(f.calls.includes("issue"), false);
}
{
  const f = fixture(), controller = createLocalEntryController(f.deps);
  await controller.refresh(); f.expire();
  const gate = deferred(), entered = deferred(), issue = f.deps.api.issue;
  f.deps.api.issue = async data => { entered.resolve(); await gate.promise; return issue(data); };
  const late = controller.refresh(); await entered.promise;
  const stop = controller.stop(); gate.resolve(); await Promise.all([late, stop]);
  assert.equal(controller.getSnapshot().phase, "stopped"); assert.equal(f.local().intent, "stopped");
  assert.deepEqual(f.calls.slice(-2), ["issue", "stop"]);
}
{
  const f = fixture(); f.deps.store.read = async () => { throw new Error("local_connection_storage_unavailable"); };
  const controller = createLocalEntryController(f.deps); await controller.refresh();
  assert.equal(controller.getSnapshot().phase, "unavailable"); assert.deepEqual(f.calls, []);
}
{
  const f = fixture(), entered = deferred(), gate = deferred();
  f.deps.api.challenge = async () => { entered.resolve(); await gate.promise; };
  const controller = createLocalEntryController(f.deps), refresh = controller.refresh();
  await entered.promise; controller.invalidate(); gate.resolve(); await refresh;
  assert.equal(controller.getSnapshot().user, null); assert.equal(f.calls.includes("prepare"), false);
}
{
  // No Web Locks: a stop committed on the server but its response arrives
  // after a different tab explicitly resumed a newer generation.
  const f = fixture(); f.deps.store.serialize = async (_installation, work) => work();
  const first = createLocalEntryController(f.deps), second = createLocalEntryController(f.deps);
  await first.refresh(); await second.refresh();
  const committed = deferred(), delivery = deferred(), stop = f.deps.api.stop;
  f.deps.api.stop = async data => { const result = await stop(data); committed.resolve(); await delivery.promise; return result; };
  const pending = first.stop(); await committed.promise;
  await second.refresh(); await second.resume();
  assert.equal(second.getSnapshot().phase, "authenticated");
  delivery.resolve(); await pending;
  assert.equal(first.getSnapshot().phase, "authenticated");
  assert.equal(f.local().intent, "active"); assert.equal(f.local().generation, 2);
  assert.equal(f.calls.filter(c => c === "stop").length, 1);
}
console.log("local_entry_controller_pass: fresh/single-flight, natural expiry, two clients, persistent stop, response loss, late issue/stop, storage failure, runtime replacement");
