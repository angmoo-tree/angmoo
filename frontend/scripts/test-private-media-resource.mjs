// Real resource hook, authenticated fetch, runtime/session scope and browser Blob URLs.
// Only the HTTP responses and AuthContext identity are fixtures; no hook is stubbed.
import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import { execFileSync } from "node:child_process";
import { createServer } from "node:http";
import { once } from "node:events";
import path from "node:path";
import { fileURLToPath } from "node:url";
const root = fileURLToPath(new URL("..",import.meta.url)), require = createRequire(new URL("../package.json",import.meta.url));
const output = process.env.ANGMOO_PHOTO_RESOURCE_OUTPUT, baseline = process.env.ANGMOO_PHOTO_BASELINE_REF;
if (!output || !baseline || !process.env.ANGMOO_BROWSER_TEST_MODULES) throw Error("Explicit output, baseline ref and browser modules are required");
await mkdir(output,{recursive:true});
const prior = execFileSync("git",["show",`${baseline}:frontend/src/hooks/use-private-media-url.ts`],{cwd:root,encoding:"utf8"});
await writeFile(path.join(output,"baseline.ts"),prior);
await writeFile(path.join(output,"ts.cjs"),`const ts=require(${JSON.stringify(require.resolve("typescript"))});module.exports=s=>ts.transpileModule(s,{compilerOptions:{jsx:ts.JsxEmit.ReactJSX,module:ts.ModuleKind.ESNext,target:ts.ScriptTarget.ES2022}}).outputText;`);
const {webpack} = require("next/dist/compiled/webpack/webpack");
const compiler = webpack({mode:"development",devtool:false,context:root,entry:path.join(root,"scripts/fixtures/private-media-resource.tsx"),
  plugins:[new webpack.DefinePlugin({"process.env":JSON.stringify({NODE_ENV:"development"})})],output:{path:output,filename:"bundle.js"},
  resolve:{extensions:[".tsx",".ts",".js"],alias:{"baseline-private-media":path.join(output,"baseline.ts"),"@":path.join(root,"src")},modules:[path.join(root,"node_modules"),"node_modules"]},module:{rules:[{test:/\.tsx?$/,use:path.join(output,"ts.cjs")}]}});
await new Promise((resolve,reject)=>compiler.run((error,stats)=>error||stats.hasErrors()?reject(error??Error(stats.toString({all:false,errors:true}))):resolve()));
await new Promise(resolve=>compiler.close(resolve));
const bundle=await readFile(path.join(output,"bundle.js"));
let color="red",failure=false,block=false;const pending=[],requests=[];
const server=createServer((req,res)=>{
  if(req.url==="/bundle.js"){res.setHeader("content-type","text/javascript");return res.end(bundle);}
  if(req.url.startsWith("/api/backend/agents/")){
    requests.push({path:req.url,method:req.method,cache:req.headers["cache-control"]});
    const selected=color,failed=failure;
    const reply=()=>{res.statusCode=failed?503:200;res.setHeader("content-type","image/svg+xml");res.end(`<svg xmlns="http://www.w3.org/2000/svg" width="4" height="4"><rect width="4" height="4" fill="${selected}"/></svg>`);};
    if(block)pending.push(reply);else reply();return;
  }
  res.setHeader("content-type","text/html");res.end('<div id="root"></div><script src="/bundle.js"></script>');
});
server.listen(0,"127.0.0.1");await once(server,"listening");
const {chromium}=createRequire(path.join(process.env.ANGMOO_BROWSER_TEST_MODULES,"_test.cjs"))("@playwright/test");
const browser=await chromium.launch(),page=await browser.newPage();
const errors=[];page.on("pageerror",error=>errors.push(error.message));
async function wait(condition){await page.waitForFunction(condition,undefined,{timeout:10000});}
const pixel=id=>page.locator(`#${id}`).evaluate(image=>{const canvas=document.createElement("canvas");canvas.width=canvas.height=1;const context=canvas.getContext("2d");context.drawImage(image,0,0,1,1);return Array.from(context.getImageData(0,0,1,1).data);});
const release=()=>{block=false;for(const reply of pending.splice(0))reply();};
try{
  await page.goto(`http://127.0.0.1:${server.address().port}`);
  await wait(()=>document.querySelector("#current").naturalWidth&&document.querySelector("#baseline").naturalWidth);
  assert.deepEqual(await pixel("current"),[255,0,0,255]);
  color="lime";await page.evaluate(()=>fixture.set({revision:1}));
  await wait(()=>document.querySelector("#status").textContent==="ready"&&document.querySelector("#current").complete);
  assert.deepEqual(await pixel("current"),[0,255,0,255]);assert.deepEqual(await pixel("baseline"),[255,0,0,255]);
  const good=await page.locator("#current").getAttribute("src");
  failure=true;await page.evaluate(()=>fixture.set({revision:2}));await wait(()=>document.querySelector("#status").textContent==="error");
  assert.equal(await page.locator("#current").getAttribute("src"),good);
  failure=false;await page.evaluate(()=>fixture.retry());await wait(()=>document.querySelector("#status").textContent==="ready");
  block=true;color="blue";await page.evaluate(()=>fixture.set({revision:3}));await wait(()=>document.querySelector("#status").textContent==="loading");
  await page.evaluate(()=>fixture.set({identity:"new-owner",source:"/api/v1/agents/drafts/new-owner/media/avatar"}));
  await wait(()=>!document.querySelector("#current").getAttribute("src"));
  release();await wait(()=>document.querySelector("#status").textContent==="ready");
  block=true;await page.evaluate(()=>fixture.set({revision:4}));await wait(()=>document.querySelector("#status").textContent==="loading");
  await page.evaluate(()=>fixture.set({show:false}));release();
  await wait(()=>fixture.urls.every(url=>fixture.revoked.includes(url)));
  assert(requests.every(row=>row.method==="GET"));assert.equal(errors.length,0,errors.join("\n"));
  await writeFile(path.join(output,"result.json"),JSON.stringify({baseline,status:"PASS",baseline_same_url_stale:true,current_pixel_refresh:true,saved_get_failure_retained:true,get_only_retry:true,scope_change_clears:true,unmount_releases:true,requests},null,2));
  console.log("PASS private media: baseline reproduction, pixels, GET retry, scope, late response and URL cleanup");
}finally{release();await browser.close();await new Promise(resolve=>server.close(resolve));}
