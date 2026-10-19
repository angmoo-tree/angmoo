import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import vm from "node:vm";
import { execFileSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import ts from "typescript";
import { approvedErrorMessage } from "./approved-error-transitions.mjs";

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
    return {ok: response.status >= 200 && response.status < 300, status: response.status,
      headers: new Headers(response.headers), text: async () => response.text};
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
    pending:load(historical?"frontend/src/lib/agents.ts":"frontend/src/features/identity/stores/pending-signup.ts")};
}
// Comparing serialized values avoids realm-specific object prototypes.
const plain=value=>JSON.parse(JSON.stringify(value));
const calls=[
  ["signup",{email:"fixture@example.test",password:"fixture",display_name:"owner",privacy_policy_agreed:true,terms_agreed:true}],
  ["getLocalBootstrapStatus"], ["createLocalBootstrapChallenge"],
  ["login",{email:"fixture@example.test",password:"fixture"}],
  ["logoutCurrentSession"], ["googleLogin",{credential:"fixture"}],
  ["completeGoogleSignup",{display_name:"owner",privacy_policy_agreed:true,terms_agreed:true}],
  ["linkGoogleAccount",{credential:"fixture"}], ["getMe",{suppressAuthFailureEvent:true}],
  ["updateMe",{display_name:"renamed"}], ["updateMePreferences",{feed_content_filter:"posts"}],
  ["deleteCurrentAccount",{confirmation:"fixture"}],
];
for(const [name,arg] of calls){
  const before=harness(true),after=harness(false);
  assert.deepEqual(plain(await after.api[name](arg)),plain(await before.api[name](arg)),name);
  if (name === "getLocalBootstrapStatus") {
    // Bootstrap now recovers a bound browser client from its existing cookie.
    assert.equal(before.requests[0][1].credentials,"omit");
    assert.equal(after.requests[0][1].credentials,"same-origin");
    assert.deepEqual(plain(after.requests),plain(before.requests.map(([url, options])=>[url,{...options,credentials:"same-origin"}])));
  } else assert.deepEqual(plain(after.requests),plain(before.requests),name+" request contract");
}
// Approved local-entry protocol transition: retain the historical fixture,
// assert its old contract, and verify the new explicit generation-bound API.
{
  const before=harness(true),after=harness(false);
  await before.api.claimLocalOwner({owner_user_id:"owner",privacy_acknowledged:true});
  const api=after.load("frontend/src/features/identity/api/local-entry.ts").localEntryApi;
  const data={protocol:2,installation_id:"installation",client_instance_id:"synthetic-client-01",expected_generation:0};
  await api.claim(data,"owner");
  assert.equal(after.requests[0][0],before.requests[0][0]);
  assert.deepEqual(JSON.parse(after.requests[0][1].body),{...data,owner_user_id:"owner"});
  assert.equal(JSON.parse(before.requests[0][1].body).privacy_acknowledged,true);
  assert.equal(after.requests[0][1].credentials,"same-origin");
  await api.issue(data);
  assert.equal(after.requests[1][0],"/api/backend/auth/local/session");
  assert.deepEqual(JSON.parse(after.requests[1][1].body),data);
  assert.equal(after.api.claimLocalOwner,undefined);
  assert.equal(after.api.issueLocalSession,undefined);
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
  assert.equal(await error(after),approvedErrorMessage(await error(before),response.status));
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
console.log("Identity parity passed: 11 unchanged request contracts, explicit bootstrap-cookie binding, 2 local protocol replacements, 5 failure paths, 4 storage/event transitions.");
