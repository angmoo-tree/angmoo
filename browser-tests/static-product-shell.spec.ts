import { expect, test } from "@playwright/test";

const ROUTES = [
  "/",
  "/studio",
  "/studio/import",
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
  "/agents/new",
  "/agents",
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

function staticProfilePost(id: string, title: string) {
  return {
    id,
    author_name: "Profile Scroll Parrot",
    author_handle: "profile_scroll",
    author_avatar_url: null,
    title,
    body: `${title} body`,
    info_kind: null,
    source_name: null,
    source_url: null,
    observed_at: null,
    location_label: null,
    created_at: "2026-08-30T00:00:00Z",
    post_type: "post",
    author_user_id: null,
    author_character_id: "character-profile-scroll",
    mentioned_characters: [],
    reply_to_post_id: null,
    quote_post_id: null,
    repost_of_post_id: null,
    comment_count: 0,
    like_count: 0,
    reply_count: 0,
    repost_count: 0,
    quote_count: 0,
    quoted_post: null,
    reposted_post: null,
    report_hidden: false,
    media: [],
  };
}

function staticAgentDetail(characterId: string) {
  return {
    character: {
      id: characterId,
      owner_id: "owner-static-probe",
      name: "Profile Scroll Parrot",
      handle: "profile_scroll",
      avatar_url: null,
      banner_url: null,
      one_liner: "Device owner pagination probe",
      personality: "calm",
      speech_style: "brief",
      worldview: "local",
      topic_preferences: "testing",
      safety_rules: "safe",
      status: "active",
      execution_mode: "local",
      persona_summary: "Device owner pagination probe",
    },
    state: null,
    credential: null,
    settings: {
      character_id: characterId,
      auto_enabled: false,
      activity_level: "normal",
      activity_interval_minutes: 60,
      comment_cooldown_minutes: 30,
      max_comments_per_day: 10,
      post_cooldown_hours: 2,
      max_posts_per_day: 10,
      allow_post: true,
      allow_reply: true,
      allow_like: true,
      allow_repost: false,
      allow_follow: false,
      allow_unfollow: false,
      allow_observe: true,
      tendency_summary: "",
      tendency_action_ranges: {},
      tendency_analysis_ready: true,
      tendency_updated_at: null,
      tendency_error: null,
      active_hours_start: "10:00",
      active_hours_end: "20:00",
      writing_temperature: 0.7,
      writing_repetition_level: "normal",
      updated_at: "2026-08-30T00:00:00Z",
    },
    image_settings: {
      character_id: characterId,
      image_generation_enabled: false,
      image_key_mode: "disabled",
      max_images_per_day: 0,
      pollinations_image_model: "replicate-zimage-turbo-lora",
      seed_image_url: null,
      key_fingerprint: null,
      has_pollinations_api_key: false,
      replicate_key_fingerprint: null,
      has_replicate_api_key: false,
      service_image_available: false,
      service_image_model: "",
      service_image_model_label: "",
      service_free_quota_limit: 0,
      service_free_quota_used: 0,
      service_free_quota_remaining: 0,
      service_free_quota_date: null,
      visual_identity_prompt_available: false,
      visual_identity_prompt: null,
      visual_identity_mode: "none",
      visual_identity_source_hash: null,
      updated_at: "2026-08-30T00:00:00Z",
    },
    promotion_usage: {
      promotion_usage_allowed: false,
      promotion_usage_agreed_at: null,
      promotion_usage_revoked_at: null,
      promotion_usage_policy_version: null,
    },
    assigned_slot: null,
    activity_profile_readiness: {
      ready: true,
      source: "legacy_tendency",
      reason_code: null,
      world_id: null,
      world_character_id: null,
    },
    activity_summary: {
      within_active_hours: true,
      timezone: "Asia/Seoul",
      allowed_actions: [],
      blocked_reasons: {},
      last_activity_at: null,
      next_activity_at: null,
      manual_run_available_at: null,
      first_greeting_available_at: null,
      today_comment_count: 0,
      max_comments_per_day: 10,
      today_post_count: 0,
      max_posts_per_day: 10,
      today_like_count: 0,
    },
    recent_activity: [],
  };
}

for (const route of ROUTES) {
  test(`direct-open static route ${route}`, async ({ page }) => {
    await page.goto(route);
    await expect(page.getByText("제품 화면을 준비하고 있습니다...")).toHaveCount(0);
    await expect(page.getByText("지원하지 않는 Angmoo 경로입니다.")).toHaveCount(0);
    await expect(page.locator("body")).not.toBeEmpty();
    await expect(page.locator("main")).toHaveCount(1);
    await expect(page.locator("main main")).toHaveCount(0);
  });
}

test("static Phone routes share one frame, one scroll owner, and supported navigation", async ({
  page,
}) => {
  for (const viewport of [
    { width: 360, height: 800 },
    { width: 390, height: 844 },
    { width: 436, height: 880 },
    { width: 1440, height: 900 },
  ]) {
    await page.setViewportSize(viewport);
    await page.goto("/agents");

    const frame = page.locator('[data-product-shell="device"]');
    await expect(frame).toHaveCount(1);
    await expect(page.locator('[data-device-shell="phone"]')).toHaveCount(1);
    await expect(page.locator('[data-device-scroll-owner="true"]')).toHaveCount(1);
    await expect(page.locator(".angmoo-left-rail, .angmoo-right-rail")).toHaveCount(0);

    const navigation = page.getByRole("navigation", { name: "모바일 주요 메뉴" });
    await expect(navigation.locator('[aria-current="page"]')).toHaveCount(1);
    await expect(navigation.locator("a")).toHaveCount(4);
    expect(
      await navigation
        .locator("a")
        .evaluateAll((anchors) => anchors.map((anchor) => anchor.getAttribute("href"))),
    ).toEqual(["/", "/posts", "/agents", "/settings"]);
    await expect(navigation.locator('a[href="/agents"]')).toHaveAttribute(
      "aria-current",
      "page",
    );

    const geometry = await frame.evaluate((node) => {
      const rect = node.getBoundingClientRect();
      return {
        documentOverflow:
          document.documentElement.scrollWidth - document.documentElement.clientWidth,
        left: rect.left,
        viewportWidth: window.innerWidth,
        width: rect.width,
      };
    });
    expect(geometry.documentOverflow).toBe(0);
    expect(geometry.width).toBeLessThanOrEqual(436);
    if (viewport.width <= 436) {
      expect(Math.abs(geometry.width - viewport.width)).toBeLessThanOrEqual(1);
    } else {
      expect(Math.abs(geometry.left - (viewport.width - geometry.width) / 2)).toBeLessThanOrEqual(1);
    }
  }
});

test("Tauri Phone reserves titlebar controls above page-owned header actions", async ({
  page,
}) => {
  await page.addInitScript(() => {
    const desktop = window as unknown as {
      __ANGMOO_DESKTOP_WINDOW__: { kind: "phone"; route: string };
      __TAURI__: {
        core: {
          invoke: (command: string) => Promise<unknown>;
        };
      };
    };
    desktop.__ANGMOO_DESKTOP_WINDOW__ = { kind: "phone", route: "/agents" };
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

  for (const viewport of [
    { width: 360, height: 800 },
    { width: 390, height: 844 },
    { width: 433, height: 848 },
    { width: 436, height: 880 },
  ]) {
    await page.setViewportSize(viewport);
    await page.goto("/");

    const controls = page.locator('[data-window-route="/agents"]');
    const createAction = page.getByRole("link", { name: "만들기", exact: true });
    const inset = page.locator('[data-device-titlebar-inset="true"]');
    await expect(controls).toBeVisible();
    await expect(createAction).toBeVisible();
    await expect(inset).toBeVisible();

    const [controlsBox, createBox, insetBox] = await Promise.all([
      controls.boundingBox(),
      createAction.boundingBox(),
      inset.boundingBox(),
    ]);
    expect(controlsBox).not.toBeNull();
    expect(createBox).not.toBeNull();
    expect(insetBox).not.toBeNull();
    expect(createBox!.y).toBeGreaterThanOrEqual(controlsBox!.y + controlsBox!.height);
    expect(insetBox!.height).toBeGreaterThanOrEqual(controlsBox!.y + controlsBox!.height);
  }

  const navigation = page.getByRole("navigation", { name: "모바일 주요 메뉴" });
  await navigation.getByRole("link", { name: "피드" }).click();
  await expect(page).toHaveURL(/\/posts$/);
  await expect
    .poll(() =>
      page.evaluate(() => {
        const desktop = window as unknown as {
          __ANGMOO_DESKTOP_WINDOW__: { kind: string; route: string };
        };
        return desktop.__ANGMOO_DESKTOP_WINDOW__;
      }),
    )
    .toEqual({ kind: "phone", route: "/posts" });
  await expect(navigation.locator('a[href="/posts"]')).toHaveAttribute(
    "aria-current",
    "page",
  );
});

test("static Browser canonicalizes legacy World creator aliases", async ({ page }) => {
  await page.goto("/worlds/new?source=legacy&tag=a&tag=b&empty=");
  await expect(page).toHaveURL(
    /\/studio\/worlds\/new\?source=legacy&tag=a&tag=b&empty=$/,
  );
  await expect(page.locator('[data-product-shell="creator-studio"]')).toBeVisible();

  await page.goto(
    "/worlds/world-static-probe/creator?source=legacy&focus=a&focus=b&empty=",
  );
  await expect(page).toHaveURL(
    /\/studio\/worlds\/world-static-probe\?source=legacy&focus=a&focus=b&empty=$/,
  );
  await expect(page.locator('[data-product-shell="creator-studio"]')).toBeVisible();
});

test("static feed paginates on the Device scroll owner and keeps hosted-only routes inert", async ({
  page,
}) => {
  const feedRequests: string[] = [];
  await page.route("http://127.0.0.1:8080/api/v1/**", async (route) => {
    const url = new URL(route.request().url());
    if (url.pathname !== "/api/v1/feed") {
      await route.fallback();
      return;
    }
    const cursor = url.searchParams.get("cursor");
    feedRequests.push(`${url.pathname}${url.search}`);
    await route.fulfill({
      contentType: "application/json",
      json: {
        items: [
          {
            id: cursor ? "post-static-second" : "post-static-first",
            author_name: cursor ? "두 번째 앵무" : "첫 번째 앵무",
            author_handle: cursor ? "second_bird" : "first_bird",
            author_avatar_url: null,
            title: cursor ? "두 번째 페이지" : "첫 번째 페이지",
            body: cursor ? "Device scroll owner가 다음 글을 불렀어요." : "@friend 안녕!",
            info_kind: null,
            source_name: null,
            source_url: null,
            observed_at: null,
            location_label: null,
            created_at: "2026-08-30T00:00:00Z",
            post_type: "post",
            author_user_id: null,
            author_character_id: cursor ? "character-second" : "character-first",
            mentioned_characters: cursor
              ? []
              : [
                  {
                    handle: "friend",
                    character_id: "character-friend",
                    name: "친구 앵무",
                  },
                ],
            reply_to_post_id: null,
            quote_post_id: null,
            repost_of_post_id: null,
            comment_count: 0,
            like_count: 0,
            reply_count: 0,
            repost_count: 0,
            quote_count: 0,
            quoted_post: null,
            reposted_post: null,
            report_hidden: false,
            media: [],
          },
        ],
        next_cursor: cursor ? null : "page-two",
      },
      status: 200,
    });
  });

  await page.goto("/posts");
  await expect(page.getByText("첫 번째 페이지", { exact: true })).toBeVisible();
  await expect(page.locator('a[href^="/profiles/"]')).toHaveCount(0);
  const unavailableRoutes = page.locator('[data-product-route-unavailable="true"]');
  await expect(unavailableRoutes).toHaveCount(2);
  await expect(unavailableRoutes.first()).toHaveAttribute("aria-disabled", "true");
  await expect(unavailableRoutes.first()).toHaveAttribute("role", "link");
  await expect(unavailableRoutes.first()).toHaveAttribute(
    "title",
    "현재 앱에서는 열 수 없는 화면입니다.",
  );

  const unavailableMention = unavailableRoutes.filter({ hasText: "@friend" });
  await unavailableMention.hover();
  await expect(unavailableMention).toHaveCSS("cursor", "not-allowed");
  await expect(unavailableMention).toHaveCSS("text-decoration-line", "none");
  const feedUrl = page.url();
  await unavailableMention.click({ force: true });
  expect(page.url()).toBe(feedUrl);
  await expect(page.locator('a[href^="/posts/post-static-first"]')).not.toHaveCount(0);

  const scrollSurface = page.locator('[data-device-scroll-owner="true"]');
  await scrollSurface.evaluate((node) => {
    node.scrollTop = node.scrollHeight;
    node.dispatchEvent(new Event("scroll"));
  });

  await expect(page.getByText("두 번째 페이지", { exact: true })).toBeVisible();
  expect(feedRequests.some((request) => request.includes("cursor=page-two"))).toBe(true);
});

test("static feed pull-to-refresh follows a touch sequence on the Device scroll owner", async ({
  page,
}) => {
  let feedReadCount = 0;
  await page.addInitScript(() => {
    if (!("ontouchstart" in window)) {
      Object.defineProperty(window, "ontouchstart", {
        configurable: true,
        value: null,
      });
    }
  });
  await page.route("http://127.0.0.1:8080/api/v1/feed**", async (route) => {
    feedReadCount += 1;
    await route.fulfill({
      contentType: "application/json",
      json: {
        items: [staticProfilePost("post-touch-refresh", "Touch refresh probe")],
        next_cursor: null,
      },
      status: 200,
    });
  });

  await page.goto("/posts");
  await expect(page.getByText("Touch refresh probe", { exact: true })).toBeVisible();
  expect(feedReadCount).toBe(1);

  const scrollSurface = page.locator('[data-device-scroll-owner="true"]');
  await scrollSurface.evaluate((node) => {
    const touchAt = (clientY: number) => {
      const init = {
        identifier: 1,
        target: node,
        clientX: 120,
        clientY,
        screenX: 120,
        screenY: clientY,
        pageX: 120,
        pageY: clientY,
        radiusX: 1,
        radiusY: 1,
        rotationAngle: 0,
        force: 1,
      };
      return typeof Touch === "function" ? new Touch(init) : (init as unknown as Touch);
    };
    const dispatch = (type: string, touches: Touch[]) => {
      node.dispatchEvent(
        new TouchEvent(type, {
          bubbles: true,
          cancelable: true,
          touches,
        }),
      );
    };

    node.scrollTop = 0;
    dispatch("touchstart", [touchAt(100)]);
    dispatch("touchmove", [touchAt(180)]);
    dispatch("touchend", []);
  });

  await expect.poll(() => feedReadCount).toBe(2);
});

test("static Agent profile feed paginates on the Device scroll owner", async ({
  page,
}) => {
  const profileFeedRequests: string[] = [];
  await page.route("http://127.0.0.1:8080/api/v1/**", async (route) => {
    const url = new URL(route.request().url());
    const characterId = "character-profile-scroll";
    if (url.pathname === `/api/v1/agents/${characterId}`) {
      await route.fulfill({
        contentType: "application/json",
        json: staticAgentDetail(characterId),
        status: 200,
      });
      return;
    }
    if (url.pathname === `/api/v1/profiles/characters/${characterId}`) {
      await route.fulfill({
        contentType: "application/json",
        json: {
          profile: {
            profile_type: "character",
            id: characterId,
            display_name: "Profile Scroll Parrot",
            handle: "profile_scroll",
            avatar_url: null,
            banner_url: null,
          },
          execution_mode: "local",
          post_count: 2,
          reply_count: 0,
          liked_post_count: 0,
          received_like_count: 0,
          follower_count: 0,
          user_follower_count: 0,
          character_follower_count: 0,
          following_count: 0,
          one_liner: "Device owner pagination probe",
        },
        status: 200,
      });
      return;
    }
    if (url.pathname === `/api/v1/profiles/characters/${characterId}/feed`) {
      const cursor = url.searchParams.get("cursor");
      profileFeedRequests.push(`${url.pathname}${url.search}`);
      await route.fulfill({
        contentType: "application/json",
        json: {
          items: [
            staticProfilePost(
              cursor ? "profile-post-second" : "profile-post-first",
              cursor ? "Profile second page" : "Profile first page",
            ),
          ],
          next_cursor: cursor ? null : "profile-page-two",
        },
        status: 200,
      });
      return;
    }
    await route.fallback();
  });

  await page.goto("/agents/character-profile-scroll");
  await expect(page.getByText("Profile first page", { exact: true })).toBeVisible();

  const scrollSurface = page.locator('[data-device-scroll-owner="true"]');
  await expect
    .poll(async () => {
      await scrollSurface.evaluate((node) => {
        node.scrollTop = node.scrollHeight;
        node.dispatchEvent(new Event("scroll"));
      });
      return profileFeedRequests.filter((request) => request.includes("cursor=")).length;
    })
    .toBe(1);

  await expect(page.getByText("Profile second page", { exact: true })).toBeVisible();
  expect(
    profileFeedRequests.some((request) => request.includes("cursor=profile-page-two")),
  ).toBe(true);
});

test("static local creation stays available beyond the former hosted count cap", async ({
  page,
}) => {
  const pageErrors: string[] = [];
  page.on("pageerror", (error) => pageErrors.push(error.stack ?? error.message));
  await page.route("http://127.0.0.1:8080/api/v1/agents", async (route) => {
    expect(route.request().method()).toBe("GET");
    await route.fulfill({
      contentType: "application/json",
      json: [
        ...Array.from({ length: 3 }, (_, index) => ({
          character: {
            id: `llm-static-${index}`,
            execution_mode: "llm",
            name: `LLM Static ${index}`,
          },
          settings: { auto_enabled: false },
          assigned_slot: null,
        })),
        ...Array.from({ length: 3 }, (_, index) => ({
          character: {
            id: `local-static-${index}`,
            execution_mode: "local",
            name: `Local Static ${index}`,
          },
          settings: { auto_enabled: false },
          assigned_slot: null,
        })),
      ],
      status: 200,
    });
  });

  await page.goto("/agents/new");

  await expect(page.getByRole("heading", { name: "앵무 만들기" })).toBeVisible();
  await expect(page.getByText("앵무 생성 제한")).toHaveCount(0);
  await expect(page.getByText("한도 도달")).toHaveCount(0);
  await expect(page.getByText("3/3")).toHaveCount(0);

  const llmMode = page.getByRole("button", { name: /서버 LLM 앵무/ });
  const localMode = page.getByRole("button", { name: /외부 연결 앵무/ });
  await expect(llmMode).toBeEnabled();
  await expect(localMode).toBeEnabled();
  await localMode.click();
  await expect(page.getByRole("heading", { name: "외부 연결 앵무 만들기" })).toBeVisible();
  expect(pageErrors).toEqual([]);
});

test("Tauri Phone retries Creator Studio return without creating a duplicate Character", async ({
  page,
}) => {
  const fixtureRoute =
    "/agents/new?worldId=world-static-probe&returnTo=%2Fstudio%2Fworlds%2Fworld-static-probe";
  await page.addInitScript((route) => {
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
    desktop.__ANGMOO_DESKTOP_WINDOW__ = { kind: "phone", route };
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
          const studioOpenCount = desktop.__ANGMOO_DESKTOP_INVOCATIONS__.filter(
            (invocation) => invocation.command === "open_product_window",
          ).length;
          if (command === "open_product_window" && studioOpenCount === 1) {
            throw new Error("static_studio_open_probe");
          }
          return undefined;
        },
      },
    };
  }, fixtureRoute);

  let createRequestCount = 0;
  const agentRequests: string[] = [];
  await page.route("http://127.0.0.1:8080/api/v1/**", async (route) => {
    const url = new URL(route.request().url());
    if (url.pathname.startsWith("/api/v1/agents")) {
      agentRequests.push(url.pathname);
    }
    if (url.pathname === "/api/v1/agents" && route.request().method() === "GET") {
      await route.fulfill({
        contentType: "application/json",
        json: [],
        status: 200,
      });
      return;
    }
    if (url.pathname === "/api/v1/agents" && route.request().method() === "POST") {
      createRequestCount += 1;
      await route.fulfill({
        contentType: "application/json",
        json: {
          character: {
            id: "char-new-1",
            name: "미도리야 이즈쿠",
            handle: "midoriya_izuku",
            execution_mode: "llm",
            status: "inactive",
          },
        },
        status: 201,
      });
      return;
    }
    await route.fallback();
  });

  await page.goto(fixtureRoute);
  await page.getByLabel("API key").fill("static-fixture-api-key");
  await page.getByRole("button", { name: "입력 계속하기" }).click();
  await page.getByLabel("이름", { exact: true }).fill("미도리야 이즈쿠");
  await page.getByRole("textbox", { name: /^핸들 / }).fill("midoriya_izuku");
  await page
    .getByPlaceholder("조금 소심하지만, 먼저 움직이고 싶은 히어로 지망생입니다!")
    .fill("계승한 힘을 바르게 쓰려는 히어로 지망생");
  await page.getByRole("button", { name: "다음" }).click();
  await page.getByLabel("성격").fill("관찰력이 뛰어나고 책임감이 강하다.");
  await page.getByRole("button", { name: "다음" }).click();
  await page.getByRole("button", { name: "최종 확인" }).click();
  await page.getByRole("button", { name: "앵무 만들기" }).click();

  await expect(
    page.locator('[data-world-fixture-return-status="failed"]'),
  ).toBeVisible();
  await expect(page.getByText("캐릭터 생성은 완료되었습니다.")).toBeVisible();
  await expect(
    page.getByText(/캐릭터는 정상적으로 생성됐지만 Creator Studio를 열지 못했습니다/),
  ).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "제품 창 경로를 열지 못했습니다." }),
  ).toHaveCount(0);
  expect(createRequestCount).toBe(1);
  expect(agentRequests).not.toContain("/api/v1/agents/new");
  await expect
    .poll(() =>
      page.evaluate(() => {
        const desktop = window as unknown as {
          __ANGMOO_DESKTOP_WINDOW__: { kind: string; route: string };
        };
        return desktop.__ANGMOO_DESKTOP_WINDOW__;
      }),
    )
    .toEqual({ kind: "phone", route: fixtureRoute });

  await page.getByRole("button", { name: "Creator Studio로 다시 돌아가기" }).click();

  await expect(
    page.locator('[data-world-fixture-return-status="opened"]'),
  ).toBeVisible();
  expect(createRequestCount).toBe(1);
  await expect
    .poll(() =>
      page.evaluate(() => {
        const desktop = window as unknown as {
          __ANGMOO_DESKTOP_INVOCATIONS__: unknown[];
        };
        return desktop.__ANGMOO_DESKTOP_INVOCATIONS__;
      }),
    )
    .toEqual([
      {
        command: "open_product_window",
        args: {
          kind: "studio",
          route:
            "/studio/worlds/world-static-probe?createdCharacterId=char-new-1",
        },
      },
      {
        command: "open_product_window",
        args: {
          kind: "studio",
          route:
            "/studio/worlds/world-static-probe?createdCharacterId=char-new-1",
        },
      },
    ]);
  await expect
    .poll(() =>
      page.evaluate(() => {
        const desktop = window as unknown as {
          __ANGMOO_DESKTOP_WINDOW__: { kind: string; route: string };
        };
        return desktop.__ANGMOO_DESKTOP_WINDOW__;
      }),
    )
    .toEqual({ kind: "phone", route: fixtureRoute });

  await page.getByRole("button", { name: "생성된 앵무 보기" }).click();
  await expect
    .poll(() =>
      page.evaluate(() => {
        const desktop = window as unknown as {
          __ANGMOO_DESKTOP_WINDOW__: { kind: string; route: string };
        };
        return desktop.__ANGMOO_DESKTOP_WINDOW__;
      }),
    )
    .toEqual({ kind: "phone", route: "/agents/char-new-1" });
  await expect(page).toHaveURL(/\/agents\/char-new-1$/);
  expect(createRequestCount).toBe(1);
});

test("returned Studio preselects the created Character and clears the query after entry", async ({
  page,
}) => {
  const studioRoute =
    "/studio/worlds/world-static-probe?createdCharacterId=char-new-1";
  await page.addInitScript((route) => {
    const desktop = window as unknown as {
      __ANGMOO_DESKTOP_WINDOW__: { kind: "studio"; route: string };
      __TAURI__: {
        core: {
          invoke: (command: string) => Promise<unknown>;
        };
      };
    };
    desktop.__ANGMOO_DESKTOP_WINDOW__ = { kind: "studio", route };
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
  }, studioRoute);

  let entryRequestCount = 0;
  let entryBody: Record<string, unknown> | null = null;
  await page.route("http://127.0.0.1:8080/api/v1/**", async (route) => {
    const url = new URL(route.request().url());
    if (
      url.pathname === "/api/v1/worlds/world-static-probe/creator-context" &&
      route.request().method() === "GET"
    ) {
      await route.fulfill({
        contentType: "application/json",
        json: {
          membership_role: "owner",
          world: {
            id: "world-static-probe",
            slug: "static-world",
            name: "히어로 학교",
            tagline: "영웅을 꿈꾸는 학생들의 학교",
            setting_description: "충분히 긴 세계관 설명",
            daily_life_description: "충분히 긴 일상 설명",
            genre_tags: ["히어로"],
            tone_tags: ["성장"],
            timezone: "Asia/Seoul",
            language: "ko",
            visibility: "private",
            join_policy: "approval_required",
            additional_generation_guidance: "",
            places: [],
            roles: [
              {
                key: "student",
                name: "학생",
                description: "히어로 지망생",
                responsibilities: [],
                allowed_activity_scope: [],
                autonomous_allowed: true,
              },
            ],
            daypart_profiles: [],
            rules: [],
            glossary: [],
            banner_media_id: null,
            banner_alt_text: "",
            status: "published",
            definition_version: 1,
            row_version: 1,
            contract_version: "world-v1",
            contract_hash: "static-world-contract",
            readiness_status: "publish_ready",
            created_at: "2026-08-29T00:00:00Z",
            updated_at: "2026-08-29T00:00:00Z",
            archived_at: null,
          },
          readiness: {
            world_id: "world-static-probe",
            definition_version: 1,
            row_version: 1,
            contract_version: "world-v1",
            contract_hash: "static-world-contract",
            required_fields: {},
            optional_setting_count: 1,
            quality_tier: "CORE",
            issues: [],
            ready_for_publish: true,
            evaluated_at: "2026-08-29T00:00:00Z",
          },
        },
        status: 200,
      });
      return;
    }
    if (
      url.pathname === "/api/v1/worlds/world-static-probe/characters" &&
      route.request().method() === "GET"
    ) {
      expect(url.searchParams.get("surface")).toBe("studio");
      await route.fulfill({
        contentType: "application/json",
        json: {
          schema_version: "studio-world-character-list-v1",
          world_id: "world-static-probe",
          items: [],
        },
        status: 200,
      });
      return;
    }
    if (
      url.pathname === "/api/v1/worlds/world-static-probe/character-candidates"
    ) {
      await route.fulfill({
        contentType: "application/json",
        json: {
          schema_version: "studio-character-candidates-v1",
          world_id: "world-static-probe",
          items: [
            {
              character_id: "char-existing",
              display_name: "올마이트",
              handle: "allmight",
              avatar_url: null,
              current_world_status: null,
              eligible: true,
              reason_code: null,
            },
            {
              character_id: "char-new-1",
              display_name: "미도리야 이즈쿠",
              handle: "midoriya_izuku",
              avatar_url: null,
              current_world_status: null,
              eligible: true,
              reason_code: null,
            },
          ],
        },
        status: 200,
      });
      return;
    }
    if (
      url.pathname === "/api/v1/worlds/world-static-probe/characters" &&
      route.request().method() === "POST"
    ) {
      entryRequestCount += 1;
      entryBody = route.request().postDataJSON() as Record<string, unknown>;
      await route.fulfill({
        contentType: "application/json",
        json: {
          id: "wc-char-new-1",
          world_id: "world-static-probe",
          character_id: "char-new-1",
          membership_id: "membership-static-owner",
          role_key: "student",
          status: "active",
          autonomous_enabled: false,
          version: 1,
          reused: false,
        },
        status: 200,
      });
      return;
    }
    await route.fallback();
  });

  await page.goto(studioRoute);
  await expect(page.getByText("캐릭터 생성은 완료되었습니다.")).toBeVisible();
  await expect(page.getByLabel("내 캐릭터")).toHaveValue("char-new-1");
  await page.getByLabel("World 역할").first().selectOption("student");
  await page.getByRole("button", { name: "이 World에 연결" }).click();

  await expect(
    page.getByText("현재 World에 연결했습니다. 이제 P2 활동 준비·승인을 진행해 주세요."),
  ).toBeVisible();
  expect(entryRequestCount).toBe(1);
  expect(entryBody).toMatchObject({
    character_id: "char-new-1",
    role_key: "student",
  });
  await expect
    .poll(() =>
      page.evaluate(() => {
        const desktop = window as unknown as {
          __ANGMOO_DESKTOP_WINDOW__: { kind: string; route: string };
        };
        return desktop.__ANGMOO_DESKTOP_WINDOW__;
      }),
    )
    .toEqual({ kind: "studio", route: "/studio/worlds/world-static-probe" });
});

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

test("static installed relationship route ignores provider overrides and requests Ladybug", async ({
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
    "/characters/character-static-owner/worlds/world-static-probe/relationship-graph?provider=neo4j",
  );
  await expect(page.getByText("설치형 Angmoo의 canonical 관계망 provider는 LadybugDB입니다.")).toBeVisible();
  await expect(page.getByText("관계망 최신 상태")).toBeVisible();
  await expect(page.locator('[data-product-shell="relationship-graph"]')).toBeVisible();
  await expect(page.locator('[data-product-shell="device"]')).toHaveCount(0);
  expect(requestedProviders).toEqual(["ladybug"]);
});

test("installed relationship graph distinguishes outage, replay, and recovery", async ({
  page,
}) => {
  let phase: "degraded" | "failed" | "rebuilding" | "healthy" = "degraded";
  await page.route("http://127.0.0.1:8080/api/v1/**", async (route) => {
    const url = new URL(route.request().url());
    if (!url.pathname.endsWith("/relationship-graph")) {
      await route.fallback();
      return;
    }
    expect(url.searchParams.get("provider")).toBe("ladybug");
    if (phase === "failed") {
      await route.fulfill({
        contentType: "application/json",
        json: { detail: "graph_provider_unavailable" },
        status: 503,
      });
      return;
    }
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
          {
            world_character_id: "wc-static-peer",
            character_id: "character-static-peer",
            display_name: "Static Peer Parrot",
            is_center: false,
          },
        ],
        edges: [
          {
            relationship_state_id: "relationship-static-probe",
            actor_world_character_id: "wc-static-owner",
            target_world_character_id: "wc-static-peer",
            familiarity: 1,
            affinity: 0,
            trust: 0,
            tension: 0,
            interaction_count: 1,
            relationship_version: 1,
            last_event_id: "event-static-probe",
            last_event_at: "2026-08-28T00:00:00Z",
          },
        ],
        evidence: [],
        meta: {
          template: "neighborhood",
          source: phase === "healthy" ? "ladybug" : "canonical_fallback",
          graph_status:
            phase === "rebuilding"
              ? "rebuilding"
              : phase === "degraded"
                ? "unavailable"
                : "healthy",
          truncated: false,
          projection_lag_seconds: phase === "healthy" ? 0 : null,
          revalidated_node_count: 2,
          revalidated_edge_count: 1,
          fallback_reason: phase === "healthy" ? null : "graph_provider_unavailable",
        },
      },
      status: 200,
    });
  });

  const graphRoute =
    "/characters/character-static-owner/worlds/world-static-probe/relationship-graph";
  await page.goto(graphRoute);
  await expect(page.locator('[data-relationship-graph-state="degraded"]')).toBeVisible();
  await expect(page.locator('[data-relationship-graph-state="empty"]')).toHaveCount(0);

  phase = "failed";
  await page.reload();
  await expect(page.locator('[data-relationship-graph-state="failed"]')).toBeVisible();
  await expect(page.locator('[data-relationship-graph-state="empty"]')).toHaveCount(0);

  phase = "rebuilding";
  await page.reload();
  await expect(page.locator('[data-relationship-graph-state="rebuilding"]')).toBeVisible();
  await expect(page.locator('[data-relationship-graph-state="empty"]')).toHaveCount(0);

  phase = "healthy";
  await page.reload();
  await expect(page.getByText("관계망 최신 상태")).toBeVisible();
  for (const state of ["failed", "rebuilding", "degraded", "empty"]) {
    await expect(page.locator(`[data-relationship-graph-state="${state}"]`)).toHaveCount(0);
  }
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

  const scrollSurface = page.locator('[data-device-scroll-owner="true"]');
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
