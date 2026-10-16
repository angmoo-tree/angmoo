import { expect, test } from "@playwright/test";
import { installNotificationFixture } from "./world-notifications-fixture";
import { FEED_WORLD, OTHER_FEED_WORLD, feedRoute } from "./world-feed-fixture";
import { uiDWorld } from "./continuity-next-fixture";
import { VISUAL_ENVIRONMENT } from "./fixtures/visual-environment.mjs";

const baseline = process.env.ANGMOO_HOME_BASELINE === "1";
for (const language of ["ko", "en"] as const) test(`retains World DOM and coalesces resume with an active foreign lease (${language})`, async ({ page }, info) => {
  const { state, feed } = await installNotificationFixture(page, info.project.name === "static-export", String(info.project.use.baseURL), language);
  let reads = 0, writes = 0, release: (() => void) | undefined;
  let gate: Promise<void> | undefined;
  const intercept = async (route: import("@playwright/test").Route) => {
    const path = new URL(route.request().url()).pathname.replace(/^\/api\/(backend|v1)/, "");
    if (path === "/auth/local/environment") {
      if (route.request().method() === "POST") { writes++; return route.fulfill({ status: 409, json: { detail: { code: "environment_detector_owned" } } }); }
      return route.fulfill({ json: { ...VISUAL_ENVIRONMENT, lease_token: undefined, preferred_language: language } });
    }
    if (path === "/worlds/mine") {
      reads++; if (gate) await gate;
      return route.fulfill({ json: { schema_version: "local-world-surface-v1", surface: "device_home", items: [uiDWorld(FEED_WORLD), uiDWorld(OTHER_FEED_WORLD)] } });
    }
    return route.fallback();
  };
  await page.route("**/api/backend/**", intercept); await page.route("http://127.0.0.1:8080/api/v1/**", intercept);
  await page.clock.install(); await page.goto("/");
  const icon = page.locator(`a[href^="${feedRoute()}"]`);
  await expect(icon.locator("[data-count-badge]")).toHaveText("99+");
  await icon.focus(); const original = await icon.elementHandle();
  const initialReads = reads, initialEnsures = feed.writes.filter(x => x.path.endsWith("/ensure")).length;
  await page.clock.runFor(300); // a later return, outside the initial event-coalescing window
  // Use a real response barrier, not an arbitrary network sleep.
  gate = new Promise(resolve => { release = resolve; });
  await page.evaluate(() => { window.dispatchEvent(new Event("focus")); document.dispatchEvent(new Event("visibilitychange")); });
  await expect.poll(() => reads).toBeGreaterThan(initialReads);
  if (baseline) {
    await expect(page.getByText(language === "ko" ? "World 앱을 불러오는 중" : "Loading World apps", { exact: true })).toBeVisible();
    expect(await original!.evaluate(el => el.isConnected)).toBe(false);
    expect(writes).toBeGreaterThan(0);
    expect(feed.writes.filter(x => x.path.endsWith("/ensure")).length).toBeGreaterThan(initialEnsures);
  } else {
    await expect(icon).toBeFocused();
    expect(await original!.evaluate(el => el.isConnected)).toBe(true);
    await expect(icon.locator("[data-count-badge]")).toHaveText("99+");
    expect(writes).toBe(0); expect(reads).toBe(initialReads + 1);
    expect(feed.writes.filter(x => x.path.endsWith("/ensure"))).toHaveLength(initialEnsures);
    expect(state.batchIds.every(ids => ids.length === 2)).toBe(true);
    await page.screenshot({path:`../artifacts/device-home-refresh-environment-20261016/${language}-${info.project.name}-retained.png`,fullPage:true});
  }
  release!(); gate = undefined; await expect(icon).toBeVisible();
  await info.attach("request-counts", { body: JSON.stringify({ baseline, reads, writes, initialEnsures, ensures: feed.writes.filter(x => x.path.endsWith("/ensure")).length }), contentType: "application/json" });
});

for (const language of ["ko", "en"] as const) test(`refresh failure, revoked scope and empty success (${language})`, async ({ page }, info) => {
  test.skip(baseline, "Baseline capture uses only the before/after scenario.");
  await installNotificationFixture(page, info.project.name === "static-export", String(info.project.use.baseURL), language);
  let status = 200, schema = "local-world-surface-v1", empty = false;
  const handler = async (route: import("@playwright/test").Route) => {
    if (!new URL(route.request().url()).pathname.endsWith("/worlds/mine")) return route.fallback();
    return route.fulfill({status, json: status === 200 ? {schema_version:schema,surface:"device_home",items:empty?[]:[uiDWorld(FEED_WORLD)]} : {detail:"controlled_failure"}});
  };
  await page.route("**/api/backend/**",handler); await page.route("http://127.0.0.1:8080/api/v1/**",handler);
  await page.clock.install(); await page.goto("/");
  const icon=page.locator(`a[href^="${feedRoute()}"]`);
  await expect(icon).toBeVisible();
  const resume=async()=>{await page.clock.runFor(300);await page.evaluate(()=>window.dispatchEvent(new Event("focus")));};
  status=503; await resume();
  const retry=page.getByRole("button",{name:language==="ko"?"World 목록 다시 시도":"Retry World list"});
  await expect(retry).toBeVisible(); await expect(icon).toBeVisible();
  await expect(page.getByText(language==="ko"?"World 목록을 새로 불러오지 못했어요. 이전에 확인한 목록을 표시하고 있어요.":"Couldn't refresh your Worlds. Showing the previously loaded list.")).toBeVisible();
  // Small screens and zoom must leave retry accessible and the page un-clipped.
  await page.setViewportSize({width:360,height:800}); await page.evaluate(()=>document.documentElement.style.fontSize="200%");
  const bounds=await retry.boundingBox(); expect(bounds!.height).toBeGreaterThanOrEqual(44);
  status=200; await retry.click(); await expect(retry).toHaveCount(0);
  schema="unknown"; await resume(); await expect(retry).toBeVisible(); await expect(icon).toHaveCount(0);
  schema="local-world-surface-v1"; empty=true; await retry.click();
  await expect(page.getByText(language==="ko"?"World 앱을 불러오는 중":"Loading World apps",{exact:true})).toHaveCount(0);
  await expect(retry).toHaveCount(0); // an empty response is successful, not an error
  empty=false; await resume(); await expect(icon).toBeVisible();
  status=403; await resume(); await expect(icon).toHaveCount(0); await expect(retry).toBeVisible();
  await info.attach("layout", {body:JSON.stringify({retryHeight:bounds!.height,emptySuccess:true}),contentType:"application/json"});
});

test("an environment recheck failure retains the prepared Home and hidden replies cannot restore a removed World", async ({page},info)=>{
  test.skip(baseline, "Baseline capture uses only the before/after scenario.");
  const {feed}=await installNotificationFixture(page,info.project.name==="static-export",String(info.project.use.baseURL));
  let failEnvironment=false, empty=false, release:(()=>void)|undefined, gate:Promise<void>|undefined;
  const handler=async(route:import("@playwright/test").Route)=>{
    const path=new URL(route.request().url()).pathname;
    if(path.endsWith("/auth/local/environment")&&failEnvironment)return route.fulfill({status:503,json:{detail:{code:"controlled_failure"}}});
    if(path.endsWith("/worlds/mine")){
      const items=empty?[]:[uiDWorld(FEED_WORLD)]; if(gate)await gate;
      return route.fulfill({json:{schema_version:"local-world-surface-v1",surface:"device_home",items}});
    }
    return route.fallback();
  };
  await page.route("**/api/backend/**",handler);await page.route("http://127.0.0.1:8080/api/v1/**",handler);
  await page.clock.install();await page.goto("/");
  const icon=page.locator(`a[href^="${feedRoute()}"]`); await expect(icon).toBeVisible();
  const ensures=feed.writes.filter(x=>x.path.endsWith("/ensure")).length;
  failEnvironment=true;await page.clock.runFor(300);await page.evaluate(()=>window.dispatchEvent(new Event("focus")));
  await expect(icon).toBeVisible(); expect(feed.writes.filter(x=>x.path.endsWith("/ensure"))).toHaveLength(ensures);
  gate=new Promise(resolve=>release=resolve);await page.clock.runFor(300);await page.evaluate(()=>window.dispatchEvent(new Event("focus")));
  await page.evaluate(()=>{Object.defineProperty(document,"visibilityState",{configurable:true,value:"hidden"});document.dispatchEvent(new Event("visibilitychange"));});
  release!();gate=undefined;empty=true;await page.clock.runFor(300);
  await page.evaluate(()=>{Object.defineProperty(document,"visibilityState",{configurable:true,value:"visible"});document.dispatchEvent(new Event("visibilitychange"));window.dispatchEvent(new Event("focus"));});
  await expect(icon).toHaveCount(0);
});

test("two browser detectors use the real authenticated environment API without repeat conflicts",async({browser,request},info)=>{
  test.skip(baseline,"New API regression.");
  await request.post("http://127.0.0.1:3483/_test/reset");
  const contexts=await Promise.all([browser.newContext(),browser.newContext()]);
  const pages=await Promise.all(contexts.map(c=>c.newPage()));
  const writes=[0,0];
  const headers=(index:number)=>({Origin:"http://127.0.0.1:3000",Host:"127.0.0.1:3000","X-Angmoo-Frontend-Origin":"http://127.0.0.1:3000","Sec-Fetch-Site":"same-origin",Cookie:`angmoo_browser_session=synthetic-browser-${index+1}`});
  try {
    for(const [index,page] of pages.entries()) {
      await installNotificationFixture(page,info.project.name==="static-export",String(info.project.use.baseURL));
      const environment=async(route:import("@playwright/test").Route)=>{
        if(!new URL(route.request().url()).pathname.endsWith("/auth/local/environment"))return route.fallback();
        if(route.request().method()==="POST")writes[index]++;
        const response=await route.fetch({url:"http://127.0.0.1:3483/api/v1/auth/local/environment",headers:{...await route.request().allHeaders(),...headers(index)}});
        expect(response.status()).toBe(200);
        await route.fulfill({response});
      };
      await page.route("**/api/backend/**",environment);await page.route("http://127.0.0.1:8080/api/v1/**",environment);
      await page.clock.install();await page.goto(String(info.project.use.baseURL));
      await expect(page.locator(`a[href^="${feedRoute()}"]`)).toBeVisible();
    }
    expect(writes).toEqual([1,0]);
    for(const page of pages) {
      await page.clock.runFor(500);
      await page.evaluate(()=>{window.dispatchEvent(new Event("focus"));document.dispatchEvent(new Event("visibilitychange"));});
      await expect(page.locator(`a[href^="${feedRoute()}"]`)).toBeVisible();
    }
    expect(writes).toEqual([1,0]);
    await pages[1].reload();await expect(pages[1].locator(`a[href^="${feedRoute()}"]`)).toBeVisible();expect(writes).toEqual([1,0]);
    await request.post("http://127.0.0.1:3483/_test/advance-clock?seconds=61");
    await pages[0].clock.runFor(60_100);
    await expect.poll(()=>writes[0]).toBe(2);
    const current=await request.get("http://127.0.0.1:3483/api/v1/auth/local/environment",{headers:headers(1)});
    const contender=await request.post("http://127.0.0.1:3483/api/v1/auth/local/environment",{headers:headers(1),data:{client_id:"synthetic-contender",sequence:1,expected_revision:(await current.json()).environment_revision,preferred_language:"en",timezone:"UTC"}});
    expect(contender.status()).toBe(409);
    await request.post("http://127.0.0.1:3483/_test/advance-clock?seconds=121");
    await pages[1].clock.runFor(500);
    await pages[1].evaluate(()=>window.dispatchEvent(new Event("focus")));
    await expect.poll(()=>writes[1]).toBe(1);
    const unauthorized=await request.get("http://127.0.0.1:3483/api/v1/auth/local/environment",{headers:{...headers(0),Cookie:""}});
    expect(unauthorized.status()).toBe(401);
    const csrf=await request.post("http://127.0.0.1:3483/api/v1/auth/local/environment",{headers:{...headers(0),Origin:"https://foreign.invalid"},data:{client_id:"synthetic-bad-origin",sequence:1,expected_revision:0,preferred_language:"en",timezone:"UTC"}});
    expect(csrf.status()).toBe(403);
    await info.attach("real-api-detectors",{body:JSON.stringify({writes,contender:contender.status(),anonymous:unauthorized.status(),csrf:csrf.status()}),contentType:"application/json"});
  } finally {await Promise.all(contexts.map(c=>c.close()));}
});

test("runtime identity change discards the previous snapshot before the new scope is ready",async({page},info)=>{
  test.skip(baseline,"New runtime scope regression.");
  await installNotificationFixture(page,info.project.name==="static-export",String(info.project.use.baseURL));
  await page.goto("/");const icon=page.locator(`a[href^="${feedRoute()}"]`);await expect(icon).toBeVisible();
  let release:(()=>void)|undefined;const barrier=new Promise<void>(resolve=>release=resolve);
  const handler=async(route:import("@playwright/test").Route)=>{
    const path=new URL(route.request().url()).pathname;
    if(path.endsWith("/auth/local/environment")){await barrier;return route.fallback();}
    if(path.endsWith("/worlds/mine"))return route.fulfill({json:{schema_version:"local-world-surface-v1",surface:"device_home",items:[]}});
    return route.fallback();
  };
  await page.route("**/api/backend/**",handler);await page.route("http://127.0.0.1:8080/api/v1/**",handler);
  await page.evaluate(()=>window.dispatchEvent(new Event("angmoo:desktop-runtime-config-changed")));
  await expect(icon).toHaveCount(0);release!();
  await expect(page.getByText("World 앱을 불러오는 중",{exact:true})).toHaveCount(0);
  await expect(icon).toHaveCount(0);
});
