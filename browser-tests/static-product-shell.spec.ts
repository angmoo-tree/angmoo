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
  "/worlds/world-static-probe/posts/post-static-probe",
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
        graphProvider: "ladybug",
        launchToken: "static-route-probe-token-000000000000",
      },
    });
  });
  await page.route("http://127.0.0.1:8080/api/v1/**", async (route) => {
    expect(route.request().headers()["x-angmoo-launcher-token"]).toBe(
      "static-route-probe-token-000000000000",
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

test("static P4 evidence opens the exact World-scoped post thread", async ({
  page,
}) => {
  const requestedPaths: string[] = [];
  await page.route("http://127.0.0.1:8080/api/v1/**", async (route) => {
    const pathname = new URL(route.request().url()).pathname;
    requestedPaths.push(pathname);
    if (pathname === "/api/v1/worlds/mine/world-static-probe") {
      await route.fulfill({
        contentType: "application/json",
        json: {
          schema_version: "local-world-app-v1",
          surface: "world_app",
          world: {
            world_id: "world-static-probe",
            name: "Static World",
            tagline: "World-scoped post probe",
            banner_media_id: null,
            banner_alt_text: "",
            status: "published",
            visibility: "public",
            readiness_status: "publish_ready",
            membership_role: "owner",
            updated_at: "2026-08-22T00:00:00Z",
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
            intro: "Static post probe",
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
    if (
      pathname ===
      "/api/v1/worlds/world-static-probe/manual-social/posts/post-static-probe"
    ) {
      await route.fulfill({
        contentType: "application/json",
        json: {
          schema_version: "owner-manual-social-v1",
          world_id: "world-static-probe",
          owner_world_character_id: "wc-static-owner",
          items: [
            {
              id: "post-static-probe",
              world_id: "world-static-probe",
              author_world_character_id: "wc-static-autonomous",
              author_name: "Static Mango",
              title: "World-scoped evidence",
              body: "This post belongs only to Static World.",
              post_type: "text",
              reply_to_post_id: null,
              created_at: "2026-08-22T00:00:00Z",
              can_owner_reply: true,
            },
          ],
        },
        status: 200,
      });
      return;
    }
    await route.fallback();
  });

  await page.goto("/worlds/world-static-probe/posts/post-static-probe");
  await expect(page.getByRole("heading", { name: "게시글과 답글" })).toBeVisible();
  await expect(page.getByText("World-scoped evidence")).toBeVisible();
  await expect(page.getByRole("link", { name: "World Feed로 돌아가기" })).toHaveAttribute(
    "href",
    /\/worlds\/world-static-probe\/feed\/?$/,
  );
  expect(requestedPaths).toContain(
    "/api/v1/worlds/world-static-probe/manual-social/posts/post-static-probe",
  );
  expect(requestedPaths).not.toContain("/api/v1/posts/post-static-probe");
});

test("static installed relationship route always requests the Ladybug provider", async ({
  page,
}) => {
  const requestedProviders: Array<string | null> = [];
  await page.route("http://127.0.0.1:8080/api/v1/**", async (route) => {
    const url = new URL(route.request().url());
    if (url.pathname.endsWith("/relationship-graph")) {
      requestedProviders.push(url.searchParams.get("provider"));
      await route.fulfill({
        contentType: "application/json",
        json: {
          world_id: "world-static-probe",
          center_world_character_id: "wc-static-owner",
          nodes: [
            {
              world_character_id: "wc-static-owner",
              character_id: "character-static-owner",
              display_name: "Static Owner Parrot",
              is_center: true,
            },
          ],
          edges: [],
          evidence: [],
          meta: {
            template: "neighborhood",
            source: "ladybug",
            graph_status: "healthy",
            truncated: false,
            projection_lag_seconds: 0,
            revalidated_node_count: 1,
            revalidated_edge_count: 0,
            fallback_reason: null,
          },
        },
        status: 200,
      });
      return;
    }
    await route.fallback();
  });

  await page.goto(
    "/characters/character-static-owner/worlds/world-static-probe/relationship-graph",
  );
  await expect(page.getByText("설치형 Angmoo의 canonical 관계망 provider는 LadybugDB입니다.")).toBeVisible();
  await expect(page.getByText("관계망 최신 상태")).toBeVisible();
  expect(requestedProviders).toEqual(["ladybug"]);
});

test("installed wide-window bootstrap restores the exact relationship route", async ({
  page,
}) => {
  await page.addInitScript(() => {
    const desktop = window as unknown as {
      __TAURI__: {
        core: { invoke: (command: string) => Promise<unknown> };
      };
    };
    desktop.__TAURI__ = {
      core: {
        invoke: async (command) =>
          command === "desktop_runtime_status"
            ? {
                phase: "ready",
                apiBaseUrl: "http://127.0.0.1:8080",
                graphProvider: "ladybug",
                launchToken: "static-route-probe-token-000000000000",
              }
            : undefined,
      },
    };
  });
  await page.route("http://127.0.0.1:8080/api/v1/**", async (route) => {
    const url = new URL(route.request().url());
    if (url.pathname.endsWith("/relationship-graph")) {
      expect(url.searchParams.get("provider")).toBe("ladybug");
      await route.fulfill({
        contentType: "application/json",
        json: {
          world_id: "world-static-probe",
          center_world_character_id: "wc-static-owner",
          nodes: [
            {
              world_character_id: "wc-static-owner",
              character_id: "character-static-owner",
              display_name: "Static Owner Parrot",
              is_center: true,
            },
          ],
          edges: [],
          evidence: [],
          meta: {
            template: "neighborhood",
            source: "ladybug",
            graph_status: "healthy",
            truncated: false,
            projection_lag_seconds: 0,
            revalidated_node_count: 1,
            revalidated_edge_count: 0,
            fallback_reason: null,
          },
        },
        status: 200,
      });
      return;
    }
    await route.fallback();
  });

  const relationshipRoute =
    "/characters/character-static-owner/worlds/world-static-probe/relationship-graph?provider=ladybug";
  const bootstrap = new URLSearchParams({
    __angmoo_window_kind: "relationship-graph",
    __angmoo_window_route: relationshipRoute,
  });
  await page.goto(`/?${bootstrap.toString()}`);

  await expect(page.locator("body")).toHaveAttribute(
    "data-angmoo-desktop-window",
    "relationship-graph",
  );
  await expect(page.getByRole("heading", { name: "World 관계망" })).toBeVisible();
  await expect(page.getByText("관계망 최신 상태")).toBeVisible();
  await expect(page.getByText("LOCAL DEVICE")).toHaveCount(0);
  await expect(page).toHaveURL(new RegExp(`${relationshipRoute.replace("?", "\\?")}$`));
});

for (const bootstrapKind of ["phone", "main"] as const) {
  test(`installed Phone bootstrap ${bootstrapKind} opens Device Home instead of /index.html`, async ({
    page,
  }) => {
    await page.addInitScript(() => {
      const desktop = window as unknown as {
        __TAURI__: {
          core: { invoke: (command: string) => Promise<unknown> };
        };
      };
      desktop.__TAURI__ = {
        core: {
          invoke: async (command) =>
            command === "desktop_runtime_status"
              ? {
                  phase: "ready",
                  apiBaseUrl: "http://127.0.0.1:8080",
                  graphProvider: "ladybug",
                  launchToken: "static-route-probe-token-000000000000",
                }
              : undefined,
        },
      };
    });
    const bootstrap = new URLSearchParams({
      __angmoo_window_kind: bootstrapKind,
      __angmoo_window_route: "/",
    });

    await page.goto(`/index.html?${bootstrap.toString()}`);

    await expect(page.locator("body")).toHaveAttribute(
      "data-angmoo-desktop-window",
      "phone",
    );
    await expect(page.locator('main[data-product-surface="device-home"]')).toBeVisible();
    await expect(page.getByText("지원하지 않는 Angmoo 경로입니다.")).toHaveCount(0);
    await expect(page).toHaveURL(/\/$/);
  });
}

test("installed wide window keeps its route while runtime auth becomes ready", async ({
  page,
}) => {
  await page.addInitScript(() => {
    const desktop = window as unknown as {
      __ANGMOO_RUNTIME_CONFIG__?: unknown;
      __TAURI__: {
        core: { invoke: (command: string) => Promise<unknown> };
      };
    };
    delete desktop.__ANGMOO_RUNTIME_CONFIG__;
    desktop.__TAURI__ = {
      core: {
        invoke: async (command) => {
          if (command !== "desktop_runtime_status") return undefined;
          await new Promise((resolve) => window.setTimeout(resolve, 120));
          return {
            phase: "ready",
            apiBaseUrl: "http://127.0.0.1:8080",
            graphProvider: "ladybug",
            launchToken: "static-route-probe-token-000000000000",
          };
        },
      },
    };
  });
  await page.route("http://127.0.0.1:8080/api/v1/**", async (route) => {
    const url = new URL(route.request().url());
    if (url.pathname.endsWith("/relationship-graph")) {
      expect(url.searchParams.get("provider")).toBe("ladybug");
      await route.fulfill({
        contentType: "application/json",
        json: {
          world_id: "world-static-probe",
          center_world_character_id: "wc-static-owner",
          nodes: [
            {
              world_character_id: "wc-static-owner",
              character_id: "character-static-owner",
              display_name: "Static Owner Parrot",
              is_center: true,
            },
          ],
          edges: [],
          evidence: [],
          meta: {
            template: "neighborhood",
            source: "ladybug",
            graph_status: "healthy",
            truncated: false,
            projection_lag_seconds: 0,
            revalidated_node_count: 1,
            revalidated_edge_count: 0,
            fallback_reason: null,
          },
        },
        status: 200,
      });
      return;
    }
    await route.fallback();
  });

  const relationshipRoute =
    "/characters/character-static-owner/worlds/world-static-probe/relationship-graph?provider=ladybug";
  const bootstrap = new URLSearchParams({
    __angmoo_window_kind: "relationship-graph",
    __angmoo_window_route: relationshipRoute,
  });
  await page.goto(`/?${bootstrap.toString()}`);

  await expect(page.getByRole("heading", { name: "World 관계망" })).toBeVisible();
  await expect(page.getByText("관계망 최신 상태")).toBeVisible();
  await expect(page.getByRole("heading", { name: "제품 창 경로를 열지 못했습니다." })).toHaveCount(0);
  await expect(page.getByRole("heading", { name: "이 장치의 owner 준비" })).toHaveCount(0);
  await expect(page).toHaveURL(new RegExp(`${relationshipRoute.replace("?", "\\?")}$`));
});

test("wide-window route mismatch fails closed instead of rendering Device Home", async ({
  page,
}) => {
  await page.addInitScript(() => {
    const desktop = window as unknown as {
      __TAURI__: {
        core: { invoke: (command: string) => Promise<unknown> };
      };
    };
    desktop.__TAURI__ = {
      core: {
        invoke: async (command) =>
          command === "desktop_runtime_status"
            ? {
                phase: "ready",
                apiBaseUrl: "http://127.0.0.1:8080",
                graphProvider: "ladybug",
                launchToken: "static-route-probe-token-000000000000",
              }
            : undefined,
      },
    };
  });
  const bootstrap = new URLSearchParams({
    __angmoo_window_kind: "relationship-graph",
    __angmoo_window_route: "/",
  });

  await page.goto(`/?${bootstrap.toString()}`);

  await expect(
    page.getByRole("heading", { name: "제품 창 경로를 열지 못했습니다." }),
  ).toBeVisible();
  await expect(page.getByText("LOCAL DEVICE")).toHaveCount(0);
});

test("Tauri Phone keeps the local owner bootstrap form scrollable above navigation", async ({
  page,
}) => {
  await page.setViewportSize({ width: 433, height: 848 });
  await page.addInitScript(() => {
    const desktop = window as unknown as {
      __ANGMOO_DESKTOP_WINDOW__: { kind: "phone"; route: string };
      __TAURI__: {
        core: {
          invoke: (command: string) => Promise<unknown>;
        };
      };
    };
    desktop.__ANGMOO_DESKTOP_WINDOW__ = {
      kind: "phone",
      route: "/login?returnTo=%2F",
    };
    desktop.__TAURI__ = {
      core: {
        invoke: async (command) => {
          if (command === "desktop_runtime_status") {
            return {
              phase: "ready",
              apiBaseUrl: "http://127.0.0.1:8080",
              graphProvider: "ladybug",
              launchToken: "static-route-probe-token-000000000000",
            };
          }
          return undefined;
        },
      },
    };
  });
  await page.route("http://127.0.0.1:8080/api/v1/**", async (route) => {
    const pathname = new URL(route.request().url()).pathname;
    if (pathname === "/api/v1/auth/local/bootstrap") {
      await route.fulfill({
        contentType: "application/json",
        json: {
          state: "unclaimed",
          installation_id: "installation-static-owner-scroll",
          local_label: null,
          owner: null,
          candidates: [
            {
              user_id: "owner-static-probe",
              display_name: "Demo User",
              character_count: 1,
              world_count: 0,
              credential_count: 1,
              suggested: true,
            },
          ],
        },
        status: 200,
      });
      return;
    }
    await route.fallback();
  });

  await page.goto("/login?returnTo=%2F");
  await expect(page.getByRole("heading", { name: "이 장치의 owner 준비" })).toBeVisible();

  const scrollSurface = page.locator(".angmoo-main");
  await expect(scrollSurface).toHaveCSS("overflow-y", "auto");
  const initialGeometry = await scrollSurface.evaluate((node) => ({
    clientHeight: node.clientHeight,
    scrollHeight: node.scrollHeight,
    scrollTop: node.scrollTop,
  }));
  expect(initialGeometry.scrollHeight).toBeGreaterThan(initialGeometry.clientHeight);
  expect(initialGeometry.scrollTop).toBe(0);

  await scrollSurface.hover();
  await page.mouse.wheel(0, 900);
  await expect.poll(() => scrollSurface.evaluate((node) => node.scrollTop)).toBeGreaterThan(0);

  await scrollSurface.evaluate((node) => {
    node.scrollTop = node.scrollHeight;
  });
  const submitButton = page.getByRole("button", { name: "이 owner로 Angmoo 시작" });
  const mobileNavigation = page.getByRole("navigation", { name: "모바일 주요 메뉴" });
  await expect(submitButton).toBeVisible();
  const bottomGeometry = await Promise.all([
    submitButton.boundingBox(),
    mobileNavigation.boundingBox(),
  ]);
  expect(bottomGeometry[0]).not.toBeNull();
  expect(bottomGeometry[1]).not.toBeNull();
  expect(bottomGeometry[0]!.y + bottomGeometry[0]!.height).toBeLessThanOrEqual(
    bottomGeometry[1]!.y,
  );
});

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
          invoke: (command: string, args?: Record<string, unknown>) => Promise<unknown>;
        };
      };
    };
    desktop.__ANGMOO_DESKTOP_INVOCATIONS__ = [];
    desktop.__ANGMOO_DESKTOP_WINDOW__ = { kind: "phone", route: "/" };
    desktop.__TAURI__ = {
      core: {
        invoke: async (command, args) => {
          if (command === "desktop_runtime_status") {
            return {
              phase: "ready",
              apiBaseUrl: "http://127.0.0.1:8080",
              graphProvider: "ladybug",
              launchToken: "static-route-probe-token-000000000000",
            };
          }
          desktop.__ANGMOO_DESKTOP_INVOCATIONS__.push({ command, args });
          return undefined;
        },
      },
    };
  });
  await page.goto("/");

  await expect(page.locator("body")).toHaveAttribute(
    "data-angmoo-desktop-window",
    "phone",
  );
  await expect(page.locator("body")).toHaveAttribute("data-angmoo-window-drag", "manual");
  await expect(page.locator("[data-tauri-drag-region]")).toHaveCount(0);
  await expect(page.locator('[data-window-route="/"]')).toHaveAttribute(
    "data-window-drag-disabled",
    "true",
  );
  const phoneGeometry = await page.locator('[data-product-shell="device"]').evaluate((node) => {
    const rect = node.getBoundingClientRect();
    const root = node.parentElement;
    return {
      height: rect.height,
      rootBackground: root ? getComputedStyle(root).backgroundColor : null,
      viewportHeight: window.innerHeight,
      viewportWidth: window.innerWidth,
      width: rect.width,
    };
  });
  expect(Math.abs(phoneGeometry.width - phoneGeometry.viewportWidth)).toBeLessThanOrEqual(1);
  expect(Math.abs(phoneGeometry.height - phoneGeometry.viewportHeight)).toBeLessThanOrEqual(1);
  expect(phoneGeometry.rootBackground).toBe("rgba(0, 0, 0, 0)");

  const radius = Math.min(
    42,
    Math.max(26, phoneGeometry.viewportWidth * 0.0725),
  );
  const cornerOffset = radius - radius / Math.sqrt(2);
  const resizeProbes = [
    {
      cursor: "ns-resize",
      direction: "north",
      x: phoneGeometry.viewportWidth / 2,
      y: 2,
    },
    {
      cursor: "nesw-resize",
      direction: "north-east",
      x: phoneGeometry.viewportWidth - cornerOffset,
      y: cornerOffset,
    },
    {
      cursor: "ew-resize",
      direction: "east",
      x: phoneGeometry.viewportWidth - 2,
      y: phoneGeometry.viewportHeight / 2,
    },
    {
      cursor: "nwse-resize",
      direction: "south-east",
      x: phoneGeometry.viewportWidth - cornerOffset,
      y: phoneGeometry.viewportHeight - cornerOffset,
    },
    {
      cursor: "ns-resize",
      direction: "south",
      x: phoneGeometry.viewportWidth / 2,
      y: phoneGeometry.viewportHeight - 2,
    },
    {
      cursor: "nesw-resize",
      direction: "south-west",
      x: cornerOffset,
      y: phoneGeometry.viewportHeight - cornerOffset,
    },
    {
      cursor: "ew-resize",
      direction: "west",
      x: 2,
      y: phoneGeometry.viewportHeight / 2,
    },
    {
      cursor: "nwse-resize",
      direction: "north-west",
      x: cornerOffset,
      y: cornerOffset,
    },
  ] as const;
  for (const probe of resizeProbes) {
    await page.locator('[data-product-shell="device"]').dispatchEvent("pointermove", {
      buttons: 0,
      clientX: probe.x,
      clientY: probe.y,
      isPrimary: true,
      pointerType: "mouse",
    });
    await expect(page.locator("html")).toHaveAttribute(
      "data-angmoo-window-resize",
      probe.direction,
    );
    await expect(page.locator("html")).toHaveCSS("cursor", probe.cursor);
    await page.locator('[data-product-shell="device"]').dispatchEvent("pointerdown", {
      button: 0,
      buttons: 1,
      clientX: probe.x,
      clientY: probe.y,
      isPrimary: true,
      pointerType: "mouse",
    });
  }
  await expect
    .poll(() =>
      page.evaluate(() => {
        const desktop = window as unknown as {
          __ANGMOO_DESKTOP_INVOCATIONS__: unknown[];
        };
        return desktop.__ANGMOO_DESKTOP_INVOCATIONS__;
      }),
    )
    .toEqual(
      resizeProbes.map(({ direction }) => ({
        command: "start_product_window_resize",
        args: { direction },
      })),
    );
  await page.evaluate(() => {
    const desktop = window as unknown as {
      __ANGMOO_DESKTOP_INVOCATIONS__: unknown[];
    };
    desktop.__ANGMOO_DESKTOP_INVOCATIONS__ = [];
  });
  await page.locator('[data-product-shell="device"]').dispatchEvent("pointermove", {
    buttons: 0,
    clientX: phoneGeometry.viewportWidth / 2,
    clientY: phoneGeometry.viewportHeight / 2,
    isPrimary: true,
    pointerType: "mouse",
  });
  await expect(page.locator("html")).not.toHaveAttribute("data-angmoo-window-resize", /.+/);

  await page.locator('[data-product-shell="device"]').dispatchEvent("pointerdown", {
    button: 0,
    buttons: 1,
    clientX: phoneGeometry.viewportWidth / 2,
    clientY: phoneGeometry.viewportHeight / 2,
    isPrimary: true,
    pointerType: "mouse",
  });
  await expect
    .poll(() =>
      page.evaluate(() => {
        const desktop = window as unknown as {
          __ANGMOO_DESKTOP_INVOCATIONS__: Array<{ command: string }>;
        };
        return desktop.__ANGMOO_DESKTOP_INVOCATIONS__.map(({ command }) => command);
      }),
    )
    .toEqual(["start_product_window_drag"]);

  await expect(page.getByLabel("Memory Explorer는 후속 단계에서 연결됩니다")).toHaveAttribute(
    "data-disabled",
    "true",
  );
  await page.getByRole("link", { name: "Creator Studio 열기" }).dispatchEvent("pointerdown", {
    button: 0,
    buttons: 1,
    isPrimary: true,
    pointerType: "mouse",
  });
  await expect
    .poll(() =>
      page.evaluate(() => {
        const desktop = window as unknown as {
          __ANGMOO_DESKTOP_INVOCATIONS__: Array<{ command: string }>;
        };
        return desktop.__ANGMOO_DESKTOP_INVOCATIONS__.filter(
          ({ command }) => command === "start_product_window_drag",
        ).length;
      }),
    )
    .toBe(1);
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
          invoke: (command: string, args?: Record<string, unknown>) => Promise<unknown>;
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
          if (command === "desktop_runtime_status") {
            return {
              phase: "ready",
              apiBaseUrl: "http://127.0.0.1:8080",
              graphProvider: "ladybug",
              launchToken: "static-route-probe-token-000000000000",
            };
          }
          desktop.__ANGMOO_DESKTOP_INVOCATIONS__.push({ command, args });
          return undefined;
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

test("static Device Home authenticates sidecar media before rendering a blob URL", async ({
  page,
}) => {
  const mediaRequests: string[] = [];
  await page.route("http://127.0.0.1:8080/**", async (route) => {
    expect(route.request().headers()["x-angmoo-launcher-token"]).toBe(
      "static-route-probe-token-000000000000",
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
    if (pathname === "/api/v1/worlds/mine") {
      await route.fulfill({
        contentType: "application/json",
        json: {
          schema_version: "local-world-surface-v1",
          surface: "device_home",
          items: [
            {
              world_id: "world-media-probe",
              name: "Media World",
              tagline: "Authenticated media probe",
              banner_media_id: "/media/probe.png",
              banner_alt_text: "",
              status: "published",
              visibility: "public",
              readiness_status: "publish_ready",
              membership_role: "owner",
              updated_at: "2026-08-21T00:00:00Z",
              launchable: true,
              launch_block_reason: null,
            },
          ],
          next_cursor: null,
        },
        status: 200,
      });
      return;
    }
    if (pathname === "/api/v1/runtime/status") {
      await route.fulfill({
        contentType: "application/json",
        json: {
          schema_version: "local-runtime-status-v1",
          installation_state: "ready",
        },
        status: 200,
      });
      return;
    }
    if (pathname === "/media/probe.png") {
      mediaRequests.push(route.request().url());
      await route.fulfill({
        body: Buffer.from(
          "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9Wl2lU8AAAAASUVORK5CYII=",
          "base64",
        ),
        contentType: "image/png",
        status: 200,
      });
      return;
    }
    await route.fulfill({
      contentType: "application/json",
      json: { detail: "unexpected_static_media_probe" },
      status: 503,
    });
  });

  await page.goto("/");

  await expect(page.getByRole("link", { name: "Media World World 열기" })).toBeVisible();
  await expect(page.locator('img[src^="blob:"]')).toBeVisible();
  expect(mediaRequests).toHaveLength(1);
});

test("Tauri wide marker opens the shared static Studio route without a server page", async ({
  page,
}) => {
  await page.addInitScript(() => {
    const desktop = window as unknown as {
      __ANGMOO_DESKTOP_WINDOW__: { kind: "studio"; route: string };
      __TAURI__: {
        core: { invoke: (command: string) => Promise<unknown> };
      };
    };
    desktop.__ANGMOO_DESKTOP_WINDOW__ = {
      kind: "studio",
      route: "/studio",
    };
    desktop.__TAURI__ = {
      core: {
        invoke: async (command) =>
          command === "desktop_runtime_status"
            ? {
                phase: "ready",
                apiBaseUrl: "http://127.0.0.1:8080",
                graphProvider: "ladybug",
                launchToken: "static-route-probe-token-000000000000",
              }
            : undefined,
      },
    };
  });
  await page.goto("/");

  await expect(page.locator('[data-product-shell="creator-studio"]')).toBeVisible();
  await expect(page.locator("body")).toHaveAttribute(
    "data-angmoo-desktop-window",
    "studio",
  );
  await expect(page.getByText("지원하지 않는 Angmoo 경로입니다.")).toHaveCount(0);
});
