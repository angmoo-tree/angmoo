import { expect, test } from "@playwright/test";
import { continuityAgentDetail as staticAgentDetail } from "./continuity-fixture";
import { verifyMemoryRecovery } from "./memory-recovery-fixture";
import { json, uiDWorld } from "./continuity-next-fixture";

test("static memory: failed selection retry refreshes retained items and evidence", async ({ page }) => {
  const world = uiDWorld();
  await page.route("**/api/v1/worlds/mine**", (route) => json(route, {
    schema_version: "local-world-surface-v1", surface: "device_home", items: [world],
  }));
  await verifyMemoryRecovery(page, world.world_id);
});

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
    author_handle:
      authorName === "Static UI-D Owner"
        ? "static_ui_d_owner"
        : "static_ui_d_autonomous",
    author_avatar_url: null,
    author_profile_capability: "available" as const,
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

test("continuity: static persona overflow uses code points and blocks the native save form", async ({ page }) => {
  const id = "static-persona-limit";
  const agent = staticAgentDetail(id);
  agent.character.execution_mode = "llm";
  let writes = 0;
  await page.route("http://127.0.0.1:8080/api/v1/**", async (route) => {
    const url = new URL(route.request().url());
    if (url.pathname === `/api/v1/agents/${id}`) return route.fulfill({ json: agent });
    if (url.pathname.endsWith("/persona")) { writes++; return route.fulfill({ json: agent }); }
    return route.fallback();
  });
  await page.goto(`/agents/${id}?tab=settings`);
  const field = page.getByRole("textbox", { name: "성격", exact: true });
  await field.fill("😀".repeat(6001));
  await expect(field).toHaveValue("😀".repeat(6001));
  await expect(page.getByRole("alert").filter({hasText: "1자 초과"})).toBeVisible();
  const submit = field.locator("xpath=ancestor::form").locator('button[type="submit"]');
  await submit.click();
  expect(writes).toBe(0);
  await field.fill("정상 범위");
  await submit.click();
  await expect.poll(() => writes).toBe(1);
});


test("continuity: static evidence reply uses its verified root and exact target", async ({ page }) => {
  const root = staticUiDManualPost({ id: UI_D_STATIC_ROOT_POST_ID, title: "원문", body: "원 게시글", replyCount: 60 });
  const target = {...staticUiDManualPost({ id: "static-nested-target", title: "", body: "정확한 정적 대댓글",
    replyToPostId: "static-parent" }), thread_root_post_id: root.id};
  await page.route("http://127.0.0.1:8080/api/v1/**", async (route) => {
    const url = new URL(route.request().url());
    if (url.pathname === `/api/v1/worlds/mine/${UI_D_STATIC_WORLD_ID}`) return route.fulfill({json: staticUiDWorld()});
    if (url.pathname.endsWith("/owner-character")) return route.fulfill({json: staticUiDOwnerActor()});
    if (url.pathname.includes("/manual-social/posts/")) return route.fulfill({json: {
      ...staticUiDManualFeed([root, target]), root_post_id: root.id, target_post_id: target.id, page_offset: 50, next_offset: null,
    }});
    return route.fallback();
  });
  await page.goto(`/worlds/${UI_D_STATIC_WORLD_ID}/posts/${target.id}`);
  const evidence = page.getByRole("article", {name: "근거가 가리키는 답글"});
  await expect(evidence).toContainText("정확한 정적 대댓글");
  await expect(evidence).toBeInViewport();
  await expect(evidence.getByRole("link", {name: /부모 답글 보기/})).toHaveAttribute("href", /static-parent\/?$/);
});
