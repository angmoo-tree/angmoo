import assert from "node:assert/strict";
import fs from "node:fs";
import vm from "node:vm";
import ts from "typescript";

const source = fs.readFileSync(new URL("../src/features/media/api/world-image-policy.ts", import.meta.url), "utf8");
const code = ts.transpileModule(source, {compilerOptions: {
  module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022,
}}).outputText;
const sent = [], mod = {exports: {}};
const require = name => {
  assert.equal(name, "@/lib/http/api-request");
  return {apiRequest: async (path, options) => { sent.push({path, ...options}); return {}; }};
};
vm.runInNewContext(`(function(module,exports,require){${code}\n})`)(mod, mod.exports, require);
// Runtime callers may still provide stale/extra JS fields after a partial UI
// refresh. Only the documented partner fields may cross this boundary.
const transport = mod.exports.imageCredentialTransport("world", "actor", {
  expected_revision: 1, expected_configuration_revision: 2, expected_key_revision: 1,
  provider: "wrong", model: "wrong", partner_api_key: "synthetic-partner",
});
const snapshot = {expected_revision: 5, expected_configuration_revision: 8,
  expected_key_revision: 3, provider: "comfyui"};
await transport.save({...snapshot, model: "workflow", label: "Display only"}, undefined);
await transport.remove(snapshot, undefined);
for (const call of sent) {
  for (const [key, value] of Object.entries(snapshot)) assert.equal(call.body[key], value);
  assert.ok(!("label" in call.body));
}
assert.equal(sent[0].body.partner_api_key, "synthetic-partner");
assert.equal(sent[0].body.model, "workflow");
assert.ok(!("partner_api_key" in sent[1].body));
console.log("image_credential_transport_pass: confirmed revisions, extra whitelist, provider-scoped delete");
