import { expect, type Page } from "@playwright/test";

/** Reach the final real control inside the product scroll owner at each width. */
export async function verifyCreatorResponsive(page: Page) {
  for (const width of [480, 1024, 1440]) {
    await page.setViewportSize({ width, height: 900 });
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBe(true);
    const control = page.locator("main button, main input, main select, main textarea").filter({ visible: true }).last();
    if (await control.count()) {
      await control.scrollIntoViewIfNeeded();
      const bounds = await control.boundingBox();
      expect(bounds).not.toBeNull();
      expect(bounds!.x).toBeGreaterThanOrEqual(-1);
      expect(bounds!.x + bounds!.width).toBeLessThanOrEqual(width + 1);
      expect(bounds!.y + bounds!.height).toBeLessThanOrEqual(901);
      expect(bounds!.y + bounds!.height).toBeGreaterThan(0);
    }
  }
}
