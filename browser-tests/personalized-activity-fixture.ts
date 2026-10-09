import { expect, test, type Page } from "@playwright/test";
import { installIntegrationFixture } from "./home-activity-memory-fixture";
import { worldCharacterRoute } from "./world-character-management-fixture";

export function personalizedActivityTests(staticMode: boolean, bootstrap: (page: Page) => Promise<void> = async () => {}) {
  test("personalized settings keep engine CAS and transitions without current state or run details", async ({ page }, info) => {
    await bootstrap(page);
    const state = await installIntegrationFixture(page, staticMode, String(info.project.use.baseURL));
    state.engine = "current"; state.transition = "needs_preparation";
    await page.goto(`${worldCharacterRoute()}?view=settings`);
    const panel = page.getByRole("region", { name: "활동 방식", exact: true });
    await expect(panel).toContainText("기존 활동 방식");
    await expect(panel.getByRole("status")).toContainText("승인된 설정과 일과 준비");
    await expect(panel).not.toContainText(state.note);
    await expect(panel).not.toContainText("최근 실행");
    await expect(panel.getByLabel("적용 범위", { exact: true })).toHaveCount(0);
    const choice = panel.getByLabel("사용할 방식", { exact: true });
    await expect(choice.locator("option")).toHaveCount(2);
    await expect(choice.locator('option[value="current"]')).toHaveCount(0);
    await choice.focus(); await expect(choice).toBeFocused();
    await choice.selectOption("personalized_graph_v2");
    await panel.getByRole("button", { name: "활동 방식 저장", exact: true }).click();
    await expect.poll(() => state.writes.length).toBe(1);
    expect(state.writes[0].body).toEqual({ scope: "character", engine: "personalized_graph_v2", expected_version: 1 });
    await expect(panel).toContainText("기억을 반영하는 활동 방식 (V2)");
    await choice.selectOption("inherit");
    await panel.getByRole("button", { name: "활동 방식 저장", exact: true }).click();
    await expect.poll(() => state.writes.length).toBe(2);
    expect(state.writes[1].body).toEqual({ scope: "character", engine: null, expected_version: 2 });
    await expect(panel).toContainText("World 기본값");
    await page.setViewportSize({ width: 390, height: 844 });
    expect(await choice.evaluate(node => node.getBoundingClientRect().height)).toBeGreaterThanOrEqual(44);
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
    await panel.screenshot({ path: info.outputPath("sns-transition-mobile.png") });
    state.runtimeFailure = 503;
    await page.reload();
    await expect(panel.getByRole("alert")).toBeVisible();
    state.runtimeFailure = 0;
    await panel.getByRole("button", { name: "다시 시도", exact: true }).click();
    await expect(choice).toBeVisible();
    expect(state.unexpected).toEqual([]);
  });
}
