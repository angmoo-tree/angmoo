import { expect, test } from "@playwright/test";
import { continuityAgentDetail } from "./continuity-fixture";
import { installBackendFixture, json } from "./continuity-next-fixture";

const staticShell = process.env.ANGMOO_CREATOR_STATIC === "1";

test("description and optional background stay separate in character settings", async ({ page }) => {
  if (staticShell) await page.addInitScript(() => Object.assign(window, { __ANGMOO_RUNTIME_CONFIG__: {
    profile: "tauri-static", apiBaseUrl: "http://127.0.0.1:8080", graphProvider: "ladybug", launchToken: "creator-fixture-token-0000000000000",
  } }));
  else await installBackendFixture(page);
  const characterId = "description-bird";
  let agent = { ...continuityAgentDetail(characterId), character: {
    ...continuityAgentDetail(characterId).character,
    worldview: "책을 좋아하는 서점 주인", character_background: "오래된 왕국 출신", personality: "",
  } };
  const writes: Array<Record<string, string>> = [];
  await page.route(staticShell ? "http://127.0.0.1:8080/api/v1/**" : "**/api/backend/**", async (route) => {
    const url = new URL(route.request().url());
    const path = url.pathname.replace(/^\/api\/(backend|v1)/, "");
    if (staticShell && path === "/auth/me") return json(route, { id: "owner", display_name: "Owner", email: null, profile_setup_completed: true,
      feed_content_filter: "all", ui_language: "ko", ui_preference_revision: 0, is_admin: false, display_name_updated_at: null, display_name_change_available_at: null });
    if (path === `/agents/${characterId}`) return json(route, agent);
    if (path === `/agents/${characterId}/persona`) {
      const body = route.request().postDataJSON() as Record<string, string>;
      writes.push(body);
      agent = { ...agent, character: { ...agent.character, ...body } };
      return json(route, agent);
    }
    if (path.endsWith("/lore-sources")) return json(route, { items: [] });
    return route.fallback();
  });
  await page.goto(`/agents/${characterId}?tab=settings`);
  await expect(page.getByRole("textbox", { name: "캐릭터 설명", exact: true })).toHaveValue("책을 좋아하는 서점 주인");
  await expect(page.getByRole("textbox", { name: "캐릭터 배경·세계관", exact: true })).toHaveValue("오래된 왕국 출신");
  await page.getByRole("textbox", { name: "캐릭터 배경·세계관", exact: true }).fill("다른 도시 출신");
  await page.getByRole("button", { name: "페르소나 저장" }).click();
  await expect.poll(() => writes.length).toBe(1);
  expect(writes[0].worldview).toBe("책을 좋아하는 서점 주인");
  expect(writes[0].character_background).toBe("다른 도시 출신");
  expect(writes[0].personality).toBe("");
  await page.reload();
  await expect(page.getByRole("textbox", { name: "캐릭터 배경·세계관", exact: true })).toHaveValue("다른 도시 출신");
  await page.getByRole("textbox", { name: "캐릭터 배경·세계관", exact: true }).fill("");
  await page.getByRole("button", { name: "페르소나 저장" }).click();
  await expect.poll(() => writes.length).toBe(2);
  expect(writes[1].character_background).toBe("");
  expect(writes[1].worldview).toBe("책을 좋아하는 서점 주인");
});
