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
      // Memory chooses a default scoped URL asynchronously. Complete that
      // navigation before testing the next direct entry.
      if (route === "/memory") await expect(page).toHaveURL(/\/memory\?world=/);
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
    expect((await state(request)).display_name).toBe("Synthetic User · 原文 A-17");
    expect(errors).toEqual([]);
  } finally {await context.close();}
});
