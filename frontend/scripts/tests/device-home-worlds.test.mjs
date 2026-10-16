import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import vm from "node:vm";
import { test } from "node:test";
import ts from "typescript";
const code = ts.transpileModule(readFileSync(new URL("../../src/features/device-home/hooks/device-home-world-controller.ts", import.meta.url), "utf8"), {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
}).outputText;
const exports = {};
vm.runInNewContext(code, { exports, AbortController, DOMException, performance, setTimeout, clearTimeout });
const turn = () => new Promise(resolve => setImmediate(resolve));
const deferred = () => { let resolve, reject; const promise = new Promise((a,b) => { resolve=a; reject=b; }); return { promise, resolve, reject }; };
function fixture() {
  const requests = [], preparation = deferred(); let ensures = 0, time = 0, scope = true;
  const controller = exports.createDeviceHomeWorldController({
    ensure: () => { ensures++; return preparation.promise; },
    read: signal => { const request = { ...deferred(), signal }; requests.push(request); return request.promise; },
    captureScope: () => () => scope, transient: error => error === "busy", now: () => time,
  });
  return { controller, requests, preparation, get ensures() { return ensures; }, advance: () => time += 300, revoke: () => scope = false };
}
test("preparation survives effect replay; initial readiness, successful empty and populated snapshots survive refresh", async () => {
  const f = fixture(), c = f.controller;
  c.activate(false,true); await turn(); assert.equal(f.ensures,0);
  c.activate(true,true); await turn(); c.deactivate(); c.activate(true,true); await turn();
  assert.equal(f.ensures,1); f.preparation.resolve(); await turn(); await turn();
  await new Promise(resolve => setTimeout(resolve,260));
  assert.equal(f.requests.length,1); f.requests[0].resolve({items:[]}); await turn();
  assert.equal(c.getSnapshot().hasSnapshot,true); f.advance(); c.resume(); c.resume();
  assert.equal(f.requests.length,2); assert.equal(c.getSnapshot().hasSnapshot,true);
  f.requests[1].resolve({items:[{world_id:"a"}]}); await turn();
  const previous = c.getSnapshot().items; f.advance(); c.resume();
  assert.equal(c.getSnapshot().items,previous); f.requests[2].reject("busy"); await turn();
  assert.equal(c.getSnapshot().items,previous); assert.equal(c.getSnapshot().error,"unavailable");
  c.retry(); f.requests[3].resolve({items:[{world_id:"b"}]}); await turn();
  assert.equal(c.getSnapshot().items[0].world_id,"b"); assert.equal(c.getSnapshot().error,null); assert.equal(f.ensures,1);
  c.deactivate();
});
test("hidden and revoked scopes reject late replies; denied reads clear previous IDs", async () => {
  for (const transition of ["hidden","scope","unmount","denied"]) {
    const f=fixture(), c=f.controller; c.activate(true,true); f.preparation.resolve(); await turn();
    f.requests[0].resolve({items:[{world_id:"old"}]}); await turn(); f.advance(); c.resume();
    if(transition === "hidden") c.visibility(false);
    if(transition === "scope") f.revoke();
    if(transition === "unmount") c.deactivate();
    if(transition === "denied") f.requests[1].reject("permission"); else f.requests[1].resolve({items:[{world_id:"late"}]});
    await turn(); assert.ok(!c.getSnapshot().items.some(x=>x.world_id==="late"));
    if(transition === "denied") { assert.equal(c.getSnapshot().items.length,0); assert.equal(c.getSnapshot().error,"denied"); }
    c.deactivate();
  }
});
test("one later resume during a request produces only one follow-up and preparation failure is retryable", async () => {
  const f=fixture(), c=f.controller; c.activate(true,true); f.preparation.resolve(); await turn();
  f.advance(); c.resume(); c.resume(); assert.equal(f.requests.length,1);
  f.requests[0].resolve({items:[]}); await turn(); await new Promise(resolve=>setTimeout(resolve,5));
  assert.equal(f.requests.length,2); f.requests[1].resolve({items:[]}); await turn(); c.deactivate();
  let attempts=0;
  const d=exports.createDeviceHomeWorldController({ensure: async()=>{if(++attempts===1) throw "busy";},read:async()=>({items:[]}),captureScope:()=>()=>true,transient:()=>true});
  d.activate(true,true); await turn(); assert.equal(d.getSnapshot().hasSnapshot,false);
  d.retry(); await turn(); assert.equal(d.getSnapshot().hasSnapshot,true); assert.equal(attempts,2); d.deactivate();
});

test("a quick hide and return can replace the aborted request without waiting for another focus", async () => {
  const f=fixture(), c=f.controller; c.activate(true,true); f.preparation.resolve(); await turn();
  c.visibility(false); c.visibility(true);
  assert.equal(f.requests[0].signal.aborted,true);
  f.requests[0].resolve({items:[{world_id:"aborted"}]}); await turn();
  await new Promise(resolve=>setTimeout(resolve,5));
  assert.equal(f.requests.length,2);
  f.requests[1].resolve({items:[{world_id:"current"}]}); await turn();
  assert.equal(c.getSnapshot().items[0].world_id,"current"); c.deactivate();
});
