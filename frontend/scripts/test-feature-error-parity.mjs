// Compare feature errors with the immutable pre-extraction transport.
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import vm from "node:vm";
import { execFileSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import ts from "typescript";

const root = fileURLToPath(new URL("../../", import.meta.url));
const baseline = "b648587225114ae86553381556be42e017d87f62";
const plain = value => JSON.parse(JSON.stringify(value));
function harness(historical, response) {
  const values = new Map([["angmoo.user", "cached-owner"]]), events = [], requests = [], cache = new Map();
  const storage = {getItem:k=>values.get(k)??null, setItem:(k,v)=>values.set(k,String(v)), removeItem:k=>values.delete(k)};
  const window = {sessionStorage:storage, localStorage:storage, dispatchEvent:e=>events.push(e.type)};
  const runtimeFetch = async (url, options) => {
    requests.push([url,options]);
    return {ok:response.status>=200&&response.status<300,status:response.status,text:async()=>response.text};
  };
  function load(name) {
    if (cache.has(name)) return cache.get(name).exports;
    const loadedModule = {exports:{}}; cache.set(name,loadedModule);
    const source = historical ? execFileSync("git",["show",`${baseline}:${name}`],{cwd:root,encoding:"utf8"}) : fs.readFileSync(path.join(root,name),"utf8");
    const code = ts.transpileModule(source,{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText;
    const require = spec => {
      if(spec==="@/lib/runtime/runtime-config") return {runtimeFetch};
      const target=spec.startsWith("@/")?"frontend/src/"+spec.slice(2):path.posix.normalize(path.posix.join(path.posix.dirname(name),spec));
      return load(target+".ts");
    };
    vm.runInNewContext(code,{module:loadedModule,exports:loadedModule.exports,require,window,Event,CustomEvent,FormData,File,URL,Request,Response,Headers},{filename:name});
    return loadedModule.exports;
  }
  return {load,values,events,requests};
}
const issue=(loc,type,msg)=>({loc,type,msg});
const details=[
  [issue(["body","handle"],"string_pattern_mismatch","bad")],
  [issue(["handle","activity_interval_minutes"],"greater_than_equal","bad")],
  [issue(["body","activity_interval_minutes"],"greater_than_equal","bad")],
  [issue(["body","activity_interval_minutes"],"less_than_equal","bad")],
  [issue(["body","activity_interval_minutes"],"","greater than or equal")],
  [issue(["body","activity_interval_minutes"],"","less than or equal")],
  [issue(["body","activity_interval_minutes"],"invalid","bad")],
  [issue(["body","max_comments_per_day"],"invalid","bad")],
  [issue(["body","max_posts_per_day"],"invalid","bad")],
  [issue(["body","unrelated"],"invalid","server message")],
  [null,1,"ignored",{},issue(["body","handle"],"","second")],
  [[],issue(["body","handle"],"","second")],
  [], "", "server detail", null,
];
const responses = details.map(detail=>({status:422,text:JSON.stringify({detail})}));
responses.push(
  {status:401,text:'{"detail":"Not authenticated"}'},
  {status:401,text:'{broken'},
  {status:503,text:'<!doctype html><html>fixture</html>'},
  {status:503,text:'offline'},
  {status:200,text:'{broken'},
  {status:200,text:''},
);
const consumers=[
  ["identity/api/identity.ts","login",[{email:"fixture",password:"fixture"}]],
  ["characters/api/agents.ts","updateAgentProfile",["character",{name:"fixture"}]],
  ["social/api/character-post-actions.ts","createCommunityPost",[{title:"fixture",body:"fixture"}]],
];
for (const [file,method,args] of consumers) for (const response of responses) {
  const before=harness(true,response),after=harness(false,response);
  const outcome=async h=>{try{return {value:await h.load("frontend/src/features/"+file)[method](...args)};}catch(error){return {error:error.message};}};
  assert.deepEqual(plain(await outcome(after)),plain(await outcome(before)),file+" "+response.text);
  assert.deepEqual(plain(after.requests),plain(before.requests),file+" transport");
  assert.equal(after.requests.length,1);
  assert.deepEqual(after.events,before.events,file+" auth events");
  assert.deepEqual([...after.values],[...before.values],file+" auth storage");
}
console.log(`Feature error parity passed: ${consumers.length} real API consumers × ${responses.length} validation/parsing/auth responses.`);
