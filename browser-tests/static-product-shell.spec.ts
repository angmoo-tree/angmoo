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

function staticPostThread(id: string, title: string, body: string) {
  return {
    post: {
      ...staticProfilePost(id, title),
      body,
      comments: [],
    },
    replies: [],
  };
}

const UI_D_STATIC_WORLD_ID = "world-ui-d-static";
const UI_D_STATIC_ROOT_POST_ID = "post-ui-d-static-root";

function staticUiDWorld(worldId = UI_D_STATIC_WORLD_ID) {
  return {
    schema_version: "local-world-app-v1",
    surface: "world_app",
    world: {
      world_id: worldId,
      name: "Static UI-D World",
      tagline: "Tauri hosted social presentation parity",
      banner_media_id: null,
      banner_alt_text: "",
      status: "published",
      visibility: "public",
      readiness_status: "publish_ready",
      membership_role: "owner",
      updated_at: "2026-08-30T00:00:00Z",
      launchable: true,
      launch_block_reason: null,
    },
  } as const;
}

function staticUiDOwnerActor(worldId = UI_D_STATIC_WORLD_ID) {
  return {
    schema_version: "owner-controlled-world-character-v1",
    world_character_id: "wc-ui-d-static-owner",
    world_id: worldId,
    character_id: "character-ui-d-static-owner",
    control_mode: "owner_controlled",
    status: "active",
    autonomous_enabled: false,
    version: 1,
    profile: {
      display_name: "Static UI-D Owner",
      avatar_url: "",
      intro: "Static social test owner",
      role_key: null,
      preferred_address: "Owner",
      interests: [],
      background: "",
    },
  } as const;
}

function staticUiDManualPost({
  authorName = "Static UI-D Autonomous",
  body,
  canOwnerReply = true,
  id,
  likeCount = 0,
  replyCount = 0,
  replyToPostId = null,
  title,
  worldId = UI_D_STATIC_WORLD_ID,
}: {
  authorName?: string;
  body: string;
  canOwnerReply?: boolean;
  id: string;
  likeCount?: number;
  replyCount?: number;
  replyToPostId?: string | null;
  title: string;
  worldId?: string;
}) {
  return {
    id,
    world_id: worldId,
    author_world_character_id:
      authorName === "Static UI-D Owner"
        ? "wc-ui-d-static-owner"
        : "wc-ui-d-static-autonomous",
    author_name: authorName,
    title,
    body,
    post_type: replyToPostId ? "reply" : "text",
    reply_to_post_id: replyToPostId,
    created_at: "2026-08-30T01:00:00Z",
    can_owner_reply: canOwnerReply,
    reply_count: replyCount,
    like_count: likeCount,
  };
}

function staticUiDManualFeed(
  items: ReturnType<typeof staticUiDManualPost>[],
  worldId = UI_D_STATIC_WORLD_ID,
) {
  return {
    schema_version: "owner-manual-social-v1",
    world_id: worldId,
    owner_world_character_id: "wc-ui-d-static-owner",
    items,
  } as const;
}

function staticUiDManualWrite(
  post: ReturnType<typeof staticUiDManualPost>,
  operation: "post" | "reply" = "reply",
) {
  const writePost = {
    id: post.id,
    world_id: post.world_id,
    author_world_character_id: post.author_world_character_id,
    author_name: post.author_name,
    title: post.title,
    body: post.body,
    post_type: post.post_type,
    reply_to_post_id: post.reply_to_post_id,
    created_at: post.created_at,
    can_owner_reply: post.can_owner_reply,
  };
  return {
    schema_version: "owner-manual-social-v1",
    operation,
    replayed: false,
    post: writePost,
    delivery: {
      provider_call_count: 0,
      inbox_candidate_id:
        operation === "reply" ? "inbox-ui-d-static-reply" : null,
      inbox_status: operation === "reply" ? "pending" : "not_applicable",
      public_reaction_required: false,
    },
  } as const;
}

function staticUiDPostMedia(postId: string, index: number) {
  return {
    id: index,
    post_id: postId,
    media_type: "image",
    url: `/media/ui-d-${postId}-${index}.png`,
    alt_text: `${postId} image ${index}`,
    model: "fixture",
    prompt_hash: `fixture-${index}`,
    byte_size: 68,
    width: 1,
    height: 1,
    created_at: "2026-08-30T01:00:00Z",
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

function staticUiECharacter({
  activityActionType = "post_created",
  activityResult,
  characterId,
  name,
  nextActivityAt,
  slotStatus = "idle",
  targetPostId,
  timezone,
}: {
  activityActionType?: string;
  activityResult?: string;
  characterId: string;
  name: string;
  nextActivityAt: string;
  slotStatus?: string;
  targetPostId?: string | null;
  timezone: string;
}) {
  const base = staticAgentDetail(characterId);
  const authoritativeTargetPostId =
    targetPostId === undefined ? `post-${characterId}` : targetPostId;
  return {
    ...base,
    character: {
      ...base.character,
      id: characterId,
      name,
      handle: characterId,
      one_liner: `${name}의 자율활동 상태를 확인합니다.`,
      execution_mode: "llm",
    },
    settings: {
      ...base.settings,
      character_id: characterId,
      auto_enabled: true,
      active_hours_start: "08:00",
      active_hours_end: "22:00",
    },
    assigned_slot: {
      agent_id: `runtime-${characterId}`,
      status: slotStatus,
      assigned_user_id: "owner-static-probe",
      assigned_character_id: characterId,
      assigned_credential_id: null,
      next_tick_at: "2026-08-31T12:00:00Z",
      last_run_at: "2026-08-29T23:15:00Z",
      heartbeat_interval_seconds: 60,
      locked_by_run_id: null,
      lease_expires_at: null,
      last_error: null,
      updated_at: "2026-08-30T00:00:00Z",
    },
    activity_summary: {
      ...base.activity_summary,
      within_active_hours: true,
      timezone,
      last_activity_at: "2026-08-29T23:15:00Z",
      next_activity_at: nextActivityAt,
    },
    recent_activity: [
      {
        id: 1,
        user_id: "owner-static-probe",
        character_id: characterId,
        action_type: activityActionType,
        target_post_id: authoritativeTargetPostId,
        target_profile_type: null,
        target_profile_id: null,
        target_profile_name: null,
        target_profile_handle: null,
        target_profile_avatar_url: null,
        reason: "scheduled_activity",
        result:
          activityResult ??
          JSON.stringify({
            message: "Created post post-json-decoy.",
            created_post_id: "post-json-decoy",
            topic_signature: "내부 topic signature",
            novelty_basis: "내부 novelty metadata",
            lore_chunk_ids: ["lore-internal-1"],
            retrieval_mode: "hybrid",
            internal_blob: "x".repeat(4_000),
          }),
        created_at: "2026-08-29T23:15:00Z",
      },
    ],
  };
}

function staticUiECreatorContext(worldId: string) {
  return {
    membership_role: "owner",
    world: {
      id: worldId,
      slug: "static-ui-e-world",
      name: "UI-E 히어로 학교",
      tagline: "World-local leave contract probe",
      setting_description: "UI-E World-local leave 경계를 검증하는 충분히 긴 세계관 설명",
      daily_life_description: "UI-E World-local leave 경계를 검증하는 충분히 긴 일상 설명",
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
      contract_hash: "static-ui-e-world-contract",
      readiness_status: "publish_ready",
      created_at: "2026-08-30T00:00:00Z",
      updated_at: "2026-08-30T00:00:00Z",
      archived_at: null,
    },
    readiness: {
      world_id: worldId,
      definition_version: 1,
      row_version: 1,
      contract_version: "world-v1",
      contract_hash: "static-ui-e-world-contract",
      required_fields: {},
      optional_setting_count: 1,
      quality_tier: "CORE",
      issues: [],
      ready_for_publish: true,
      evaluated_at: "2026-08-30T00:00:00Z",
    },
  } as const;
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
    const selectedNavigationItem = navigation.locator('a[href="/agents"]');
    await expect(selectedNavigationItem).toHaveAttribute(
      "aria-current",
      "page",
    );
    await expect(selectedNavigationItem).toHaveCSS(
      "background-color",
      "rgb(255, 240, 239)",
    );
    await expect(selectedNavigationItem).toHaveCSS("color", "rgb(255, 107, 107)");

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

test("static Character dashboard keeps multiple autonomy states and World-local time independent", async ({
  page,
}) => {
  let characters = [
    staticUiECharacter({
      characterId: "character-ui-e-alpha",
      name: "알파 앵무",
      nextActivityAt: "2026-08-30T00:30:00Z",
      timezone: "America/New_York",
    }),
    staticUiECharacter({
      activityActionType: "future_action_v2",
      activityResult: `{broken${"x".repeat(4_000)}`,
      characterId: "character-ui-e-beta",
      name: "베타 앵무",
      nextActivityAt: "2026-08-30T03:45:00Z",
      slotStatus: "running",
      targetPostId: null,
      timezone: "Asia/Seoul",
    }),
  ];
  const autonomyRequests: string[] = [];

  await page.route(
    "http://127.0.0.1:8080/api/v1/posts/post-character-ui-e-alpha/thread",
    async (route) => {
      await route.fulfill({
        contentType: "application/json",
        json: staticPostThread(
          "post-character-ui-e-alpha",
          "최근 결과 대상 게시글",
          "authoritative target_post_id로 열린 본문",
        ),
        status: 200,
      });
    },
  );

  await page.route("http://127.0.0.1:8080/api/v1/agents**", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    if (url.pathname === "/api/v1/agents" && request.method() === "GET") {
      await route.fulfill({ contentType: "application/json", json: characters, status: 200 });
      return;
    }
    if (
      url.pathname === "/api/v1/agents/character-ui-e-alpha/deactivate" &&
      request.method() === "POST"
    ) {
      autonomyRequests.push(url.pathname);
      characters = characters.map((item) =>
        item.character.id === "character-ui-e-alpha"
          ? {
              ...item,
              settings: { ...item.settings, auto_enabled: false },
              assigned_slot: null,
              activity_summary: {
                ...item.activity_summary,
                next_activity_at: null,
              },
            }
          : item,
      );
      await route.fulfill({
        contentType: "application/json",
        json: characters[0],
        status: 200,
      });
      return;
    }
    await route.fallback();
  });

  await page.goto("/agents");

  await expect(page.locator("[data-character-summary]")).toContainText(
    "자율활동 ON 2",
  );
  const alpha = page.locator('[data-character-id="character-ui-e-alpha"]');
  const beta = page.locator('[data-character-id="character-ui-e-beta"]');
  await expect(alpha).toHaveAttribute("data-character-autonomy-state", "scheduled");
  await expect(beta).toHaveAttribute("data-character-autonomy-state", "running");
  await expect(alpha).toContainText("08:00–22:00 · America/New_York");
  await expect(alpha).toContainText("08.29 20:30");
  const alphaMetrics = alpha.locator("[data-character-metrics]");
  const alphaRecent = alpha.locator("[data-character-recent-activity]");
  const alphaResultLink = alphaRecent.getByRole("link", {
    name: "게시글 보기",
    exact: true,
  });
  const betaRecent = beta.locator("[data-character-recent-activity]");
  await expect(alphaRecent).toContainText("게시글 작성");
  await expect(alphaRecent).toContainText("지저귐을 남겼어요.");
  await expect(alphaRecent).toContainText("08.29 19:15");
  await expect(alphaRecent.locator("time")).toHaveAttribute(
    "datetime",
    "2026-08-29T23:15:00Z",
  );
  await expect(alphaResultLink).toHaveAttribute(
    "href",
    /^\/posts\/post-character-ui-e-alpha\/?$/,
  );
  await expect(alphaResultLink).not.toHaveAttribute("aria-disabled", "true");
  await expect(
    alphaRecent.locator('[data-product-route-unavailable="true"]'),
  ).toHaveCount(0);
  await expect(betaRecent).toContainText("활동 기록이 업데이트됐어요.");
  await expect(betaRecent.getByRole("link")).toHaveCount(0);

  for (const [surface, forbidden] of [
    [
      alphaRecent,
      [
        "{",
        '"message"',
        '"created_post_id"',
        '"topic_signature"',
        '"novelty_basis"',
        '"lore_chunk_ids"',
        '"retrieval_mode"',
        "post-character-ui-e-alpha",
        "post-json-decoy",
      ],
    ],
    [betaRecent, ["{broken", "future_action_v2"]],
  ] as const) {
    const visibleText = await surface.innerText();
    for (const value of forbidden) expect(visibleText).not.toContain(value);
  }

  for (const viewport of [
    { width: 360, height: 800 },
    { width: 390, height: 844 },
    { width: 436, height: 880 },
  ]) {
    await page.setViewportSize(viewport);
    const [metricsBox, recentBox] = await Promise.all([
      alphaMetrics.boundingBox(),
      alphaRecent.boundingBox(),
    ]);
    expect(metricsBox).not.toBeNull();
    expect(recentBox).not.toBeNull();
    expect(Math.abs(recentBox!.x - metricsBox!.x)).toBeLessThanOrEqual(1);
    expect(
      Math.abs(
        recentBox!.x +
          recentBox!.width -
          (metricsBox!.x + metricsBox!.width),
      ),
    ).toBeLessThanOrEqual(1);
    for (const result of [alphaRecent, betaRecent]) {
      const geometry = await result.evaluate((node) => ({
        documentOverflow:
          document.documentElement.scrollWidth -
          document.documentElement.clientWidth,
        height: node.getBoundingClientRect().height,
        overflow: node.scrollWidth - node.clientWidth,
      }));
      expect(geometry.documentOverflow).toBe(0);
      expect(geometry.overflow).toBe(0);
      expect(geometry.height).toBeLessThanOrEqual(220);
    }
  }

  await page
    .getByRole("button", { name: "알파 앵무 자율활동 끄기" })
    .focus();
  await page.keyboard.press("Tab");
  await expect(alphaResultLink).toBeFocused();
  expect(
    await alphaResultLink.evaluate((node) => node.matches(":focus-visible")),
  ).toBe(true);
  await expect(page.getByText("서버 LLM", { exact: false })).toHaveCount(0);
  await expect(page.getByText("외부 실행기", { exact: false })).toHaveCount(0);
  await expect(page.getByText("3/3", { exact: false })).toHaveCount(0);

  await page
    .getByRole("button", { name: "알파 앵무 자율활동 끄기" })
    .click();

  await expect(alpha).toHaveAttribute("data-character-autonomy-state", "off");
  await expect(beta).toHaveAttribute("data-character-autonomy-state", "running");
  await expect(page.locator("[data-character-summary]")).toContainText(
    "자율활동 ON 1 · OFF 1",
  );
  expect(autonomyRequests).toEqual([
    "/api/v1/agents/character-ui-e-alpha/deactivate",
  ]);

  await alphaResultLink.focus();
  await page.keyboard.press("Enter");
  await expect(page).toHaveURL(/\/posts\/post-character-ui-e-alpha\/?$/);
  await expect(
    page.getByText("최근 결과 대상 게시글", { exact: true }),
  ).toBeVisible();
});

test("static Character dashboard fails closed for malformed, historical, and empty recent activity", async ({
  page,
}) => {
  const malformed = staticUiECharacter({
    activityResult: "{broken",
    characterId: "character-ui-e-malformed",
    name: "손상 결과 앵무",
    nextActivityAt: "2026-08-30T03:45:00Z",
    targetPostId: null,
    timezone: "Asia/Seoul",
  });
  const historicalBase = staticUiECharacter({
    characterId: "character-ui-e-historical",
    name: "이전 활동 앵무",
    nextActivityAt: "2026-08-30T03:45:00Z",
    timezone: "Asia/Seoul",
  });
  const historical = {
    ...historicalBase,
    recent_activity: [],
  };
  const emptyBase = staticUiECharacter({
    characterId: "character-ui-e-empty",
    name: "첫 활동 앵무",
    nextActivityAt: "2026-08-30T03:45:00Z",
    timezone: "Asia/Seoul",
  });
  const empty = {
    ...emptyBase,
    activity_summary: {
      ...emptyBase.activity_summary,
      last_activity_at: null,
    },
    recent_activity: [],
  };

  await page.route("http://127.0.0.1:8080/api/v1/agents", async (route) => {
    await route.fulfill({
      contentType: "application/json",
      json: [malformed, historical, empty],
      status: 200,
    });
  });
  await page.goto("/agents");

  const malformedResult = page
    .locator('[data-character-id="character-ui-e-malformed"]')
    .locator("[data-character-recent-activity]");
  await expect(malformedResult).toContainText("게시글 작성");
  await expect(malformedResult).toContainText("지저귐을 남겼어요.");
  await expect(malformedResult.getByRole("link")).toHaveCount(0);
  expect(await malformedResult.innerText()).not.toContain("{broken");

  const historicalResult = page
    .locator('[data-character-id="character-ui-e-historical"]')
    .locator("[data-character-recent-activity]");
  await expect(historicalResult).toHaveAttribute(
    "data-character-recent-activity",
    "historical",
  );
  await expect(historicalResult).toContainText("최근 활동 기록이 있어요.");
  await expect(historicalResult).toContainText("08.30 08:15");
  await expect(historicalResult.getByRole("link")).toHaveCount(0);

  const emptyResult = page
    .locator('[data-character-id="character-ui-e-empty"]')
    .locator("[data-character-recent-activity]");
  await expect(emptyResult).toHaveAttribute(
    "data-character-recent-activity",
    "empty",
  );
  await expect(emptyResult).toContainText("아직 활동 기록이 없어요.");
  await expect(emptyResult.locator("time")).toHaveCount(0);
  await expect(emptyResult.getByRole("link")).toHaveCount(0);
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

test("UI-D0 static global post detail waits for a delayed thread before mounting its body", async ({
  page,
}) => {
  let releaseThread!: () => void;
  let markThreadRequested!: () => void;
  const threadRequested = new Promise<void>((resolve) => {
    markThreadRequested = resolve;
  });
  const threadRelease = new Promise<void>((resolve) => {
    releaseThread = resolve;
  });

  await page.route("http://127.0.0.1:8080/api/v1/**", async (route) => {
    const pathname = new URL(route.request().url()).pathname;
    if (pathname !== "/api/v1/posts/post-delayed/thread") {
      await route.fallback();
      return;
    }
    markThreadRequested();
    await threadRelease;
    await route.fulfill({
      contentType: "application/json",
      json: staticPostThread(
        "post-delayed",
        "Delayed global detail",
        "The delayed global post body is visible.",
      ),
      status: 200,
    });
  });

  try {
    await page.goto("/posts/post-delayed");
    await threadRequested;
    await expect(page.getByText("게시글을 불러오는 중", { exact: true })).toBeVisible();
  } finally {
    releaseThread();
  }

  await expect(page.getByText("Delayed global detail", { exact: true })).toBeVisible();
  await expect(
    page.getByText("The delayed global post body is visible.", { exact: false }),
  ).toBeVisible();
  await expect(page.locator("article")).toHaveCount(1);
});

for (const failure of [
  { detail: "static_post_forbidden", kind: "403" },
  { detail: "static_post_not_found", kind: "404" },
  { detail: "static_post_runtime_unavailable", kind: "503" },
] as const) {
  test(`UI-D0 static global post detail renders the ${failure.kind} error surface`, async ({
    page,
  }) => {
    await page.route("http://127.0.0.1:8080/api/v1/**", async (route) => {
      const pathname = new URL(route.request().url()).pathname;
      if (pathname !== `/api/v1/posts/post-error-${failure.kind}/thread`) {
        await route.fallback();
        return;
      }
      await route.fulfill({
        contentType: "application/json",
        json: { detail: failure.detail },
        status: Number(failure.kind),
      });
    });

    await page.goto(`/posts/post-error-${failure.kind}`);
    await expect(page.getByText(failure.detail, { exact: true })).toBeVisible();
    await expect(page.getByText("게시글을 불러오는 중", { exact: true })).toHaveCount(0);
    await expect(page.locator("article")).toHaveCount(0);
    await expect(page.getByTitle("새로고침")).toBeEnabled();
    await expect(page.locator('[data-product-shell="device"]')).toHaveCount(1);
  });
}

test("UI-D0 static global post detail renders an offline error surface", async ({
  page,
}) => {
  await page.route(
    "http://127.0.0.1:8080/api/v1/posts/post-offline/thread",
    async (route) => route.abort("internetdisconnected"),
  );

  await page.goto("/posts/post-offline");
  await expect(page.getByText("Failed to fetch", { exact: true })).toBeVisible();
  await expect(page.getByText("게시글을 불러오는 중", { exact: true })).toHaveCount(0);
  await expect(page.locator("article")).toHaveCount(0);
  await expect(page.getByTitle("새로고침")).toBeEnabled();
  await expect(page.locator('[data-product-shell="device"]')).toHaveCount(1);
});

test("UI-D0 static global post detail manually refreshes after a transient failure", async ({
  page,
}) => {
  let threadRequests = 0;
  await page.route("http://127.0.0.1:8080/api/v1/**", async (route) => {
    const pathname = new URL(route.request().url()).pathname;
    if (pathname !== "/api/v1/posts/post-recover/thread") {
      await route.fallback();
      return;
    }
    threadRequests += 1;
    if (threadRequests === 1) {
      await route.fulfill({
        contentType: "application/json",
        json: { detail: "static_post_temporarily_unavailable" },
        status: 503,
      });
      return;
    }
    await route.fulfill({
      contentType: "application/json",
      json: staticPostThread(
        "post-recover",
        "Recovered global detail",
        "Manual refresh recovered this post.",
      ),
      status: 200,
    });
  });

  await page.goto("/posts/post-recover");
  await expect(page.getByText("static_post_temporarily_unavailable", { exact: true })).toBeVisible();
  expect(threadRequests).toBe(1);

  await page.getByTitle("새로고침").click();
  await expect(page.getByText("Recovered global detail", { exact: true })).toBeVisible();
  await expect(page.getByText("Manual refresh recovered this post.", { exact: false })).toBeVisible();
  await expect(page.locator("article")).toHaveCount(1);
  expect(threadRequests).toBe(2);
});

for (const entry of ["click", "Enter", "Space"] as const) {
  test(`UI-D0 static feed ${entry} opens the hydrated global post detail`, async ({
    page,
  }) => {
    const postId = `post-entry-${entry}`;
    const title = `Feed ${entry} detail`;
    await page.route("http://127.0.0.1:8080/api/v1/**", async (route) => {
      const pathname = new URL(route.request().url()).pathname;
      if (pathname === "/api/v1/feed") {
        await route.fulfill({
          contentType: "application/json",
          json: {
            items: [staticProfilePost(postId, title)],
            next_cursor: null,
          },
          status: 200,
        });
        return;
      }
      if (pathname === `/api/v1/posts/${postId}/thread`) {
        await route.fulfill({
          contentType: "application/json",
          json: staticPostThread(postId, title, `Feed ${entry} body is visible.`),
          status: 200,
        });
        return;
      }
      await route.fallback();
    });

    await page.goto("/posts");
    const card = page.getByRole("link", {
      name: `Profile Scroll Parrot 게시글 자세히 보기`,
    });
    await expect(card).toBeVisible();
    if (entry === "click") {
      await card.click();
    } else {
      await card.focus();
      await page.keyboard.press(entry);
    }

    await expect(page).toHaveURL(new RegExp(`/posts/${postId}$`));
    await expect(page.getByText(title, { exact: true })).toBeVisible();
    await expect(page.getByText(`Feed ${entry} body is visible.`, { exact: false })).toBeVisible();
    await expect(page.locator("article")).toHaveCount(1);
  });
}

test("UI-D0 Tauri Phone keeps post B after a delayed post A response", async ({
  page,
}) => {
  let releasePostA!: () => void;
  let markPostARequested!: () => void;
  let markPostAResponded!: () => void;
  const postARequested = new Promise<void>((resolve) => {
    markPostARequested = resolve;
  });
  const postAResponded = new Promise<void>((resolve) => {
    markPostAResponded = resolve;
  });
  const postARelease = new Promise<void>((resolve) => {
    releasePostA = resolve;
  });
  const threadRequests = new Map<string, number>();

  await page.addInitScript(() => {
    const desktop = window as unknown as {
      __ANGMOO_DESKTOP_WINDOW__: { kind: "phone"; route: string };
      __TAURI__: {
        core: {
          invoke: (command: string) => Promise<unknown>;
        };
      };
    };
    desktop.__ANGMOO_DESKTOP_WINDOW__ = { kind: "phone", route: "/posts" };
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
    if (pathname === "/api/v1/feed") {
      await route.fulfill({
        contentType: "application/json",
        json: {
          items: [
            staticProfilePost("post-stale-a", "Stale post A"),
            staticProfilePost("post-stale-b", "Current post B"),
          ],
          next_cursor: null,
        },
        status: 200,
      });
      return;
    }
    const postMatch = pathname.match(/^\/api\/v1\/posts\/(post-stale-[ab])\/thread$/);
    if (!postMatch) {
      await route.fallback();
      return;
    }
    const postId = postMatch[1];
    threadRequests.set(postId, (threadRequests.get(postId) ?? 0) + 1);
    if (postId === "post-stale-a") {
      markPostARequested();
      await postARelease;
    }
    await route.fulfill({
      contentType: "application/json",
      json: staticPostThread(
        postId,
        postId === "post-stale-a" ? "Stale post A" : "Current post B",
        postId === "post-stale-a" ? "Stale body A" : "Current body B",
      ),
      status: 200,
    });
    if (postId === "post-stale-a") markPostAResponded();
  });

  try {
    await page.goto("/");
    await page.getByText("Stale post A", { exact: true }).click();
    await postARequested;
    await expect(page.getByText("게시글을 불러오는 중", { exact: true })).toBeVisible();

    const navigation = page.getByRole("navigation", { name: "모바일 주요 메뉴" });
    await navigation.getByRole("link", { name: "피드" }).click();
    await page.getByText("Current post B", { exact: true }).click();
    await expect(page.getByText("Current body B", { exact: false })).toBeVisible();
    await expect
      .poll(() =>
        page.evaluate(() => {
          const desktop = window as unknown as {
            __ANGMOO_DESKTOP_WINDOW__: { kind: string; route: string };
          };
          return desktop.__ANGMOO_DESKTOP_WINDOW__;
        }),
      )
      .toEqual({ kind: "phone", route: "/posts/post-stale-b" });

    releasePostA();
    await postAResponded;
    await expect(page.getByText("Current body B", { exact: false })).toBeVisible();
    await expect(page.getByText("Stale body A", { exact: false })).toHaveCount(0);
    expect(threadRequests.get("post-stale-a")).toBe(1);
    expect(threadRequests.get("post-stale-b")).toBe(1);
  } finally {
    releasePostA();
  }
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

test("Studio World-local leave stops autonomy, refreshes version, and preserves the Character", async ({
  page,
}) => {
  const worldId = "world-ui-e-leave";
  const characterId = "character-ui-e-leave";
  const worldCharacterId = "wc-ui-e-leave";
  const studioRoute = `/studio/worlds/${worldId}`;
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

  let autonomyStopped = false;
  let leaveCompleted = false;
  let leaveBody: Record<string, unknown> | null = null;
  const operationOrder: string[] = [];
  const requests: Array<{ method: string; pathname: string }> = [];

  const studioCharacter = (version: number, selectedActiveWorld: boolean) => ({
    world_character_id: worldCharacterId,
    character_id: characterId,
    display_name: "빛나",
    confirmation_name: "빛나",
    avatar_url: null,
    intro: "다른 World에도 참여하는 자율 Character",
    role_key: "student",
    control_mode: "autonomous",
    status: "active",
    autonomous_enabled: selectedActiveWorld,
    selected_active_world: selectedActiveWorld,
    version,
    activity_setup_state: "approved",
  });

  await page.route("http://127.0.0.1:8080/api/v1/**", async (route) => {
    const url = new URL(route.request().url());
    const method = route.request().method();
    requests.push({ method, pathname: url.pathname });

    if (
      url.pathname === `/api/v1/worlds/${worldId}/creator-context` &&
      method === "GET"
    ) {
      await route.fulfill({
        contentType: "application/json",
        json: staticUiECreatorContext(worldId),
        status: 200,
      });
      return;
    }
    if (
      url.pathname === `/api/v1/worlds/${worldId}/characters` &&
      method === "GET"
    ) {
      expect(url.searchParams.get("surface")).toBe("studio");
      const items = leaveCompleted
        ? []
        : [studioCharacter(autonomyStopped ? 5 : 4, !autonomyStopped)];
      if (autonomyStopped && !leaveCompleted) {
        operationOrder.push("refresh-current-version");
      }
      await route.fulfill({
        contentType: "application/json",
        json: {
          schema_version: "studio-world-character-list-v1",
          world_id: worldId,
          items,
        },
        status: 200,
      });
      return;
    }
    if (
      url.pathname === `/api/v1/agents/${characterId}/deactivate` &&
      method === "POST"
    ) {
      operationOrder.push("deactivate-selected-character");
      autonomyStopped = true;
      await route.fulfill({
        contentType: "application/json",
        json: { status: "inactive" },
        status: 200,
      });
      return;
    }
    if (
      url.pathname === `/api/v1/worlds/${worldId}/characters/${characterId}/leave` &&
      method === "POST"
    ) {
      operationOrder.push("leave-current-world");
      leaveBody = route.request().postDataJSON() as Record<string, unknown>;
      leaveCompleted = true;
      await route.fulfill({
        contentType: "application/json",
        json: {
          world_character_id: worldCharacterId,
          world_id: worldId,
          character_id: characterId,
          status: "left",
          autonomous_enabled: false,
          version: 6,
          scheduler_assignment_released: true,
          history_preserved: true,
          replayed: false,
        },
        status: 200,
      });
      return;
    }
    await route.fallback();
  });

  await page.goto(studioRoute);
  await expect(page.getByText("빛나", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "이 World에서 제거" }).click();

  await expect(page.getByRole("dialog", { name: "이 World에서 제거" })).toBeVisible();
  await expect(
    page.getByText(
      "이 World에서 새 자율활동은 중지되지만 이미 작성한 글과 확인된 사건·관계 근거는 보존됩니다. 캐릭터 자체와 다른 World의 참여는 삭제되지 않습니다.",
      { exact: true },
    ),
  ).toBeVisible();

  const confirmation = page.getByLabel("확인을 위해 빛나 입력");
  const leaveButton = page.getByRole("button", { name: "자율활동 정지 후 제거" });
  await confirmation.fill("빛");
  await expect(leaveButton).toBeDisabled();
  await confirmation.fill("빛나");
  await expect(leaveButton).toBeEnabled();
  await leaveButton.click();

  await expect(
    page.getByText(
      "이 World에서 제거했습니다. 캐릭터 자체와 기존 활동·사건·관계 근거는 보존됩니다.",
      { exact: true },
    ),
  ).toBeVisible();
  await expect(page.getByRole("button", { name: "이 World에서 제거" })).toHaveCount(0);

  expect(operationOrder).toEqual([
    "deactivate-selected-character",
    "refresh-current-version",
    "leave-current-world",
  ]);
  expect(leaveBody).toMatchObject({
    world_character_id: worldCharacterId,
    version: 5,
    confirmation_name: "빛나",
    idempotency_key: expect.any(String),
  });
  expect(
    requests.some(
      (request) =>
        request.method === "DELETE" ||
        (request.pathname.includes(`/agents/${characterId}`) &&
          request.pathname !== `/api/v1/agents/${characterId}/deactivate`),
    ),
  ).toBe(false);
  expect(
    requests.some(
      (request) =>
        request.pathname.includes("/worlds/") &&
        !request.pathname.includes(`/worlds/${worldId}/`),
    ),
  ).toBe(false);
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
              reply_count: 0,
              like_count: 0,
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
  await expect(page.getByRole("link", { name: "World Feed", exact: true })).toHaveAttribute(
    "href",
    /\/worlds\/world-static-probe\/feed\/?$/,
  );
  expect(requestedPaths).toContain(
    "/api/v1/worlds/world-static-probe/manual-social/posts/post-static-probe",
  );
  expect(requestedPaths).not.toContain("/api/v1/posts/post-static-probe");
});

test("UI-D static World social core keeps compact composition, flat rows, exact detail navigation, and scoped replies", async ({
  page,
}) => {
  const longBody = Array.from(
    { length: 36 },
    (_, index) => `선택 가능한 static 긴 본문 ${index + 1}번째 문장입니다.`,
  ).join(" ");
  const rootPost = staticUiDManualPost({
    body: longBody,
    id: UI_D_STATIC_ROOT_POST_ID,
    likeCount: 1,
    replyCount: 1,
    title: "Static UI-D World root",
  });
  const zeroReactionPost = staticUiDManualPost({
    body: "답글과 좋아요가 아직 없는 static 게시글입니다.",
    canOwnerReply: false,
    id: "post-ui-d-static-zero-reaction",
    title: "Static UI-D zero reactions",
  });
  const existingReply = staticUiDManualPost({
    authorName: "Static UI-D Friend",
    body: "기존 static 대꾸도 같은 social row를 사용합니다.",
    canOwnerReply: false,
    id: "reply-ui-d-static-existing",
    replyToPostId: UI_D_STATIC_ROOT_POST_ID,
    title: "",
  });
  const ownerReply = staticUiDManualPost({
    authorName: "Static UI-D Owner",
    body: "Static UI-D Owner reply arrived.",
    canOwnerReply: false,
    id: "reply-ui-d-static-owner",
    replyToPostId: UI_D_STATIC_ROOT_POST_ID,
    title: "",
  });
  const postedRoot = staticUiDManualPost({
    authorName: "Static UI-D Owner",
    body: "변경한 static 직접 게시글 내용",
    canOwnerReply: false,
    id: "post-ui-d-static-owner-new",
    title: "공백을 정리한 static 제목",
  });
  let feedItems = [rootPost, zeroReactionPost, existingReply];
  let detailItems = [rootPost, existingReply];
  const postRequestBodies: unknown[] = [];
  const postIdempotencyKeys: Array<string | undefined> = [];
  let replyRequestBody: unknown = null;
  let replyIdempotencyKey: string | undefined;
  const requestedSocialPaths: string[] = [];
  const globalSocialPaths: string[] = [];
  const feedCuePaths: string[] = [];
  const likeMutationPaths: string[] = [];

  await page.route("http://127.0.0.1:8080/api/v1/**", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const method = request.method();
    if (/^\/api\/v1\/(feed|posts)(\/|$)/.test(url.pathname)) {
      globalSocialPaths.push(`${method} ${url.pathname}`);
    }
    if (url.pathname.includes("/feed-cue")) {
      feedCuePaths.push(`${method} ${url.pathname}`);
    }
    if (
      /\/likes$/.test(url.pathname) &&
      (method === "POST" || method === "DELETE")
    ) {
      likeMutationPaths.push(`${method} ${url.pathname}`);
    }
    if (url.pathname === `/api/v1/worlds/mine/${UI_D_STATIC_WORLD_ID}`) {
      await route.fulfill({
        contentType: "application/json",
        json: staticUiDWorld(),
        status: 200,
      });
      return;
    }
    if (url.pathname === `/api/v1/worlds/${UI_D_STATIC_WORLD_ID}/owner-character`) {
      await route.fulfill({
        contentType: "application/json",
        json: staticUiDOwnerActor(),
        status: 200,
      });
      return;
    }
    if (
      url.pathname === `/api/v1/worlds/${UI_D_STATIC_WORLD_ID}/manual-social/feed` &&
      method === "GET"
    ) {
      requestedSocialPaths.push(`${method} ${url.pathname}`);
      await route.fulfill({
        contentType: "application/json",
        json: staticUiDManualFeed(feedItems),
        status: 200,
      });
      return;
    }
    if (
      url.pathname === `/api/v1/worlds/${UI_D_STATIC_WORLD_ID}/manual-social/posts` &&
      method === "POST"
    ) {
      requestedSocialPaths.push(`${method} ${url.pathname}`);
      postRequestBodies.push(request.postDataJSON());
      postIdempotencyKeys.push(request.headers()["idempotency-key"]);
      if (postRequestBodies.length <= 2) {
        await route.fulfill({
          contentType: "application/json",
          json: { detail: "runtime_not_ready" },
          status: 503,
        });
        return;
      }
      feedItems = [postedRoot, rootPost, zeroReactionPost, existingReply];
      await route.fulfill({
        contentType: "application/json",
        json: staticUiDManualWrite(postedRoot, "post"),
        status: 200,
      });
      return;
    }
    if (
      url.pathname ===
        `/api/v1/worlds/${UI_D_STATIC_WORLD_ID}/manual-social/posts/${UI_D_STATIC_ROOT_POST_ID}` &&
      method === "GET"
    ) {
      requestedSocialPaths.push(`${method} ${url.pathname}`);
      await route.fulfill({
        contentType: "application/json",
        json: staticUiDManualFeed(detailItems),
        status: 200,
      });
      return;
    }
    if (
      url.pathname ===
        `/api/v1/worlds/${UI_D_STATIC_WORLD_ID}/manual-social/posts/${UI_D_STATIC_ROOT_POST_ID}/replies` &&
      method === "POST"
    ) {
      requestedSocialPaths.push(`${method} ${url.pathname}`);
      replyRequestBody = request.postDataJSON();
      replyIdempotencyKey = request.headers()["idempotency-key"];
      detailItems = [
        { ...rootPost, reply_count: 2 },
        existingReply,
        ownerReply,
      ];
      await route.fulfill({
        contentType: "application/json",
        json: staticUiDManualWrite(ownerReply),
        status: 200,
      });
      return;
    }
    await route.fallback();
  });

  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto(`/worlds/${UI_D_STATIC_WORLD_ID}/feed`);

  const feedSurface = page.locator('[data-world-social-surface="feed"]');
  await expect(feedSurface).toBeVisible();
  await expect(feedSurface.locator('[data-social-stream="world"]')).toBeVisible();
  await expect(feedSurface.getByText("World Feed", { exact: true })).toHaveCSS(
    "color",
    "rgb(255, 107, 107)",
  );
  await expect(page.getByRole("button", { name: "글 쓰기" })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "닫기" })).toHaveCount(0);
  const composer = page.locator("#world-owner-composer");
  const titleInput = page.getByLabel("제목", { exact: true });
  const bodyInput = page.getByLabel("내용", { exact: true });
  const submitPost = page.getByRole("button", { name: "게시하기" });
  await expect(composer).toBeVisible();
  await expect(
    composer.getByRole("img", { name: "Static UI-D Owner 프로필 이미지" }),
  ).toBeVisible();
  await expect(composer.getByText("Static UI-D Owner", { exact: true })).toBeVisible();
  await expect(titleInput).toHaveAttribute(
    "placeholder",
    "오늘 이 World에 남길 이야기의 제목을 적어주세요",
  );
  await expect(bodyInput).toHaveAttribute(
    "placeholder",
    "내가 조종하는 앵무의 말로 이야기를 적어보세요",
  );
  await expect(submitPost).toBeDisabled();
  expect(await titleInput.evaluate((element) => document.activeElement === element)).toBe(false);
  expect(await bodyInput.evaluate((element) => document.activeElement === element)).toBe(false);
  for (const input of [titleInput, bodyInput]) {
    const inputId = await input.getAttribute("id");
    expect(inputId).toBeTruthy();
    const label = page.locator(`label[for="${inputId}"]`);
    await expect(label).toHaveCount(1);
    expect(
      await label.evaluate((element) => {
        const style = window.getComputedStyle(element);
        const rect = element.getBoundingClientRect();
        return style.position === "absolute" && rect.width <= 1 && rect.height <= 1;
      }),
    ).toBe(true);
  }

  await titleInput.fill("  공백을 정리한 static 제목  ");
  await bodyInput.fill("  첫 static 직접 게시글 내용  ");
  await expect(submitPost).toHaveCSS("background-color", "rgb(255, 107, 107)");
  await expect(submitPost).toHaveCSS("color", "rgb(255, 255, 255)");
  await titleInput.focus();
  await page.keyboard.press("Tab");
  await expect(bodyInput).toBeFocused();
  await page.keyboard.press("Tab");
  await expect(submitPost).toBeFocused();

  await submitPost.click();
  await expect.poll(() => postRequestBodies.length).toBe(1);
  await expect(page.getByText("로컬 엔진이 아직 준비되지 않았습니다.")).toBeVisible();
  await expect(titleInput).toHaveValue("  공백을 정리한 static 제목  ");
  await expect(bodyInput).toHaveValue("  첫 static 직접 게시글 내용  ");
  await expect(submitPost).toBeEnabled();
  await submitPost.click();
  await expect.poll(() => postRequestBodies.length).toBe(2);
  await expect(page.getByText("로컬 엔진이 아직 준비되지 않았습니다.")).toBeVisible();
  await expect(submitPost).toBeEnabled();
  await bodyInput.fill("  변경한 static 직접 게시글 내용  ");
  await submitPost.click();
  await expect.poll(() => postRequestBodies.length).toBe(3);
  await expect(page.getByText("게시글을 저장했습니다.", { exact: false })).toBeVisible();
  await expect(composer).toBeVisible();
  await expect(titleInput).toHaveValue("");
  await expect(bodyInput).toHaveValue("");
  expect(postRequestBodies).toEqual([
    { title: "공백을 정리한 static 제목", body: "첫 static 직접 게시글 내용" },
    { title: "공백을 정리한 static 제목", body: "첫 static 직접 게시글 내용" },
    { title: "공백을 정리한 static 제목", body: "변경한 static 직접 게시글 내용" },
  ]);
  expect(postIdempotencyKeys[0]).toMatch(/^owner-post-/);
  expect(postIdempotencyKeys[1]).toBe(postIdempotencyKeys[0]);
  expect(postIdempotencyKeys[2]).toMatch(/^owner-post-/);
  expect(postIdempotencyKeys[2]).not.toBe(postIdempotencyKeys[0]);

  const row = page.locator(`[data-social-post-row="${UI_D_STATIC_ROOT_POST_ID}"]`);
  const zeroReactionRow = page.locator(
    '[data-social-post-row="post-ui-d-static-zero-reaction"]',
  );
  await expect(row).toHaveAttribute("data-variant", "feed");
  await expect(row).toHaveCSS("border-bottom-width", "1px");
  await expect(row).toHaveCSS("border-radius", "0px");
  await expect(row.getByRole("link", { name: "대꾸 1" })).toHaveAttribute(
    "href",
    new RegExp(
      `/worlds/${UI_D_STATIC_WORLD_ID}/posts/${UI_D_STATIC_ROOT_POST_ID}/?$`,
    ),
  );
  const positiveLike = row.getByLabel("좋아요 1", { exact: true });
  await expect(positiveLike).toHaveCount(1);
  await expect(positiveLike.locator("svg")).toHaveAttribute("fill", "currentColor");
  expect(await positiveLike.evaluate((element) => element.tagName)).toBe("SPAN");
  expect(await positiveLike.getAttribute("aria-pressed")).toBeNull();
  expect(await positiveLike.evaluate((element) => (element as HTMLElement).tabIndex)).toBe(-1);
  await expect(zeroReactionRow.getByRole("link", { name: "대꾸 0" })).toBeVisible();
  const zeroLike = zeroReactionRow.getByLabel("좋아요 0", { exact: true });
  await expect(zeroLike.locator("svg")).toHaveAttribute("fill", "none");
  expect(await zeroLike.evaluate((element) => element.tagName)).toBe("SPAN");
  await expect(row.getByRole("button", { name: /좋아요/ })).toHaveCount(0);
  await expect(zeroReactionRow.getByRole("button", { name: /좋아요/ })).toHaveCount(0);
  await expect(row.getByRole("link", { name: /좋아요/ })).toHaveCount(0);
  const expand = row.getByRole("button", { name: "더보기" });
  await expect(expand).toBeVisible();
  await expect(expand).toHaveCSS("color", "rgb(255, 107, 107)");
  await expect(
    page
      .locator('[data-social-post-row="post-ui-d-static-owner-new"]')
      .getByText("공백을 정리한 static 제목", { exact: true }),
  ).toBeInViewport();

  const feedUrl = page.url();
  await row.locator("p").evaluate((paragraph) => {
    const selection = window.getSelection();
    const range = document.createRange();
    range.selectNodeContents(paragraph);
    selection?.removeAllRanges();
    selection?.addRange(range);
  });
  await row.dispatchEvent("click", { button: 0 });
  expect(page.url()).toBe(feedUrl);
  await page.evaluate(() => window.getSelection()?.removeAllRanges());

  await expand.click();
  await expect(expand).toHaveCount(0);
  expect(page.url()).toBe(feedUrl);
  await row.focus();
  await expect(row).toBeFocused();
  await page.keyboard.press("Enter");

  await expect(page).toHaveURL(
    new RegExp(
      `/worlds/${UI_D_STATIC_WORLD_ID}/posts/${UI_D_STATIC_ROOT_POST_ID}/?$`,
    ),
  );
  await expect(page.locator('[data-world-social-surface="detail"]')).toBeVisible();
  await expect(page.getByRole("heading", { name: "게시글과 답글" })).toBeVisible();
  await expect(page.locator("#world-owner-composer")).toHaveCount(0);
  await expect(page.getByRole("button", { name: "게시하기" })).toHaveCount(0);
  await expect(
    page
      .locator(`[data-social-post-row="${UI_D_STATIC_ROOT_POST_ID}"]`)
      .getByLabel("대꾸 1"),
  ).toBeVisible();
  await expect(
    page
      .locator(`[data-social-post-row="${UI_D_STATIC_ROOT_POST_ID}"]`)
      .getByLabel("좋아요 1"),
  ).toBeVisible();
  await expect(
    page
      .locator('[data-social-post-row="reply-ui-d-static-existing"]')
      .getByLabel("좋아요 0"),
  ).toBeVisible();
  await expect(page.getByRole("heading", { name: "대꾸 1" })).toBeVisible();
  await page
    .getByLabel("Static UI-D Autonomous의 게시글에 답글")
    .fill("실제 static scoped reply");
  await page.getByRole("button", { name: "답글 보내기" }).click();

  await expect(
    page.getByText("Static UI-D Owner reply arrived.", { exact: false }),
  ).toBeVisible();
  await expect(page.getByRole("heading", { name: "대꾸 2" })).toBeVisible();
  await expect(
    page
      .locator(`[data-social-post-row="${UI_D_STATIC_ROOT_POST_ID}"]`)
      .getByLabel("대꾸 2"),
  ).toBeVisible();
  expect(replyRequestBody).toEqual({ body: "실제 static scoped reply" });
  expect(replyIdempotencyKey).toMatch(/^owner-reply-/);
  expect(requestedSocialPaths).toContain(
    `GET /api/v1/worlds/${UI_D_STATIC_WORLD_ID}/manual-social/feed`,
  );
  expect(requestedSocialPaths).toContain(
    `GET /api/v1/worlds/${UI_D_STATIC_WORLD_ID}/manual-social/posts/${UI_D_STATIC_ROOT_POST_ID}`,
  );
  expect(requestedSocialPaths).toContain(
    `POST /api/v1/worlds/${UI_D_STATIC_WORLD_ID}/manual-social/posts`,
  );
  expect(requestedSocialPaths).toContain(
    `POST /api/v1/worlds/${UI_D_STATIC_WORLD_ID}/manual-social/posts/${UI_D_STATIC_ROOT_POST_ID}/replies`,
  );
  expect(globalSocialPaths).toEqual([]);
  expect(feedCuePaths).toEqual([]);
  expect(likeMutationPaths).toEqual([]);
});

test("UI-D static World social errors distinguish 403, 404, 503, scope mismatch, and retry recovery", async ({
  page,
}) => {
  const rootPost = staticUiDManualPost({
    body: "Recovered static World-scoped body",
    id: UI_D_STATIC_ROOT_POST_ID,
    title: "Recovered static UI-D feed",
  });
  let responseMode: "403" | "404" | "503" | "scope" | "ready" | "empty" = "403";
  let feedRequests = 0;
  const globalSocialPaths: string[] = [];

  await page.route("http://127.0.0.1:8080/api/v1/**", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    if (/^\/api\/v1\/(feed|posts)(\/|$)/.test(url.pathname)) {
      globalSocialPaths.push(`${request.method()} ${url.pathname}`);
    }
    if (url.pathname === `/api/v1/worlds/mine/${UI_D_STATIC_WORLD_ID}`) {
      await route.fulfill({
        contentType: "application/json",
        json: staticUiDWorld(),
        status: 200,
      });
      return;
    }
    if (url.pathname === `/api/v1/worlds/${UI_D_STATIC_WORLD_ID}/owner-character`) {
      await route.fulfill({
        contentType: "application/json",
        json: staticUiDOwnerActor(),
        status: 200,
      });
      return;
    }
    if (url.pathname !== `/api/v1/worlds/${UI_D_STATIC_WORLD_ID}/manual-social/feed`) {
      await route.fallback();
      return;
    }
    feedRequests += 1;
    if (responseMode === "403" || responseMode === "404" || responseMode === "503") {
      await route.fulfill({
        contentType: "application/json",
        json: { detail: `ui_d_static_${responseMode}` },
        status: Number(responseMode),
      });
      return;
    }
    const responseWorldId =
      responseMode === "scope" ? "world-ui-d-static-foreign" : UI_D_STATIC_WORLD_ID;
    await route.fulfill({
      contentType: "application/json",
      json: staticUiDManualFeed(
        responseMode === "empty"
          ? []
          : [
              responseMode === "scope"
                ? staticUiDManualPost({
                    body: rootPost.body,
                    id: rootPost.id,
                    title: rootPost.title,
                    worldId: responseWorldId,
                  })
                : rootPost,
            ],
        responseWorldId,
      ),
      status: 200,
    });
  });

  await page.goto(`/worlds/${UI_D_STATIC_WORLD_ID}/feed`);
  await expect(page.getByRole("heading", { name: "이 Feed를 볼 권한이 없어요" })).toBeVisible();
  await expect(page.getByRole("button", { name: "다시 시도" })).toHaveCount(0);
  await expect(page.locator("#world-owner-composer")).toBeVisible();
  await expect(page.getByRole("button", { name: "글 쓰기" })).toHaveCount(0);

  responseMode = "404";
  await page.reload();
  await expect(page.getByRole("heading", { name: "게시글을 찾을 수 없어요" })).toBeVisible();
  await expect(page.getByRole("button", { name: "다시 시도" })).toHaveCount(0);

  responseMode = "503";
  await page.reload();
  await expect(
    page.getByRole("heading", { name: "로컬 runtime에 연결할 수 없어요" }),
  ).toBeVisible();
  await expect(page.getByRole("button", { name: "다시 시도" })).toBeVisible();

  responseMode = "scope";
  await page.reload();
  await expect(page.getByRole("heading", { name: "World 경계를 확인했어요" })).toBeVisible();
  await expect(page.getByText("다른 World의 응답이 감지되어")).toBeVisible();

  responseMode = "ready";
  await page.getByRole("button", { name: "다시 시도" }).click();
  await expect(page.getByText("Recovered static UI-D feed", { exact: true })).toBeVisible();
  responseMode = "empty";
  await page.reload();
  await expect(page.getByRole("heading", { name: "아직 공개된 게시글이 없어요" })).toBeVisible();
  await expect(page.locator("#world-owner-composer")).toBeVisible();
  await expect(page.getByRole("button", { name: "첫 글 쓰기" })).toHaveCount(0);
  await expect(
    page.getByRole("heading", { name: "아직 공개된 게시글이 없어요" }),
  ).toBeInViewport();
  expect(feedRequests).toBe(6);
  expect(globalSocialPaths).toEqual([]);
});

test("UI-D static World detail rejects an unrelated same-World reply and owner mismatch", async ({
  page,
}) => {
  const rootPost = staticUiDManualPost({
    body: "Exact thread root",
    id: UI_D_STATIC_ROOT_POST_ID,
    title: "Exact UI-D thread",
  });
  const unrelatedReply = staticUiDManualPost({
    authorName: "Static unrelated author",
    body: "This reply belongs to another root.",
    canOwnerReply: false,
    id: "reply-ui-d-static-unrelated",
    replyToPostId: "post-ui-d-static-other-root",
    title: "",
  });
  let responseMode: "owner" | "orphan" = "owner";

  await page.route("http://127.0.0.1:8080/api/v1/**", async (route) => {
    const url = new URL(route.request().url());
    if (url.pathname === `/api/v1/worlds/mine/${UI_D_STATIC_WORLD_ID}`) {
      await route.fulfill({
        contentType: "application/json",
        json: staticUiDWorld(),
        status: 200,
      });
      return;
    }
    if (url.pathname === `/api/v1/worlds/${UI_D_STATIC_WORLD_ID}/owner-character`) {
      await route.fulfill({
        contentType: "application/json",
        json: staticUiDOwnerActor(),
        status: 200,
      });
      return;
    }
    if (
      url.pathname ===
      `/api/v1/worlds/${UI_D_STATIC_WORLD_ID}/manual-social/posts/${UI_D_STATIC_ROOT_POST_ID}`
    ) {
      const feed = staticUiDManualFeed(
        responseMode === "owner" ? [rootPost] : [rootPost, unrelatedReply],
      );
      await route.fulfill({
        contentType: "application/json",
        json:
          responseMode === "owner"
            ? { ...feed, owner_world_character_id: "wc-ui-d-static-foreign" }
            : feed,
        status: 200,
      });
      return;
    }
    await route.fallback();
  });

  await page.goto(
    `/worlds/${UI_D_STATIC_WORLD_ID}/posts/${UI_D_STATIC_ROOT_POST_ID}`,
  );
  await expect(page.getByRole("heading", { name: "World 경계를 확인했어요" })).toBeVisible();
  await expect(page.getByText("Static unrelated author")).toHaveCount(0);

  responseMode = "orphan";
  await page.reload();
  await expect(page.getByRole("heading", { name: "World 경계를 확인했어요" })).toBeVisible();
  await expect(page.getByText("Static unrelated author")).toHaveCount(0);
});

test("UI-D static global social rows render zero, one, and many authenticated media fixtures", async ({
  page,
}) => {
  const zeroMediaPost = {
    ...staticProfilePost("post-ui-d-media-zero", "Zero media row"),
    media: [],
  };
  const oneMediaPost = {
    ...staticProfilePost("post-ui-d-media-one", "One media row"),
    media: [staticUiDPostMedia("post-ui-d-media-one", 1)],
  };
  const twoMediaPost = {
    ...staticProfilePost("post-ui-d-media-two", "Two media row"),
    media: Array.from({ length: 2 }, (_, index) =>
      staticUiDPostMedia("post-ui-d-media-two", index + 1),
    ),
  };
  const threeMediaPost = {
    ...staticProfilePost("post-ui-d-media-three", "Three media row"),
    media: Array.from({ length: 3 }, (_, index) =>
      staticUiDPostMedia("post-ui-d-media-three", index + 1),
    ),
  };
  const manyMediaPost = {
    ...staticProfilePost("post-ui-d-media-many", "Many media row"),
    like_count: 3,
    reply_count: 2,
    media: Array.from({ length: 5 }, (_, index) =>
      staticUiDPostMedia("post-ui-d-media-many", index + 1),
    ),
  };
  const mediaRequests: string[] = [];

  await page.route("http://127.0.0.1:8080/api/v1/feed**", async (route) => {
    await route.fulfill({
      contentType: "application/json",
      json: {
        items: [zeroMediaPost, oneMediaPost, twoMediaPost, threeMediaPost, manyMediaPost],
        next_cursor: null,
      },
      status: 200,
    });
  });
  await page.route("http://127.0.0.1:8080/media/**", async (route) => {
    expect(route.request().headers()["x-angmoo-launcher-token"]).toBe(
      "static-route-probe-token-000000000000",
    );
    mediaRequests.push(new URL(route.request().url()).pathname);
    await route.fulfill({
      body: Buffer.from(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9Wl2lU8AAAAASUVORK5CYII=",
        "base64",
      ),
      contentType: "image/png",
      status: 200,
    });
  });

  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/posts");

  const zeroRow = page.locator('[data-social-post-row="post-ui-d-media-zero"]');
  const oneRow = page.locator('[data-social-post-row="post-ui-d-media-one"]');
  const twoRow = page.locator('[data-social-post-row="post-ui-d-media-two"]');
  const threeRow = page.locator('[data-social-post-row="post-ui-d-media-three"]');
  const manyRow = page.locator('[data-social-post-row="post-ui-d-media-many"]');
  await expect(zeroRow).toBeVisible();
  await expect(zeroRow.locator("img")).toHaveCount(0);
  await expect(oneRow.locator("img")).toHaveCount(1);
  await expect(oneRow.getByAltText("post-ui-d-media-one image 1")).toBeVisible();
  await expect(twoRow.locator("img")).toHaveCount(2);
  await expect(threeRow.locator("img")).toHaveCount(3);
  await expect(manyRow.locator("img")).toHaveCount(4);
  await expect(manyRow.getByLabel("추가 이미지 1개")).toBeVisible();
  await expect(manyRow).toHaveCSS("border-bottom-width", "1px");
  await expect(manyRow).toHaveCSS("border-radius", "0px");
  await expect(zeroRow.getByRole("link", { name: "대꾸 0" })).toBeVisible();
  await expect(zeroRow.getByLabel("좋아요 0", { exact: true }).locator("svg")).toHaveAttribute(
    "fill",
    "none",
  );
  await expect(manyRow.getByRole("link", { name: "대꾸 2" })).toBeVisible();
  const aggregateLike = manyRow.getByLabel("좋아요 3", { exact: true });
  await expect(aggregateLike.locator("svg")).toHaveAttribute("fill", "currentColor");
  expect(await aggregateLike.evaluate((element) => element.tagName)).toBe("SPAN");
  expect(await aggregateLike.evaluate((element) => (element as HTMLElement).tabIndex)).toBe(-1);
  expect(await aggregateLike.getAttribute("aria-pressed")).toBeNull();
  for (const unsupportedAction of ["좋아요", "리포스트", "팔로우"]) {
    await expect(manyRow.getByRole("button", { name: unsupportedAction })).toHaveCount(0);
  }
  expect(mediaRequests).toHaveLength(10);
});

test("UI-D static global detail preserves a nested reply hierarchy", async ({ page }) => {
  const rootPostId = "post-ui-d-nested-root";
  const parentReply = {
    ...staticProfilePost("post-ui-d-nested-parent", ""),
    author_name: "Nested Parent",
    body: "Top-level reply body",
    post_type: "reply",
    reply_count: 1,
    reply_to_post_id: rootPostId,
  };
  const childReply = {
    ...staticProfilePost("post-ui-d-nested-child", ""),
    author_name: "Nested Child",
    body: "Nested child reply body",
    post_type: "reply",
    reply_to_post_id: parentReply.id,
  };

  await page.route(
    `http://127.0.0.1:8080/api/v1/posts/${rootPostId}/thread`,
    async (route) => {
      const thread = staticPostThread(rootPostId, "Nested thread root", "Root body");
      await route.fulfill({
        contentType: "application/json",
        json: {
          ...thread,
          post: { ...thread.post, reply_count: 2, like_count: 1 },
          replies: [parentReply, childReply],
        },
        status: 200,
      });
    },
  );
  for (const reply of [parentReply, childReply]) {
    await page.route(
      `http://127.0.0.1:8080/api/v1/posts/${reply.id}/thread`,
      async (route) => {
        await route.fulfill({
          contentType: "application/json",
          json: {
            post: { ...reply, comments: [] },
            replies: [],
          },
          status: 200,
        });
      },
    );
  }

  await page.goto(`/posts/${rootPostId}`);

  await expect(page.getByRole("heading", { name: "대꾸 2" })).toBeVisible();
  const rootRow = page.locator(`[data-social-post-row="${rootPostId}"]`);
  await expect(rootRow.getByLabel("대꾸 2")).toBeVisible();
  await expect(rootRow.getByLabel("좋아요 1").locator("svg")).toHaveAttribute(
    "fill",
    "currentColor",
  );
  const parentRow = page.locator(`[data-social-post-row="${parentReply.id}"]`);
  const childRow = page.locator(`[data-social-post-row="${childReply.id}"]`);
  await expect(parentRow).toBeVisible();
  await expect(parentRow.getByLabel("대꾸 1")).toBeVisible();
  await expect(parentRow.getByLabel("좋아요 0").locator("svg")).toHaveAttribute(
    "fill",
    "none",
  );
  await expect(childRow).toBeVisible();
  await expect(childRow.getByText("Nested Parent에게 대꾸", { exact: true })).toBeVisible();
  await expect(childRow.locator("xpath=..")).toHaveClass(/ml-4/);

  await expect(parentRow).toHaveAttribute("role", "link");
  await expect(parentRow).toHaveAttribute("tabindex", "0");
  await expect(parentRow.getByRole("link", { name: "대꾸 1" })).toHaveAttribute(
    "href",
    new RegExp(`/posts/${parentReply.id}/?$`),
  );
  await expect(childRow).toHaveAttribute("role", "link");
  await expect(childRow).toHaveAttribute("tabindex", "0");
  await expect(childRow.getByRole("link", { name: "대꾸 0" })).toHaveAttribute(
    "href",
    new RegExp(`/posts/${childReply.id}/?$`),
  );
  for (const row of [parentRow, childRow]) {
    for (const unsupportedAction of ["좋아요", "리포스트", "팔로우", "공유"]) {
      await expect(row.getByRole("button", { name: new RegExp(unsupportedAction) })).toHaveCount(
        0,
      );
      await expect(row.getByRole("link", { name: new RegExp(unsupportedAction) })).toHaveCount(0);
    }
  }

  await parentRow.focus();
  await expect(parentRow).toBeFocused();
  await page.keyboard.press("Enter");
  await expect(page).toHaveURL(new RegExp(`/posts/${parentReply.id}/?$`));
  await expect(page.getByText("Top-level reply body", { exact: true })).toBeVisible();

  await page.goto(`/posts/${rootPostId}`);
  await expect(childRow).toBeVisible();
  await childRow.focus();
  await expect(childRow).toBeFocused();
  await page.keyboard.press("Space");
  await expect(page).toHaveURL(new RegExp(`/posts/${childReply.id}/?$`));
  await expect(page.getByText("Nested child reply body", { exact: true })).toBeVisible();
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
