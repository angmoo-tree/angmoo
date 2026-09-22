import { expect, type Page, type Route } from "@playwright/test";

export function memoryBatchFixture(worldId: string, subjectId: string, enabled: () => boolean) {
  let embedding = { scope: { world_id: worldId, subject_world_character_id: subjectId }, enabled: false,
    provider: "google", model: "gemini-embedding-2", credential_id: null as string | null,
    profile: "fixture-profile", version: 0, ready: false, reason_code: "memory_embedding_disabled" as string | null,
    runtime_status: "ready", available_credentials: [{ id: "fixture-google-key", label: "기존 Google 설정" }] };
  let manualPolls = 0;
  let manualRequests = 0;
  let manualKey: string | null = null;
  let pollsAfterSave = 0;
  let retryCount = 0;
  let saved = {
    scope: { world_id: worldId, subject_world_character_id: subjectId }, version: 0,
    ai_enabled: false, shutdown_enabled: true, schedule_enabled: false,
    local_time: "22:30", timezone: "Asia/Seoul", next_due_at: null as string | null,
    model_id: null as string | null, thinking_level: "high", profile_version: 0, pending_count: 32,
    status: "disabled", last_code: null as string | null, last_completed_at: null as string | null,
    available_models: ["gemini-3.1-flash-lite", "gemini-3.5-flash-lite"],
    stored_count: 4, storage_limit: 100000, capacity_blocked: false, can_run: true, retryable: true,
    run_saved_count: null as number | null, run_pending_count: null as number | null,
  };
  const handle = async (route: Route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    const manualProgress = () => ({ request_id: "manual-receipt", effective_request_id: "manual-receipt", kind: "manual",
      accepted_at: "2026-09-17T04:00:00Z", state: manualPolls < 2 ? "queued" : manualPolls < 4 ? "ai_running" : "completed",
      saved_count: manualPolls >= 4 ? 2 : 0, remaining_count: 0, job_count: 2, completed_job_count: manualPolls >= 4 ? 2 : 0, last_code: null, workflow_version: 1, followup: "relationships",
      flow_state: manualPolls < 4 ? "memory_running" : manualPolls < 6 ? "relationship_running" : "completed",
      relationship: { state: manualPolls < 6 ? "running" : "completed", request_id: "manual-receipt",
        target_count: manualPolls < 4 ? null : 1, memory_count: manualPolls < 4 ? null : 2,
        completed_count: manualPolls < 6 ? 0 : 1, kept_count: manualPolls < 6 ? 0 : 1, changed_count: 0, last_code: null, completed_at: null } });
    if (path.endsWith("/memory/batch-progress")) {
      if (manualKey) manualPolls++;
      await route.fulfill({ json: { scope: saved.scope, capability: { relationships: true, reason: null }, progress: manualKey ? manualProgress() : null } });
      return true;
    }
    if (path.endsWith("/memory/batch-run")) {
      expect(request.method()).toBe("POST");
      const body = request.postDataJSON();
      expect(body.followup).toBe("relationships");
      expect(body.expected_version).toBe(saved.version);
      expect(body.expected_profile_version).toBe(saved.profile_version);
      expect(body.expected_scope_version).toBeGreaterThan(0);
      expect(++manualRequests).toBe(1);
      manualKey = body.idempotency_key;
      await route.fulfill({ status: 202, json: { scope: saved.scope, disposition: "accepted", ...manualProgress() } });
      return true;
    }
    if (path.endsWith("/memory/embedding-settings")) {
      if (request.method() === "PUT") {
        const body = request.postDataJSON();
        expect(body.expected_version).toBe(embedding.version);
        embedding = { ...embedding, enabled: body.enabled, credential_id: body.credential_id,
          version: embedding.version + 1, ready: body.enabled, reason_code: body.enabled ? null : "memory_embedding_disabled" };
      }
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(embedding) });
      return true;
    }
    if (path.endsWith("/memory/batch-retry")) {
      expect(request.method()).toBe("POST");
      expect(++retryCount).toBe(1);
      saved = { ...saved, status: "pending", last_code: null };
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ ...saved, memory_enabled: enabled() }) });
      return true;
    }
    if (!path.endsWith("/memory/batch-settings")) return false;
    if (request.method() === "GET" && saved.ai_enabled && !saved.capacity_blocked) {
      if (retryCount) saved = { ...saved, status: "completed", pending_count: 0, last_code: null, last_completed_at: "2026-09-09T09:00:00Z" };
      else if (++pollsAfterSave >= 1) saved = { ...saved, status: "attention", last_code: "memory_selection_request_invalid" };
    }
    if (request.method() === "PUT") {
      const body = request.postDataJSON();
      expect(body.expected_version).toBe(saved.version);
      expect(body.consent_version).toBe("memory-selection-consent.v1");
      saved = { ...saved, ai_enabled: body.ai_enabled, shutdown_enabled: body.shutdown_enabled,
        schedule_enabled: body.schedule_enabled, local_time: body.local_time, model_id: body.model_id,
        thinking_level: body.thinking_level,
        version: saved.version + 1, profile_version: 1, status: "waiting", next_due_at: "2026-09-05T14:15:00Z" };
    }
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ ...saved, memory_enabled: enabled() }) });
    return true;
  };
  return Object.assign(handle, { capacityReached() {
    saved = { ...saved, status: "capacity_blocked", stored_count: 100000,
      capacity_blocked: true, can_run: false, retryable: false, pending_count: 1,
      run_saved_count: 1, run_pending_count: 1, last_code: "memory_capacity_reached" };
  } });
}

export async function verifyMemoryBatchControls(page: Page) {
  const embedding = page.getByRole("region", { name: "기억 의미 검색", exact: true });
  await expect(embedding.getByText("의미 검색 꺼짐", { exact: true })).toBeVisible();
  await embedding.getByLabel("의미 검색 사용", { exact: true }).check();
  await expect(embedding.getByRole("button", { name: "의미 검색 설정 저장" })).toBeDisabled();
  await expect(embedding.getByLabel("임베딩 모델", { exact: true })).toBeDisabled();
  await embedding.getByLabel("의미 검색용 API 설정", { exact: true }).selectOption("fixture-google-key");
  await embedding.getByRole("button", { name: "의미 검색 설정 저장" }).click();
  await expect(embedding.getByText("의미 검색 설정을 저장했어요.", { exact: true })).toBeVisible();
  await expect(embedding.getByText("의미 검색 설정됨", { exact: true })).toBeVisible();
  await embedding.getByLabel("의미 검색 사용", { exact: true }).uncheck();
  await embedding.getByRole("button", { name: "의미 검색 설정 저장" }).click();
  await expect(embedding.getByText("의미 검색 꺼짐", { exact: true })).toBeVisible();
  await expect(embedding.getByLabel("의미 검색용 API 설정", { exact: true })).toHaveValue("fixture-google-key");
  const region = page.getByRole("region", { name: "기억 정리 예약" });
  await expect(region.getByText("AI 기억 정리 사용 안 함", { exact: false })).toBeVisible();
  await region.getByLabel("AI 선별·정리 사용", { exact: true }).check();
  await expect(region.getByRole("button", { name: "정리 설정 저장" })).toBeDisabled();
  await expect(region.getByRole("combobox").locator('option:not([value=""])')).toHaveText([
    "Gemini 3.5 Flash-Lite (high)", "Gemini 3.5 Flash-Lite (medium)",
    "Gemini 3.1 Flash-Lite (high)", "Gemini 3.1 Flash-Lite (medium)",
  ]);
  await region.getByRole("combobox").selectOption("gemini-3.1-flash-lite:medium");
  await region.getByLabel("선택한 모델로 경험의 발췌가 전송되고 API 비용이 발생할 수 있음에 동의합니다.").check();
  await region.getByLabel("매일 정해진 시각에 정리").check();
  await region.getByLabel("예약 시각 · Asia/Seoul").fill("23:15");
  await region.getByRole("button", { name: "정리 설정 저장" }).click();
  await expect(region.getByText("기억 정리 설정을 저장했어요. 저장만으로 AI를 호출하지 않습니다.")).toBeVisible();
  await expect(region.getByLabel("예약 시각 · Asia/Seoul")).toHaveValue("23:15");
  await expect(region.getByRole("combobox")).toHaveValue("gemini-3.1-flash-lite:medium");
  await expect(region.getByText("예약 또는 종료를 기다리고 있어요", { exact: false })).toBeVisible();
  await expect(region.getByText("앱 업데이트 또는 지원 확인이 필요해요.", { exact: false })).toBeVisible();
  await region.getByRole("button", { name: "실패한 정리 다시 시도" }).click();
  await expect(region.getByText("다시 정리하도록 요청했어요.")).toBeVisible();
  await expect(region.getByText("정리를 마쳤어요.", { exact: false })).toBeVisible();
  await expect(region.getByText("앱 업데이트 또는 지원 확인이 필요해요.", { exact: false })).toHaveCount(0);
  await expect(region.getByRole("button", { name: "실패한 정리 다시 시도" })).toHaveCount(0);
  await region.getByLabel("예약 시각 · Asia/Seoul").fill("23:16");
  await expect(region.getByRole("button", { name: "지금 기억·관계 정리", exact: true })).toBeDisabled();
  await region.getByLabel("예약 시각 · Asia/Seoul").fill("23:15");
  const manualButton = region.getByRole("button", { name: "지금 기억·관계 정리", exact: true });
  await manualButton.focus();
  await expect(manualButton).toBeFocused();
  await manualButton.press("Enter");
  await expect(region.getByRole("button", { name: "지금 기억·관계 정리", exact: true })).toBeDisabled();
  await expect(region.getByText("기억 정리 중", { exact: true })).toBeVisible();
  await expect(region.getByText("기억 정리 완료 · 관계 정리 중 · 새 기억 2개", { exact: true })).toBeVisible();
  await expect(region.getByText("기억·관계 정리 완료 · 새 기억 2개", { exact: true })).toBeVisible();
  await expect(region.getByRole("button", { name: "지금 기억·관계 정리", exact: true })).toBeEnabled();
  await page.evaluate(() => { document.documentElement.style.zoom = "2"; });
  await expect(manualButton).toBeVisible();
  expect(await region.evaluate((element) => element.scrollWidth <= element.clientWidth + 1)).toBe(true);
  await page.evaluate(() => { document.documentElement.style.zoom = ""; });
}
