import { test, expect, type Page } from "@playwright/test";
import { continuityAgentDetail } from "./continuity-fixture";
import { installBackendFixture, json, uiDWorld, uiDOwnerActor, uiDManualPost, uiDManualFeed } from "./continuity-next-fixture";
import { readFileSync } from "node:fs";
import { VISUAL_ENVIRONMENT } from "./fixtures/visual-environment.mjs";
import { installWorldCharacterManagementFixture, worldCharacterRoute, WORLD_AGENT } from "./world-character-management-fixture";
import { FEED_WORLD } from "./world-feed-fixture";

test.use({screenshot:"on", locale:"ko-KR", timezoneId:"Asia/Seoul"});
test.beforeEach(async ({page}, info) => {
  const origin = new URL(String(info.project.use.baseURL)).origin;
  await page.route("**/*", route => new URL(route.request().url()).origin === origin ? route.fallback() : route.abort("blockedbyclient"));
});

const character="image-fixture-bird";
const models=[
  ["novelai","nai-diffusion-4-5-full",true], ["nanogpt","krea-v2/turbo",true],
  ["nanogpt","z-image-turbo",false], ["nanogpt","nano-banana-2",true],
  ["openrouter","krea/krea-2-medium-turbo",true],["openrouter","google/gemini-3.1-flash-image",true],["openrouter","openai/gpt-image-2.5-flare",true],
].map(([provider,id,reference_supported])=>({provider,id,reference_supported,negative_supported:provider==="novelai",parameters:{},pricing:null,availability:"requires_connection_check"}));
const options={mode:"opus_free",width:1024,height:1024,steps:28,scale:5,sampler:"k_euler_ancestral",noise_schedule:"karras",seed:-1,cfg_rescale:0,decrisper:false,variety_boost:false,reference_strength:1,reference_fidelity:1,reference_type:"character&style"};
const comfyTokens: Record<string,string> = {"%prompt%":"positive","%negative_prompt%":"negative","%model%":"model","%vae%":"vae","%width%":"width","%height%":"height","%steps%":"steps","%scale%":"cfg","%sampler%":"sampler","%scheduler%":"scheduler","%seed%":"seed","%denoise%":"denoise","%clip_skip%":"clip_skip","%char_avatar%":"reference"};
function viewAnalysis(source:string, mode:string) {
  const prompt = JSON.parse(source), positions:Record<string,unknown>[] = [], notices:Record<string,unknown>[] = [];
  function visit(value:unknown, node_id:string, input_name:string, path:(string|number)[]) {
    if (typeof value === "string") {
      if (comfyTokens[value]) positions.push({token:value,role:comfyTokens[value],node_id,input_name,path});
      else if(value.includes("%")) notices.push({node_id,input_name,path,kind:"preserved_expression"});
    } else if(Array.isArray(value)) {
      if (value.length===2 && typeof value[0]==="string" && Number.isInteger(value[1])) return;
      value.forEach((item,index)=>visit(item,node_id,input_name,[...path,index]));
    } else if(value && typeof value==="object") Object.entries(value).forEach(([key,item])=>visit(item,node_id,input_name,[...path,key]));
  }
  for(const [id,node] of Object.entries(prompt) as [string,{inputs:Record<string,unknown>}][]) {
    for(const [name,value] of Object.entries(node.inputs)) visit(value,id,name,[]);
  }
  const used_roles = [...new Set(positions.map(item=>String(item.role)))];
  return {input_mode:mode,prompt,supported_tokens:comfyTokens,positions,notices,used_roles,reference_required:used_roles.includes("reference"),prompt_applied:used_roles.includes("positive"),source_digest:"synthetic-view-digest"};
}
async function fixtures(page:Page, staticShell:boolean, initial:{comfy?:Record<string,unknown>;language?:"ko"|"en"}={}) {
  if(staticShell) await page.addInitScript(()=>Object.assign(window,{__ANGMOO_RUNTIME_CONFIG__:{profile:"tauri-static",apiBaseUrl:"http://127.0.0.1:8080",graphProvider:"ladybug",launchToken:"image-fixture-token-0000000000000"}}));
  else await installBackendFixture(page,{worldReads:{[uiDWorld().world_id]:uiDWorld()}});
  const writes:Record<string,unknown>[]=[];
  let settings={character_id:character,revision:1,installation_revision:1,provider:null as string|null,model:null as string|null,auto_enabled:false,daily_limit:null as number|null,installation_daily_limit:10,appearance:"",style:"",negative:"",reference_asset_id:null as string|null,has_api_key:false,profiles:{} as Record<string,unknown>,active_profile:{} as Record<string,unknown>};
  if(initial.comfy) { const profile={active:true,reference_initialized:true,reference_enabled:false,options:initial.comfy,connection:null};settings={...settings,provider:"comfyui",model:"workflow",profiles:{"comfyui:workflow:":profile},active_profile:profile}; }
  let recognition={revision:0,enabled:false,model:"gemini-3.1-flash-lite",thinking_level:"medium",daily_limit:null,has_api_key:false};
  let upload=0;
  await page.route(staticShell?"http://127.0.0.1:8080/api/v1/**":"**/api/backend/**",async route=>{
    const request=route.request();const path=new URL(request.url()).pathname.replace(/^\/api\/(backend|v1)/,"");
    if(path==="/auth/me")return json(route,{id:"local-owner",email:null,display_name:"Local Owner",profile_setup_completed:true,ui_language:initial.language??"ko",ui_preference_revision:1,feed_content_filter:"all",is_admin:true});
    if(path==="/auth/local/environment")return json(route,VISUAL_ENVIRONMENT);
    if(path===`/agents/${character}`)return json(route,continuityAgentDetail(character));
    if(path.endsWith("/lore-sources"))return json(route,{items:[]});
    if(path==="/media/catalog")return json(route,{models,quota_timezone:"Asia/Seoul",upload_limit_bytes:10485760});
    if(path.includes("/generation-settings")){
      if(request.method()!=="GET"){
        const body=request.postDataJSON();writes.push(body);const mode=body.options.mode??"";const referenceSupported=Boolean(body.options.workflow?.bindings?.reference)||JSON.stringify(body.options.workflow?.prompt??{}).includes("%char_avatar%");const profile={active:true,reference_initialized:true,reference_enabled:body.reference_enabled??(body.provider==="comfyui"&&path.endsWith("/check")&&referenceSupported),options:body.options,reference_effective:body.reference_enabled??false,connection:path.endsWith("/check")?{ready:true,server_connection:{state:"connected"},input_readiness:{state:"ready",path:"workflow"},candidate_lookup:{state:"unavailable"},reference_supported:body.provider==="comfyui"?referenceSupported:body.provider!=="novelai"||mode!=="opus_free",opus_verified:true,credential_validation:"not_verified",object_info:{}}:null};
        settings={...settings,...body,revision:settings.revision+1,installation_revision:settings.installation_revision+1,has_api_key:Boolean(body.api_key)||settings.has_api_key,profiles:{...settings.profiles,[`${body.provider}:${body.model}:${mode}`]:profile},active_profile:profile};
      } return json(route,settings);
    }
    if(path==="/media/interpretation-settings"){
      if(request.method()!=="GET"){const body=request.postDataJSON();writes.push(body);recognition={...recognition,...body,revision:recognition.revision+1,has_api_key:Boolean(body.api_key)};}return json(route,recognition);
    }
    if(path==="/media/usage-settings")return json(route,{revision:1,daily_limit:10,quota_day:"2026-09-30",generation_reserved_or_used:2,interpretation_reserved_or_used:1,interpretation_daily_limit:4});
    if(path.startsWith("/media/comfy-samples/")){const kind=path.split("/").at(-1);return json(route,JSON.parse(readFileSync(`../backend/app/domains/media/samples/comfy-${kind}.json`,"utf8")));}
    if(path==="/media/comfy-workflows/analyze"){
      try {const body=request.postDataJSON();return json(route,viewAnalysis(body.source_json,body.input_mode));}
      catch {return json(route,{detail:"comfy_json_invalid"},422);}
    }
    if(path==="/media/assets"&&request.method()==="POST"){upload++;writes.push(request.postDataJSON());return json(route,{id:`draft-${upload}`,url:`/api/v1/media/assets/draft-${upload}/content`,revision:1,width:2,height:1,state:"draft",byte_size:80},201);}
    if(path.endsWith("/content"))return route.fulfill({contentType:"image/png",body:Buffer.from("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=","base64")});
    if(path.endsWith("/preflight"))return json(route,{allowed:false,reason:"interpretation_disabled"});
    if(path.startsWith("/media/assets/")&&request.method()==="DELETE")return route.fulfill({status:204});
    if(path.endsWith("/image-generation"))return json(route,null);
    if(path.endsWith("/owner-character"))return json(route,uiDOwnerActor());
    if(path.endsWith("/app")||path===`/worlds/mine/${uiDWorld().world_id}`)return json(route,{schema_version:"local-world-app-v1",surface:"world_app",world:uiDWorld()});
    if(path.includes("/chat/threads/")){
      const role={world_character_id:"wc-image",character_id:character,display_name:"이미지 친구",handle:"image_friend",avatar_url:null,banner_url:null,role_key:null,control_mode:"autonomous",profile_capability:"available"};
      const thread={id:"thread-image",world_id:uiDWorld().world_id,requester:{...role,world_character_id:"wc-owner",control_mode:"owner_controlled"},responding:role,selected_model:"gemini-3.1-flash-lite",selected_thinking_level:"high",default_model:"gemini-3.1-flash-lite",default_thinking_level:"high",model_binding_mode:"default",last_message_at:null,created_at:"2026-09-30T00:00:00Z",latest_message:null,messages:[],evidence_summaries:[]};
      if(path.endsWith("/requests/latest"))return json(route,{response_request:null});
      if(path.endsWith("/thread-image"))return json(route,thread);
    }
    if(path.endsWith("/manual-social/posts")&&request.method()==="POST"){
      const body=request.postDataJSON();writes.push(body);
      const post={...uiDManualPost({id:"uploaded-post",authorName:"UI-D Owner",title:body.title,body:body.body}),media:[{id:1,post_id:"uploaded-post",asset_id:body.attachment_asset_id,url:`/api/v1/media/assets/${body.attachment_asset_id}/content`,alt_text:"업로드 사진",model:null,prompt_hash:null,byte_size:80,width:1,height:1,created_at:"2026-09-30T00:00:00Z",media_type:"image",source_kind:"upload"}]};
      return json(route,{schema_version:"owner-manual-social-v1",operation:"post",post,replayed:false,delivery:{provider_call_count:0,inbox_candidate_id:null,inbox_status:"not_applicable",public_reaction_required:false}},201);
    }
    if(path.endsWith("/manual-social/feed"))return json(route,uiDManualFeed([]));
    if(staticShell)return json(route,{detail:"fixture_read_unavailable"},404);
    return route.fallback();
  });
  return {writes,getSettings:()=>settings};
}

for(const viewport of [{width:360,height:800},{width:390,height:844},{width:436,height:880},{width:1440,height:1000}]){
  test(`generation controls and reference defaults at ${viewport.width}`,async({page},info)=>{
    const audit=await fixtures(page,info.project.name==="static");await page.setViewportSize(viewport);await page.emulateMedia({reducedMotion:"reduce"});
    await page.goto(`/agents/${character}?tab=settings`);const panel=page.getByRole("region",{name:"SNS 이미지 생성 설정"});
    await expect(panel.getByRole("combobox",{name:"비용 모드"})).toHaveValue("opus_free");
    await expect(panel.getByRole("checkbox",{name:"참조 이미지 사용"})).toBeDisabled();
    await expect(panel.getByRole("spinbutton",{name:"Steps",exact:true})).toHaveAttribute("max","28");
    await panel.getByRole("combobox",{name:"비용 모드"}).selectOption("allow_anlas");await expect(panel.getByRole("checkbox",{name:"참조 이미지 사용"})).toBeChecked();
    await panel.getByRole("combobox",{name:"이미지 서비스"}).selectOption("nanogpt");await expect(panel.getByRole("checkbox",{name:"참조 이미지 사용"})).toBeChecked();
    await panel.getByRole("combobox",{name:"이미지 모델"}).selectOption("z-image-turbo");await expect(panel.getByRole("checkbox",{name:"참조 이미지 사용"})).not.toBeChecked();await expect(panel.getByRole("checkbox",{name:"참조 이미지 사용"})).toBeDisabled();
    await expect(panel.getByText(/参照|참조 사진과 외형/)).toBeVisible();await expect(panel.getByRole("checkbox",{name:"새 Routine 게시글 자동 이미지 생성 허용"})).not.toBeChecked();
    await panel.getByRole("button",{name:"설정 저장",exact:true}).click();await expect.poll(()=>audit.writes.length).toBe(1);
    expect(audit.writes[0].auto_enabled).toBe(false);expect(audit.writes[0].appearance).toBe("");expect(audit.writes[0].reference_enabled).toBe(false);
    await page.reload();await expect(panel.getByRole("checkbox",{name:"참조 이미지 사용"})).not.toBeChecked();
    if(viewport.width===1440)await page.evaluate(()=>{document.body.style.zoom="2";});
    expect(await panel.evaluate(e=>e.scrollWidth<=e.clientWidth+1)).toBe(true);
  });
}

test("Comfy samples provide editable bindings and a separate text path without generation",async({page},info)=>{
  const audit=await fixtures(page,info.project.name==="static");await page.goto(`/agents/${character}?tab=settings`);
  const panel=page.getByRole("region",{name:"SNS 이미지 생성 설정"});await panel.getByRole("combobox",{name:"이미지 서비스"}).selectOption("comfyui");
  await panel.getByRole("button",{name:"참조 예시",exact:true}).click();await panel.getByText("고급 입력 연결",{exact:true}).click();await expect(panel.getByRole("combobox",{name:"positive · 입력 노드"})).toHaveValue("2");
  await panel.getByRole("button",{name:"참조 없는 텍스트 경로 입력"}).click();await panel.getByRole("button",{name:"텍스트 예시",exact:true}).click();if(!await panel.getByRole("combobox",{name:"positive · 입력 노드"}).isVisible())await panel.getByText("고급 입력 연결",{exact:true}).click();await expect(panel.getByRole("combobox",{name:"positive · 입력 노드"})).toHaveValue("2");
  await expect(panel.getByRole("combobox",{name:"reference · 입력 노드"})).toHaveValue("");
  await panel.getByRole("button",{name:"연결·입력 확인 및 저장"}).click();await expect.poll(()=>audit.writes.length).toBe(1);
  const written=audit.writes[0].options as Record<string,unknown>;expect(written.workflow).toBeTruthy();expect(written.text_workflow).toBeTruthy();expect(audit.writes[0].auto_enabled).toBe(false);
});

const placeholderGraph = {"9":{class_type:"CustomNotInstalled",inputs:{text:"%prompt%",negative:"%negative_prompt%",nested:{"a/b":["%seed%","%clip_skip%"]},model:"%model%",prefix:"image_%seed%",untouched:"%unknown%"},_meta:{title:"%prompt%"}}};
const placeholderOptions = (prompt:Record<string,unknown> = placeholderGraph) => ({options_schema_version:2,clip_skip_value_mode:"skip_count",base_url:"http://comfyui:8188/base",values:{seed:-1,clip_skip:1,model:"custom.ckpt"},workflow:{input_mode:"placeholders",prompt,output:{mode:"auto_first_image"}}});
for(const language of ["ko","en"] as const) {
test(`Comfy editable raw JSON and manual values survive invalid drafts, import and save (${language})`,async({page},info)=>{
  const audit=await fixtures(page,info.project.name==="static",{comfy:placeholderOptions(),language});
  const catalog = JSON.parse(readFileSync(`../frontend/src/features/media/locales/${language}.json`,"utf8"));const t=(key:string)=>catalog[key]??key;
  await page.goto(`/agents/${character}?tab=settings`);await page.setViewportSize({width:360,height:880});
  const panel=page.getByRole("region",{name:t("SNS 이미지 생성 설정")});const raw=panel.getByLabel(t("불러온 API workflow JSON"),{exact:true});
  await expect(panel.getByText(t("JSON 분석 완료"),{exact:true})).toBeVisible();
  await panel.getByText(t("연결 확인과 크기 제한"),{exact:true}).click();
  await expect(panel.getByText(t("서버 연결 미확인"),{exact:true})).toBeVisible();
  await expect(panel.getByText(t("서버 연결과 입력 준비를 확인했습니다. 실행 가능 여부는 생성 요청 시 ComfyUI가 확인합니다."),{exact:true})).toHaveCount(0);
  await panel.getByText(t("연결 확인과 크기 제한"),{exact:true}).click();
  await raw.fill('{"broken":');await expect(panel.getByRole("alert")).toContainText(t("JSON을 확인하지 못했습니다. 입력한 내용을 수정해 주세요."));
  await expect(raw).toHaveValue('{"broken":');await expect(panel.getByRole("button",{name:t("설정 저장"),exact:true})).toBeDisabled();
  await panel.getByLabel(t("API workflow 파일")).setInputFiles({name:"synthetic-api.json",mimeType:"application/json",buffer:Buffer.from(JSON.stringify(placeholderGraph))});
  await expect(panel.getByText(t("JSON 분석 완료"),{exact:true})).toBeVisible();await expect(raw).toHaveValue(JSON.stringify(placeholderGraph));
  await panel.getByLabel(`model · ${t("값")}`,{exact:true}).fill("manual-model.safetensors");
  await expect(panel.getByText(t("CLIP skip은 양수로 입력해 주세요. 1은 노드에 -1로 전달됩니다."),{exact:true})).toBeVisible();
  await panel.getByText(t("고급 출력 설정"),{exact:true}).focus();await page.keyboard.press("Enter");
  await panel.getByRole("combobox",{name:t("이미지 출력"),exact:true}).selectOption("explicit_node");
  await expect(panel.getByRole("combobox",{name:t("이미지 출력 노드"),exact:true})).toHaveValue("9");
  await panel.getByRole("button",{name:t("연결·입력 확인 및 저장"),exact:true}).click();await expect.poll(()=>audit.writes.length).toBe(1);
  const stored=audit.writes[0].options as ReturnType<typeof placeholderOptions>;
  expect(stored.workflow.prompt).toEqual(placeholderGraph);expect(stored.values.model).toBe("manual-model.safetensors");expect(stored.workflow.output).toEqual({mode:"explicit_node",node_id:"9"});
  await panel.getByText(t("연결 확인과 크기 제한"),{exact:true}).click();
  await expect(panel.getByText(t("서버 연결과 입력 준비를 확인했습니다. 실행 가능 여부는 생성 요청 시 ComfyUI가 확인합니다."),{exact:true})).toBeVisible();
  await expect(panel.getByText(t("설정 후보를 불러오지 못했습니다. 값을 직접 입력할 수 있습니다."),{exact:true})).toBeVisible();
  expect(await panel.evaluate(element=>element.scrollWidth<=element.clientWidth+1)).toBe(true);
  expect(await raw.evaluate(element=>element.scrollHeight>element.clientHeight)).toBe(true);
  await page.setViewportSize({width:1440,height:1000});expect(await panel.evaluate(element=>element.scrollWidth<=element.clientWidth+1)).toBe(true);
  for(const width of [360,1440]) {
    await page.setViewportSize({width,height:1000});await panel.getByRole("heading",{name:t("ComfyUI workflow 입력"),exact:true}).evaluate(element=>element.scrollIntoView({block:"start"}));
    await page.screenshot({path:`../artifacts/image-integration/browser/${info.project.name}-comfy-${language}-${width===1440?"wide":"narrow"}.png`,fullPage:true});
  }
  await page.reload();await expect(raw).toHaveValue(JSON.stringify(placeholderGraph,null,2));await expect(panel.getByLabel(`model · ${t("값")}`,{exact:true})).toHaveValue("manual-model.safetensors");
});
}

test("Comfy fixed prompt graphs are editable and save without required placeholder values",async({page},info)=>{
  const graph={"a":{class_type:"Custom",inputs:{text:"fixed prompt",value:"%unsupported%"}}};
  const audit=await fixtures(page,info.project.name==="static",{comfy:placeholderOptions(graph)});await page.goto(`/agents/${character}?tab=settings`);
  const panel=page.getByRole("region",{name:"SNS 이미지 생성 설정"});await expect(panel.getByText("이 워크플로에는 Angmoo의 이미지 프롬프트가 적용되지 않습니다. JSON의 고정 프롬프트를 사용합니다.",{exact:true})).toBeVisible();
  await expect(panel.getByLabel("model · 값",{exact:true})).toHaveCount(0);
  await panel.getByRole("button",{name:"설정 저장",exact:true}).click();await expect.poll(()=>audit.writes.length).toBe(1);
  expect((audit.writes[0].options as ReturnType<typeof placeholderOptions>).workflow.prompt).toEqual(graph);
});

test("new Comfy reference preference can be switched off before the first connection check",async({page},info)=>{
  const audit=await fixtures(page,info.project.name==="static");await page.goto(`/agents/${character}?tab=settings`);
  const panel=page.getByRole("region",{name:"SNS 이미지 생성 설정"});await panel.getByRole("combobox",{name:"이미지 서비스"}).selectOption("comfyui");
  await panel.getByLabel("불러온 API workflow JSON",{exact:true}).fill(JSON.stringify({"9":{class_type:"Base64Image",inputs:{data:"%char_avatar%"}}}));
  const reference=panel.getByRole("checkbox",{name:"참조 이미지 사용"});await expect(reference).toBeEnabled();await expect(reference).toBeChecked();
  await panel.getByRole("button",{name:"참조 없는 텍스트 경로 입력",exact:true}).click();
  await panel.getByLabel("불러온 API workflow JSON",{exact:true}).fill(JSON.stringify({"9":{class_type:"TextImage",inputs:{text:"%prompt%"}}}));
  await expect(panel.getByText("JSON 분석 완료",{exact:true})).toBeVisible();
  await reference.uncheck();await panel.getByRole("button",{name:"연결·입력 확인 및 저장",exact:true}).click();
  await expect.poll(()=>audit.writes.length).toBe(1);expect(audit.writes[0].reference_enabled).toBe(false);
});

test("Comfy legacy settings retain direct CLIP and single-output contract until explicit conversion",async({page},info)=>{
  const sample=JSON.parse(readFileSync("../backend/app/domains/media/samples/comfy-text.json","utf8"));
  const old={base_url:"http://localhost:8188",workflow:sample.workflow,values:{...sample.values,clip_skip:-1}};
  const audit=await fixtures(page,info.project.name==="static",{comfy:old});await page.goto(`/agents/${character}?tab=settings`);
  const panel=page.getByRole("region",{name:"SNS 이미지 생성 설정"});await expect(panel.getByRole("button",{name:"기존 설정을 새 형식으로 전환"})).toBeEnabled();
  expect(audit.writes).toHaveLength(0);await panel.getByRole("button",{name:"설정 저장",exact:true}).click();await expect.poll(()=>audit.writes.length).toBe(1);
  expect(audit.writes[0].options).toEqual(old);await panel.getByRole("button",{name:"기존 설정을 새 형식으로 전환"}).click();
  await panel.getByRole("button",{name:"설정 저장",exact:true}).click();await expect.poll(()=>audit.writes.length).toBe(2);
  const converted=audit.writes[1].options as Record<string,unknown>;expect(converted.options_schema_version).toBe(2);expect(converted.clip_skip_value_mode).toBe("node_value");expect(converted.values).toEqual(old.values);
});

test("Comfy late analysis cannot overwrite the newly selected provider profile",async({page},info)=>{
  await fixtures(page,info.project.name==="static",{comfy:placeholderOptions()});let release:()=>void=()=>{};const gate=new Promise<void>(resolve=>release=resolve);let waiting=false;
  await page.route("**/media/comfy-workflows/analyze",async route=>{waiting=true;await gate;try{await json(route,{detail:"comfy_json_invalid"},422);}catch{/* The scoped request was aborted. */}});
  try {
    await page.goto(`/agents/${character}?tab=settings`);await expect.poll(()=>waiting).toBe(true);
    const panel=page.getByRole("region",{name:"SNS 이미지 생성 설정"});await panel.getByRole("combobox",{name:"이미지 서비스"}).selectOption("nanogpt");release();
    await expect(panel.getByRole("combobox",{name:"이미지 모델"})).toHaveValue("krea-v2/turbo");await expect(panel.getByLabel("불러온 API workflow JSON")).toHaveCount(0);
    await expect(panel.getByRole("alert")).toHaveCount(0);
  } finally {release();}
});

test("World Comfy settings use the shared editor and preserve scope during raw correction and save",async({page},info)=>{
  const state=await installWorldCharacterManagementFixture(page,info.project.name==="static",String(info.project.use.baseURL));
  state.management.credentials.set(`${FEED_WORLD}:${WORLD_AGENT}:image`,{purpose:"image",provider:"comfyui",model:"workflow",thinking_level:null,has_key:false,has_partner_key:false,revision:1,configuration_revision:1});
  const policy={world_id:FEED_WORLD,world_character_id:WORLD_AGENT,revision:1,generation_limit:20,vision_limit:10,generation_enabled:false,vision_enabled:false,generation_settings:{appearance:"",style:"",negative:"",reference_enabled:false,reference_asset_id:null,profiles:{"comfyui:workflow":{options:placeholderOptions(),connection:null}}},generation_usage:0,vision_usage:0,timezone:"Asia/Seoul",reset_at:"2026-10-09T15:00:00Z"};
  let written:Record<string,unknown>|null=null;
  await page.route(info.project.name==="static"?"http://127.0.0.1:8080/api/v1/**":"**/api/backend/**",async route=>{
    const path=new URL(route.request().url()).pathname.replace(/^\/api\/(backend|v1)/,"");
    if(path==="/media/comfy-workflows/analyze") {try{const data=route.request().postDataJSON();return json(route,viewAnalysis(data.source_json,data.input_mode));}catch{return json(route,{detail:"comfy_json_invalid"},422);}}
    if(path===`/worlds/${FEED_WORLD}/world-characters/${WORLD_AGENT}/image-policy`){if(route.request().method()==="PATCH"){written=route.request().postDataJSON();Object.assign(policy,written,{revision:2});}return json(route,policy);}
    return route.fallback();
  });
  await page.goto(`${worldCharacterRoute()}?view=settings`);const raw=page.getByLabel("불러온 API workflow JSON",{exact:true});await expect(raw).toBeVisible();
  await raw.fill("{invalid");await expect(page.getByRole("button",{name:"이미지 설정 저장",exact:true})).toBeDisabled();await expect(raw).toHaveValue("{invalid");
  await raw.fill(JSON.stringify({...placeholderGraph,"ref":{class_type:"Base64Image",inputs:{data:"%char_avatar%"}}}));await expect(page.getByText("JSON 분석 완료",{exact:true})).toBeVisible();await page.getByLabel("model · 값",{exact:true}).fill("world-only.ckpt");
  const reference=page.getByRole("checkbox",{name:"참조 이미지 사용"});await expect(reference).toBeEnabled();await expect(reference).not.toBeChecked();
  await page.getByRole("button",{name:"이미지 설정 저장",exact:true}).click();await expect.poll(()=>written).not.toBeNull();
  expect((policy.generation_settings.profiles["comfyui:workflow"].options).values.model).toBe("world-only.ckpt");expect(written!.expected_revision).toBe(1);expect(state.management.providerCalls).toEqual([]);
});

test("Comfy accepted warning stays visible with safe details and causes no retry submission",async({page},info)=>{
  await fixtures(page,info.project.name==="static");let submissions=0;
  const post={...uiDManualPost({id:"comfy-warning-post",title:"수락된 작업",body:"서버가 이미지를 반환했어요"}),media:[{id:9,post_id:"comfy-warning-post",asset_id:"generated-warning",url:"/api/v1/media/assets/generated-warning/content",source_kind:"generated",alt_text:"생성 이미지",media_type:"image",byte_size:80,width:1,height:1,created_at:"2026-10-09T00:00:00Z"}]};
  await page.route(info.project.name==="static"?"http://127.0.0.1:8080/api/v1/**":"**/api/backend/**",async route=>{
    const path=new URL(route.request().url()).pathname.replace(/^\/api\/(backend|v1)/,"");
    if(path.endsWith("/manual-social/feed"))return json(route,uiDManualFeed([post]));
    if(path.endsWith("/image-generation")){if(route.request().method()!=="GET")submissions++;return json(route,{job_id:9,post_id:post.id,status:"succeeded",reason:null,attempt_count:1,cancellable:false,retryable:false,provider_diagnostic:{kind:"warning",stage:"submission",messages:[{node_id:"9",message:"<script>safe text</script>"}],truncated:true}});}
    return route.fallback();
  });
  await page.goto(`/worlds/${uiDWorld().world_id}/feed`);await page.getByText("ComfyUI 실행 안내",{exact:true}).click();await expect(page.getByText("9 · <script>safe text</script>",{exact:true})).toBeVisible();
  await expect(page.getByText("오류 정보 일부가 생략되었습니다.",{exact:true})).toBeVisible();await expect(page.getByRole("button",{name:"이미지 생성 다시 시도"})).toHaveCount(0);expect(submissions).toBe(0);
});

test("World recognition is separate, defaults medium, and usage retains character scope",async({page},info)=>{
  const state=await installWorldCharacterManagementFixture(page,info.project.name==="static",String(info.project.use.baseURL));await page.goto(`${worldCharacterRoute()}?view=settings`);
  const panel=page.getByRole("region",{name:"SNS·Chat 이미지 인식 API key"});
  await expect(panel.getByRole("combobox",{name:"Google AI 모델"})).toHaveValue("google:gemini-3.1-flash-lite:medium");await expect(panel.getByRole("checkbox",{name:"SNS·Chat 이미지 인식 사용"})).not.toBeChecked();
  await expect(panel.getByText("오늘 인식 3 / 10회",{exact:true})).toBeVisible();
  const generation=page.getByRole("region",{name:"SNS 게시글 이미지 생성"});await expect(generation.getByText("오늘 생성 2 / 20회",{exact:true})).toBeVisible();
  await panel.getByLabel("새 API key",{exact:true}).fill("fake-browser-only");await panel.getByRole("button",{name:"모델 저장",exact:true}).click();
  await expect.poll(()=>state.management.writes.filter(write=>write.path.endsWith("/credentials/vision")).length).toBe(1);
  const credential=state.management.writes.find(write=>write.path.endsWith("/credentials/vision"))!;
  expect(credential.body.model).toBe("gemini-3.1-flash-lite");expect(credential.body.thinking_level).toBe("medium");
  await panel.getByRole("spinbutton",{name:"캐릭터 일일 인식 상한"}).fill("4");await panel.getByRole("button",{name:"인식 설정 저장",exact:true}).click();
  await expect.poll(()=>state.management.writes.filter(write=>write.path.endsWith("/image-policy")).length).toBe(1);
  const policy=state.management.writes.find(write=>write.path.endsWith("/image-policy"))!;expect(policy.body.vision_enabled).toBe(false);expect(policy.body.vision_limit).toBe(4);
  expect(state.management.providerCalls).toEqual([]);
  expect(await page.evaluate(()=>Object.values(localStorage).join(""))).not.toContain("fake-browser-only");
});

for (const [extension,mime] of [["png","image/png"],["jpg","image/jpeg"],["webp","image/webp"]]) {
test(`${extension} reference uploads preserve previews and removing a draft makes no analysis request`,async({page},info)=>{
  const audit=await fixtures(page,info.project.name==="static");await page.goto(`/agents/${character}?tab=settings`);const panel=page.getByRole("region",{name:"SNS 이미지 생성 설정"});
  await page.route(info.project.name==="static"?"http://127.0.0.1:8080/api/v1/**":"**/api/backend/**",async route=>{
    if(new URL(route.request().url()).pathname.endsWith("/content"))return route.fulfill({contentType:mime,body:readFileSync(`../backend/tests/image_integration/fixtures/pixels.${extension}`)});
    return route.fallback();
  });
  await panel.getByLabel("첨부 이미지 선택").setInputFiles({name:`fixture.${extension}`,mimeType:mime,buffer:readFileSync(`../backend/tests/image_integration/fixtures/pixels.${extension}`)});
  await expect(panel.getByRole("img",{name:"선택한 첨부 이미지 미리보기"})).toBeVisible();expect(audit.writes.length).toBe(1);
  expect(audit.writes[0].content_type).toBe(mime);
  await expect.poll(()=>panel.getByRole("img").evaluate((element)=>(element as HTMLImageElement).naturalWidth)).toBe(18);
  await panel.getByRole("button",{name:"사진 제거"}).click();await expect(panel.getByRole("img")).toHaveCount(0);
});
}


const syntheticFile={name:"fixture.png",mimeType:"image/png",buffer:Buffer.from("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=","base64")};
test("chat preview stays selected when recognition is unavailable until explicit removal",async({page},info)=>{
  const audit=await fixtures(page,info.project.name==="static");await page.goto(`/worlds/${uiDWorld().world_id}/chat/thread-image`);
  const send=page.getByRole("button",{name:"메시지 보내기"});await expect(send).toBeDisabled();
  await page.getByLabel("첨부 이미지 선택").setInputFiles(syntheticFile);
  await expect(page.getByRole("img",{name:"선택한 첨부 이미지 미리보기"})).toBeVisible();
  await expect(page.getByRole("alert").filter({hasText:"이미지를 인식할 수 없습니다"})).toBeVisible();
  await expect(send).toBeDisabled();await page.getByPlaceholder("메시지를 입력하세요").fill("이 텍스트를 유지");await expect(send).toBeDisabled();
  expect(audit.writes).toHaveLength(1);expect(audit.writes[0].scope_kind).toBe("thread");expect(audit.writes[0].scope_id).toBe("thread-image");
  await page.getByRole("button",{name:"사진 제거"}).click();await expect(send).toBeEnabled();await expect(page.getByPlaceholder("메시지를 입력하세요")).toHaveValue("이 텍스트를 유지");
});
test("manual SNS submission preserves title body and selected asset without recognition",async({page},info)=>{
  const audit=await fixtures(page,info.project.name==="static");await page.goto(`/worlds/${uiDWorld().world_id}/feed`);
  for (const width of [360, 390, 436]) {
    await page.setViewportSize({width,height:880});
    const composer=page.locator("#world-owner-composer");
    await expect(composer).toBeVisible();
    const composerBox=await composer.boundingBox();
    expect(composerBox).not.toBeNull();
    for (const control of [page.getByLabel("제목",{exact:true}),page.getByLabel("내용",{exact:true}),page.getByRole("button",{name:"사진 첨부",exact:true}),page.getByRole("button",{name:"게시하기",exact:true})]) {
      await expect(control).toBeVisible();
      const box=await control.boundingBox();
      expect(box).not.toBeNull();
      expect(box!.x).toBeGreaterThanOrEqual(composerBox!.x-1);
      expect(box!.x+box!.width).toBeLessThanOrEqual(composerBox!.x+composerBox!.width+1);
    }
    expect((await page.getByRole("button",{name:"게시하기",exact:true}).boundingBox())!.height).toBeLessThanOrEqual(60);
  }
  await page.getByLabel("제목",{exact:true}).fill("사용자 사진 제목");await page.getByLabel("내용",{exact:true}).fill("사용자가 쓴 본문");
  await page.getByLabel("첨부 이미지 선택").setInputFiles(syntheticFile);
  await expect(page.getByRole("img",{name:"선택한 첨부 이미지 미리보기"})).toBeVisible();
  await page.getByRole("button",{name:"게시하기",exact:true}).click();
  await expect.poll(()=>audit.writes.length).toBe(2);
  expect(audit.writes[1]).toEqual({title:"사용자 사진 제목",body:"사용자가 쓴 본문",attachment_asset_id:"draft-1"});
  await expect(page.getByRole("img",{name:"선택한 첨부 이미지 미리보기"})).toHaveCount(0);
});

for (const [extension,mime] of [["png","image/png"],["jpg","image/jpeg"],["webp","image/webp"]]) {
test(`completed ${extension} generation displays original authenticated pixels without resubmission`,async({page},info)=>{
  const staticShell=info.project.name==="static";
  await fixtures(page,staticShell);
  await page.addInitScript(()=>{
    const audit={types:[] as string[],created:[] as string[],revoked:[] as string[]};
    Object.assign(window,{__imageFormatAudit:audit});
    const create=URL.createObjectURL.bind(URL), revoke=URL.revokeObjectURL.bind(URL);
    URL.createObjectURL=(value)=>{const url=create(value);if(value instanceof Blob){audit.types.push(value.type);audit.created.push(url);}return url;};
    URL.revokeObjectURL=(url)=>{audit.revoked.push(url);revoke(url);};
  });
  let feedReads=0,jobReads=0,generationWrites=0;
  const post=uiDManualPost({id:"image-progress-post",title:"생성 장면",body:"새 사진이 붙는 글"});
  await page.route(staticShell?"http://127.0.0.1:8080/api/v1/**":"**/api/backend/**",async route=>{
    const request=route.request();const path=new URL(request.url()).pathname.replace(/^\/api\/(backend|v1)/,"");
    if(path.includes("/image-generation")&&request.method()!=="GET")generationWrites++;
    if(path.endsWith("/manual-social/feed")){
      feedReads++;
      const media=jobReads>=2?[{id:7,media_type:"image",url:"/api/v1/media/assets/generated-one/content",alt_text:"새로 생성된 사진",source_kind:"generated",model:"z-image-turbo",prompt_hash:"a".repeat(64),byte_size:80,width:18,height:24,created_at:"2026-09-30T00:00:00Z"}]:[];
      return json(route,uiDManualFeed([{...post,media}]));
    }
    if(path.endsWith("/image-generation")){
      expect(path).toBe(`/media/worlds/${uiDWorld().world_id}/posts/${post.id}/image-generation`);
      jobReads++;
      return json(route,{job_id:7,status:jobReads===1?"queued":"succeeded",reason:null,attempt_count:1,model:"z-image-turbo",reference_source:null,cancellable:jobReads===1,retryable:false});
    }
    if(path==="/media/assets/generated-one/content")return route.fulfill({contentType:mime,body:readFileSync(`../backend/tests/image_integration/fixtures/pixels.${extension}`)});
    return route.fallback();
  });
  await page.goto(`/worlds/${uiDWorld().world_id}/feed`);
  await expect(page.getByText("이미지 생성 대기",{exact:true})).toBeVisible();
  await expect(page.getByRole("img",{name:"새로 생성된 사진"})).toBeVisible();
  await expect(page.getByLabel("게시글 이미지 생성 상태")).toHaveCount(0);
  expect(feedReads).toBe(2);expect(jobReads).toBe(3);expect(generationWrites).toBe(0);
  const image=page.getByRole("img",{name:"새로 생성된 사진"});
  await expect.poll(()=>image.evaluate((element)=>[ (element as HTMLImageElement).naturalWidth,(element as HTMLImageElement).naturalHeight ])).toEqual([18,24]);
  expect(await page.evaluate(()=>Reflect.get(window,"__imageFormatAudit").types)).toContain(mime);
  await page.reload();await expect(image).toBeVisible();
  await expect.poll(()=>image.evaluate((element)=>(element as HTMLImageElement).naturalWidth)).toBe(18);
  const previousBlob=await image.getAttribute("src");
  await page.locator("[data-feed-header]").getByRole("link",{name:"Angmoo",exact:true}).click();
  if(staticShell) {
    // Static navigation unloads the document; its blob URLs expire with it.
    await expect.poll(()=>page.evaluate(async url=>{try{await fetch(url!);return false;}catch{return true;}},previousBlob)).toBe(true);
  } else {
    await expect.poll(()=>page.evaluate(()=>Reflect.get(window,"__imageFormatAudit").revoked.length)).toBeGreaterThan(0);
  }
  expect(generationWrites).toBe(0);
});
}

test("NovelAI missing local validation resource prevents activation while preserving editable settings",async({page},info)=>{
  const staticShell=info.project.name==="static";
  const audit=await fixtures(page,staticShell);
  await page.route(staticShell?"http://127.0.0.1:8080/api/v1/**":"**/api/backend/**",async route=>{
    const path=new URL(route.request().url()).pathname.replace(/^\/api\/(backend|v1)/,"");
    if(path==="/media/catalog")return json(route,{models:models.map(model=>({...model,...(model.provider==="novelai"?{availability:"local_validation_unavailable",prompt_validation:{state:"unavailable",exact_verified:false,generation_available:false,reason:"novelai_tokenizer_unavailable"}}:{})})),quota_timezone:"Asia/Seoul",upload_limit_bytes:10485760});
    return route.fallback();
  });
  await page.goto(`/agents/${character}?tab=settings`);
  const panel=page.getByRole("region",{name:"SNS 이미지 생성 설정"});
  await expect(panel.getByRole("checkbox",{name:"새 Routine 게시글 자동 이미지 생성 허용"})).toBeDisabled();
  await expect(panel.getByText(/입력 검사에 필요한 파일을 확인할 수 없어/)).toBeVisible();
  await expect(panel.getByRole("status").filter({hasText:/^연결 상태:/})).toHaveText(/^연결 상태:\s*입력 검사 준비 필요 · 생성 비활성화$/);
  await panel.getByLabel("외형 (선택)").fill("검증 이후 사용할 외형");
  await panel.getByRole("button",{name:"설정 저장",exact:true}).click();
  await expect.poll(()=>audit.writes.length).toBe(1);
  expect(audit.writes[0].auto_enabled).toBe(false);
  expect(audit.writes[0].appearance).toBe("검증 이후 사용할 외형");
  await panel.getByText(/입력 검사에 필요한 파일을 확인할 수 없어/).scrollIntoViewIfNeeded();
});

test("NovelAI local preflight permits activation without falsely certifying exact server validation",async({page},info)=>{
  const staticShell=info.project.name==="static";
  const audit=await fixtures(page,staticShell);
  await page.route(staticShell?"http://127.0.0.1:8080/api/v1/**":"**/api/backend/**",async route=>{
    const path=new URL(route.request().url()).pathname.replace(/^\/api\/(backend|v1)/,"");
    if(path==="/media/catalog")return json(route,{models:models.map(model=>({...model,...(model.provider==="novelai"?{prompt_validation:{state:"local_preflight",exact_verified:false,generation_available:true,resource_verified:true}}:{})})),quota_timezone:"Asia/Seoul",upload_limit_bytes:10485760});
    return route.fallback();
  });
  await page.goto(`/agents/${character}?tab=settings`);
  const panel=page.getByRole("region",{name:"SNS 이미지 생성 설정"});
  const enabled=panel.getByRole("checkbox",{name:"새 Routine 게시글 자동 이미지 생성 허용"});
  await expect(enabled).toBeEnabled();
  await expect(panel.getByText(/실제 서비스와의 정확한 일치는 미확인/)).toBeVisible();
  await panel.getByLabel("이미지 API 키",{exact:true}).fill("synthetic-only-key");
  await panel.getByLabel("캐릭터 일일 생성 시도 상한",{exact:true}).fill("2");
  await enabled.check();
  await panel.getByRole("button",{name:"연결·입력 확인 및 저장",exact:true}).click();
  await expect(panel.getByRole("status").filter({hasText:/^연결 상태:/})).toHaveText(/^연결 상태:\s*Opus 혜택 확인됨$/);
  expect(audit.writes).toHaveLength(1);
  expect(audit.writes[0].auto_enabled).toBe(true);
  expect(audit.writes[0].reference_enabled).toBe(false);
  await expect(enabled).toBeChecked();
  await expect(panel.getByText(/실제 서비스와의 정확한 일치는 미확인/)).toBeVisible();
});

test("saved reference state shows actual source preference and the available generation path",async({page},info)=>{
  const staticShell=info.project.name==="static";
  const audit=await fixtures(page,staticShell);
  let state={preferred:true,applied:false,source:"none",status:"missing",reason:"source_missing",generation_path:"text",scene_only:true};
  await page.route(staticShell?"http://127.0.0.1:8080/api/v1/**":"**/api/backend/**",async route=>{
    const path=new URL(route.request().url()).pathname.replace(/^\/api\/(backend|v1)/,"");
    if(path.endsWith("/generation-settings")&&route.request().method()==="GET")return json(route,{...audit.getSettings(),provider:"nanogpt",model:"krea-v2/turbo",active_profile:{reference_enabled:true,options:{}},reference_state:state});
    return route.fallback();
  });
  await page.goto(`/agents/${character}?tab=settings`);
  const status=page.getByLabel("저장된 참조 적용 상태");
  await expect(status.getByRole("status")).toHaveText(/^저장된 참조 선호:\s*ON\s*· 실제 출처:\s*없음$/);
  await expect(status).toContainText("이번 게시글의 장면만으로 생성");
  for(const [source,label] of [["profile","프로필 이미지"],["card","캐릭터 카드 이미지"],["override","사용자 지정 이미지"]]){
    state={...state,source,applied:true,status:"available",reason:"",generation_path:"reference",scene_only:false};
    await page.reload();await expect(status.getByRole("status")).toHaveText(new RegExp(`^저장된 참조 선호:\\s*ON\\s*· 실제 출처:\\s*${label}$`));
    await expect(status).not.toContainText("이번 게시글의 장면만으로 생성");
  }
  state={...state,source:"none",applied:false,status:"missing",reason:"comfy_reference_or_text_path_required",generation_path:"unavailable"};
  await page.reload();await expect(status).toContainText("사용할 이미지와 텍스트 경로가 없습니다");
  await expect(status.getByRole("alert")).toContainText("검증된 텍스트 workflow가 필요합니다");
  expect(audit.writes).toHaveLength(0);
});

function recoveryChat(content:string,state:"waiting"|"failed"){
  const role={world_character_id:"wc-image",character_id:character,display_name:"이미지 친구",handle:"image_friend",avatar_url:null,banner_url:null,role_key:null,control_mode:"autonomous",profile_capability:"available"};
  const user={id:41,thread_id:"thread-image",role:"user",content,attachment:{asset_id:"original-photo",url:"/api/v1/media/assets/original-photo/content",analysis_state:"pending"},model:null,status:"ok",error_code:null,created_at:"2026-09-30T00:00:00Z"};
  const request={protocol_version:"chat-generation-stream.v1",request_id:"image-failed",request_scope_hash:"a".repeat(64),generation_id:"image-generation",attempt_number:1,response_slot_id:"image-slot",state:state==="waiting"?"accepted":"failed",route:null,retryable:state==="failed",failure_class:state==="failed"?"image_interpretation_unavailable":null,last_accepted_sequence:-1,user_message:user,assistant_message:null,response_metadata:{},image_analysis_state:state,can_retry_without_image:state==="failed"&&Boolean(content)};
  const thread={id:"thread-image",world_id:uiDWorld().world_id,requester:{...role,world_character_id:"wc-owner",control_mode:"owner_controlled"},responding:role,selected_model:"gemini-3.1-flash-lite",selected_thinking_level:"high",default_model:"gemini-3.1-flash-lite",default_thinking_level:"high",model_binding_mode:"default",last_message_at:user.created_at,created_at:user.created_at,latest_message:user,messages:[user],evidence_summaries:[]};
  return {user,request,thread};
}

for(const content of ["", "사진 없이도 이 질문에 답해 줘."]){
  test(`accepted analysis failure offers explicit text recovery only with original text ${Boolean(content)}`,async({page},info)=>{
    const staticShell=info.project.name==="static";
    await fixtures(page,staticShell);
    const data=recoveryChat(content,"failed");
    const writes:Record<string,unknown>[]=[];
    let completed=false;
    const retried={...data.request,request_id:"image-text-only",generation_id:"image-text-generation",attempt_number:2,state:"accepted",failure_class:null,retryable:false,image_analysis_state:"excluded",can_retry_without_image:false};
    const assistant={...data.user,id:42,role:"assistant",content:"사진 없이 원문에 답한 응답",attachment:null};
    await page.route(staticShell?"http://127.0.0.1:8080/api/v1/**":"**/api/backend/**",async route=>{
      const path=new URL(route.request().url()).pathname.replace(/^\/api\/(backend|v1)/,"");
      if(path.endsWith("/requests/latest"))return json(route,{response_request:data.request});
      if(path.endsWith("/thread-image"))return json(route,{...data.thread,messages:completed?[data.user,assistant]:[data.user]});
      if(path.endsWith("/requests/image-text-only"))return json(route,{...retried,state:"committed",last_accepted_sequence:2,assistant_message:assistant});
      if(path.endsWith("/retry")){
        writes.push(route.request().postDataJSON());
        return json(route,{outcome:"accepted",user_message:data.user,response_request:retried});
      }
      if(path.endsWith("/image-text-only/events")){
        completed=true;
        const events=[{sequence:0,type:"accepted",payload:{}},{sequence:1,type:"delta",payload:{text:assistant.content}},{sequence:2,type:"completed",payload:{}}].map(event=>({protocol_version:retried.protocol_version,request_id:retried.request_id,request_scope_hash:retried.request_scope_hash,generation_id:retried.generation_id,attempt_number:retried.attempt_number,...event}));
        return route.fulfill({contentType:"application/x-ndjson",body:events.map(event=>JSON.stringify(event)).join("\n")+"\n"});
      }
      return route.fallback();
    });
    await page.goto(`/worlds/${uiDWorld().world_id}/chat/thread-image`);
    await expect(page.getByText("사진을 인식하지 못했어요.", {exact:true})).toBeVisible();
    const recovery=page.getByRole("button",{name:"사진 없이 이 텍스트로 진행"});
    if(!content){await expect(recovery).toHaveCount(0);expect(writes).toHaveLength(0);return;}
    await expect(recovery).toBeVisible();expect(writes).toHaveLength(0);
    await recovery.click();await expect(page.getByText(assistant.content,{exact:true})).toBeVisible();
    await expect(page.locator("[data-response-slot='image-slot']")).toHaveCount(0);
    expect(writes).toHaveLength(1);expect(writes[0]).toMatchObject({failed_request_id:"image-failed",exclude_attachment:true});
    await expect(page.getByText(content,{exact:true})).toHaveCount(1);
    await expect(page.getByRole("img",{name:"대화에 첨부한 이미지"})).toBeVisible();
  });
}

test("Chat typing shows one pending indicator before any image stream result",async({page},info)=>{
  const staticShell=info.project.name==="static";
  await fixtures(page,staticShell);const data=recoveryChat("사진을 봐 줘.","waiting");
  let release:(()=>void)|undefined;
  const gate=new Promise<void>(resolve=>{release=resolve;});
  await page.route(staticShell?"http://127.0.0.1:8080/api/v1/**":"**/api/backend/**",async route=>{
    const path=new URL(route.request().url()).pathname.replace(/^\/api\/(backend|v1)/,"");
    if(path.endsWith("/requests/latest"))return json(route,{response_request:data.request});
    if(path.endsWith("/thread-image"))return json(route,data.thread);
    if(path.endsWith("/events")){await gate;return route.fulfill({status:204});}
    return route.fallback();
  });
  try{
    await page.goto(`/worlds/${uiDWorld().world_id}/chat/thread-image`);
    await expect(page.getByText("입력 중",{exact:true})).toBeVisible();
    await expect(page.getByText("사진을 인식하고 있어요. 인식이 끝나면 답장을 만들어요.",{exact:true})).toHaveCount(0);
    await expect(page.getByRole("button",{name:"사진 없이 이 텍스트로 진행"})).toHaveCount(0);
  }finally{release?.();}
});
