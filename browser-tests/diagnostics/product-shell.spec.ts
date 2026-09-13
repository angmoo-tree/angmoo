import { expect, test } from "@playwright/test";

test("RT diagnostic history selects failures and exports matching snapshots", async ({ page }) => {
  const worldId = "world-rt";
  const threadId = "thread-rt";
  const role = (id: string, mode: string) => ({ world_character_id: id, character_id: id,
    display_name: id, handle: id, avatar_url: null, banner_url: null, role_key: "student",
    control_mode: mode, profile_capability: "available" });
  const thread = { id: threadId, world_id: worldId, requester: role("owner-bird", "owner_controlled"),
    responding: role("friend-bird", "autonomous"), selected_model: "gemini-3.1-flash-lite", default_model: "gemini-3.1-flash-lite",
    model_binding_mode: "default", selected_thinking_level: "high", default_thinking_level: "high",
    created_at: "2026-09-12T12:00:00Z", last_message_at: null, latest_message: null, messages: [], evidence_summaries: [] };
  const requests = Array.from({ length: 31 }, (_, i) => ({ request_id: `request-${i}`, created_at: `2026-09-12T12:${String(i).padStart(2, "0")}:00Z`,
    state: i === 0 ? "committed" : "failed", user_message_id: i + 1, attempt_number: 1, retry_of_request_id: null }));
  let latest = requests[0];
  let releaseSlow: (() => void) | undefined;
  let slow = false;
  const writes: string[] = [];
  await page.route("**/api/backend/**", async route => {
    const url = new URL(route.request().url());
    if (route.request().method() !== "GET") writes.push(url.pathname);
    const send = (value: unknown, status = 200) => route.fulfill({ contentType: "application/json", body: JSON.stringify(value), status });
    if (url.pathname.endsWith("/auth/me")) return send({ id: "local-owner", email: null, display_name: "Local Owner",
      display_name_updated_at: null, display_name_change_available_at: null, profile_setup_completed: true, feed_content_filter: "all" });
    if (url.pathname.endsWith("/runtime/status")) return send({ schema_version: "local-runtime-status-v1", installation_state: "ready" });
    if (url.pathname.endsWith(`/worlds/mine/${worldId}`)) return send({ schema_version: "local-world-app-v1", surface: "world_app",
      world: { world_id: worldId, name: "RT World", tagline: "", banner_media_id: null, banner_alt_text: null, status: "published",
        visibility: "private", readiness_status: "publish_ready", membership_role: "owner", updated_at: "2026-09-12T12:00:00Z", launchable: true, launch_block_reason: null } });
    if (url.pathname.endsWith("/diagnostics/requests")) return send({ world_id: worldId, thread_id: threadId,
      items: url.searchParams.has("cursor") ? requests.slice(30) : requests.slice(0, 30), next_cursor: url.searchParams.has("cursor") ? null : "request-29" });
    if (url.pathname.endsWith("/diagnostics")) {
      const id = url.searchParams.get("request_id");
      const request = requests.find(r => r.request_id === id) ?? latest;
      if (id === "request-2" && slow) await new Promise<void>(resolve => { releaseSlow = resolve; });
      return send({ world_id: worldId, thread_id: threadId, request_id: request.request_id, request_state: request.state, request,
        status: "available", record: { version: "chat-retrieval-diagnostics.v1", events: [], omitted_events: 0 },
        capture: { enabled: true, remaining: 8, expires_at: "2026-09-12T13:00:00Z" },
        details: request.request_id === "request-30" ? null : [{ event: "reference_failure", trace_version: "decision-trace.v2", field_path: "entities.ref" }] });
    }
    if (url.pathname.endsWith("/requests/latest")) return send({ response_request: null });
    if (url.pathname.endsWith(`/threads/${threadId}`)) return send(thread);
    if (url.pathname.endsWith("/threads")) return send({ items: [thread], ambiguous_legacy_count: 0, max_threads: 5 });
    return send({ detail: "unexpected_fixture_route" }, 404);
  });
  await page.goto(`/worlds/${worldId}/chat/${threadId}`);
  await page.getByText("검색 진단 · 문제 해결", { exact: true }).click();
  const select = page.getByRole("combobox", { name: "확인할 요청" });
  await expect(select.locator("option")).toHaveCount(31);
  await select.selectOption("request-1");
  await expect(page.getByText("요청 ID: request-1", { exact: true })).toBeVisible();
  const downloadPromise = page.waitForEvent("download");
  await page.getByRole("button", { name: "상세 진단 파일 저장", exact: true }).click();
  const download = await downloadPromise;
  expect(download.suggestedFilename()).toContain("request-1.json");
  const stream = await download.createReadStream();
  const chunks: Buffer[] = [];
  for await (const chunk of stream!) chunks.push(Buffer.from(chunk));
  const exported = JSON.parse(Buffer.concat(chunks).toString());
  expect(exported.request.request_id).toBe("request-1");
  expect(exported.request.state).toBe("failed");
  expect(exported.export_version).toBe("angmoo-query-diagnostics.export.v1");
  // Opening the nested details must not refresh the parent or lose selection.
  await page.getByText("수집한 검색 조건 보기", { exact: true }).click();
  await expect(select).toHaveValue("request-1");
  await page.getByRole("button", { name: "이전 요청 더 보기" }).click();
  await expect(select.locator("option")).toHaveCount(32);
  await select.selectOption("request-30");
  await expect(page.getByRole("button", { name: "기본 진단만 파일 저장" })).toBeVisible();
  slow = true;
  await select.selectOption("request-2");
  await expect.poll(() => !!releaseSlow).toBe(true);
  await expect(page.getByRole("button", { name: /파일 저장/ })).toHaveCount(0);
  await select.selectOption("request-3");
  await expect(page.getByText("요청 ID: request-3", { exact: true })).toBeVisible();
  releaseSlow?.();
  await expect(page.getByText("요청 ID: request-3", { exact: true })).toBeVisible();
  latest = requests[4];
  await select.selectOption("");
  await expect(page.getByText("요청 ID: request-4", { exact: true })).toBeVisible();
  expect(writes).toEqual([]);
});
