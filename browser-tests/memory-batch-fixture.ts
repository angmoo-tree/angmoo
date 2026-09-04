import { expect, type Page, type Route } from "@playwright/test";

export function memoryBatchFixture(worldId: string, subjectId: string, enabled: () => boolean) {
  let saved = {
    scope: { world_id: worldId, subject_world_character_id: subjectId }, version: 0,
    ai_enabled: false, shutdown_enabled: true, schedule_enabled: false,
    local_time: "22:30", timezone: "Asia/Seoul", next_due_at: null as string | null,
    model_id: null as string | null, profile_version: 0, pending_count: 2,
    status: "disabled", last_code: null, last_completed_at: null,
    available_models: ["gemini-3.1-flash-lite", "gemini-3.5-flash-lite"],
  };
  return async (route: Route) => {
    const request = route.request();
    if (!new URL(request.url()).pathname.endsWith("/memory/batch-settings")) return false;
    if (request.method() === "PUT") {
      const body = request.postDataJSON();
      expect(body.expected_version).toBe(saved.version);
      expect(body.consent_version).toBe("memory-selection-consent.v1");
      saved = { ...saved, ai_enabled: body.ai_enabled, shutdown_enabled: body.shutdown_enabled,
        schedule_enabled: body.schedule_enabled, local_time: body.local_time, model_id: body.model_id,
        version: saved.version + 1, profile_version: 1, status: "waiting", next_due_at: "2026-09-05T14:15:00Z" };
    }
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ ...saved, memory_enabled: enabled() }) });
    return true;
  };
}

export async function verifyMemoryBatchControls(page: Page) {
  const region = page.getByRole("region", { name: "기억 정리 예약" });
  await expect(region.getByText("AI 기억 정리 사용 안 함", { exact: false })).toBeVisible();
  await region.getByLabel("AI 선별·정리 사용", { exact: true }).check();
  await expect(region.getByRole("button", { name: "정리 설정 저장" })).toBeDisabled();
  await region.getByRole("combobox").selectOption("gemini-3.1-flash-lite");
  await region.getByLabel("선택한 모델로 경험의 발췌가 전송되고 API 비용이 발생할 수 있음에 동의합니다.").check();
  await region.getByLabel("매일 정해진 시각에 정리").check();
  await region.getByLabel("예약 시각 · Asia/Seoul").fill("23:15");
  await region.getByRole("button", { name: "정리 설정 저장" }).click();
  await expect(region.getByText("기억 정리 설정을 저장했어요. 저장만으로 AI를 호출하지 않습니다.")).toBeVisible();
  await expect(region.getByLabel("예약 시각 · Asia/Seoul")).toHaveValue("23:15");
  await expect(region.getByText("예약 또는 종료를 기다리고 있어요", { exact: false })).toBeVisible();
}
