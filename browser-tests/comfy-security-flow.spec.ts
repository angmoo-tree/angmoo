import {test,expect,type Page,type BrowserContext} from "@playwright/test";
import {readFileSync} from "node:fs";
import {createHash} from "node:crypto";
const world="019f2000-0000-7000-8000-000000000000";
const cases=["text-next","reference-next","text-static","reference-static"];
const character=(name:string)=>`019f2000-0000-7000-8000-00000000000${cases.indexOf(name)+1}`;
const ko=JSON.parse(readFileSync("../frontend/src/features/media/locales/ko.json","utf8"));
const en=JSON.parse(readFileSync("../frontend/src/features/media/locales/en.json","utf8"));
async function login(page:Page,context:BrowserContext,baseURL:string,staticShell:boolean,language:"ko"|"en"){
  await context.addCookies([{name:"angmoo_browser_session",value:"synthetic-comfy-browser-session-only",url:baseURL,httpOnly:true,sameSite:"Lax"}]);
  if(staticShell)await page.addInitScript(()=>Object.assign(window,{__ANGMOO_RUNTIME_CONFIG__:{profile:"tauri-static",apiBaseUrl:"http://127.0.0.1:3443",graphProvider:"ladybug"}}));
  const api=staticShell?"http://127.0.0.1:3443/api/v1":`${baseURL}/api/backend`;
  const me=await (await context.request.get(api+"/auth/me")).json();
  const changed=await context.request.patch(api+"/auth/me/preferences",{headers:{Origin:baseURL,"X-Angmoo-Frontend-Origin":baseURL},data:{ui_language:language,expected_ui_revision:me.ui_preference_revision}});
  expect(changed.status()).toBe(200);
  // Network is limited to these owned loopback fixtures; app responses are real.
  await page.route("**/*",route=>[baseURL,"http://127.0.0.1:3443"].includes(new URL(route.request().url()).origin)?route.fallback():route.abort("blockedbyclient"));
  return api;
}
for(const kind of ["text","reference"] as const){
 test(`Comfy real ${kind} download import save generate and decoded pixels`,async({page,context,baseURL},info)=>{
  const staticShell=info.project.name==="static",name=`${kind}-${info.project.name}`;
  const language=kind==="text"?(staticShell?"en":"ko"):(staticShell?"ko":"en");
  const t=(key:string)=>(language==="ko"?ko:en)[key]??key;
  const api=await login(page,context,String(baseURL),staticShell,language);
  await page.setViewportSize({width:kind==="text"?360:1440,height:1000});await page.emulateMedia({reducedMotion:"reduce"});
  await page.goto(`/agents/${character(name)}?tab=settings`);
  const panel=page.getByRole("region",{name:t("SNS 이미지 생성 설정")});await expect(panel).toBeVisible();
  const original=await (await context.request.get(`${api}/agents/${character(name)}/generation-settings`)).json();
  const downloadPromise=page.waitForEvent("download");
  const button=panel.getByRole("button",{name:t(kind==="text"?"텍스트 예시 JSON 다운로드":"참조 예시 JSON 다운로드"),exact:true});
  await button.focus();await page.keyboard.press("Enter");const download=await downloadPromise;
  const file=await download.path();expect(file).not.toBeNull();const bytes=readFileSync(file!);
  const expected=readFileSync(`../backend/app/domains/media/samples/comfy-api-${kind}.json`);
  expect(createHash("sha256").update(bytes).digest("hex")).toBe(createHash("sha256").update(expected).digest("hex"));
  expect(JSON.parse(bytes.toString())).not.toHaveProperty("workflow");
  const after=await (await context.request.get(`${api}/agents/${character(name)}/generation-settings`)).json();
  expect(after).toEqual(original);
  await panel.getByLabel(t("API workflow 파일"),{exact:true}).setInputFiles(file!);
  await expect(panel.getByRole("combobox",{name:t("입력 모드"),exact:true})).toHaveValue("placeholders");
  await expect(panel.getByText(t("첫 이미지 자동 선택"),{exact:true}).first()).toBeVisible();
  await expect(panel.getByLabel("model · "+t("값"),{exact:true})).toHaveValue("");
  await panel.getByLabel("model · "+t("값"),{exact:true}).fill(`fixture-${name}.safetensors`);
  if(kind==="reference"){
   // Actual owned upload using a PNG with identifiable pixels and metadata.
   const png=readFileSync("../backend/tests/image_integration/fixtures/comfy-reference.png");
   await panel.getByLabel(t("첨부 이미지 선택"),{exact:true}).setInputFiles({name:"fixture.png",mimeType:"image/png",buffer:png});
   await expect(panel.getByAltText(t("선택한 첨부 이미지 미리보기"))).toBeVisible();
   await panel.getByRole("checkbox",{name:t("참조 이미지 사용"),exact:true}).check();
  }
  await panel.getByRole("button",{name:t("연결·입력 확인 및 저장"),exact:true}).click();
  await expect(panel.getByText(t("연결과 입력을 확인하고 저장했습니다. 이미지 생성 요청은 보내지 않았습니다."),{exact:true})).toBeVisible();
  await page.reload();await expect(panel.getByRole("combobox",{name:t("입력 모드"),exact:true})).toHaveValue("placeholders");
  const stored=await (await context.request.get(`${api}/agents/${character(name)}/generation-settings`)).json();
  expect(stored.active_profile.options.workflow.input_mode).toBe("placeholders");
  expect(stored.active_profile.options.workflow.output).toEqual({mode:"auto_first_image"});
  expect(stored.active_profile.options.workflow.bindings).toBeUndefined();
  expect(stored.active_profile.options.base_url).toBe(original.active_profile.options.base_url);
  expect(stored.has_partner_api_key).toBe(true);expect(stored.active_profile.options.values.seed).toBe(17);
  const enable=panel.getByRole("checkbox",{name:t("새 Routine 게시글 자동 이미지 생성 허용"),exact:true});
  await expect(enable).toBeEnabled();await enable.check();
  await panel.getByRole("button",{name:t("설정 저장"),exact:true}).click();
  await expect(panel.getByText(t("이미지 설정을 저장했습니다."),{exact:true})).toBeVisible();
  // One synthetic external AI scene enters the actual SNS image admission.
  await expect.poll(async()=>{const response=await context.request.get(`${api}/media/worlds/${world}/posts/post-${name}/image-generation`);return response.ok()?(await response.json())?.status:response.status();},{timeout:35_000}).toBe("succeeded");
  await page.goto(`/worlds/${world}/posts/post-${name}`);
  const pixels=page.locator("img").filter({hasNot:page.locator("[data-unused]")});
  await expect.poll(()=>pixels.evaluateAll(elements=>elements.some(e=>{const image=e as HTMLImageElement;return image.complete&&image.naturalWidth===16&&image.src.startsWith("blob:");}))).toBe(true);
  const color=await page.locator("img").evaluateAll(elements=>{
   const image=elements.find(e=>(e as HTMLImageElement).naturalWidth===16&&(e as HTMLImageElement).src.startsWith("blob:")) as HTMLImageElement;
   const canvas=document.createElement("canvas");canvas.width=canvas.height=16;const ctx=canvas.getContext("2d")!;ctx.drawImage(image,0,0);return Array.from(ctx.getImageData(0,0,1,1).data);
  });expect(color).toEqual(kind==="text"?[255,0,0,255]:[0,0,255,255]);
  await page.getByText(t("ComfyUI 실행 안내"),{exact:true}).click();
  await expect(page.getByText(/<img src=x onerror=window.fixture_xss=1>/)).toBeVisible();
  expect(await page.evaluate(()=>Boolean((window as unknown as Record<string,unknown>).fixture_xss))).toBe(false);
  const audit=(await (await context.request.get("http://127.0.0.1:3442/audit")).json())[name];
  expect(audit).toMatchObject({prompt:1,history:2,view:1,upload:0,scene:1});
  await page.screenshot({path:`../artifacts/comfy-security-20261012/${name}.png`,fullPage:true});
 });
}

test("CSP production fresh nonce matches bootstrap, blocks inline XSS and preserves Guide",async({page,context,baseURL},info)=>{
 test.skip(info.project.name!=="next","Server document Guide/CSP are Next-owned; static/Tauri policy is separate.");
 await login(page,context,String(baseURL),false,"en");
 const first=await page.goto("/angmoo-api");expect(first!.status()).toBe(200);
 const policy=first!.headers()["content-security-policy"];const nonce=policy.match(/'nonce-([^']+)'/)![1];
 expect(policy).not.toContain("script-src 'self' 'unsafe-inline'");expect(policy).not.toContain(" 'unsafe-eval'");
 expect(policy).toContain("wasm-unsafe-eval");expect(policy).toContain("script-src-attr 'none'");
 expect(first!.headers()["cache-control"]).toContain("no-store");expect(first!.headers()["x-content-type-options"]).toBe("nosniff");
 await expect(page.getByRole("heading",{name:"Character API",exact:true})).toBeVisible();
 const bootstraps=await page.locator("script:not([src])").evaluateAll(elements=>elements.filter(e=>e.textContent?.trim()&&(!e.type||e.type==="text/javascript")).map(e=>e.nonce));
 expect(bootstraps.length).toBeGreaterThan(0);expect([...new Set(bootstraps)]).toEqual([nonce]);
 const violations=await page.evaluate(async()=>{
  const events:string[]=[];document.addEventListener("securitypolicyviolation",event=>events.push(event.effectiveDirective));
  const code="window.__comfy_xss_executed=true";
  const script=document.createElement("script");script.textContent=code;document.body.append(script);
  const image=document.createElement("img");image.setAttribute("onerror",code);image.src="/missing-xss-image";document.body.append(image);
  const pre=document.createElement("pre");pre.textContent="<script>"+code+"</script>";document.body.append(pre);
  await new Promise(resolve=>setTimeout(resolve,250));return {events,executed:Boolean((window as unknown as Record<string,unknown>).__comfy_xss_executed),raw:pre.textContent};
 });expect(violations.executed).toBe(false);expect(violations.events).toContain("script-src-elem");expect(violations.events).toContain("script-src-attr");expect(violations.raw).toContain("<script>");
 const second=await page.reload();expect(second!.headers()["content-security-policy"]).not.toContain(`nonce-${nonce}`);
 const spoof=await context.request.get(String(baseURL)+"/angmoo-api",{headers:{"x-nonce":"attacker-nonce","Content-Security-Policy":"script-src * 'unsafe-inline'"}});
 expect(spoof.headers()["content-security-policy"]).not.toContain("attacker-nonce");expect(spoof.headers()["content-security-policy-report-only"]).toBeUndefined();
 const missing=await context.request.get(`${baseURL}/missing-page.json`);expect(missing.status()).toBe(404);
 expect(missing.headers()["content-security-policy"]).toContain("script-src-attr 'none'");
 for(const language of ["ko","en"]){const response=await context.request.get(`${baseURL}/agent_guide.md?lang=${language}`);expect(response.status()).toBe(200);expect(await response.text()).toBe(readFileSync(`../docs/agent_guide${language==="ko"?".ko":""}.md`,"utf8"));}
 expect((await context.request.get(`${baseURL}/agent_guide.md?lang=../secrets`)).status()).toBe(400);
 expect(await (await context.request.get(`${baseURL}/agent_guide.md`)).text()).toBe(readFileSync("../docs/agent_guide.ko.md","utf8"));
 await expect(page.getByRole("link",{name:"Open source",exact:true}).first()).toBeVisible();
 await expect(page.locator("#agent-guide pre")).toHaveText(readFileSync("../docs/agent_guide.md","utf8"));
 await expect(page.getByRole("link",{name:"Agent Guide.md",exact:true})).toHaveAttribute("href","/agent_guide.md?lang=en");
 const user=await(await context.request.get(`${baseURL}/api/backend/auth/me`)).json();
 expect((await context.request.patch(`${baseURL}/api/backend/auth/me/preferences`,{headers:{Origin:String(baseURL)},data:{ui_language:"ko",expected_ui_revision:user.ui_preference_revision}})).status()).toBe(200);
 await page.reload();await expect(page.locator("#agent-guide pre")).toHaveText(readFileSync("../docs/agent_guide.ko.md","utf8"));
 await expect(page.getByRole("link",{name:"Agent Guide.md",exact:true})).toHaveAttribute("href","/agent_guide.md");
});

test("CSP production local HEIC WASM decoding and World crop canvas remain usable",async({page,context,baseURL},info)=>{
 test.skip(info.project.name!=="next","Next enforcing CSP exercise.");
 const api=await login(page,context,String(baseURL),false,"en");
 await page.goto(`/worlds/${world}/feed`);
 const upload=page.waitForResponse(response=>response.url().endsWith("/media/assets")&&response.request().method()==="POST");
 await page.getByLabel("Select image attachment",{exact:true}).setInputFiles("fixtures/photos/primary.heic");
 const response=await upload;expect(response.status()).toBe(201);const asset=await response.json();
 const content=await context.request.get(`${api}/media/assets/${asset.id}/content`);expect(content.status()).toBe(200);
 const pixels=await page.evaluate(async bytes=>{const bitmap=await createImageBitmap(new Blob([new Uint8Array(bytes)],{type:"image/jpeg"}));const canvas=document.createElement("canvas");canvas.width=bitmap.width;canvas.height=bitmap.height;const context=canvas.getContext("2d")!;context.drawImage(bitmap,0,0);return {width:bitmap.width,red:context.getImageData(0,0,1,1).data[0]};},Array.from(await content.body()));
 expect(pixels.width).toBe(320);expect(pixels.red).toBeGreaterThan(230);
 // No post is sent; this checks the actual browser decoder and owned upload.
 await page.goto(`/studio/worlds/${world}`);
 await page.getByLabel("Upload icon",{exact:true}).setInputFiles("../backend/tests/image_integration/fixtures/comfy-reference.png");
 const dialog=page.getByRole("dialog");await expect(dialog).toBeVisible();
 expect(await dialog.locator("canvas").evaluate((canvas:HTMLCanvasElement)=>{const data=canvas.getContext("2d")!.getImageData(0,0,1,1).data;return [canvas.width,canvas.height,data[1]];})).toEqual([768,768,255]);
 await dialog.getByRole("button",{name:"Cancel",exact:true}).click();await expect(dialog).toHaveCount(0);
});

test("Comfy World editor uses the same raw replacement and readonly download contract",async({page,context,baseURL},info)=>{
 const staticShell=info.project.name==="static",language=staticShell?"ko":"en";
 const t=(key:string)=>(language==="ko"?ko:en)[key]??key;
 await login(page,context,String(baseURL),staticShell,language);
 await page.setViewportSize({width:staticShell?360:1440,height:1000});
 await page.goto(`/worlds/${world}/characters/actor-text-next?view=settings`);
 const card=page.getByRole("region",{name:t("SNS 게시글 이미지 생성"),exact:true});await expect(card).toBeVisible();
 const captured=page.waitForEvent("download");await card.getByRole("button",{name:t("텍스트 예시 JSON 다운로드"),exact:true}).click();
 const file=await(await captured).path();await card.getByLabel(t("API workflow 파일"),{exact:true}).setInputFiles(file!);
 await expect(card.getByRole("combobox",{name:t("입력 모드"),exact:true})).toHaveValue("placeholders");
 await expect(card.getByText(t("첫 이미지 자동 선택"),{exact:true}).first()).toBeVisible();
 await expect(card.getByLabel(t("서버 주소"))).toHaveValue("http://localhost:3442/comfy");
 expect(await card.evaluate(element=>element.scrollWidth<=element.clientWidth+1)).toBe(true);
});
