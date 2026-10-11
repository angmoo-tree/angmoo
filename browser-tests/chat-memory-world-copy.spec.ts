import { test, expect } from "@playwright/test";
import { installIntegrationFixture } from "./home-activity-memory-fixture";
import { FEED_WORLD } from "./world-feed-fixture";
import { installSocialChatFixture, chatRoute, SYNTHETIC_THREAD } from "./world-social-chat-fixture";

for (const language of ["ko", "en"] as const) test(`feed and chat writing copy ${language}`, async ({ page }, info) => {
  await installIntegrationFixture(page, info.project.name !== "next", String(info.project.use.baseURL), language);
  await page.goto(`/worlds/${FEED_WORLD}/feed`);
  await expect(page.getByPlaceholder(language === "ko" ? "본문을 적어주세요" : "Write your post.", { exact: true })).toBeVisible();
  await expect(page.getByPlaceholder(language === "ko" ? "오늘 이 World에 남길 이야기의 제목을 적어주세요" : "Give today's World story a title", { exact: true })).toBeVisible();
  await expect(page.getByText(/원본은 20MB|original.*20MB/i)).toHaveCount(0);
  await expect(page.getByRole("button", { name: language === "ko" ? "사진 첨부" : "Attach photo", exact: true })).toBeVisible();
  const state = await page.evaluate(() => document.querySelector("textarea")?.value ?? "");
  expect(state).toBe("");
  await installSocialChatFixture(page, info.project.name !== "next", String(info.project.use.baseURL), language);
  await page.goto(chatRoute());
  await expect(page.getByRole("button", { name: language === "ko" ? "사진 첨부" : "Attach photo", exact: true })).toBeVisible();
  await expect(page.getByText(/원본은 20MB|original.*20MB/i)).toHaveCount(0);
  await expect(page.getByRole("textbox")).toBeVisible();
});

for (const language of ["ko", "en"] as const) test(`canonical read diagnostics preserve unknown ${language}`, async ({ page }, info) => {
  await installIntegrationFixture(page, info.project.name !== "next", String(info.project.use.baseURL), language);
  await installSocialChatFixture(page, info.project.name !== "next", String(info.project.use.baseURL), language);
  const request = { request_id: "synthetic-canonical-read", created_at: "2026-10-11T10:00:00Z", state: "committed", user_message_id: 1, attempt_number: 1, retry_of_request_id: null };
  const diagnostics = { world_id: FEED_WORLD, thread_id: SYNTHETIC_THREAD, request_id: request.request_id,
    request_state: request.state, request, status: "available",
    record: { version: "chat-retrieval-diagnostics.v1", events: [], omitted_events: 0 },
    capture: { enabled: false, remaining: 0, expires_at: null }, details: null, detail_availability: "available",
    search_trace: { version: "search-diagnostic-trace.v1", coverage: "complete", stages: [], lineage: [], terminals: [],
      stage_events_dropped: 0, lineage_edges_dropped: 0, aliases_dropped: 0,
      canonical_reads: [{ stage: "revalidate", status: "completed", wait_ms: 1, elapsed_ms: 8, sql_count: 32, unique_nodes: 2, memo_hits: 1, cleaned: true },
        { stage: "hydrate", status: "deadline", wait_ms: null, elapsed_ms: null, sql_count: null, unique_nodes: null, memo_hits: null, cleaned: null }] } };
  const handler: Parameters<typeof page.route>[1] = route => {
    const path = new URL(route.request().url()).pathname;
    if (path.endsWith("/diagnostics/requests")) return route.fulfill({ json: { world_id: FEED_WORLD, thread_id: SYNTHETIC_THREAD, items: [request], next_cursor: null } });
    if (path.endsWith("/diagnostics")) return route.fulfill({ json: diagnostics });
    return route.fallback();
  };
  await page.route("**/api/backend/**", handler); await page.route("http://127.0.0.1:8080/api/v1/**", handler);
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto(chatRoute());
  await page.getByRole("button", { name: language === "ko" ? "기억과 진단 보기" : "Open memory and diagnostics", exact: true }).click();
  await page.getByText(language === "ko" ? "검색 진단 · 문제 해결" : "Search diagnostics · Troubleshooting", { exact: true }).click();
  await expect(page.getByText(language === "ko" ? "기억 원문 확인 작업 · revalidate · completed" : "Canonical memory read · revalidate · completed", { exact: true })).toBeVisible();
  await expect(page.getByText(language === "ko" ? "기억 원문 확인 작업 · hydrate · deadline" : "Canonical memory read · hydrate · deadline", { exact: true })).toBeVisible();
  const download = page.waitForEvent("download");
  await page.getByRole("button", { name: language === "ko" ? "상세 진단 파일 저장" : "Save detailed diagnostics", exact: true }).click();
  const stream = await (await download).createReadStream(), chunks: Buffer[] = [];
  for await (const chunk of stream!) chunks.push(Buffer.from(chunk));
  const saved = JSON.parse(Buffer.concat(chunks).toString());
  expect(saved.search_trace.canonical_reads[0].sql_count).toBe(32);
  expect(saved.search_trace.canonical_reads[1].sql_count).toBeNull();
  expect(saved.search_trace.canonical_reads[1].cleaned).toBeNull();
});
