import { expect, test, type Route } from "@playwright/test";

const OWNER = {
  id: "ui-e-local-owner",
  email: null,
  display_name: "UI-E Local Owner",
  display_name_updated_at: null,
  display_name_change_available_at: null,
  profile_setup_completed: true,
  feed_content_filter: "all",
  is_admin: true,
};

async function json(route: Route, body: unknown, status = 200): Promise<void> {
  await route.fulfill({
    body: JSON.stringify(body),
    contentType: "application/json",
    status,
  });
}

test("Local Settings exposes installation/session truth and no unsupported owner-delete action", async ({
  page,
}) => {
  const writes: string[] = [];
  await page.route("**/api/backend/**", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    if (!["GET", "HEAD"].includes(request.method())) {
      writes.push(`${request.method()} ${url.pathname}`);
    }

    if (url.pathname === "/api/backend/auth/me" && request.method() === "GET") {
      await json(route, OWNER);
      return;
    }
    if (
      url.pathname === "/api/backend/auth/local/bootstrap" &&
      request.method() === "GET"
    ) {
      await json(route, {
        state: "claimed",
        installation_id: "installation-ui-e-settings",
        local_label: "작업실 PC",
        owner: OWNER,
        candidates: [],
      });
      return;
    }
    if (url.pathname === "/api/backend/messages/settings" && request.method() === "GET") {
      await json(route, {
        credential_source: "message_key",
        source_character_id: null,
        default_model: "gemini-2.5-flash-lite",
        message_key_fingerprint: null,
        agent_key_fingerprint: null,
        has_usable_key: false,
        owned_agents: [],
      });
      return;
    }
    await json(route, { detail: `unexpected_ui_e_request:${url.pathname}` }, 404);
  });

  await page.goto("/settings");

  await expect(page.getByRole("heading", { name: "설정" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "현재 설치와 로컬 세션" })).toBeVisible();
  await expect(page.getByText("작업실 PC", { exact: true })).toBeVisible();
  await expect(page.getByText("UI-E Local Owner", { exact: true })).toBeVisible();
  await expect(page.getByText("installation-ui-e-settings", { exact: true })).toBeVisible();
  await expect(page.getByText("owner 전체 삭제 지원 안 함", { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: /회원탈퇴|owner.*탈퇴/ })).toHaveCount(0);
  await expect(page.getByPlaceholder("회원탈퇴")).toHaveCount(0);
  expect(writes.filter((entry) => entry.startsWith("DELETE "))).toEqual([]);
});

test("Local Settings fails closed when installation status is unavailable", async ({
  page,
}) => {
  const writes: string[] = [];
  await page.route("**/api/backend/**", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    if (!["GET", "HEAD"].includes(request.method())) {
      writes.push(`${request.method()} ${url.pathname}`);
    }

    if (url.pathname === "/api/backend/auth/me" && request.method() === "GET") {
      await json(route, OWNER);
      return;
    }
    if (
      url.pathname === "/api/backend/auth/local/bootstrap" &&
      request.method() === "GET"
    ) {
      await json(route, { detail: "bootstrap_unavailable" }, 503);
      return;
    }
    if (url.pathname === "/api/backend/messages/settings" && request.method() === "GET") {
      await json(route, {
        credential_source: "message_key",
        source_character_id: null,
        default_model: "gemini-2.5-flash-lite",
        message_key_fingerprint: null,
        agent_key_fingerprint: null,
        has_usable_key: false,
        owned_agents: [],
      });
      return;
    }
    await json(route, { detail: `unexpected_ui_e_request:${url.pathname}` }, 404);
  });

  await page.goto("/settings");

  await expect(page.getByText("설치 확인 실패", { exact: true })).toBeVisible();
  await expect(
    page.locator('[data-status-tone="degraded"]').filter({ hasText: "설치 확인 실패" }),
  ).toBeVisible();
  await expect(page.getByText("로컬 세션 연결됨", { exact: true })).toHaveCount(0);
  await expect(page.getByText("owner 전체 삭제 지원 안 함", { exact: true })).toBeVisible();
  expect(writes.filter((entry) => entry.startsWith("DELETE "))).toEqual([]);
});
