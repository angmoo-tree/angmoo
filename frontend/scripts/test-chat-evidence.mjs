import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import ts from "typescript";

const source = readFileSync("src/features/memory/utils/chat-evidence-presentation.ts", "utf8");
const compiled = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 }, reportDiagnostics: true });
assert.equal(compiled.diagnostics.length, 0);
const { evidenceTimes, evidenceTimeMatches, relationshipFieldsMatch, evidenceLimitationsMatch, evidenceWarnings, relationshipStatus } = await import(`data:text/javascript;base64,${Buffer.from(compiled.outputText).toString("base64")}`);
const item = () => ({ kind: "graph_relationship", availability: "available", excerpt: "Original perception", related_character: "Original name", direction: "outgoing", canonical_href: null,
  relationship_change: "changed", relationship_projection: { familiarity: 22, affinity: -3, trust: 10, tension: 4, interactions: 5, relationship_label: null, perception: "Original perception" } });
const read = () => ({ capability: "available", retrieval_limitations: { partial_axes: [], degraded_reason: null }, read_limitations: [] });

test("normal changes keep historical evidence without a search or current-read warning", () => {
  assert.equal(relationshipFieldsMatch(item()), true);
  assert.equal(evidenceLimitationsMatch(read()), true);
  assert.deepEqual(evidenceWarnings(read()), { retrieval: false, current: false, legacy: false });
  for (const [change, text] of [["same", "현재도 동일"], ["changed", "이후 변경됨"], ["not_checked", "현재 상태 비교 불가"]]) {
    assert.equal(relationshipStatus({ ...item(), relationship_change: change }, read()), text);
  }
});
test("unavailable and nonrelationship items cannot carry names, projections or change status", () => {
  for (const field of ["excerpt", "related_character", "direction", "canonical_href", "episode", "relationship_projection", "relationship_change"]) {
    const hidden = { ...item(), availability: "unavailable", excerpt: null, related_character: null, direction: null, canonical_href: null, episode: null, relationship_projection: null, relationship_change: null };
    assert.equal(relationshipFieldsMatch(hidden), true);
    hidden[field] = field === "episode" ? {} : item()[field] ?? "unexpected";
    assert.equal(relationshipFieldsMatch(hidden), false, field);
  }
  assert.equal(relationshipFieldsMatch({ ...item(), kind: "canonical_source" }), false);
});
test("additive fields reject unknown enum, malformed projection and unsafe numbers", () => {
  for (const change of ["later", 1, true, {}, []]) assert.equal(relationshipFieldsMatch({ ...item(), relationship_change: change }), false);
  for (const projection of [[], {}, { ...item().relationship_projection, identifier: "private" }, { ...item().relationship_projection, affinity: 101 }, { ...item().relationship_projection, interactions: 0.5 }, { ...item().relationship_projection, perception: false }]) {
    assert.equal(relationshipFieldsMatch({ ...item(), relationship_projection: projection }), false);
  }
  for (const limitations of [{ partial_axes: ["unknown"], degraded_reason: null }, { partial_axes: ["graph", "graph"], degraded_reason: null }, { partial_axes: [], degraded_reason: "changed" }, { partial_axes: [], degraded_reason: null, extra: 1 }]) {
    assert.equal(evidenceLimitationsMatch({ ...read(), retrieval_limitations: limitations }), false);
  }
  for (const codes of [["changed"], ["historical_unverified", "historical_unverified"], {}]) assert.equal(evidenceLimitationsMatch({ ...read(), read_limitations: codes }), false);
});
test("generation and current-read limitations remain separate; old response has safe fallback", () => {
  assert.deepEqual(evidenceWarnings({ ...read(), retrieval_limitations: { partial_axes: ["graph"], degraded_reason: "graph_unavailable" } }), { retrieval: true, current: false, legacy: false });
  assert.deepEqual(evidenceWarnings({ ...read(), capability: "degraded", read_limitations: ["current_unavailable"] }), { retrieval: false, current: true, legacy: false });
  const old = { capability: "degraded" };
  assert.equal(evidenceLimitationsMatch(old), true);
  assert.deepEqual(evidenceWarnings(old), { retrieval: false, current: false, legacy: true });
  const hidden = { ...item(), availability: "unavailable" };
  assert.equal(relationshipStatus(hidden, { ...read(), read_limitations: ["historical_unverified"] }), "당시 근거 확인 불가");
  assert.equal(relationshipStatus(hidden, { ...read(), read_limitations: ["current_unavailable"] }), "현재 표시할 수 없음");
  assert.equal(relationshipStatus({ ...item(), relationship_change: undefined }, old), "현재 상태 비교 불가");
});
test("all new visible copy exists in both feature catalogs", () => {
  const keys = ["답변 당시 관계", "현재도 동일", "이후 변경됨", "현재 상태 비교 불가", "당시 근거 확인 불가", "현재 표시할 수 없음", "답변을 만들 때 전달한 관계 정보예요. 이후 관계가 바뀌어도 당시 확인된 내용을 표시하며, 전체 관계 목록이나 과거 사건 기록은 아니에요.", "답변 생성 당시 일부 검색이 제한됐어요. 전달된 근거 중 확인 가능한 내용을 표시해요.", "일부 근거는 지금 확인하거나 표시할 수 없어요.", "일부 근거의 상태를 확인할 수 없어요.", "친숙도 {{familiarity}} · 호감 {{affinity}} · 신뢰 {{trust}} · 긴장 {{tension}} · 상호작용 {{interactions}}회"];
  for (const language of ["ko", "en"]) {
    const catalog = JSON.parse(readFileSync(`src/features/memory/locales/${language}.json`, "utf8"));
    for (const key of keys) assert.ok(typeof catalog[key] === "string" && catalog[key].length, `${language}: ${key}`);
    assert.equal((catalog[keys.at(-1)].match(/{{\w+}}/g) ?? []).length, 5);
  }
});


test("evidence timestamps distinguish events, source intervals and later recording",()=>{
  const base={kind:"episode_memory",availability:"available",occurred_at:"2026-10-17T00:00:00Z"};
  assert.equal(evidenceTimes(base)[0].label,"기록된 시각·사건 시각 여부 미확인");
  const time={kind:"interval",event_from:"2026-10-15T00:00:00Z",event_to:"2026-10-16T00:00:00Z",recorded_at:"2026-10-17T00:00:00Z"};
  assert.equal(evidenceTimeMatches({...base,time_provenance:time}),true);
  const rows=evidenceTimes({...base,time_provenance:time});
  assert.deepEqual(rows.map(row=>row.value),[time.event_from,time.event_to,time.recorded_at]);
  assert.equal(rows[2].label,"기억 기록 시각·사건 시각 아님");
  assert.deepEqual(evidenceTimes({...base,time_provenance:{kind:"unknown",event_from:null,event_to:null,recorded_at:null}}),[{label:"사건 시각 미확인",value:null}]);
  assert.equal(evidenceTimeMatches({...base,time_provenance:{...time,event_from:"not-a-date"}}),false);
  assert.equal(evidenceTimeMatches({...base,availability:"unavailable",time_provenance:time}),false);
  for(const language of ["ko","en"]){
    const catalog=JSON.parse(readFileSync(`src/features/memory/locales/${language}.json`,"utf8"));
    for(const row of rows)assert.ok(catalog[row.label]);
  }
});
