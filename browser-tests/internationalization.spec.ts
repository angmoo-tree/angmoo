import { test, expect, type Browser, type Page, type APIRequestContext, type TestInfo } from "@playwright/test";

const BACKEND = "http://127.0.0.1:18399";
const CONTROL = {"x-fixture-control": "synthetic-only"};
async function state(request: APIRequestContext) {
  const response=await request.get(`${BACKEND}/__fixture/state`, {headers:CONTROL});
  expect(response.ok()).toBeTruthy();
  return response.json();
}
async function open(browser: Browser, info: TestInfo, locale: string, timezoneId: string, viewport={width:1280,height:900}) {
  const context=await browser.newContext({locale,timezoneId,viewport, reducedMotion:"reduce"});
  await context.addInitScript(() => {
    window.__ANGMOO_RUNTIME_CONFIG__ = {apiBaseUrl:"http://127.0.0.1:18399", graphProvider:"ladybug", profile:"tauri-static"};
  });
  const page=await context.newPage(), errors:string[]=[];
  page.on("pageerror", err=>errors.push(err.message));
  page.on("console", msg=>{if(/hydration|did not match/i.test(msg.text()))errors.push(msg.text());});
  await page.goto(`${info.project.use.baseURL}/settings`);
  const section=page.locator("[data-language-settings]");
  await expect(section.getByRole("button", {name:"Korean",exact:true})).toBeEnabled();
  await expect(section.getByRole("button", {name:"English",exact:true})).toBeEnabled();
  await expect(section).toContainText(timezoneId);
  return {context,page,section,errors};
}
test.beforeEach(async({request})=>{
  const reset=await request.post(`${BACKEND}/__fixture/reset`, {headers:CONTROL});
  expect(reset.ok()).toBeTruthy();
});

for(const [locale,zone,initial] of [["ko-KR","Asia/Seoul","ko"],["en-US","America/New_York","en"],["ja-JP","Asia/Tokyo","en"],["ar-AE","Europe/London","en"]]) {
  test(`real SQLite auth: ${locale}; saved UI independent of locale and time zone`,async({browser,request},info)=>{
    const {context,page,section,errors}=await open(browser,info,locale,zone);
    try {
      await expect(page.locator("html")).toHaveAttribute("lang",initial);
      const before=await state(request);
      expect(before.environment.memory_search_locale).toBe(locale);
      for(const language of ["ko","en"] as const) {
        await section.getByRole("button",{name:language==="ko"?"Korean":"English",exact:true}).click();
        await expect.poll(async()=>(await state(request)).ui_language).toBe(language);
        await expect(page.locator("html")).toHaveAttribute("lang",language);
        await expect(section.getByRole("button",{name:"Korean",exact:true})).toHaveAttribute("aria-pressed",String(language==="ko"));
        const after=await state(request);
        expect(after.environment.memory_search_locale).toBe(locale);
        expect(after.environment.timezone).toBe(zone);
        expect(after.environment.environment_revision).toBe(before.environment.environment_revision);
      }
      await page.reload();
      await expect(page.locator("html")).toHaveAttribute("lang","en");
      await expect(page.getByRole("navigation", {name:"Main mobile navigation"})).toContainText("Home");
      await expect(page.getByRole("navigation", {name:"Main mobile navigation"})).not.toContainText("내 캐릭터");
      await expect(section).toContainText(locale);
      await expect(page.getByText("Synthetic User · 原文 A-17",{exact:true}).first()).toBeVisible();
      expect((await state(request)).display_name).toBe("Synthetic User · 原文 A-17");
      expect(errors).toEqual([]);
      await page.screenshot({path:info.outputPath(`settings-${locale}.png`), fullPage:true});
    } finally {await context.close();}
  });
}

test("two active clients: first detector owns lease, later client inherits only after expiry",async({browser,request},info)=>{
  const first=await open(browser,info,"ja-JP","America/New_York");
  const context=await browser.newContext({locale:"ar-AE",timezoneId:"Europe/London"});
  await context.addInitScript(()=>{window.__ANGMOO_RUNTIME_CONFIG__={apiBaseUrl:"http://127.0.0.1:18399",graphProvider:"ladybug",profile:"tauri-static"};});
  const second=await context.newPage();
  try {
    await second.goto(`${info.project.use.baseURL}/settings`);
    await expect(second.locator("[data-language-settings]")).toContainText("America/New_York");
    expect((await state(request)).environment.memory_search_locale).toBe("ja-JP");
    await first.context.close();
    await request.post(`${BACKEND}/__fixture/expire-lease`,{headers:CONTROL});
    await second.evaluate(()=>window.dispatchEvent(new Event("languagechange")));
    await expect.poll(async()=>(await state(request)).environment.memory_search_locale).toBe("ar-AE");
    await expect(second.locator("[data-language-settings]")).toContainText("Europe/London");
  } finally {await context.close();await first.context.close();}
});

test("real environment HTTP: auth, CSRF, revision and invalid detector protect saved values",async({browser,request},info)=>{
  const {context,page}=await open(browser,info,"en-US","America/New_York");
  try {
    const before=await state(request);
    const statuses=await page.evaluate(async()=>{
      const staticProfile=location.port==="3362";
      const url=staticProfile?"http://127.0.0.1:18399/api/v1/auth/local/environment":"/api/backend/auth/local/environment";
      const headers={"Content-Type":"application/json","X-Angmoo-Frontend-Origin":location.origin};
      const send=(data:unknown)=>fetch(url,{method:"POST",credentials:"include",headers,body:JSON.stringify(data)}).then(r=>r.status);
      return [await send({client_id:"stale-screen-000000",sequence:1,expected_revision:0,preferred_language:"ar-AE",timezone:"UTC"}),
        await send({client_id:"stale-screen-000000",sequence:1,expected_revision:1,preferred_language:"en_US",timezone:"Not/AZone"})];
    });
    expect(statuses).toEqual([409,422]);
    expect((await state(request)).environment).toEqual(before.environment);
    const anonymous=await request.get(`${BACKEND}/api/v1/auth/local/environment`,{headers:{"X-Angmoo-Frontend-Origin":String(info.project.use.baseURL)}});
    expect(anonymous.status()).toBe(401);
    const foreign=await context.request.post(`${BACKEND}/api/v1/auth/local/environment`,{headers:{Origin:"https://invalid.example", "X-Angmoo-Frontend-Origin":"https://invalid.example"},data:{}});
    expect(foreign.status()).toBe(403);
  } finally {await context.close();}
});

test("mobile English settings: original data, 44px controls, keyboard, 200% text and no overflow",async({browser,request},info)=>{
  const {context,page,section,errors}=await open(browser,info,"en-US","America/New_York",{width:390,height:844});
  try {
    await section.getByRole("button",{name:"English",exact:true}).click();
    await expect.poll(async()=>(await state(request)).ui_language).toBe("en");
    for(const name of ["Korean","English"]) {
      const button=section.getByRole("button",{name,exact:true});
      const box=await button.boundingBox(); expect(box!.height).toBeGreaterThanOrEqual(44); expect(box!.width).toBeGreaterThanOrEqual(44);
    }
    await section.getByRole("button",{name:"Korean",exact:true}).focus();
    await page.keyboard.press("Tab");
    await expect(section.getByRole("button",{name:"English",exact:true})).toBeFocused();
    await page.addStyleTag({content:"html {font-size:200% !important;}"});
    expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1)).toBeTruthy();
    await expect(section).toContainText("America/New_York");
    await expect(page.locator("body")).not.toContainText("Asia/Seoul 기준");
    expect(errors).toEqual([]);
  } finally {await context.close();}
});

test("mock-only failure coverage: save 409 retains selected UI and safe translated state",async({browser},info)=>{
  const {context,page,section}=await open(browser,info,"ko-KR","Asia/Seoul");
  try {
    await page.route(/\/auth\/me\/preferences$/,route=>route.fulfill({status:409,contentType:"application/json",body:JSON.stringify({detail:"raw-provider-private-token-must-not-display"})}));
    await section.getByRole("button",{name:"English",exact:true}).click();
    await expect(section).toContainText("언어를 저장하지 못했습니다");
    await expect(page.locator("html")).toHaveAttribute("lang","ko");
    await expect(page.locator("body")).not.toContainText("raw-provider-private");
  } finally {await context.close();}
});

test("real routes: saved English, translated navigation and original records survive direct entry", async({browser,request},info) => {
  const {context,page,section,errors}=await open(browser,info,"en-US","Europe/London");
  try {
    await section.getByRole("button",{name:"English",exact:true}).click();
    await expect.poll(async()=>(await state(request)).ui_language).toBe("en");
    const supported = ["/", "/agents", "/agents/new", "/posts", "/memory", "/studio"];
    const nextOnly = ["/notifications", "/messages", "/search"];
    for (const route of [...supported, ...nextOnly]) {
      await page.goto(`${info.project.use.baseURL}${route}`);
      await expect(page.locator("html")).toHaveAttribute("lang","en");
      if (["/", "/agents", "/agents/new", "/posts"].includes(route))
        await expect(page.getByRole("navigation",{name:"Main mobile navigation"})).toContainText("Settings");
      if (route === "/memory") await expect(page.getByRole("link", {name:"Back to Home",exact:true})).toBeVisible();
      // A fresh isolated DB can have no runnable memory scope. Both the empty
      // state and an asynchronous default-scope navigation are real outcomes.
      if (route === "/memory") await Promise.race([
        page.waitForURL(/\/memory\?world=/),
        page.getByRole("heading", {name:"No manageable memory scopes",exact:true}).waitFor({state:"visible"}),
      ]);
      if (route === "/studio") await expect(page.getByRole("complementary", {name:"Browse Creator Studio"})).toBeVisible();
      if (info.project.name === "static" && nextOnly.includes(route)) {
        await page.getByRole("heading",{name:"Unsupported Angmoo route."}).waitFor({state:"attached"});
        await info.attach("unsupported-route-layout", {contentType:"application/json", body:JSON.stringify(await page.evaluate(() =>
          ["html","body","main","main > div","h1"].map(selector => {
            const element=document.querySelector(selector); if(!element) return {selector,missing:true};
            const style=getComputedStyle(element); return {selector,rectangle:element.getBoundingClientRect().toJSON(),
              width:style.width,height:style.height,display:style.display,visibility:style.visibility,
              className:element.className,contentVisibility:style.contentVisibility};
          }))) });
        await expect(page.getByRole("heading",{name:"Unsupported Angmoo route."})).toBeVisible();
        const box = await page.getByRole("heading",{name:"Unsupported Angmoo route."}).boundingBox();
        expect(box!.width).toBeGreaterThan(100);
        expect(await page.evaluate(() => document.documentElement.scrollWidth - innerWidth)).toBeLessThanOrEqual(1);
      }
      await expect(page.locator("body")).not.toContainText("Application error");
      await page.waitForTimeout(100);
      const korean = await page.locator("main").innerText();
      expect(korean.match(/[가-힣]+/g) ?? [], `${route}: untranslated product copy`).toEqual([]);
    }
    await page.goto(`${info.project.use.baseURL}/settings`);
    await page.locator("[data-language-settings]").getByRole("button",{name:"Korean",exact:true}).click();
    await expect.poll(async()=>(await state(request)).ui_language).toBe("ko");
    await page.goto(`${info.project.use.baseURL}/posts`);
    await expect(page.getByRole("heading",{name:"피드",exact:true})).toBeVisible();
    await expect(page.getByLabel("피드 범위",{exact:true})).toBeVisible();
    await expect(page.getByRole("button",{name:"게시글",exact:true})).toBeVisible();
    await expect(page.locator("html")).toHaveAttribute("lang","ko");
    expect((await state(request)).display_name).toBe("Synthetic User · 原文 A-17");
    expect(errors).toEqual([]);
  } finally {await context.close();}
});

for (const [locale, expected, detectorFails] of [["ko-KR", "ko", false], ["en-US", "en", false],
  ["ja-JP", "en", false], ["ko-KR", "en", true]] as const) {
  test(`anonymous first visit: ${locale}, detector failure=${detectorFails}`, async ({browser}, info) => {
    const context = await browser.newContext({locale});
    let environmentCalls = 0;
    await context.addInitScript(({fails}) => {
      window.__ANGMOO_RUNTIME_CONFIG__ = {apiBaseUrl:"http://127.0.0.1:18399", graphProvider:"ladybug", profile:"tauri-static"};
      if (fails) for (const property of ["language", "languages"]) Object.defineProperty(navigator, property,
        {get() {throw new Error("synthetic detector unavailable");}});
    }, {fails: detectorFails});
    await context.route(/\/auth\//, async route => {
      const pathname = new URL(route.request().url()).pathname;
      if (pathname.endsWith("/local/environment")) environmentCalls++;
      const bootstrap = pathname.endsWith("/local/bootstrap");
      await route.fulfill({status: bootstrap ? 200 : pathname.endsWith("/me") ? 401 : 409,
        contentType:"application/json", body:JSON.stringify(bootstrap
          ? {state:"unclaimed",installation_id:"synthetic-unclaimed",local_label:null,owner:null,candidates:[]}
          : {detail:"not_authenticated"})});
    });
    const page = await context.newPage(), errors:string[] = [];
    page.on("pageerror", error => errors.push(error.message));
    page.on("console", message => {if (/hydration|did not match/i.test(message.text())) errors.push(message.text());});
    try {
      await page.goto(`${info.project.use.baseURL}/login`);
      await expect(page.locator('[data-local-owner-state="unclaimed"]')).toBeVisible();
      await expect(page.locator("html")).toHaveAttribute("lang", expected);
      await expect(page.getByRole("heading", {name:expected === "ko" ? "이 장치의 owner 준비" : "Prepare device owner", exact:true})).toBeVisible();
      await page.reload();
      await expect(page.locator('[data-local-owner-state="unclaimed"]')).toBeVisible();
      await expect(page.locator("html")).toHaveAttribute("lang", expected);
      expect(environmentCalls).toBe(0);
      expect(errors).toEqual([]);
    } finally {await context.close();}
  });
}

for (const language of ["en", "ko"] as const) {
  test(`${language}: PersonaField native validity and typed handle validation`, async ({browser,request}, info) => {
    const {context,page,section,errors} = await open(browser,info,"en-US","Europe/London");
    const alerts = page.getByRole("main").getByRole("alert");
    try {
      await section.getByRole("button", {name:language === "en" ? "English" : "Korean", exact:true}).click();
      await expect.poll(async () => (await state(request)).ui_language).toBe(language);
      await page.goto(`${info.project.use.baseURL}/agents/new`);
      const next = page.getByRole("button", {name:language === "en" ? "Save and continue" : "저장하고 다음", exact:true});
      await next.click();
      const name = page.getByRole("textbox", {name:language === "en" ? "Name" : "이름", exact:true});
      await name.fill("Original 原文");
      const introduction = page.getByRole("textbox", {name:language === "en" ? "One-line introduction" : "한 줄 소개", exact:true});
      const original = "😀".repeat(501);
      await introduction.fill(original);
      const expected = language === "en" ? "Up to 500 characters allowed. You are 1 over the limit."
        : "500자까지 입력할 수 있습니다. 현재 1자 초과했습니다.";
      await expect(alerts).toHaveText(expected);
      await expect(introduction).toHaveValue(original);
      await expect(introduction).toHaveAttribute("aria-invalid", "true");
      expect(await introduction.evaluate((control:HTMLTextAreaElement) => control.validationMessage)).toBe(expected);
      await introduction.fill("e\u0301😀");
      await expect(alerts).toHaveCount(0);
      expect(await introduction.evaluate((control:HTMLTextAreaElement) => control.validationMessage)).toBe("");
      await page.route(/\/agents\/drafts\/[^/]+$/, route => route.request().method() === "PATCH"
        ? route.fulfill({status:422,contentType:"application/json",body:JSON.stringify({detail:[{
          loc:["body","handle"],type:"string_pattern_mismatch",msg:"PRIVATE credential",input:"PRIVATE input"}]})}) : route.continue());
      await next.click();
      await expect(alerts).toHaveText(language === "en"
        ? "Handles can contain only lowercase letters, numbers, and underscores."
        : "핸들은 영문 소문자, 숫자, 밑줄(_)만 사용할 수 있습니다.");
      await expect(name).toHaveValue("Original 原文");
      await expect(page.locator("body")).not.toContainText("PRIVATE");
      expect(errors).toEqual([]);
    } finally {await context.close();}
  });
}

for (const [code,status,english,korean] of [
  ["world_package_persona_invalid",422,"Personality: 6,001 / 6,000 characters","성격: 6,001 / 6,000자"],
  ["world_package_preparation_failed",503,"The server could not process the import.","서버가 가져오기 요청을 처리하지 못했습니다."],
  ["world_package_manifest_missing",422,"The World Package is missing its manifest.","World Package에 필수 매니페스트가 없습니다."],
] as const) {
  test(`World Package ${code}: safe translated error persists across UI language change`, async ({browser,request}, info) => {
    const {context,page,section,errors} = await open(browser,info,"ko-KR","Asia/Seoul");
    const alerts = page.getByRole("main").getByRole("alert");
    let submissions = 0;
    try {
      await section.getByRole("button", {name:"English",exact:true}).click();
      await expect.poll(async () => (await state(request)).ui_language).toBe("en");
      await page.route(/\/world-package-imports\/stage$/, route => {
        submissions++;
        return route.fulfill({status,contentType:"application/json",body:JSON.stringify({detail:{code,
          fields:[{field:"personality",actual:6001,limit:6000,input:"PRIVATE uploaded text"},
            {field:"character_background",actual:8001,limit:8000}],raw:"PRIVATE credential"}})});
      });
      await page.goto(`${info.project.use.baseURL}/studio/import`);
      await page.locator('input[type="file"]').setInputFiles({name:"synthetic.angmoo-world",mimeType:"application/octet-stream",buffer:Buffer.from("synthetic-only")});
      await expect(alerts).toContainText(english);
      expect(await alerts.innerText()).not.toMatch(/[가-힣]|world_package_|PRIVATE/);
      if (code === "world_package_persona_invalid") await expect(alerts).toContainText("Character background / worldview: 8,001 / 8,000 characters");
      // Use the real preference endpoint and normal auth refresh while the
      // import component stays mounted. No second package request is sent.
      const changed = await page.evaluate(async () => {
        const prefix = location.port === "3362" ? "http://127.0.0.1:18399/api/v1" : "/api/backend";
        const headers = {"Content-Type":"application/json","X-Angmoo-Frontend-Origin":location.origin};
        const owner = await fetch(`${prefix}/auth/me`, {credentials:"include"}).then(response => response.json());
        const response = await fetch(`${prefix}/auth/me/preferences`, {method:"PATCH",credentials:"include",headers,
          body:JSON.stringify({ui_language:"ko",expected_ui_revision:owner.ui_preference_revision})});
        if (response.ok) window.dispatchEvent(new Event("angmoo:auth-changed"));
        return response.status;
      });
      expect(changed).toBe(200);
      await expect(page.locator("html")).toHaveAttribute("lang","ko");
      await expect(alerts).toContainText(korean);
      await expect(alerts).not.toContainText("PRIVATE");
      if (code === "world_package_persona_invalid") await expect(alerts).toContainText("캐릭터 배경·세계관: 8,001 / 8,000자");
      expect(submissions).toBe(1);
      expect(errors).toEqual([]);
    } finally {await context.close();}
  });
}
