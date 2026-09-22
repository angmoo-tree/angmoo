"use client";

import { useEffect, useRef, useState } from "react";
import { getActivityRuntime, setActivityEngine, type ActivityRuntimeStatus, type ActivityEngine, type EngineScope } from "@/features/characters/api/personalized-activity";

const engines = { current: "기존 활동 방식", personalized_graph_v2: "기억을 반영하는 활동 방식 (V2)" };
const scopes = { character: "이 캐릭터", world: "이 World의 기본값", global: "모든 World의 기본값" };
const moods: Record<string, string> = { neutral: "보통", curious: "호기심", joyful: "기쁨", hopeful: "희망", calm: "평온", concerned: "걱정", frustrated: "답답함", sad: "슬픔", embarrassed: "쑥스러움" };
const sources: Record<string, string> = { character: "캐릭터 설정", world: "World 기본값", global: "전체 기본값", default: "초기 기본값" };
const reasons: Record<string, string> = { no_candidate: "새로 확인할 대상이 없습니다.", model_abstained: "이번에는 반응하지 않기로 했습니다.", activity_memory_followup_changed: "기억이 갱신되어 다음 활동에서 다시 판단합니다.", activity_source_changed: "원문이 바뀌어 이번 판단을 중단했습니다.", activity_state_changed: "현재 상태가 갱신되어 이번 판단을 중단했습니다.", activity_input_budget_exceeded: "이번 입력이 처리 범위를 넘어 정리가 필요합니다.", writer_failed: "판단은 마쳤지만 글 작성에 실패했습니다." };
const statuses: Record<string, string> = { running: "진행 중", waiting: "재개 대기", interrupted: "중단됨", aborted: "조건 변경으로 중단", no_action: "행동 없이 완료", completed: "완료", observed: "행동 없이 완료", failed: "확인 필요", delegated_current: "기존 방식으로 실행" };

/** LOCAL: payload-backed controls using existing semantic surface tokens. */
export function PersonalizedActivityPanel({ worldId, actorId }: { worldId: string; actorId: string }) {
  const [data, setData] = useState<ActivityRuntimeStatus | null>(null);
  const [scope, setScope] = useState<EngineScope>("character");
  const [choice, setChoice] = useState<ActivityEngine | "inherit">("inherit");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [revision, setRevision] = useState(0);
  const identity = `${worldId}:${actorId}`;
  const active = useRef(identity);
  const current = data?.world_id === worldId && data.world_character_id === actorId ? data : null;

  useEffect(() => {
    active.current = identity;
    const controller = new AbortController();
    getActivityRuntime(worldId, actorId, controller.signal).then((result) => {
      if (!controller.signal.aborted) { setData(result); setError(null); }
    }).catch(() => {
      if (!controller.signal.aborted) setError("활동 방식과 현재 상태를 불러오지 못했습니다. 다시 확인해 주세요.");
    });
    return () => { controller.abort(); active.current = ""; };
  }, [worldId, actorId, identity, revision]);

  async function save() {
    if (!current || busy) return;
    setBusy(true); setError(null);
    try {
      const next = await setActivityEngine(worldId, actorId, scope, choice === "inherit" ? null : choice, current.policies[scope].version);
      if (active.current === identity) setData(next);
    } catch {
      if (active.current === identity) setError("저장하지 못했습니다. 다른 곳에서 설정이 바뀌었는지 새로고침한 뒤 다시 시도해 주세요.");
    } finally { setBusy(false); }
  }

  return <section aria-label="개인화 활동 방식과 현재 상태" className="space-y-4 rounded-2xl border border-border-default bg-surface p-4">
    <h3 className="font-bold text-text-strong">활동 방식과 현재 상태</h3>
    {error && <p role="alert" className="text-sm text-text-secondary">{error}</p>}
    {!current ? <p className="text-sm text-text-secondary">상태 확인 중</p> : <>
      <p className="text-sm text-text-secondary">{engines[current.effective.engine]} · {sources[current.effective.source] ?? "설정 확인 필요"}</p>
      <p className="text-sm text-text-secondary">자율활동 {current.autonomous_enabled ? "켜짐" : "꺼짐"}. 활동 방식을 바꿔도 켜짐·꺼짐 설정은 유지됩니다. 진행 중인 활동은 시작 당시 방식으로 마칩니다.</p>
      <div className="space-y-2">
        <h4 className="font-bold text-text-strong">현재 상태</h4>
        {current.current_state.known ? <>
          <p className="text-sm text-text-secondary">{moods[current.current_state.mood ?? ""] ?? current.current_state.mood} · 강도 {current.current_state.mood_intensity}</p>
          <p className="break-words text-sm text-text-secondary">{current.current_state.state_note}</p>
          <p className="text-xs text-text-secondary">마지막 확인 {current.current_state.confirmed_at ? new Date(current.current_state.confirmed_at).toLocaleString("ko-KR") : "미확인"}</p>
        </> : <p className="text-sm text-text-secondary">아직 확인된 상태가 없습니다. 이후 정상적인 활동에서 형성됩니다.</p>}
      </div>
      {current.control_mode === "autonomous" && <fieldset disabled={busy} className="space-y-3">
        <legend className="font-bold text-text-strong">활동 방식 설정</legend>
        <label className="block text-sm text-text-secondary">적용 범위
          <select className="mt-1 min-h-11 w-full rounded-xl border border-border-default bg-surface px-3" value={scope} onChange={(event) => setScope(event.target.value as EngineScope)}>
            {Object.entries(scopes).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
          </select>
        </label>
        <label className="block text-sm text-text-secondary">사용할 방식
          <select className="mt-1 min-h-11 w-full rounded-xl border border-border-default bg-surface px-3" value={choice} onChange={(event) => setChoice(event.target.value as ActivityEngine | "inherit")}>
            <option value="inherit">기본값 따르기</option>
            {Object.entries(engines).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
          </select>
        </label>
        <p className="text-xs text-text-secondary">{scopes[scope]}에 저장된 설정: {current.policies[scope].engine ? engines[current.policies[scope].engine] : "기본값 따름"}. 개별 설정이 있는 캐릭터는 해당 설정을 우선합니다.</p>
        <button type="button" className="min-h-11 rounded-xl border border-border-default px-4 font-bold text-text-strong disabled:opacity-50" onClick={save}>{busy ? "저장 중" : "활동 방식 저장"}</button>
      </fieldset>}
      <div className="space-y-2 text-sm text-text-secondary">
        <h4 className="font-bold text-text-strong">최근 진행</h4>
        {current.runs.length ? current.runs.map((run) => <div key={run.activity_id}>
          <p>{new Date(run.started_at).toLocaleString("ko-KR")} · {statuses[run.status] ?? "확인 필요"}{run.public_action_count !== null && ` · 행동 ${run.public_action_count}개`}</p>
          {Object.entries(run.paths ?? {}).map(([name, path]) => <p key={name} className="text-xs">{({ inbox: "받은 대화", routine: "일과", feed: "피드" } as Record<string, string>)[name] ?? name} · {statuses[path.status] ?? "확인 필요"} · 행동 {path.public_action_count}개 · 선택 {path.selected_count}개 · 기억 검색 {path.recall_count}회{path.reason && ` · ${reasons[path.reason] ?? "이 경로를 완료하지 못했습니다. 다음 활동 결과를 확인해 주세요."}`}</p>)}
        </div>) : <p>아직 이 방식으로 기록된 실행이 없습니다.</p>}
      </div>
    </>}
    <button type="button" className="min-h-11 rounded-xl border border-border-default px-4 text-sm text-text-strong" onClick={() => setRevision((value) => value + 1)}>상태 새로고침</button>
  </section>;
}
