import {expect,test} from "@playwright/test";
import {writeFileSync} from "node:fs";
import {installWorldFeedFixture} from "./world-feed-fixture";

test("actual HTTP SQLite source survives lost reply response and reaction reload",async({page,request},info)=>{
  const state=await installWorldFeedFixture(page,false,String(info.project.use.baseURL),"en");
  const actual=async(route:import("@playwright/test").Route)=>{
    // Native frontend transport -> Next proxy -> actual product router/UoW.
    const response=await route.fetch({headers:{...route.request().headers(),origin:String(info.project.use.baseURL)}});
    if(route.request().method()==="POST" && lostReply){lostReply=false;return route.fulfill({status:503,json:{detail:"fixture_response_lost_after_commit"}});}
    return route.fulfill({response});
  };
  let lostReply=true;
  await page.route("**/api/backend/worlds/world-manual/manual-social/**",actual);
  await page.route("**/api/backend/worlds/world-manual/owner-character",actual);
  await page.goto("/worlds/world-manual/posts/reply-C");
  const surface=page.locator('[data-world-social-surface="detail"]');await expect(surface).toBeVisible();
  const row=page.locator('[data-social-post-row="reply-C"]');
  const heart=row.getByRole("button",{name:/Like/});await heart.click();await expect(heart).toHaveAttribute("aria-pressed","true");
  await page.reload();await expect(heart).toHaveAttribute("aria-pressed","true");
  const field=surface.locator("form textarea"),send=surface.locator('form button[type="submit"]');
  await field.fill("Actual canonical nested reply");await send.click();
  await expect(surface.locator('[role="alert"]')).toBeVisible();await expect(field).toHaveValue("Actual canonical nested reply");
  await send.click();await expect(field).toHaveValue("");
  await page.reload();await expect(surface.getByText("Actual canonical nested reply",{exact:true})).toBeVisible();
  const evidence=await (await request.get("http://127.0.0.1:3342/fixture/evidence")).json();
  expect(evidence.like_count).toBe(1);expect(evidence.relationship_count).toBe(0);expect(evidence.projection_count).toBe(0);expect(evidence.outbound).toEqual([]);
  const replies=evidence.posts.filter((p:{body:string})=>p.body==="Actual canonical nested reply");expect(replies).toHaveLength(1);expect(replies[0].parent).toBe("reply-C");
  expect(evidence.inbox).toEqual([{target:"reply-C",recipient:"world-character-autonomous-target"}]);
  const writes=evidence.requests.filter((r:{method:string;path:string})=>r.method==="POST"&&r.path.endsWith("/replies"));expect(writes).toHaveLength(2);expect(writes[0].key).toBe(writes[1].key);
  expect(evidence.events.every((e:{retrieval:string})=>e.retrieval==="audit_only")).toBe(true);expect(evidence.events).toHaveLength(2);
  expect(state.providerCalls).toEqual([]);
  writeFileSync(info.outputPath("actual-db-evidence.json"),JSON.stringify(evidence,null,2));
});
