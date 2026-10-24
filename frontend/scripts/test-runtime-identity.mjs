import assert from "node:assert/strict";
import fs from "node:fs";
import { createRequire } from "node:module";
import vm from "node:vm";
import ts from "typescript";

// Execute the actual server handler with isolated environment inputs. No server,
// user data or provider is involved, and package metadata is read from this source.
const route = new URL("../src/app/api/runtime-identity/route.ts", import.meta.url);
const require = createRequire(route);
const source = ts.transpileModule(fs.readFileSync(route, "utf8"), {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
}).outputText;
const env = {};
const loaded = { exports: {} };
vm.runInNewContext(`(function(module,exports,require){${source}\n})`, {
  process: { env }, Response,
}, { filename: route.pathname })(loaded, loaded.exports, require);

for (const version of [undefined, "0.1.2", "0.1.2-dev", "0.1.2-dev-a123456"]) {
  if (version === undefined) delete env.ANGMOO_VERSION;
  else env.ANGMOO_VERSION = version;
  env.ANGMOO_SOURCE_SHA = "a".repeat(40);
  env.ANGMOO_LAUNCH_ID = "b".repeat(32);
  const response = await loaded.exports.GET();
  assert.equal(response.status, 200);
  assert.equal(response.headers.get("cache-control"), "private, no-store");
  assert.deepEqual(await response.json(), {
    version: "0.1.2", source_sha: env.ANGMOO_SOURCE_SHA, launch_id: env.ANGMOO_LAUNCH_ID,
  });
}
for (const version of ["0.1.0", "0.1.1", "0.1.3", "release-v0.1.2", "", "0x1x1", "0.1.2-dev-WRONG", "private-value", "0.1.2\n", "0.1.2\r\n", "0.1.2 "]) {
  env.ANGMOO_VERSION = version;
  const response = await loaded.exports.GET();
  assert.equal(response.status, 503);
  assert.equal(response.headers.get("cache-control"), "private, no-store");
  assert.deepEqual(await response.json(), { error: "product_version_mismatch" });
}
delete env.ANGMOO_VERSION;
env.ANGMOO_SOURCE_SHA = "private-source";
env.ANGMOO_LAUNCH_ID = "private-launch";
const response = await loaded.exports.GET();
assert.deepEqual(await response.json(), { version: "0.1.2", source_sha: "unknown", launch_id: "" });
for (const ending of ["\n", "\r\n", " "]) {
  env.ANGMOO_SOURCE_SHA = "a".repeat(40) + ending;
  env.ANGMOO_LAUNCH_ID = "b".repeat(32) + ending;
  const response = await loaded.exports.GET();
  assert.deepEqual(await response.json(), { version: "0.1.2", source_sha: "unknown", launch_id: "" });
}
console.log("Runtime identity: current/dev versions, mismatch refusal and content-free response PASS");
