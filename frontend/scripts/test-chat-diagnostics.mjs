import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import ts from "typescript";

// Use the project's compiler on Node 20 as well as runtimes with native TS stripping.
const source = readFileSync(new URL("../src/features/chat/utils/diagnostic-export.ts", import.meta.url), "utf8");
const compiled = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 } }).outputText;
const { diagnosticExport, diagnosticFilename, diagnosticSnapshotMatches } = await import(`data:text/javascript;base64,${Buffer.from(compiled).toString("base64")}`);

function sample(id = "failed-request") {
  return { world_id: "world", thread_id: "thread", request_id: id, request_state: "failed",
    request: { request_id: id, created_at: "2026-09-12T12:00:00Z", state: "failed", user_message_id: 1, attempt_number: 2, retry_of_request_id: "previous" },
    status: "available", record: { version: "chat-retrieval-diagnostics.v1", events: [{ event: "decision_summary", detail_captured: true, detail_omitted: 0, trace_complete: true }], omitted_events: 0 },
    capture: { enabled: false, remaining: 0, expires_at: null }, details: [{ event: "reference_failure", trace_version: "decision-trace.v2", field_path: "entities.ref" }] };
}

test("export identifies the actual failed request and separates capture time", () => {
  const data = sample();
  data.credential = "must-not-export";
  data.request.scope_hash = "must-not-export";
  const file = diagnosticExport(data, "world", "thread", "failed-request", new Date("2026-09-12T13:00:00Z"));
  assert.equal(file.request.state, "failed");
  assert.notEqual(file.exported_at, file.request.created_at);
  assert.equal(file.completeness.detail_captured, true);
  assert.equal(file.capture_at_export.enabled, false);
  assert.equal(file.request.retry_of_request_id, "previous");
  assert.ok(!JSON.stringify(file).includes("must-not-export"));
  assert.match(diagnosticFilename(file.request.request_id, file.request.created_at), /failed-request.json$/);
});

test("snapshot refuses stale request, mismatched metadata and changed scope", () => {
  for (const args of [["world", "thread", "other"], ["other", "thread", ""], ["world", "other", ""]]) {
    assert.throws(() => diagnosticExport(sample(), ...args));
  }
  const data = sample();
  data.request.request_id = "old-success";
  assert.equal(diagnosticSnapshotMatches(data, "world", "thread", ""), false);
});

test("basic-only and legacy traces do not fabricate detailed capture", () => {
  const data = sample();
  data.details = null;
  data.record.events = [];
  const file = diagnosticExport(data, "world", "thread", "");
  assert.equal(file.details_status, "not_available");
  assert.equal(file.completeness.trace_complete, null);
  assert.equal(file.details, null);
  data.details = [{ trace_version: "decision-trace.v1" }];
  assert.equal(diagnosticExport(data, "world", "thread", "").details[0].trace_version, "decision-trace.v1");
});

test("v2 export keeps structured failure nulls and strips undeclared trace fields", () => {
  const data = sample();
  data.details = null;
  data.detail_availability = "available";
  data.search_trace = {
    version: "search-diagnostic-trace.v1", coverage: "partial", stages: [], lineage: [],
    stage_events_dropped: 1, lineage_edges_dropped: 0, aliases_dropped: 0, credential: "must-not-export",
    terminals: [{ axis: "vector", terminal_state: "error", worker_exit_code: -15,
      eligible_vector_count: null, traceback: "must-not-export",
      failure: { failure_code: "mapping_missing", failure_stage: "mapping_read",
        exception_kind: "MemoryVectorProjectionError", sqlite_error_code: null, message: "must-not-export" } }],
  };
  const output = diagnosticExport(data, "world", "thread", "failed-request");
  assert.equal(output.export_version, "angmoo-query-diagnostics.export.v2");
  assert.equal(output.details_status, "available");
  assert.equal(output.search_trace.terminals[0].eligible_vector_count, null);
  assert.equal(output.search_trace.terminals[0].worker_exit_code, -15);
  assert.ok(!JSON.stringify(output).includes("must-not-export"));
});

test("missing trace is not fabricated for old requests or lost detail", () => {
  const data = sample();
  data.details = null;
  data.detail_availability = "not_retained";
  const output = diagnosticExport(data, "world", "thread", "failed-request");
  assert.equal(output.search_trace, null);
  assert.equal(output.detail_availability, "not_retained");
});

test("canonical receipt retains unknown counts and never exports worker internals", () => {
  const data = sample();
  data.search_trace = { version: "search-diagnostic-trace.v1", coverage: "complete", stages: [], lineage: [], terminals: [],
    stage_events_dropped: 0, lineage_edges_dropped: 0, aliases_dropped: 0,
    canonical_reads: [{ stage: "revalidate", status: "deadline", wait_ms: null, elapsed_ms: null, sql_count: null,
      unique_nodes: null, memo_hits: null, cleaned: null, connection: "must-not-export" }] };
  const output = diagnosticExport(data, "world", "thread", "failed-request");
  assert.equal(output.search_trace.canonical_reads[0].sql_count, null);
  assert.equal(output.search_trace.canonical_reads[0].cleaned, null);
  assert.ok(!JSON.stringify(output).includes("must-not-export"));
  delete data.search_trace.canonical_reads;
  assert.ok(!("canonical_reads" in diagnosticExport(data, "world", "thread", "failed-request").search_trace));
});


test("temporal and DB export keep null timing and bounded content-free attempts", () => {
  const data = sample();
  data.temporal_recall = { time_resolution: "invalid", query_origin: "original_user_message", retrieval_executed: true,
    time_filter_applied: false, applied_from: null, expression: "must-not-export" };
  data.db_write = { request_id: data.request_id, attempt_number: 2, coverage: "partial", longest_hold_ms: null,
    total_write_span_ms: 0, attempts: Array.from({length:70}, (_,i)=>({sequence:i+1, stage:"response_finalize", basis:"write_span_only",
      hold_ms:null, write_span_ms:0, sql:"must-not-export", path:"must-not-export"})), parameters:"must-not-export" };
  const output = diagnosticExport(data,"world","thread",data.request_id);
  assert.equal(output.temporal_recall.time_resolution,"invalid");
  assert.equal(output.temporal_recall.applied_from,null);
  assert.equal(output.db_write.attempts.length,64);
  assert.equal(output.db_write.longest_hold_ms,null);
  assert.equal(output.db_write.attempts[0].write_span_ms,0);
  assert.ok(!JSON.stringify(output).includes("must-not-export"));
  data.db_write.attempt_number=1;
  assert.equal(diagnosticExport(data,"world","thread",data.request_id).db_write,null);
  assert.equal(diagnosticExport(sample(),"world","thread","").temporal_recall,null);
});

test("actual diagnostic component renders bilingual nulls and honest search status", async () => {
  const { createRequire } = await import("node:module");
  const require = createRequire(import.meta.url);
  const React = require("react");
  const { renderToStaticMarkup } = require("react-dom/server");
  const { I18nextProvider } = require("react-i18next");
  const i18next = require("i18next");
  function compile(path, imports) {
    const module = {exports:{}};
    const text = ts.transpileModule(readFileSync(new URL(path,import.meta.url),"utf8"),
      {compilerOptions:{module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.ReactJSX,target:ts.ScriptTarget.ES2022,esModuleInterop:true}}).outputText;
    new Function("require","module","exports",text)(name=>imports[name]??require(name),module,module.exports);
    return module.exports;
  }
  const hook=compile("../src/hooks/use-ui-text.ts",{});
  const component=compile("../src/features/chat/components/temporal-db-diagnostics.tsx",{
    "@/hooks/use-ui-text":hook,"./retrieval-diagnostics.module.css":{timing:"timing",events:"events"}}).TemporalDbDiagnostics;
  const data=sample();
  data.temporal_recall={time_resolution:"invalid",query_origin:"original_user_message",retrieval_executed:true,time_filter_applied:false,
    reference_utc:"2026-10-17T00:00:00Z",timezone:"Asia/Seoul"};
  data.db_write={request_id:data.request_id,attempt_number:2,coverage:"write_span_only",longest_hold_ms:null,total_hold_ms:null,
    total_write_span_ms:2.5,retry_count:0,retry_wait_ms:null,omitted_attempts:0,
    attempts:[{sequence:1,stage:"response_finalize",outcome:"committed",hold_ms:null,write_span_ms:2.5,commit_ms:0.5,diagnostic_persist_ms:0.2}]};
  for(const language of ["ko","en"]){
    const catalog=JSON.parse(readFileSync(new URL(`../src/features/chat/locales/${language}.json`,import.meta.url),"utf8"));
    const i18n=i18next.createInstance();
    await i18n.init({lng:language,resources:{[language]:{chat:catalog}},keySeparator:false,nsSeparator:false,interpolation:{escapeValue:false}});
    const html=renderToStaticMarkup(React.createElement(I18nextProvider,{i18n},React.createElement(component,{data})));
    assert.ok(html.includes(catalog["미측정"]));
    assert.ok(html.includes(catalog["날짜 조건을 적용하지 않은 관련 검색입니다. 검색 결과가 질문한 날짜의 일이라는 뜻은 아닙니다."]));
    assert.ok(html.includes("2.500 ms"));
    assert.ok(!html.includes("undefined"));
    if(language==="en")assert.ok(!/[가-힣]/u.test(html));
    if(process.env.CHAT_TEMPORAL_PREVIEW_DIR){
      const {mkdirSync,writeFileSync}=await import("node:fs");
      mkdirSync(process.env.CHAT_TEMPORAL_PREVIEW_DIR,{recursive:true});
      const css=readFileSync(new URL("../src/features/chat/components/retrieval-diagnostics.module.css",import.meta.url),"utf8");
      writeFileSync(`${process.env.CHAT_TEMPORAL_PREVIEW_DIR}/${language}.html`,`<!doctype html><html lang="${language}"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>Chat diagnostic fixture</title><style>body{font-family:system-ui;margin:0}main{max-width:560px;padding:16px;margin:auto}h4{margin-top:24px}${css}</style><main>${html}</main></html>`);
    }
    const notSearched={...data,db_write:null,temporal_recall:{...data.temporal_recall,retrieval_executed:false}};
    const missing=renderToStaticMarkup(React.createElement(I18nextProvider,{i18n},React.createElement(component,{data:notSearched})));
    assert.ok(!missing.includes(catalog["날짜 조건을 적용하지 않은 관련 검색입니다. 검색 결과가 질문한 날짜의 일이라는 뜻은 아닙니다."]));
    assert.ok(missing.includes(catalog["이 요청의 DB 쓰기 시간은 수집되지 않았거나 보관이 끝났습니다."]));
  }
});
