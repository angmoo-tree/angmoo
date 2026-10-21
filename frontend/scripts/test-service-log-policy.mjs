import assert from "node:assert/strict";
import fs from "node:fs";
import vm from "node:vm";
import ts from "typescript";

const source = fs.readFileSync(new URL("../src/lib/server/service-log-policy.ts", import.meta.url), "utf8");
function load(env = {}) {
  const logs = [], mono = { now: 0 }, wall = { now: 1_800_000 };
  const context = vm.createContext({ process: {env}, performance: {now: () => mono.now},
    Date: class extends Date {static now() {return wall.now;}},
    console: {info: value => logs.push(JSON.parse(value)), warn: value => logs.push(JSON.parse(value))} });
  const loaded = {exports: {}};
  const code = ts.transpileModule(source, {compilerOptions: {module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022}}).outputText;
  vm.runInContext(`(function(module,exports,require){${code}\n})`,context)(loaded,loaded.exports,name=>{assert.equal(name,"server-only");return {};});
  return {api:loaded.exports,logs,mono,wall};
}
const value = {profile_version:"angmoo-service-log.v1", service:"frontend", launch_id:"a".repeat(32), requested_mode:"detailed",
  started_at_utc:"1970-01-01T00:16:40.000Z", duration_seconds:900, detailed_until_utc:"1970-01-01T00:31:40.000Z", remaining_seconds:500};
const env = {ANGMOO_SERVICE_LOG_POLICY:JSON.stringify(value),ANGMOO_LAUNCH_ID:value.launch_id};
const subject = load(env);
assert.equal(subject.api.detailedServiceLogs(),true);
assert.equal(subject.logs.length,1);
assert.equal(subject.logs[0].event,"service_log_policy_applied");
subject.wall.now=1_900_000;
assert.equal(subject.api.detailedServiceLogs(),false,"late init must not start a new TTL");
subject.wall.now=1_200_000;
assert.equal(subject.api.detailedServiceLogs(),false,"clock rollback cannot reenable detail");
assert.equal(subject.logs.length,1,"ACK only once");
const delayed=load(env); delayed.mono.now=500001;
assert.equal(delayed.api.detailedServiceLogs(),true); // Own clock starts on receipt, UTC still bounds it.
delayed.mono.now+=500001;
assert.equal(delayed.api.detailedServiceLogs(),false);
const absent=load();assert.equal(absent.api.detailedServiceLogs(),true);assert.equal(absent.logs.length,0);
const invalid=load({...env,ANGMOO_SERVICE_LOG_POLICY:'private-canary'});
assert.equal(invalid.api.detailedServiceLogs(),false);assert.equal(invalid.api.detailedServiceLogs(),false);
assert.equal(invalid.logs.length,2);assert.ok(!JSON.stringify(invalid.logs).includes('private-canary'));
for (const change of [{service:'backend'},{launch_id:'b'.repeat(32)},{remaining_seconds:-1},{duration_seconds:3601},{detailed_until_utc:'invalid'},{secret:'private'}]) {
  assert.throws(()=>subject.api.decodeServiceLogPolicy(JSON.stringify({...value,...change}),value.launch_id));
}
console.log('service_log_policy_pass: absent compatibility, strict scope, bounded duration, lazy ACK, one-way UTC/monotonic expiry, safe fallback');
