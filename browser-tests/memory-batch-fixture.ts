import { expect, type Page, type Route } from "@playwright/test";

export function memoryBatchFixture(worldId: string, subjectId: string, enabled: () => boolean) {
  let embedding = { scope: { world_id: worldId, subject_world_character_id: subjectId }, enabled: false,
    provider: "google", model: "gemini-embedding-2", credential_id: null as string | null,
    profile: "fixture-profile", version: 0, ready: false, reason_code: "memory_embedding_disabled" as string | null,
    runtime_status: "ready", available_credentials: [], preparation_state: "needs_preparation", preparation_revision: 0 };
  let blocked = false;
  const processing = () => ({ scope: embedding.scope, version: 1, memory_enabled: enabled(),
    daily_enabled: false, local_time: "23:51", timezone: "Asia/Seoul", shutdown_apply_enabled: true,
    next_due_at: null, last_applied_at: null, pending_count: blocked ? 1 : 32, blocked_count: 0,
    applied_count: 0, status: blocked ? "partial_error" : "idle", result: null });
  const keys = {
    consolidation: {provider:"google",model:"gemini-3.1-flash-lite",thinking_level:"high",has_key:false,fingerprint:null as string|null,revision:0,configuration_revision:0},
    embedding: {provider:"google",model:"gemini-embedding-2",thinking_level:null as string|null,has_key:false,fingerprint:null as string|null,revision:0,configuration_revision:0},
  };
  let preparationRequests = 0;
  let manualPolls = 0;
  let manualRequests = 0;
  let manualKey: string | null = null;
  let pollsAfterSave = 0;
  let retryCount = 0;
  let saved = {
    scope: { world_id: worldId, subject_world_character_id: subjectId }, version: 0,
    ai_enabled: false, shutdown_enabled: true, schedule_enabled: false,
    local_time: "22:30", timezone: "Asia/Seoul", next_due_at: null as string | null,
    model_id: "gemini-3.1-flash-lite" as string | null, thinking_level: "high", profile_version: 0, pending_count: 32,
    status: "disabled", last_code: null as string | null, last_completed_at: null as string | null,
    available_models: ["gemini-3.1-flash-lite", "gemini-3.5-flash-lite"],
    stored_count: 4, storage_limit: 100000, capacity_blocked: false, can_run: true, retryable: true,
    run_saved_count: null as number | null, run_pending_count: null as number | null,
  };
  const handle = async (route: Route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    if (path.endsWith("/memory/processing-settings")) {
      await route.fulfill({ json: processing() }); return true;
    }
    if (path.endsWith("/memory/unsaved-experiences")) {
      await route.fulfill({ json: { scope: embedding.scope, items: [], next_cursor: null,
        blocked_count: 0, scope_busy: false, can_recheck: false } }); return true;
    }
    if (/\/credentials\/(consolidation|embedding)$/.test(path)) {
      const purpose = path.split("/").at(-1) as keyof typeof keys;
      if (request.method() === "PUT") {
        const body = request.postDataJSON();
        expect(body.credential_id).toBeUndefined(); expect(body.expected_revision).toBe(keys[purpose].revision);
        keys[purpose] = {...keys[purpose],provider:body.provider,model:body.model,thinking_level:body.thinking_level,
          has_key:keys[purpose].has_key || Boolean(body.api_key),fingerprint:"synthetic-fingerprint",revision:keys[purpose].revision+1};
        if (purpose === "consolidation") {
          saved = {...saved,model_id:body.model,thinking_level:body.thinking_level,profile_version:saved.profile_version+1};
          keys[purpose].configuration_revision=saved.profile_version;
        }
      }
      await route.fulfill({json:keys[purpose]}); return true;
    }
    if (path.endsWith("/memory/embedding-preparation")) {
      expect(request.method()).toBe("POST"); expect(++preparationRequests).toBe(1);
      expect(request.postDataJSON().expected_revision).toBe(embedding.preparation_revision);
      embedding={...embedding,preparation_state:"ready",preparation_revision:embedding.preparation_revision+1};
      await route.fulfill({status:202,json:embedding}); return true;
    }
    const manualProgress = () => ({ request_id: "manual-receipt", effective_request_id: "manual-receipt", kind: "manual",
      accepted_at: "2026-09-17T04:00:00Z", state: manualPolls < 2 ? "queued" : manualPolls < 4 ? "ai_running" : "completed",
      saved_count: manualPolls >= 4 ? 2 : 0, remaining_count: 0, job_count: 2, completed_job_count: manualPolls >= 4 ? 2 : 0, last_code: null, workflow_version: 1, followup: "relationships",
      flow_state: manualPolls < 4 ? "relationship_running" : "completed",
      relationship: { state: manualPolls < 4 ? "running" : "completed", request_id: "manual-receipt",
        target_count: manualPolls < 4 ? null : 1, memory_count: manualPolls < 4 ? null : 2,
        completed_count: manualPolls < 4 ? 0 : 1, kept_count: manualPolls < 4 ? 0 : 1, changed_count: 0, last_code: null, completed_at: null } });
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
          version: embedding.version + 1, ready: body.enabled && keys.embedding.has_key, reason_code: body.enabled ? null : "memory_embedding_disabled" };
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
    blocked = true;
    saved = { ...saved, status: "capacity_blocked", stored_count: 100000,
      capacity_blocked: true, can_run: false, retryable: false, pending_count: 1,
      run_saved_count: 1, run_pending_count: 1, last_code: "memory_capacity_reached" };
  } });
}

export async function verifyMemoryBatchControls(page: Page) {
  const embedding = page.getByRole("region", { name: "임베딩 모델 API 키", exact: true });
  await expect(embedding.getByText("의미 검색 꺼짐", { exact: true })).toBeVisible();
  await embedding.getByLabel("의미 검색 사용", { exact: true }).check();
  await expect(embedding.getByRole("button", { name: "의미 검색 설정 저장" })).toBeDisabled();
  await expect(embedding.getByText("Gemini Embedding 2",{exact:true})).toBeVisible();
  await expect(embedding.getByLabel("의미 검색용 API 설정",{exact:true})).toHaveCount(0);
  await embedding.getByLabel("새 API key", {exact:true}).fill("own-synthetic-embedding-key");
  await embedding.getByRole("button",{name:"키·모델 저장",exact:true}).click();
  await expect(embedding.getByLabel("새 API key",{exact:true})).toHaveValue("");
  await embedding.getByRole("button", { name: "의미 검색 설정 저장" }).click();
  await expect(embedding.getByText("의미 검색 설정을 저장했어요.", { exact: true })).toBeVisible();
  await expect(embedding.getByText("의미 검색 설정됨", { exact: true })).toBeVisible();
  await expect(embedding.getByText("검색 자료 준비 필요",{exact:true})).toBeVisible();
  await embedding.getByRole("button",{name:"검색 자료 준비 시작",exact:true}).click();
  await expect(embedding.getByText("검색 자료 준비됨",{exact:true})).toBeVisible();
  await embedding.getByLabel("의미 검색 사용", { exact: true }).uncheck();
  await embedding.getByRole("button", { name: "의미 검색 설정 저장" }).click();
  await expect(embedding.getByText("의미 검색 꺼짐", { exact: true })).toBeVisible();
  await expect(embedding.getByText("API key 저장됨",{exact:false})).toBeVisible();
  const region = page.getByRole("region", { name: "관계 정리", exact:true });
  await expect(region.getByText("저장된 기억을 바탕으로 캐릭터별 관계를 정리해요.", { exact: false })).toBeVisible();
  await region.getByLabel("AI 관계 정리 사용", { exact: true }).check();
  await expect(region.getByRole("button", { name: "관계 설정 저장" })).toBeDisabled();
  await expect(region.getByRole("combobox").locator('option:not([value=""])')).toHaveText([
    "Gemini 3.5 Flash-Lite (high)", "Gemini 3.5 Flash-Lite (medium)",
    "Gemini 3.1 Flash-Lite (high)", "Gemini 3.1 Flash-Lite (medium)",
  ]);
  await region.getByRole("combobox").selectOption("google:gemini-3.1-flash-lite:medium");
  await region.getByLabel("새 API key",{exact:true}).fill("own-synthetic-consolidation-key");
  await region.getByRole("button",{name:"키·모델 저장",exact:true}).click();
  await expect(region.getByLabel("새 API key",{exact:true})).toHaveValue("");
  await region.getByLabel("관계 정리를 위해 저장된 기억이 선택한 모델로 전송되며 API 비용이 발생할 수 있음에 동의합니다.").check();
  await region.getByLabel("매일 정해진 시각에 관계 정리").check();
  await region.getByLabel("예약 시각 · Asia/Seoul").fill("23:15");
  await region.getByRole("button", { name: "관계 설정 저장" }).click();
  await expect(region.getByText("관계 정리 설정을 저장했어요.")).toBeVisible();
  await expect(region.getByLabel("예약 시각 · Asia/Seoul")).toHaveValue("23:15");
  await expect(region.getByRole("combobox")).toHaveValue("google:gemini-3.1-flash-lite:medium");
  // Relationship settings no longer expose the retired Memory batch failure
  // control. Exercise the retained explicit, dirty-guarded relationship run below.
  await expect(region.getByRole("button", { name: "실패한 정리 다시 시도" })).toHaveCount(0);
  await region.getByLabel("예약 시각 · Asia/Seoul").fill("23:16");
  await expect(region.getByRole("button", { name: "지금 관계 정리", exact: true })).toBeDisabled();
  await region.getByLabel("예약 시각 · Asia/Seoul").fill("23:15");
  const manualButton = region.getByRole("button", { name: "지금 관계 정리", exact: true });
  await manualButton.focus();
  await expect(manualButton).toBeFocused();
  await manualButton.press("Enter");
  await expect(region.getByRole("button", { name: "지금 관계 정리", exact: true })).toBeDisabled();
  await expect(region.getByText("관계 정리 중", { exact: true })).toBeVisible();
  await expect(region.getByText("관계 정리 완료", { exact: true })).toBeVisible();
  await expect(region.getByText("관계 1 / 1개 검토 완료 · 유지 1개 · 갱신 판단 0개", { exact: true })).toBeVisible();
  await expect(region.getByRole("button", { name: "지금 관계 정리", exact: true })).toBeEnabled();
  await page.evaluate(() => { document.documentElement.style.zoom = "2"; });
  await expect(manualButton).toBeVisible();
  expect(await region.evaluate((element) => element.scrollWidth <= element.clientWidth + 1)).toBe(true);
  await page.evaluate(() => { document.documentElement.style.zoom = ""; });
}
