import { expect, test } from "@playwright/test";

const ROUTES = [
  "/",
  "/studio",
  "/studio/worlds/new",
  "/studio/worlds/world-static-probe",
  "/worlds/world-static-probe",
  "/worlds/world-static-probe/feed",
  "/worlds/world-static-probe/chat",
  "/worlds/world-static-probe/characters",
  "/worlds/world-static-probe/relationships",
  "/characters/character-static-probe/worlds/world-static-probe/autonomy-setup",
  "/characters/character-static-probe/worlds/world-static-probe/relationship-graph?provider=ladybug",
  "/agents/character-static-probe",
  "/posts",
  "/posts/post-static-probe",
  "/settings",
  "/login?returnTo=%2F",
] as const;

test.beforeEach(async ({ page }) => {
  await page.addInitScript(() => {
    Object.assign(window, {
      __ANGMOO_RUNTIME_CONFIG__: {
        profile: "tauri-static",
        apiBaseUrl: "http://127.0.0.1:8080",
        launchToken: "static-route-probe-token",
      },
    });
  });
  await page.route("http://127.0.0.1:8080/api/v1/**", async (route) => {
    expect(route.request().headers()["x-angmoo-launcher-token"]).toBe(
      "static-route-probe-token",
    );
    const pathname = new URL(route.request().url()).pathname;
    if (pathname === "/api/v1/auth/me") {
      await route.fulfill({
        contentType: "application/json",
        json: {
          id: "owner-static-probe",
          email: null,
          display_name: "Static Owner",
          display_name_updated_at: null,
          display_name_change_available_at: null,
          profile_setup_completed: true,
          feed_content_filter: "all",
          is_admin: false,
        },
        status: 200,
      });
      return;
    }
    await route.fulfill({
      contentType: "application/json",
      json: { detail: "static_route_probe" },
      status: 503,
    });
  });
});

for (const route of ROUTES) {
  test(`direct-open static route ${route}`, async ({ page }) => {
    await page.goto(route);
    await expect(page.getByText("제품 화면을 준비하고 있습니다...")).toHaveCount(0);
    await expect(page.getByText("지원하지 않는 Angmoo 경로입니다.")).toHaveCount(0);
    await expect(page.locator("body")).not.toBeEmpty();
  });
}

test("Tauri Phone delegates Studio to a reusable wide product window", async ({ page }) => {
  await page.addInitScript(() => {
    const desktop = window as unknown as {
      __ANGMOO_DESKTOP_INVOCATIONS__: Array<{
        command: string;
        args?: Record<string, unknown>;
      }>;
      __ANGMOO_DESKTOP_WINDOW__: { kind: "phone"; route: string };
      __TAURI__: {
        core: {
          invoke: (command: string, args?: Record<string, unknown>) => Promise<void>;
        };
      };
    };
    desktop.__ANGMOO_DESKTOP_INVOCATIONS__ = [];
    desktop.__ANGMOO_DESKTOP_WINDOW__ = { kind: "phone", route: "/" };
    desktop.__TAURI__ = {
      core: {
        invoke: async (command, args) => {
          desktop.__ANGMOO_DESKTOP_INVOCATIONS__.push({ command, args });
        },
      },
    };
  });
  await page.goto("/");

  await expect(page.getByLabel("Memory Explorer는 후속 단계에서 연결됩니다")).toHaveAttribute(
    "data-disabled",
    "true",
  );
  await page.getByRole("link", { name: "Creator Studio 열기" }).click();
  await expect
    .poll(() =>
      page.evaluate(() => {
        const desktop = window as unknown as {
          __ANGMOO_DESKTOP_INVOCATIONS__: unknown[];
        };
        return desktop.__ANGMOO_DESKTOP_INVOCATIONS__;
      }),
    )
    .toContainEqual({
      command: "open_product_window",
      args: { kind: "studio", route: "/studio" },
    });
  await expect(page).toHaveURL(/\/$/);

  await page.getByRole("button", { name: "Angmoo 창 최소화" }).click();
  await expect
    .poll(() =>
      page.evaluate(() => {
        const desktop = window as unknown as {
          __ANGMOO_DESKTOP_INVOCATIONS__: Array<{ command: string }>;
        };
        return desktop.__ANGMOO_DESKTOP_INVOCATIONS__.map(({ command }) => command);
      }),
    )
    .toContain("minimize_product_window");
});

test("Tauri Phone opens the owner relationship graph in a wide product window", async ({
  page,
}) => {
  await page.addInitScript(() => {
    const desktop = window as unknown as {
      __ANGMOO_DESKTOP_INVOCATIONS__: Array<{
        command: string;
        args?: Record<string, unknown>;
      }>;
      __ANGMOO_DESKTOP_WINDOW__: { kind: "phone"; route: string };
      __TAURI__: {
        core: {
          invoke: (command: string, args?: Record<string, unknown>) => Promise<void>;
        };
      };
    };
    desktop.__ANGMOO_DESKTOP_INVOCATIONS__ = [];
    desktop.__ANGMOO_DESKTOP_WINDOW__ = {
      kind: "phone",
      route: "/worlds/world-static-probe/relationships",
    };
    desktop.__TAURI__ = {
      core: {
        invoke: async (command, args) => {
          desktop.__ANGMOO_DESKTOP_INVOCATIONS__.push({ command, args });
        },
      },
    };
  });
  await page.route("http://127.0.0.1:8080/api/v1/**", async (route) => {
    const pathname = new URL(route.request().url()).pathname;
    if (pathname === "/api/v1/worlds/mine/world-static-probe") {
      await route.fulfill({
        contentType: "application/json",
        json: {
          schema_version: "local-world-app-v1",
          surface: "world_app",
          world: {
            world_id: "world-static-probe",
            name: "Static World",
            tagline: "Relationship window probe",
            banner_media_id: null,
            banner_alt_text: "",
            status: "published",
            visibility: "public",
            readiness_status: "publish_ready",
            membership_role: "owner",
            updated_at: "2026-08-21T00:00:00Z",
            launchable: true,
            launch_block_reason: null,
          },
        },
        status: 200,
      });
      return;
    }
    if (pathname === "/api/v1/worlds/world-static-probe/owner-character") {
      await route.fulfill({
        contentType: "application/json",
        json: {
          schema_version: "owner-controlled-world-character-v1",
          world_character_id: "wc-static-owner",
          world_id: "world-static-probe",
          character_id: "character-static-owner",
          control_mode: "owner_controlled",
          status: "active",
          autonomous_enabled: false,
          version: 1,
          profile: {
            display_name: "Static Owner Parrot",
            avatar_url: "http://127.0.0.1:3000/icon.svg",
            intro: "Static relationship probe",
            role_key: null,
            preferred_address: "Owner",
            interests: [],
            background: "",
          },
        },
        status: 200,
      });
      return;
    }
    await route.fallback();
  });

  await page.goto("/worlds/world-static-probe/relationships");
  await page.getByRole("link", { name: "내 조종 앵무 관계망 열기" }).click();
  await expect
    .poll(() =>
      page.evaluate(() => {
        const desktop = window as unknown as {
          __ANGMOO_DESKTOP_INVOCATIONS__: unknown[];
        };
        return desktop.__ANGMOO_DESKTOP_INVOCATIONS__;
      }),
    )
    .toContainEqual({
      command: "open_product_window",
      args: {
        kind: "relationship-graph",
        route:
          "/characters/character-static-owner/worlds/world-static-probe/relationship-graph",
      },
    });
  await expect(page).toHaveURL(/\/worlds\/world-static-probe\/relationships$/);
});

test("Tauri wide marker opens the shared static Studio route without a server page", async ({
  page,
}) => {
  await page.addInitScript(() => {
    const desktop = window as unknown as {
      __ANGMOO_DESKTOP_WINDOW__: { kind: "studio"; route: string };
      __TAURI__: {
        core: { invoke: () => Promise<void> };
      };
    };
    desktop.__ANGMOO_DESKTOP_WINDOW__ = {
      kind: "studio",
      route: "/studio",
    };
    desktop.__TAURI__ = { core: { invoke: async () => undefined } };
  });
  await page.goto("/");

  await expect(page.locator('[data-product-shell="creator-studio"]')).toBeVisible();
  await expect(page.locator("body")).toHaveAttribute(
    "data-angmoo-desktop-window",
    "studio",
  );
  await expect(page.getByText("지원하지 않는 Angmoo 경로입니다.")).toHaveCount(0);
});
