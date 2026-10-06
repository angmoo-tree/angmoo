import { expect, test, type Page } from "@playwright/test";

const noticeText = "같은 형식의 캐릭터 정의가 여러 개";
const selection = { policy: "sillytavern-first-match-v1", keyword: "chara", selected_occurrence: 0,
  same_keyword_count: 2, multiple_definitions: true, selected_json_sha256: "a".repeat(64) };
const summary = { document: null, sha256: "b".repeat(64), version: 2, source_format: "png",
  metadata_selection: selection, review: ["scenario_manual_merge"], raw_only: ["system_prompt"] };

function cardDraft(id: string, world: string | null = null) {
  return { id, revision: 2, contract_version: 2, target_world_id: world, source_kind: "card", status: "editing",
    name: "중복 카드의 첫 캐릭터", handle: null, one_liner: "", worldview: "편집 내용은 카드 원본과 구분합니다.",
    personality: "", speech_style: "", character_background: "", topic_preferences: "", safety_rules: "",
    avatar_temp_url: null, banner_temp_url: null };
}

async function seedDraft(page: Page, id: string) {
  await page.addInitScript((value) => sessionStorage.setItem("angmoo.creation.v2:default", value), id);
}

export function cardMetadataTests() {
  test("static duplicate metadata restores, retries without upload and preserves edits at 200 percent", async ({ page }, testInfo) => {
    let draft = cardDraft("static-card-duplicate");
    let summaryFails = true;
    let imports = 0;
    let rawReads = 0;
    let summaryReads = 0;
    await seedDraft(page, draft.id);
    await page.route("http://127.0.0.1:8080/api/v1/agents/**", async (route) => {
      const url = new URL(route.request().url());
      const method = route.request().method();
      if (url.pathname.endsWith("/card-source")) {
        if (url.searchParams.get("include_document") === "false") {
          summaryReads += 1;
          await route.fulfill({ status: summaryFails ? 503 : 200,
            json: summaryFails ? { detail: "synthetic_metadata_unavailable" } : summary });
        } else {
          rawReads += 1;
          await route.fulfill({ json: { ...summary, document: { data: { name: "선택된 첫 정의" } } } });
        }
      } else if (url.pathname.endsWith("/card")) {
        imports += 1;
        await route.fulfill({ status: 422, json: { detail: "카드 PNG 데이터가 손상되어 읽을 수 없습니다." } });
      } else if (url.pathname.endsWith(draft.id)) {
        if (method === "PATCH") {
          expect(route.request().postDataJSON().revision).toBe(draft.revision);
          draft = { ...draft, ...route.request().postDataJSON(), revision: draft.revision + 1 };
        }
        await route.fulfill({ json: draft });
      } else await route.fallback();
    });
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto("/agents/new");
    await expect(page.getByRole("alert").filter({ hasText: "편집 내용은 유지됩니다" })).toBeVisible();
    await expect(page.getByRole("textbox", { name: "이름", exact: true })).toHaveValue(draft.name);
    await page.getByRole("textbox", { name: "이름", exact: true }).fill("수정한 이름");
    summaryFails = false;
    await page.getByRole("button", { name: "카드 정보 다시 불러오기", exact: true }).click();
    const notice = page.getByRole("status").filter({ hasText: noticeText });
    await expect(notice).toBeVisible();
    await expect(page.getByRole("textbox", { name: "이름", exact: true })).toHaveValue("수정한 이름");
    expect(imports).toBe(0); expect(rawReads).toBe(0); expect(summaryReads).toBe(2);
    await page.evaluate(() => { document.documentElement.style.zoom = "2"; });
    await expect(notice).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1)).toBe(true);
    await page.getByRole("textbox", { name: "이름", exact: true }).focus();
    await page.keyboard.press("Tab");
    await expect(page.getByRole("textbox", { name: "핸들", exact: true })).toBeFocused();
    await page.screenshot({ path: testInfo.outputPath("duplicate-notice-200-percent.png"), fullPage: true });
    await page.evaluate(() => { document.documentElement.style.zoom = "1"; });
    await page.getByText("카드 원본과 반영 범위 확인", { exact: true }).click();
    await expect(page.getByText("반영한 정의:", { exact: false })).toContainText("chara의 첫 번째 항목");
    await page.getByRole("button", { name: "원문 보기", exact: true }).click();
    await expect(page.locator("pre")).toContainText("선택된 첫 정의");
    expect(rawReads).toBe(1);
    await page.getByRole("button", { name: "이전", exact: true }).click();
    await page.getByLabel("캐릭터 카드 PNG 또는 JSON", { exact: true }).setInputFiles({ name: "replacement.png", mimeType: "image/png", buffer: Buffer.from("synthetic") });
    await expect(page.getByText("현재 편집 내용을 이 카드의 설정으로 교체할까요?", { exact: true })).toBeVisible();
    await page.getByRole("button", { name: "취소", exact: true }).click();
    expect(imports).toBe(0);
    await page.getByLabel("만드는 방법", { exact: true }).selectOption("direct");
    await expect(notice).toHaveCount(0);
    await expect(page.locator("pre")).toHaveCount(0);
    await page.getByRole("button", { name: "저장하고 다음", exact: true }).click();
    await expect(page.getByRole("textbox", { name: "이름", exact: true })).toHaveValue("수정한 이름");
    await page.getByRole("button", { name: "초안 저장", exact: true }).click();
    await page.reload();
    await expect(notice).toBeVisible();
    await expect(page.getByRole("textbox", { name: "이름", exact: true })).toHaveValue("수정한 이름");
    expect(rawReads).toBe(1); expect(imports).toBe(0);
  });

  test("static failed replacement keeps old metadata and a new World never shows the old notice", async ({ page }) => {
    const draft = cardDraft("static-card-failed-replace");
    let imports = 0;
    let releaseSummary: () => void = () => {};
    let delaySummary = false;
    let pendingSummary = false;
    await seedDraft(page, draft.id);
    await page.route("http://127.0.0.1:8080/api/v1/agents/**", async (route) => {
      const url = new URL(route.request().url());
      if (url.pathname.endsWith("/card-source")) {
        if (delaySummary) {
          pendingSummary = true;
          await new Promise<void>((resolve) => { releaseSummary = resolve; });
        }
        await route.fulfill({ json: summary }).catch(() => undefined);
      } else if (url.pathname.endsWith("/card")) {
        imports += 1;
        await route.fulfill({ status: 422, json: { detail: "카드 PNG 데이터가 손상되어 읽을 수 없습니다." } });
      } else if (url.pathname.endsWith(draft.id)) await route.fulfill({ json: draft });
      else await route.fallback();
    });
    await page.goto("/agents/new");
    const notice = page.getByRole("status").filter({ hasText: noticeText });
    await expect(notice).toBeVisible();
    await page.getByRole("textbox", { name: "이름", exact: true }).fill("실패 후에도 유지할 이름");
    await page.getByRole("button", { name: "이전", exact: true }).click();
    await page.getByLabel("캐릭터 카드 PNG 또는 JSON", { exact: true }).setInputFiles({ name: "broken.png", mimeType: "image/png", buffer: Buffer.from("bad") });
    await page.getByRole("button", { name: "교체하기", exact: true }).click();
    await expect(page.getByRole("alert").filter({ hasText: "카드를 읽을 수 없습니다." })).toBeVisible();
    await expect(notice).toBeVisible();
    expect(imports).toBe(1);
    await page.getByRole("button", { name: "취소", exact: true }).click();
    await page.getByLabel("만드는 방법", { exact: true }).selectOption("direct");
    await page.getByRole("button", { name: "저장하고 다음", exact: true }).click();
    await expect(page.getByRole("textbox", { name: "이름", exact: true })).toHaveValue("실패 후에도 유지할 이름");
    delaySummary = true;
    await page.getByRole("button", { name: "이전", exact: true }).click();
    await page.getByLabel("만드는 방법", { exact: true }).selectOption("card");
    await expect.poll(() => pendingSummary).toBe(true);
    try {
      await page.goto("/agents/new?worldId=world-new-card-target");
      await expect(page.getByLabel("만드는 방법", { exact: true })).toBeVisible();
      releaseSummary();
      await expect(notice).toHaveCount(0);
      await expect(page.getByRole("textbox", { name: "이름", exact: true })).toHaveCount(0);
    } finally { releaseSummary(); }
  });
}
