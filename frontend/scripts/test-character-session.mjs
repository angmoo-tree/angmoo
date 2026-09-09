import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import vm from "node:vm";
import { execFileSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import ts from "typescript";

const root = fileURLToPath(new URL("../../", import.meta.url));
// Immutable pre-Character extraction. Compare real request bodies, failures and storage/event order.
const baseline = "0ba64ea8e10a2828bf0e8d99433a5903d1f104fe";
function harness(historical) {
  const requests = [], events = [];
  const storage = () => {
    const data = new Map();
    return { getItem: k => data.get(k) ?? null, setItem: (k,v) => data.set(k,String(v)),
      removeItem: k => data.delete(k), dump: () => [...data].sort() };
  };
  const window = { sessionStorage: storage(), localStorage: storage(), dispatchEvent: e => events.push([e.type, e.detail ?? null]) };
  let response = {status: 200, text: '{"ok":true}'};
  const runtimeFetch = async (url, options) => {
    requests.push([url, options]);
    return {ok: response.status >= 200 && response.status < 300, status: response.status, text: async () => response.text};
  };
  const cache = new Map();
  const source = name => historical
    ? execFileSync("git", ["show", `${baseline}:${name}`], {cwd:root, encoding:"utf8"})
    : fs.readFileSync(path.join(root,name),"utf8");
  function load(name) {
    if(cache.has(name))return cache.get(name).exports;
    const loadedModule={exports:{}};cache.set(name,loadedModule);
    const code=ts.transpileModule(source(name),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText;
    const localRequire = spec => {
      if(spec === "@/shared/runtime/public" || spec === "@/lib/runtime/runtime-config")return {runtimeFetch};
      if(spec === "@/features/chat/public")return {};
      if(spec === "@/shared/auth/public")return load("frontend/src/lib/auth/browser-session.ts");
      const resolved=spec.startsWith("@/")?"frontend/src/"+spec.slice(2):path.posix.normalize(path.posix.join(path.posix.dirname(name),spec));
      return load(resolved+".ts");
    };
    vm.runInNewContext(code,{module:loadedModule,exports:loadedModule.exports,require:localRequire,window,Event,CustomEvent,FormData,File,URL,Request,Response,Headers,console},{filename:name});
    return loadedModule.exports;
  }
  return {requests,events,window,load,setResponse(value){response=value;},
    api:load(historical?"frontend/src/lib/agents.ts":"frontend/src/features/characters/api/agents.ts"),
    session:load(historical?"frontend/src/lib/agents.ts":"frontend/src/features/characters/stores/agent-session.ts"),
    pending:load(historical?"frontend/src/lib/agents.ts":"frontend/src/features/identity/stores/pending-signup.ts")};
}
// Comparing serialized values avoids realm-specific object prototypes.
const plain=value=>JSON.parse(JSON.stringify(value));

const before=harness(true), after=harness(false);
const names=Object.keys(after.api).filter(name=>typeof after.api[name]==="function");
assert.equal(names.length,45,"All 45 migrated Character endpoints remain exported");
function args(name, newProfiles=false){
 if(name==="uploadAgentLoreSource")return ["character/id",new File(["lore fixture"],"fixture.txt"),{replaceExisting:true}];
 if(name==="giveAgentFeedCue")return ["character/id","fixture topic",{manualRun:true}];
 if(["createAgent","createAgentDraft"].includes(name))return [{name:"fixture",provider:"google",model:newProfiles?"gemini-3.1-flash-lite:high":"gemini-3.1-flash-lite",api_key:"fixture"}];
 return ["character/id",{enabled:true,confirmation:"fixture",media_type:"avatar",image_style:"fixture",appearance_prompt:"fixture"}];
}
async function normalizedRequests(h){
 return Promise.all(h.requests.map(async([url,options])=>{
  let body=options.body;
  if(body instanceof FormData)body=await Promise.all([...body.entries()].map(async([k,v])=>[k,typeof v==="string"?v:{name:v.name,type:v.type,text:await v.text()}]));
  return plain([url,{...options,body}]);
 }));
}
for(const name of names){
 assert.equal(typeof before.api[name],"function",name+" exists before extraction");
 const a=harness(true),b=harness(false);
 const outcome=async h=>{try{return {value:await h.api[name](...args(name,h===b))};}catch(e){return {error:e.message};}};
 assert.deepEqual(plain(await outcome(b)),plain(await outcome(a)),name);
 assert.equal(a.requests.length,1,name+" issues its request");
 const expected = await normalizedRequests(a);
 if(["createAgent","createAgentDraft"].includes(name)) {
   expected[0][1].body = JSON.stringify({...JSON.parse(expected[0][1].body), thinking_level:"high"});
 }
 assert.deepEqual(await normalizedRequests(b),expected,name+" request");
 assert.deepEqual(plain(b.events),plain(a.events),name+" event order");
}
for(const model of ["gemini-3.5-flash-lite","gemini-3.1-flash-lite"]){
 for(const thinking of ["high","medium"]){
  const h=harness(false);
  await h.api.saveCredential("character/id",{model:`${model}:${thinking}`});
  assert.deepEqual(JSON.parse(h.requests[0][1].body),{model,thinking_level:thinking});
 }
}
for(const status of [401,422,503]){
 const a=harness(true),b=harness(false);
 for(const h of [a,b])h.setResponse({status,text:'{"detail":"fixture failure"}'});
 const failure=async h=>{try{await h.api.updateAgentProfile("character",{name:"fixture"});return null;}catch(e){return e.message;}};
 assert.equal(await failure(b),await failure(a));assert.deepEqual(plain(b.events),plain(a.events));
}
for(const h of [before,after]){
 h.session.markFirstAgentWelcomePromptPending();
 assert.equal(h.session.hasFirstAgentWelcomePromptPending(),true);
 h.session.clearFirstAgentWelcomePromptPending();
 h.session.setAgentAutonomyMutationState("character","activating");
 h.session.setAgentAutonomyMutationState("second","deactivating");
 assert.equal(h.session.getAgentAutonomyMutationState("character"),"activating");
 h.session.clearAgentAutonomyMutationState("character");
}
assert.deepEqual(plain(after.session.getAgentAutonomyMutationStates()),plain(before.session.getAgentAutonomyMutationStates()));
assert.deepEqual(after.window.sessionStorage.dump(),before.window.sessionStorage.dump());
assert.deepEqual(plain(after.events),plain(before.events));
console.log("Character parity passed: 45 endpoint requests, 3 failure paths, onboarding/autonomy storage and ordered events.");
