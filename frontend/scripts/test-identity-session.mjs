import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import vm from "node:vm";
import { execFileSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import ts from "typescript";

const root = fileURLToPath(new URL("../../", import.meta.url));
// Immutable pre-Identity extraction, including the already moved runtime layer.
const baseline = "322130952465bbe350e0a6b63dbb21d0c57eed2f";
function harness(historical) {
  const requests = [], events = [];
  const storage = () => {
    const data = new Map();
    return { getItem: k => data.get(k) ?? null, setItem: (k,v) => data.set(k,String(v)),
      removeItem: k => data.delete(k), dump: () => [...data].sort() };
  };
  const window = { sessionStorage: storage(), localStorage: storage(), dispatchEvent: e => events.push(e.type) };
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
      if(historical && spec === "@/shared/auth/public")return load("frontend/src/shared/auth/auth-session.ts");
      const resolved=spec.startsWith("@/")?"frontend/src/"+spec.slice(2):path.posix.normalize(path.posix.join(path.posix.dirname(name),spec));
      return load(resolved+".ts");
    };
    vm.runInNewContext(code,{module:loadedModule,exports:loadedModule.exports,require:localRequire,window,Event,FormData,URL,Request,Response,Headers,console},{filename:name});
    return loadedModule.exports;
  }
  return {requests,events,window,load,setResponse(value){response=value;},
    api:load(historical?"frontend/src/lib/agents.ts":"frontend/src/features/identity/api/identity.ts"),
    session:load(historical?"frontend/src/lib/agents.ts":"frontend/src/lib/auth/browser-session.ts"),
    pending:load(historical?"frontend/src/lib/agents.ts":"frontend/src/features/identity/utils/pending-signup.ts")};
}
// Comparing serialized values avoids realm-specific object prototypes.
const plain=value=>JSON.parse(JSON.stringify(value));
const calls=[
  ["signup",{email:"fixture@example.test",password:"fixture",display_name:"owner",privacy_policy_agreed:true,terms_agreed:true}],
  ["getLocalBootstrapStatus"], ["createLocalBootstrapChallenge"],
  ["claimLocalOwner",{owner_user_id:null,display_name:"owner",local_label:"device",privacy_acknowledged:true}],
  ["issueLocalSession"], ["login",{email:"fixture@example.test",password:"fixture"}],
  ["logoutCurrentSession"], ["googleLogin",{credential:"fixture"}],
  ["completeGoogleSignup",{display_name:"owner",privacy_policy_agreed:true,terms_agreed:true}],
  ["linkGoogleAccount",{credential:"fixture"}], ["getMe",{suppressAuthFailureEvent:true}],
  ["updateMe",{display_name:"renamed"}], ["updateMePreferences",{feed_content_filter:"posts"}],
  ["deleteCurrentAccount",{confirmation:"fixture"}],
];
for(const [name,arg] of calls){
  const before=harness(true),after=harness(false);
  assert.deepEqual(plain(await after.api[name](arg)),plain(await before.api[name](arg)),name);
  assert.deepEqual(plain(after.requests),plain(before.requests),name+" request contract");
}
for(const response of [
  {status:401,text:'{"detail":"Not authenticated"}'},
  {status:422,text:'{"detail":[{"loc":["body","handle"],"msg":"bad"}]}'},
  {status:422,text:'{"detail":[{"loc":["body","activity_interval_minutes"],"type":"greater_than_equal","msg":"bad"}]}'},
  {status:503,text:'<!doctype html><html>fixture error</html>'},
  {status:503,text:'offline'},
]){
  const before=harness(true),after=harness(false);
  for(const h of [before,after]){h.setResponse(response);h.window.sessionStorage.setItem("angmoo.user","fixture");}
  const error=async h=>{try{await h.api.login({email:"fixture",password:"fixture"});return null;}catch(e){return e.message;}};
  assert.equal(await error(after),await error(before));
  assert.deepEqual(after.events,before.events);
  assert.deepEqual(after.window.sessionStorage.dump(),before.window.sessionStorage.dump());
}
for(const operation of ["storeAuth","clearAuth","storePendingGoogleSignup","clearPendingGoogleSignup"]){
  const before=harness(true),after=harness(false);
  for(const h of [before,after]){
    for(const storage of [h.window.sessionStorage,h.window.localStorage]){
      storage.setItem("angmoo.user","stale"); storage.setItem("angmoo.authToken","obsolete");
    }
    h.window.sessionStorage.setItem("angmoo.pendingGoogleSignup","pending");
    const owner=operation.includes("Pending")?h.pending:h.session;
    owner[operation]({user:{id:"owner",display_name:"owner"},expires_at:"fixture",email:"fixture@example.test"});
  }
  assert.deepEqual(after.window.sessionStorage.dump(),before.window.sessionStorage.dump(),operation);
  assert.deepEqual(after.window.localStorage.dump(),before.window.localStorage.dump(),operation);
  assert.deepEqual(after.events,before.events,operation+" event order");
}
console.log("Identity parity passed: 14 request contracts, 5 failure paths, 4 storage/event transitions.");
