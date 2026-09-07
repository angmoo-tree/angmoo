// Compare dashboard/detail state against the immutable pre-consolidation source.
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import vm from "node:vm";
import { execFileSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import ts from "typescript";

const root = fileURLToPath(new URL("../../", import.meta.url));
const baseline = "b648587225114ae86553381556be42e017d87f62";
const agentPath = "frontend/src/features/characters/stores/agent-session.ts";
const dashboardPath = "frontend/src/features/characters/stores/character-dashboard-session.ts";
const plain = value => JSON.parse(JSON.stringify(value));

function harness(historical, browser = true) {
  const values = new Map(), events = [];
  const window = browser ? {
    sessionStorage: {
      getItem: key => values.get(key) ?? null,
      setItem: (key, value) => values.set(key, String(value)),
      removeItem: key => values.delete(key),
    },
    dispatchEvent: event => events.push([event.type, event.detail ?? null]),
  } : undefined;
  function load(name) {
    const source = historical
      ? execFileSync("git", ["show", `${baseline}:${name}`], {cwd:root, encoding:"utf8"})
      : fs.readFileSync(path.join(root, name), "utf8");
    const loadedModule = { exports: {} };
    const code = ts.transpileModule(source, {compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText;
    vm.runInNewContext(code, {module:loadedModule, exports:loadedModule.exports, window, Event, CustomEvent}, {filename:name});
    return loadedModule.exports;
  }
  const agent = load(agentPath);
  return {agent, dashboard:historical ? load(dashboardPath) : agent, values, events};
}

for (const raw of [null, "{broken", "null", "7", "[]", '{"a":"activating","b":"deactivating","bad":"other"}']) {
  const before = harness(true), after = harness(false);
  for (const h of [before, after]) {
    if (raw !== null) h.values.set("angmoo.agentAutonomyMutation", raw);
    h.agent.markFirstAgentWelcomePromptPending();
    assert.equal(h.dashboard.hasFirstCharacterWelcomePending(), true);
  }
  assert.deepEqual(plain(after.dashboard.getCharacterAutonomyMutationStates()), plain(before.dashboard.getCharacterAutonomyMutationStates()));
  for (const [name, args] of [
    ["setCharacterAutonomyMutationState", ["new", "activating"]],
    ["clearCharacterAutonomyMutationState", ["a"]],
    ["clearCharacterAutonomyMutationState", ["missing"]],
    ["clearFirstCharacterWelcomePending", []],
    ["notifyCharactersChanged", []],
  ]) {
    for (const h of [before, after]) h.dashboard[name](...args);
    assert.deepEqual([...after.values], [...before.values], name + " storage");
    assert.deepEqual(plain(after.events), plain(before.events), name + " event order/payload");
    assert.equal(after.agent.hasFirstAgentWelcomePromptPending(), before.agent.hasFirstAgentWelcomePromptPending());
  }
  for (const h of [before, after]) {
    h.agent.setAgentAutonomyMutationState("cross-consumer", "deactivating");
    assert.equal(h.dashboard.getCharacterAutonomyMutationStates()["cross-consumer"], "deactivating");
    h.dashboard.clearCharacterAutonomyMutationState("cross-consumer");
    assert.equal(h.agent.getAgentAutonomyMutationState("cross-consumer"), null);
    h.dashboard.clearCharacterAutonomyMutationState("new");
    h.dashboard.clearCharacterAutonomyMutationState("b");
    assert.equal(h.values.has("angmoo.agentAutonomyMutation"), false);
  }
  assert.deepEqual(plain(after.events), plain(before.events));
}
for (const historical of [true, false]) {
  const h = harness(historical, false);
  assert.deepEqual(plain(h.dashboard.getCharacterAutonomyMutationStates()), {});
  assert.equal(h.dashboard.hasFirstCharacterWelcomePending(), false);
  h.dashboard.setCharacterAutonomyMutationState("ssr", "activating");
  h.dashboard.clearCharacterAutonomyMutationState("ssr");
  h.dashboard.notifyCharactersChanged();
  assert.equal(h.events.length, 0);
}
console.log("Character dashboard parity passed: 6 storage inputs, ordered events, cross-consumer state, final key removal and server-side no-op.");
