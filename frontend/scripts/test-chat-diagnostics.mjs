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
