import { expect, test } from "@playwright/test";
import { readFileSync } from "node:fs";
import { chatRoute } from "./world-social-chat-fixture";
import { installChatDeleteFixture } from "./world-chat-delete-fixture";
import { staticDocumentFallback } from "./world-ui-improvements-fixture";
import { FEED_WORLD } from "./world-feed-fixture";

for (const language of ["ko", "en"] as const) {
  const catalog = JSON.parse(readFileSync(`../frontend/src/features/memory/locales/${language}.json`, "utf8"));
  const t = (key: string) => catalog[key] ?? key;
  const buttonName = language === "ko" ? "근거 2개 보기" : "View 2 evidence items";
  const projection = { familiarity: 22, affinity: 12, trust: 15, tension: 2, interactions: 3, relationship_label: null, perception: "Frozen original perception" };
  const relationship = (reference: string, change: string | null = "changed", available = true) => ({ reference, kind: "graph_relationship", label: "Synthetic relation", availability: available ? "available" : "unavailable",
    related_character: available ? "Frozen World name" : null, direction: available ? "outgoing" : null, excerpt: available ? "Frozen original perception" : null,
    occurred_at: "2026-10-10T00:00:00Z", canonical_href: null, episode: null, relationship_change: available ? change : null, relationship_projection: available ? projection : null });
  test(`historical relationship statuses, decoder, locale and dialog ${language}`, async ({ page }, info) => {
    const isStatic = info.project.name !== "next", url = String(info.project.use.baseURL);
    const fixture = await installChatDeleteFixture(page, isStatic, url, language);
    if (isStatic) await staticDocumentFallback(page, url);
    let payload: any = { schema_version: "world-chat-evidence.v1", request_id: "synthetic-evidence", route: "graph", retrieval_outcome: "relationship_used", capability: "available",
      items: [relationship("graph")], current_context: [relationship("social")], retrieval_limitations: { partial_axes: [], degraded_reason: null }, read_limitations: [] };
    const handler = (route: import("@playwright/test").Route) => route.request().url().endsWith("/requests/synthetic-evidence/evidence") ? route.fulfill({ json: payload }) : route.fallback();
    await page.route("**/api/backend/**", handler); await page.route("http://127.0.0.1:8080/api/v1/**", handler);
    await page.goto(chatRoute());
    const button = page.getByRole("button", { name: buttonName, exact: true }), dialog = page.locator("[data-world-chat-evidence-dialog]");
    for (const change of ["same", "changed", "not_checked"] as const) {
      payload.items = [relationship("graph", change)]; payload.current_context = [relationship("social", change)];
      await button.click();
      await expect(dialog.getByText(t({ same: "현재도 동일", changed: "이후 변경됨", not_checked: "현재 상태 비교 불가" }[change]), { exact: true })).toHaveCount(2);
      await expect(dialog.getByText("Frozen original perception", { exact: true })).toHaveCount(2);
      await expect(dialog).not.toContainText(t("답변 생성 당시 일부 검색이 제한됐어요. 전달된 근거 중 확인 가능한 내용을 표시해요."));
      await expect(dialog).not.toContainText("Current renamed person");
      await page.keyboard.press("Escape"); await expect(button).toBeFocused();
    }
    payload.items = [relationship("graph", null, false)]; payload.current_context = [relationship("social", null, false)]; payload.read_limitations = ["historical_unverified"]; payload.capability = "degraded";
    await button.click(); await expect(dialog.getByText(t("당시 근거 확인 불가"), { exact: true })).toHaveCount(2);
    await expect(dialog).not.toContainText("Frozen original perception"); await expect(dialog).not.toContainText("Frozen World name");
    await page.keyboard.press("Escape");
    payload.read_limitations = ["current_unavailable"]; payload.retrieval_limitations = { partial_axes: ["graph"], degraded_reason: "graph_unavailable" };
    await button.click(); await expect(dialog.getByText(t("현재 표시할 수 없음"), { exact: true })).toHaveCount(2);
    await expect(dialog.getByText(t("답변 생성 당시 일부 검색이 제한됐어요. 전달된 근거 중 확인 가능한 내용을 표시해요."), { exact: true })).toBeVisible();
    await expect(dialog.getByText(t("일부 근거는 지금 확인하거나 표시할 수 없어요."), { exact: true })).toBeVisible(); await page.keyboard.press("Escape");
    delete payload.retrieval_limitations; delete payload.read_limitations; payload.items = [relationship("old")]; payload.current_context = []; delete payload.items[0].relationship_change; delete payload.items[0].relationship_projection;
    await button.click(); await expect(dialog.getByText(t("현재 상태 비교 불가"), { exact: true })).toBeVisible();
    await expect(dialog.getByText(t("일부 근거의 상태를 확인할 수 없어요."), { exact: true })).toBeVisible(); await page.keyboard.press("Escape");
    payload.items[0].relationship_change = "unsafe-enum";
    await button.click(); await expect(dialog.getByRole("alert")).toContainText(t("근거를 불러오지 못했어요.")); await page.keyboard.press("Escape");
    payload.items = Array.from({ length: 12 }, (_, i) => relationship(`graph-${i}`)); payload.current_context = Array.from({ length: 12 }, (_, i) => relationship(`social-${i}`));
    payload.capability = "available"; payload.retrieval_limitations = { partial_axes: [], degraded_reason: null }; payload.read_limitations = [];
    await page.setViewportSize({ width: 360, height: 480 }); await button.click();
    await expect(dialog.locator("li")).toHaveCount(24);
    expect(await dialog.evaluate(element => element.scrollHeight > element.clientHeight && element.scrollWidth <= element.clientWidth)).toBe(true);
    const close = dialog.getByRole("button", { name: language === "ko" ? "대화상자 닫기" : "Close dialog", exact: true });
    await close.focus(); await page.keyboard.press("Tab"); await expect(close).toBeFocused();
    await page.screenshot({ path: info.outputPath(`historical-${language}.png`) });
    fixture.base.base.language = language === "ko" ? "en" : "ko";
    await page.evaluate(() => window.dispatchEvent(new Event("angmoo:auth-changed")));
    await expect(dialog.getByRole("heading", { name: language === "ko" ? "Evidence for this response" : "이 답변의 근거", exact: true })).toBeVisible();
    await expect(dialog.getByText("Frozen original perception", { exact: true })).toHaveCount(24);
    await page.keyboard.press("Escape"); await expect(page.getByRole("button", { name: language === "ko" ? "View 2 evidence items" : "근거 2개 보기", exact: true })).toBeFocused();
    expect(fixture.deleteRequests).toEqual([]); expect(fixture.base.base.providerCalls).toEqual([]);
  });

  test(`evidence lifetime ignores late reads after close and thread switch ${language}`, async ({ page }, info) => {
    const isStatic = info.project.name !== "next", url = String(info.project.use.baseURL);
    const fixture = await installChatDeleteFixture(page, isStatic, url, language);
    if (isStatic) await staticDocumentFallback(page, url);
    let release: (() => void) | undefined;
    const handler = async (route: import("@playwright/test").Route) => {
      if (!route.request().url().endsWith("/requests/synthetic-evidence/evidence")) return route.fallback();
      await new Promise<void>(resolve => { release = resolve; });
      try { await route.fulfill({ json: { schema_version: "world-chat-evidence.v1", request_id: "synthetic-evidence", route: "graph", retrieval_outcome: "relationship_used", capability: "available", items: [relationship("late")], current_context: [], retrieval_limitations: { partial_axes: [], degraded_reason: null }, read_limitations: [] } }); } catch { /* Client aborted the delayed request. */ }
    };
    await page.route("**/api/backend/**", handler); await page.route("http://127.0.0.1:8080/api/v1/**", handler);
    await page.goto(chatRoute()); const button = page.getByRole("button", { name: buttonName, exact: true }), dialog = page.locator("[data-world-chat-evidence-dialog]");
    await button.click(); await expect(dialog.getByText(t("근거를 확인하는 중"), { exact: true })).toBeVisible();
    await expect.poll(() => Boolean(release)).toBe(true); await page.keyboard.press("Escape"); release!();
    await expect(dialog).not.toBeVisible(); await expect(button).toBeFocused();
    release = undefined; await button.click(); await expect.poll(() => Boolean(release)).toBe(true);
    await page.goto(chatRoute("synthetic-chat-1")); release!(); await expect(dialog).not.toBeVisible();
    await expect(page.getByText("Frozen original perception", { exact: true })).toHaveCount(0);
    expect(fixture.base.base.providerCalls).toEqual([]);
  });

  test(`evidence lifetime protects request and World switch ${language}`, async ({ page }, info) => {
    const isStatic = info.project.name !== "next", url = String(info.project.use.baseURL);
    const fixture = await installChatDeleteFixture(page, isStatic, url, language);
    if (isStatic) await staticDocumentFallback(page, url);
    fixture.base.thread.messages.push({ ...fixture.base.thread.messages[1], id: 4, content: "Second synthetic reply" });
    fixture.base.thread.evidence_summaries.push({ request_id: "synthetic-evidence-next", assistant_message_id: 4, capability: "available", count: 1 });
    const reads = new Map<string, string>();
    page.on("response", async response => { const path = new URL(response.url()).pathname.replace(/^\/api\/(backend|v1)/, ""); if (response.ok() && path.startsWith(`/worlds/${FEED_WORLD}/`)) { try { reads.set(path, JSON.stringify(await response.json())); } catch { /* Image or document response. */ } } });
    let release: (() => void) | undefined;
    const payload = (id: string, name: string) => ({ schema_version: "world-chat-evidence.v1", request_id: id, route: "graph", retrieval_outcome: "relationship_used", capability: "available", items: [{ ...relationship(name), related_character: name }], current_context: [], retrieval_limitations: { partial_axes: [], degraded_reason: null }, read_limitations: [] });
    const handler = async (route: import("@playwright/test").Route) => {
      const path = new URL(route.request().url()).pathname.replace(/^\/api\/(backend|v1)/, "");
      if (path.endsWith("/requests/synthetic-evidence/evidence")) { await new Promise<void>(resolve => { release = resolve; }); try { return await route.fulfill({ json: payload("synthetic-evidence", "Late old person") }); } catch { return; } }
      if (path.endsWith("/requests/synthetic-evidence-next/evidence")) return route.fulfill({ json: payload("synthetic-evidence-next", "New request person") });
      if (path.startsWith("/worlds/other-synthetic-world/")) { const original = reads.get(path.replace("other-synthetic-world", FEED_WORLD)); if (original) return route.fulfill({ contentType: "application/json", body: original.replaceAll(FEED_WORLD, "other-synthetic-world") }); }
      return route.fallback();
    };
    await page.route("**/api/backend/**", handler); await page.route("http://127.0.0.1:8080/api/v1/**", handler);
    await page.goto(chatRoute());
    const button = page.getByRole("button", { name: buttonName, exact: true }), dialog = page.locator("[data-world-chat-evidence-dialog]");
    await button.click(); await expect.poll(() => Boolean(release)).toBe(true);
    await page.keyboard.press("Escape");
    await page.getByRole("button", { name: language === "ko" ? "근거 1개 보기" : /View 1 evidence/, exact: language === "ko" }).click();
    await expect(dialog).toContainText("New request person"); release!();
    await expect(dialog).not.toContainText("Late old person"); await page.keyboard.press("Escape");
    release = undefined; await button.click(); await expect.poll(() => Boolean(release)).toBe(true);
    await expect.poll(() => reads.has(`/worlds/${FEED_WORLD}/chat/threads/synthetic-chat`)).toBe(true);
    await page.goto(chatRoute().replace(FEED_WORLD, "other-synthetic-world")); release!();
    await expect(page.getByText("Second synthetic reply", { exact: true })).toBeVisible();
    await expect(dialog).not.toBeVisible(); await expect(page.getByText("Late old person", { exact: true })).toHaveCount(0);
    expect(fixture.base.base.providerCalls).toEqual([]);
  });
}
