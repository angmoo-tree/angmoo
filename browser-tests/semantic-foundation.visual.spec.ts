import { expect, test, type Locator, type Page, type TestInfo } from "@playwright/test";

const FOUNDATION_ROUTE = "/ui-foundation";
const FIXTURE_SELECTOR = "[data-ui-foundation-fixture]";
const FIXTURE_SCHEMA = "ui-b-semantic-primitives-v1";
const FIXED_TIME = new Date("2026-08-29T10:00:00+09:00");
const STATIC_API_ORIGIN = "http://127.0.0.1:8080";

const OWNER = {
  id: "ui-b-visual-owner",
  email: null,
  display_name: "UI-B Visual Owner",
  display_name_updated_at: null,
  display_name_change_available_at: null,
  profile_setup_completed: true,
  feed_content_filter: "all",
  is_admin: false,
};

type CssState = {
  backgroundColor: string;
  borderColor: string;
  boxShadow: string;
  color: string;
  transform: string;
};

type Rgba = [number, number, number, number];

type ContrastMeasurement = {
  background: Rgba;
  foreground: Rgba;
  ratio: number;
};

const WCAG_AA_TEXT_CONTRAST = 4.5;
const WCAG_AA_NON_TEXT_CONTRAST = 3;

async function cssState(page: Page, selector: string): Promise<CssState> {
  return page.locator(selector).evaluate((node) => {
    const style = getComputedStyle(node);
    return {
      backgroundColor: style.backgroundColor,
      borderColor: style.borderColor,
      boxShadow: style.boxShadow,
      color: style.color,
      transform: style.transform,
    };
  });
}

async function textContrastMeasurements(locator: Locator): Promise<ContrastMeasurement[]> {
  return locator.evaluateAll((nodes) => {
    type BrowserRgba = [number, number, number, number];
    const rgba = (value: string): BrowserRgba => {
      const channels = value.match(/[\d.]+/g)?.map(Number);
      if (!channels || channels.length < 3) throw new Error(`rgb required: ${value}`);
      return [channels[0], channels[1], channels[2], channels[3] ?? 1];
    };
    const composite = (foreground: BrowserRgba, background: BrowserRgba): BrowserRgba => {
      const alpha = foreground[3] + background[3] * (1 - foreground[3]);
      if (alpha === 0) return [0, 0, 0, 0];
      return [
        (foreground[0] * foreground[3] +
          background[0] * background[3] * (1 - foreground[3])) /
          alpha,
        (foreground[1] * foreground[3] +
          background[1] * background[3] * (1 - foreground[3])) /
          alpha,
        (foreground[2] * foreground[3] +
          background[2] * background[3] * (1 - foreground[3])) /
          alpha,
        alpha,
      ];
    };
    const effectiveBackground = (node: Element): BrowserRgba => {
      const layers: BrowserRgba[] = [];
      for (let current: Element | null = node; current; current = current.parentElement) {
        layers.push(rgba(getComputedStyle(current).backgroundColor));
      }
      return layers.reverse().reduce(
        (background, layer) => composite(layer, background),
        [255, 255, 255, 1] as BrowserRgba,
      );
    };
    const luminance = ([red, green, blue]: BrowserRgba): number => {
      const linear = [red, green, blue].map((channel) => {
        const value = channel / 255;
        return value <= 0.04045 ? value / 12.92 : ((value + 0.055) / 1.055) ** 2.4;
      });
      return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2];
    };
    const ratio = (foreground: BrowserRgba, background: BrowserRgba): number => {
      const first = luminance(foreground);
      const second = luminance(background);
      return (Math.max(first, second) + 0.05) / (Math.min(first, second) + 0.05);
    };

    return nodes.map((node) => {
      const background = effectiveBackground(node);
      const foreground = composite(rgba(getComputedStyle(node).color), background);
      return { background, foreground, ratio: ratio(foreground, background) };
    });
  });
}

function expectApprovedTextContrastException(
  measurement: ContrastMeasurement,
  expected: {
    background: [number, number, number];
    foreground: [number, number, number];
    maximumRatio: number;
    minimumRatio: number;
  },
): void {
  expect(measurement.background.slice(0, 3)).toEqual(expected.background);
  expect(measurement.foreground.slice(0, 3)).toEqual(expected.foreground);
  expect(measurement.ratio).toBeGreaterThanOrEqual(expected.minimumRatio);
  expect(measurement.ratio).toBeLessThanOrEqual(expected.maximumRatio);
  expect(measurement.ratio).toBeLessThan(WCAG_AA_TEXT_CONTRAST);
}

async function openFoundation(page: Page, testInfo: TestInfo): Promise<void> {
  const blockedRequests: string[] = [];
  const baseURL = testInfo.project.use.baseURL;
  if (typeof baseURL !== "string") throw new Error("visual project requires baseURL");
  const productOrigin = new URL(baseURL).origin;
  const isNextProject = testInfo.project.name === "next-production";
  const isStaticProject = testInfo.project.name === "static-export";

  await page.clock.install({ time: FIXED_TIME });
  await page.route("**/*", async (route) => {
    const requestUrl = new URL(route.request().url());
    const isNextAuth =
      isNextProject &&
      requestUrl.origin === productOrigin &&
      requestUrl.pathname === "/api/backend/auth/me";
    const isStaticAuth =
      isStaticProject &&
      requestUrl.origin === STATIC_API_ORIGIN &&
      requestUrl.pathname === "/api/v1/auth/me";

    if (isNextAuth || isStaticAuth) {
      await route.fulfill({ contentType: "application/json", json: OWNER, status: 200 });
      return;
    }

    const isProductAsset =
      requestUrl.origin === productOrigin && !requestUrl.pathname.startsWith("/api/");
    if (isProductAsset) {
      await route.continue();
      return;
    }

    blockedRequests.push(route.request().url());
    await route.abort("blockedbyclient");
  });

  await page.goto(FOUNDATION_ROUTE);
  const fixture = page.locator(FIXTURE_SELECTOR);
  await expect(fixture).toBeVisible();
  await expect(fixture).toHaveAttribute("data-fixture-schema", FIXTURE_SCHEMA);
  await page.evaluate(async () => {
    await document.fonts.ready;
  });
  const fixtureImage = fixture.locator('img[src="/icon.svg"]');
  await expect(fixtureImage).toBeVisible();
  expect(
    await fixtureImage.evaluate(
      (image) => image instanceof HTMLImageElement && image.complete && image.naturalWidth > 0,
    ),
  ).toBe(true);
  await page.waitForLoadState("networkidle");
  expect(blockedRequests).toEqual([]);
}

function cssTimeToSeconds(value: string): number {
  return Math.max(
    ...value.split(",").map((entry) => {
      const duration = entry.trim();
      if (duration.endsWith("ms")) return Number.parseFloat(duration) / 1_000;
      if (duration.endsWith("s")) return Number.parseFloat(duration);
      return Number.POSITIVE_INFINITY;
    }),
  );
}

test.beforeEach(async ({ page }, testInfo) => {
  await openFoundation(page, testInfo);
});

test("semantic foundation keeps one production/static 436px Phone baseline", async ({
  page,
}) => {
  const fixture = page.locator(FIXTURE_SELECTOR);
  const geometry = await fixture.boundingBox();
  expect(geometry).not.toBeNull();
  expect(geometry!.width).toBeLessThanOrEqual(436);

  const overflow = await fixture.evaluate((node) => ({
    document: document.documentElement.scrollWidth - document.documentElement.clientWidth,
    fixture: node.scrollWidth - node.clientWidth,
  }));
  expect(overflow).toEqual({ document: 0, fixture: 0 });
  await expect(page).toHaveScreenshot("semantic-foundation-phone.png");
});

test("interactive primitives expose real pointer, focus, and state semantics", async ({
  page,
}) => {
  const minimumTargets = page.locator('[data-ui-test="minimum-target"]');
  expect(await minimumTargets.count()).toBeGreaterThan(0);
  for (const target of await minimumTargets.all()) {
    const geometry = await target.boundingBox();
    expect(geometry).not.toBeNull();
    expect(geometry!.width).toBeGreaterThanOrEqual(44);
    expect(geometry!.height).toBeGreaterThanOrEqual(44);
  }

  const hoverSelector = '[data-ui-test="hover-target"]';
  const hoverTarget = page.locator(hoverSelector);
  const hoverDefault = await cssState(page, hoverSelector);
  await hoverTarget.hover();
  await expect.poll(() => hoverTarget.evaluate((node) => node.matches(":hover"))).toBe(true);
  expect(await cssState(page, hoverSelector)).not.toEqual(hoverDefault);

  const activeSelector = '[data-ui-test="active-target"]';
  const activeTarget = page.locator(activeSelector);
  const activeBox = await activeTarget.boundingBox();
  expect(activeBox).not.toBeNull();
  await page.mouse.move(
    activeBox!.x + activeBox!.width / 2,
    activeBox!.y + activeBox!.height / 2,
  );
  const activeHover = await cssState(page, activeSelector);
  await page.mouse.down();
  expect(await activeTarget.evaluate((node) => node.matches(":active"))).toBe(true);
  await expect.poll(() => cssState(page, activeSelector)).not.toEqual(activeHover);
  await page.mouse.up();

  const focusTarget = page.locator('[data-ui-test="focus-target"]');
  await focusTarget.focus();
  await page.keyboard.press("Tab");
  await page.keyboard.press("Shift+Tab");
  await expect(focusTarget).toBeFocused();
  expect(await focusTarget.evaluate((node) => node.matches(":focus-visible"))).toBe(true);
  const focusIndicator = await focusTarget.evaluate((node) => {
    const style = getComputedStyle(node);
    return {
      boxShadow: style.boxShadow,
      outlineStyle: style.outlineStyle,
      outlineWidth: Number.parseFloat(style.outlineWidth),
    };
  });
  expect(
    (focusIndicator.outlineStyle !== "none" && focusIndicator.outlineWidth >= 2) ||
      focusIndicator.boxShadow !== "none",
  ).toBe(true);

  await expect(page.locator('[data-ui-test="disabled-button"]')).toBeDisabled();
  const loadingButton = page.locator('[data-ui-test="loading-button"]');
  await expect(loadingButton).toBeDisabled();
  await expect(loadingButton).toHaveAttribute("aria-busy", "true");

  const inlineError = page.locator('[data-ui-test="inline-error"]');
  await expect(inlineError).toHaveAttribute("role", "alert");
  const inlineErrorId = await inlineError.getAttribute("id");
  expect(inlineErrorId).toBeTruthy();
  const errorControl = page.locator('[data-ui-test="error-control"]');
  await expect(errorControl).toHaveAttribute("aria-invalid", "true");
  const describedBy = (await errorControl.getAttribute("aria-describedby"))
    ?.split(/\s+/)
    .filter(Boolean);
  expect(describedBy?.length).toBeGreaterThan(0);
  await expect(page.locator(`#${describedBy?.at(-1)}[role="alert"]`)).toBeVisible();
});

test("Tabs and BottomNavigation expose one current destination", async ({ page }) => {
  const tabs = page.locator('[data-ui-test="tabs"] [role="tablist"]');
  await expect(tabs).toHaveAttribute("role", "tablist");
  const tabItems = tabs.getByRole("tab");
  expect(await tabItems.count()).toBeGreaterThanOrEqual(2);
  await expect(tabs.locator('[role="tab"][aria-selected="true"]')).toHaveCount(1);
  await expect(tabItems.nth(0)).toHaveAttribute("aria-selected", "true");
  await expect(tabItems.nth(1)).toHaveAttribute("aria-selected", "false");
  await tabItems.nth(1).click();
  await expect(tabItems.nth(1)).toHaveAttribute("aria-selected", "true");
  await expect(tabItems.nth(0)).toHaveAttribute("aria-selected", "false");

  const navigation = page.locator('[data-ui-test="bottom-navigation"] nav');
  await expect(navigation).toHaveRole("navigation");
  await expect(navigation.locator('[aria-current="page"]')).toHaveCount(1);
  const navigationItems = navigation.locator(
    '[data-ui-primitive="bottom-navigation-item"]',
  );
  expect(await navigationItems.count()).toBeGreaterThanOrEqual(7);
  const lastNavigationItem = navigationItems.last();
  await lastNavigationItem.click();
  await expect(lastNavigationItem).toHaveAttribute("aria-current", "page");
  const activeVisibility = await lastNavigationItem.evaluate((node) => {
    const item = node.getBoundingClientRect();
    const navigation = node.parentElement?.getBoundingClientRect();
    if (!navigation) return false;
    return item.left >= navigation.left && item.right <= navigation.right;
  });
  expect(activeVisibility).toBe(true);
});

test("semantic text samples outside approved exceptions preserve WCAG AA contrast", async ({
  page,
}) => {
  const samples = page.locator(
    '[data-ui-test="contrast-sample"], [data-ui-primitive="badge"], [data-ui-primitive="status-chip"], [data-ui-primitive="field"] p',
  );
  expect(await samples.count()).toBeGreaterThan(0);
  const measurements = await textContrastMeasurements(samples);
  for (const measurement of measurements) {
    expect(measurement.ratio).toBeGreaterThanOrEqual(WCAG_AA_TEXT_CONTRAST);
  }
});

test.describe("user-approved contrast exceptions are not WCAG AA PASS", () => {
  test("EXCEPTION-A keeps the hosted bright social foreground bounded", async ({ page }) => {
    const [measurement] = await textContrastMeasurements(
      page.getByText("Angmoo Local · UI-B", { exact: true }),
    );

    expectApprovedTextContrastException(measurement, {
      background: [255, 255, 255],
      foreground: [255, 107, 107],
      minimumRatio: 2.7,
      maximumRatio: 2.9,
    });
  });

  test("EXCEPTION-B keeps bright primary CTA labels bounded in default and hover states", async ({
    page,
  }) => {
    const primaryButton = page.locator('[data-ui-test="hover-target"]');
    const [defaultMeasurement] = await textContrastMeasurements(primaryButton);
    expectApprovedTextContrastException(defaultMeasurement, {
      background: [255, 107, 107],
      foreground: [255, 255, 255],
      minimumRatio: 2.7,
      maximumRatio: 2.9,
    });

    await primaryButton.hover();
    await expect
      .poll(async () => (await textContrastMeasurements(primaryButton))[0].background.slice(0, 3))
      .toEqual([255, 82, 82]);
    const [hoverMeasurement] = await textContrastMeasurements(primaryButton);
    expectApprovedTextContrastException(hoverMeasurement, {
      background: [255, 82, 82],
      foreground: [255, 255, 255],
      minimumRatio: 3.1,
      maximumRatio: 3.3,
    });
  });

  test("EXCEPTION-C keeps selected navigation label and icon contrast bounded", async ({
    page,
  }) => {
    const selectedNavigation = page.locator(
      '[data-ui-test="bottom-navigation"] [aria-current="page"]',
    );
    await expect(selectedNavigation).toHaveCount(1);
    const [measurement] = await textContrastMeasurements(selectedNavigation);

    expectApprovedTextContrastException(measurement, {
      background: [255, 240, 239],
      foreground: [255, 107, 107],
      minimumRatio: 2.4,
      maximumRatio: 2.6,
    });
  });
});

test("control boundaries keep non-text contrast outside the approved active-indicator exception", async ({
  page,
}) => {
  const ratios = await page.evaluate(() => {
    type Rgba = [number, number, number, number];
    const rgba = (value: string): Rgba => {
      const channels = value.match(/[\d.]+/g)?.map(Number);
      if (!channels || channels.length < 3) throw new Error(`rgb required: ${value}`);
      return [channels[0], channels[1], channels[2], channels[3] ?? 1];
    };
    const composite = (foreground: Rgba, background: Rgba): Rgba => {
      const alpha = foreground[3] + background[3] * (1 - foreground[3]);
      if (alpha === 0) return [0, 0, 0, 0];
      return [
        (foreground[0] * foreground[3] +
          background[0] * background[3] * (1 - foreground[3])) /
          alpha,
        (foreground[1] * foreground[3] +
          background[1] * background[3] * (1 - foreground[3])) /
          alpha,
        (foreground[2] * foreground[3] +
          background[2] * background[3] * (1 - foreground[3])) /
          alpha,
        alpha,
      ];
    };
    const effectiveBackground = (node: Element): Rgba => {
      const layers: Rgba[] = [];
      for (let current: Element | null = node; current; current = current.parentElement) {
        layers.push(rgba(getComputedStyle(current).backgroundColor));
      }
      return layers.reverse().reduce(
        (background, layer) => composite(layer, background),
        [255, 255, 255, 1] as Rgba,
      );
    };
    const luminance = ([red, green, blue]: Rgba): number => {
      const linear = [red, green, blue].map((channel) => {
        const value = channel / 255;
        return value <= 0.04045 ? value / 12.92 : ((value + 0.055) / 1.055) ** 2.4;
      });
      return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2];
    };
    const ratio = (foreground: Rgba, background: Rgba): number => {
      const first = luminance(composite(foreground, background));
      const second = luminance(background);
      return (Math.max(first, second) + 0.05) / (Math.min(first, second) + 0.05);
    };

    const control = document.querySelector<HTMLElement>(
      '[data-ui-test="control-boundary"]',
    );
    const selectedTab = document.querySelector<HTMLElement>(
      '[role="tab"][aria-selected="true"]',
    );
    if (!control || !selectedTab) throw new Error("non-text contrast fixture missing");
    const controlStyle = getComputedStyle(control);
    const indicatorStyle = getComputedStyle(selectedTab, "::after");
    return {
      control: ratio(rgba(controlStyle.borderTopColor), rgba(controlStyle.backgroundColor)),
      indicator: ratio(
        rgba(indicatorStyle.backgroundColor),
        effectiveBackground(selectedTab),
      ),
    };
  });

  expect(ratios.control).toBeGreaterThanOrEqual(WCAG_AA_NON_TEXT_CONTRAST);
  expect(ratios.indicator).toBeGreaterThanOrEqual(2.7);
  expect(ratios.indicator).toBeLessThanOrEqual(2.9);
  expect(ratios.indicator).toBeLessThan(WCAG_AA_NON_TEXT_CONTRAST);
});

test("Dialog contains focus, closes with Escape, and returns focus", async ({ page }) => {
  const trigger = page.locator('[data-ui-test="dialog-trigger"]');
  const dialog = page.locator('[data-ui-test="dialog"]');
  const closeButton = page.locator('[data-ui-test="dialog-close"]');

  await trigger.click();
  await expect(dialog).toBeVisible();
  await expect(dialog).toHaveAttribute("role", "dialog");
  await expect(dialog).toHaveAttribute("aria-modal", "true");
  await expect(closeButton).toBeFocused();
  await page.keyboard.press("Tab");
  await expect(page.locator('[data-ui-test="dialog-link"]')).toBeFocused();
  await page.keyboard.press("Shift+Tab");
  await expect(closeButton).toBeFocused();
  await page.keyboard.press("Shift+Tab");
  expect(await dialog.evaluate((node) => node.contains(document.activeElement))).toBe(true);

  await page.keyboard.press("Escape");
  await expect(dialog).toBeHidden();
  await expect(trigger).toBeFocused();
});

test("reduced motion remains non-vacuous and stops the loading spinner", async ({
  page,
}) => {
  const spinner = page.locator('[data-ui-part="loading-indicator"]');
  const primitive = page.locator('[data-ui-test="hover-target"]');
  await expect(spinner).toBeVisible();
  await expect(primitive).toBeVisible();

  await page.emulateMedia({ reducedMotion: "no-preference" });
  const regular = await Promise.all([
    spinner.evaluate((node) => getComputedStyle(node).animationDuration),
    primitive.evaluate((node) => getComputedStyle(node).transitionDuration),
  ]);
  expect(cssTimeToSeconds(regular[0])).toBeGreaterThan(0);
  expect(cssTimeToSeconds(regular[1])).toBeGreaterThan(0);

  await page.emulateMedia({ reducedMotion: "reduce" });
  const reduced = await Promise.all([
    spinner.evaluate((node) => getComputedStyle(node).animationDuration),
    primitive.evaluate((node) => getComputedStyle(node).transitionDuration),
  ]);
  expect(cssTimeToSeconds(reduced[0])).toBeLessThanOrEqual(0.001);
  expect(cssTimeToSeconds(reduced[1])).toBeLessThanOrEqual(0.001);
});
