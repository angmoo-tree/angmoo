import {test,expect} from "@playwright/test";
import {readFileSync} from "node:fs";
const id="019f2000-0000-7000-8000-000000000001";
const t=JSON.parse(readFileSync("../frontend/src/features/media/locales/en.json","utf8"));
async function editor(page:import("@playwright/test").Page,context:import("@playwright/test").BrowserContext,baseURL:string,staticShell:boolean){
 await context.addCookies([{name:"angmoo_browser_session",value:"synthetic-comfy-browser-session-only",url:baseURL,httpOnly:true,sameSite:"Lax"}]);
 if(staticShell)await page.addInitScript(()=>Object.assign(window,{__ANGMOO_RUNTIME_CONFIG__:{profile:"tauri-static",apiBaseUrl:"http://127.0.0.1:3443",graphProvider:"ladybug"}}));
 const api=staticShell?"http://127.0.0.1:3443/api/v1":`${baseURL}/api/backend`;
 const user=await(await context.request.get(api+"/auth/me")).json();
 expect((await context.request.patch(api+"/auth/me/preferences",{headers:{Origin:baseURL,"X-Angmoo-Frontend-Origin":baseURL},data:{ui_language:"en",expected_ui_revision:user.ui_preference_revision}})).status()).toBe(200);
 await page.goto(`/agents/${id}?tab=settings`);
 const panel=page.getByRole("region",{name:t["SNS 이미지 생성 설정"]});await expect(panel).toBeVisible();
 await panel.getByRole("button",{name:t["텍스트 예시 사용"],exact:true}).click();
 await expect(panel.getByRole("combobox",{name:t["입력 모드"],exact:true})).toHaveValue("placeholders");
 return panel;
}
test("Comfy identical file replacement resets explicit output and preserves key URL and existing values",async({page,context,baseURL},info)=>{
 const panel=await editor(page,context,String(baseURL),info.project.name==="static");
 await panel.getByLabel(t["Comfy 계정 API 키"]).fill("synthetic-unsaved-draft");
 const output=panel.getByRole("combobox",{name:t["이미지 출력"],exact:true});
 await panel.getByText(t["고급 출력 설정"],{exact:true}).click();await output.selectOption("explicit_node");
 await panel.getByRole("combobox",{name:t["이미지 출력 노드"],exact:true}).selectOption("6");
 const raw=panel.getByLabel(t["불러온 API workflow JSON"],{exact:true}),before=await raw.inputValue();
 await panel.getByLabel(t["API workflow 파일"],{exact:true}).setInputFiles({name:"same.json",mimeType:"application/json",buffer:Buffer.from(before)});
 await expect(output).toHaveValue("auto_first_image");
 await expect(panel.getByLabel(t["Comfy 계정 API 키"])).toHaveValue("synthetic-unsaved-draft");
 await expect(panel.getByLabel(t["서버 주소"])).toHaveValue("http://localhost:3442/comfy");
 await expect(panel.getByLabel("seed · "+t["값"],{exact:true})).toHaveValue("17");
 expect(await panel.getByRole("button",{name:t["텍스트 예시 JSON 다운로드"]}).evaluate(e=>e.getBoundingClientRect().height)).toBeGreaterThanOrEqual(44);
});
test("Comfy edit keeps output, deleted output and duplicate raw block save and preserve text",async({page,context,baseURL},info)=>{
 const panel=await editor(page,context,String(baseURL),info.project.name==="static");
 await panel.getByText(t["고급 출력 설정"],{exact:true}).click();
 await panel.getByRole("combobox",{name:t["이미지 출력"],exact:true}).selectOption("explicit_node");
 await panel.getByRole("combobox",{name:t["이미지 출력 노드"],exact:true}).selectOption("7");
 const raw=panel.getByLabel(t["불러온 API workflow JSON"],{exact:true});const graph=JSON.parse(await raw.inputValue());
 graph["1"]._meta={title:"<img src=x onerror=window.bad=1>"};await raw.fill(JSON.stringify(graph));
 await expect(panel.getByRole("combobox",{name:t["이미지 출력 노드"],exact:true})).toHaveValue("7");
 await expect(panel.getByRole("button",{name:t["설정 저장"],exact:true})).toBeEnabled();
 delete graph["7"];await raw.fill(JSON.stringify(graph));await expect(raw).toHaveAttribute("aria-invalid","true");
 await expect(panel.getByRole("button",{name:t["설정 저장"],exact:true})).toBeDisabled();
 const invalid='{"1":{"class_type":"A","inputs":{}},"1":{"class_type":"B","inputs":{}}}';await raw.fill(invalid);
 await expect(raw).toHaveAttribute("aria-invalid","true");await expect(raw).toHaveValue(invalid);
 expect(await page.evaluate(()=>Boolean((window as unknown as Record<string,unknown>).bad))).toBe(false);
});
test("Comfy slow file A cannot replace file B or cross the text tab",async({page,context,baseURL},info)=>{
 await page.addInitScript(()=>{
  const original=File.prototype.text;
  File.prototype.text=function(){return original.call(this).then(text=>this.name==="slow-A.json"?new Promise<string>(resolve=>setTimeout(()=>resolve(text),900)):text);};
 });
 const panel=await editor(page,context,String(baseURL),info.project.name==="static");
 const a=JSON.parse(readFileSync("../backend/app/domains/media/samples/comfy-api-text.json","utf8"));
 const b=structuredClone(a);a["1"]._meta={title:"slow loser"};b["1"]._meta={title:"latest winner"};
 const input=panel.getByLabel(t["API workflow 파일"],{exact:true});
 await input.setInputFiles({name:"slow-A.json",mimeType:"application/json",buffer:Buffer.from(JSON.stringify(a))});
 await expect(panel.getByRole("button",{name:t["설정 저장"],exact:true})).toBeDisabled();
 await input.setInputFiles({name:"fast-B.json",mimeType:"application/json",buffer:Buffer.from(JSON.stringify(b))});
 const raw=panel.getByLabel(t["불러온 API workflow JSON"],{exact:true});await expect(raw).toHaveValue(JSON.stringify(b));
 await page.waitForTimeout(1100);await expect(raw).toHaveValue(JSON.stringify(b));
 await input.setInputFiles({name:"slow-A.json",mimeType:"application/json",buffer:Buffer.from(JSON.stringify(a))});
 await panel.getByRole("button",{name:t["참조 없는 텍스트 경로 입력"],exact:true}).click();
 await page.waitForTimeout(1100);await expect(raw).toHaveValue("");
});

test("Comfy locale keeps draft during reading, runtime replacement cancels the old read",async({page,context,baseURL},info)=>{
 await page.addInitScript(()=>{const original=File.prototype.text;File.prototype.text=function(){return original.call(this).then(text=>this.name.startsWith("slow-")?new Promise<string>(resolve=>setTimeout(()=>resolve(text),1200)):text);};});
 const staticShell=info.project.name==="static";
 const panel=await editor(page,context,String(baseURL),staticShell);
 await panel.getByLabel(t["Comfy 계정 API 키"]).fill("synthetic-locale-draft");
 const graph=JSON.parse(readFileSync("../backend/app/domains/media/samples/comfy-api-text.json","utf8"));graph["1"]._meta={title:"same identity latest file"};
 await panel.getByLabel(t["API workflow 파일"],{exact:true}).setInputFiles({name:"slow-locale.json",mimeType:"application/json",buffer:Buffer.from(JSON.stringify(graph))});
 const api=staticShell?"http://127.0.0.1:3443/api/v1":`${baseURL}/api/backend`;
 const user=await(await context.request.get(api+"/auth/me")).json();
 const changed=await context.request.patch(api+"/auth/me/preferences",{headers:{Origin:String(baseURL),"X-Angmoo-Frontend-Origin":String(baseURL)},data:{ui_language:"ko",expected_ui_revision:user.ui_preference_revision}});
 expect(changed.status()).toBe(200);
 // The same cache/event boundary used by LanguageSettings.storeUser.
 await page.evaluate(user=>{sessionStorage.setItem("angmoo.user",JSON.stringify(user));window.dispatchEvent(new Event("angmoo:auth-changed"));},await changed.json());
 const localized=page.getByRole("region",{name:"SNS 이미지 생성 설정"});
 await expect(localized.getByLabel("불러온 API workflow JSON",{exact:true})).toHaveValue(JSON.stringify(graph));
 await expect(localized.getByLabel("Comfy 계정 API 키")).toHaveValue("synthetic-locale-draft");
 graph["1"]._meta={title:"old runtime must not apply"};
 await localized.getByLabel("API workflow 파일",{exact:true}).setInputFiles({name:"slow-runtime.json",mimeType:"application/json",buffer:Buffer.from(JSON.stringify(graph))});
 await page.evaluate(()=>window.dispatchEvent(new Event("angmoo:desktop-runtime-config-changed")));
 await page.waitForTimeout(1500);
 expect(await localized.getByLabel("불러온 API workflow JSON",{exact:true}).inputValue()).not.toContain("old runtime must not apply");
 await expect(localized.getByLabel("Comfy 계정 API 키")).toHaveValue("");
});

test("Comfy save CAS rejection preserves valid raw and credential draft",async({page,context,baseURL},info)=>{
 const staticShell=info.project.name==="static",panel=await editor(page,context,String(baseURL),staticShell);
 await panel.getByLabel(t["Comfy 계정 API 키"]).fill("synthetic-conflict-draft");
 const raw=panel.getByLabel(t["불러온 API workflow JSON"],{exact:true}),before=await raw.inputValue();
 await page.route(staticShell?"http://127.0.0.1:3443/api/v1/agents/*/generation-settings":"**/api/backend/agents/*/generation-settings",route=>route.request().method()==="PUT"?route.fulfill({status:409,contentType:"application/json",body:JSON.stringify({detail:"image_settings_revision_conflict"})}):route.fallback());
 const save=panel.getByRole("button",{name:t["설정 저장"],exact:true});await expect(save).toBeEnabled();await save.click();
 await expect(panel.getByRole("alert")).toBeVisible();await expect(raw).toHaveValue(before);
 await expect(panel.getByLabel(t["Comfy 계정 API 키"])).toHaveValue("synthetic-conflict-draft");
});
