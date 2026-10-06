import { expect, test } from "@playwright/test";
import { writeFileSync } from "node:fs";
import { installWorldFeedFixture } from "./world-feed-fixture";

test("T48 real UI DELETE hides only the original SQLite thread and explicit restart creates a new ID", async ({ page, request }, info) => {
  const isStatic = info.project.name === "static-export", baseURL = String(info.project.use.baseURL);
  const fixtureURL = "http://127.0.0.1:3354";
  const frontendHeaders = { Origin: baseURL, "X-Angmoo-Frontend-Origin": baseURL };
  const before = await (await request.get(`${fixtureURL}/fixture/evidence`)).json();
  const audit = await installWorldFeedFixture(page, isStatic, baseURL, "en");
  // Shell/auth/media are synthetic; every Chat operation uses the product router.
  const actual = async (route: import("@playwright/test").Route) => {
    const original = route.request(), path = new URL(original.url()).pathname.replace(/^\/api\/(backend|v1)/, "");
    const response = await request.fetch(`${fixtureURL}/api/v1${path}`, { method: original.method(),
      headers: frontendHeaders, ...(original.postData() ? { data: original.postDataJSON() } : {}) });
    return route.fulfill({ status: response.status(), body: await response.body(), headers: { "Content-Type": "application/json" } });
  };
  await page.route("**/api/backend/worlds/world-a/chat/**", actual);
  await page.route("http://127.0.0.1:8080/api/v1/worlds/world-a/chat/**", actual);
  await page.goto(`/worlds/world-a/chat/${before.thread_id}`);
  const room = page.locator("[data-world-chat-surface=thread]"); await expect(room).toBeVisible();
  await expect(room.getByText("Synthetic retained original message", { exact: true })).toBeVisible();
  await room.locator(":scope > header button").last().click();
  await page.locator("[data-world-chat-delete-dialog]").getByRole("button", { name: "Delete", exact: true }).click();
  await expect(page).toHaveURL(/\/worlds\/world-a\/chat\/?$/);
  await expect(page.locator("[data-thread-row-id]")).toHaveCount(0);
  await page.goto(`/worlds/world-a/chat/${before.thread_id}`); await expect(room).toHaveCount(0);
  const deleted = await request.delete(`${fixtureURL}/api/v1/worlds/world-a/chat/threads/${before.thread_id}`, { headers: frontendHeaders });
  expect(deleted.status()).toBe(200); expect((await deleted.json()).outcome).toBe("already_deleted");
  const restarted = await request.post(`${fixtureURL}/api/v1/worlds/world-a/chat/threads`, { headers: frontendHeaders, data: { responding_world_character_id: before.responding_id } });
  expect(restarted.status()).toBe(200); const fresh = (await restarted.json()).thread;
  expect(fresh.id).not.toBe(before.thread_id); expect(fresh.messages).toEqual([]);
  await page.goto(`/worlds/world-a/chat/${fresh.id}`); await expect(room).toBeVisible();
  await expect(room.getByText("Synthetic retained original message", { exact: true })).toHaveCount(0);
  const evidence = await (await request.get(`${fixtureURL}/fixture/evidence`)).json();
  expect(evidence.provider_calls).toBe(0); expect(evidence.response_count).toBe(0); expect(evidence.foreign_key_violations).toEqual([]);
  expect(evidence.threads).toEqual([{ id: before.thread_id, deleted: true }, { id: fresh.id, deleted: false }]);
  expect(evidence.messages).toEqual(before.messages); expect(audit.providerCalls).toEqual([]);
  writeFileSync(info.outputPath("actual-chat-delete-db-evidence.json"), JSON.stringify(evidence, null, 2));
});
