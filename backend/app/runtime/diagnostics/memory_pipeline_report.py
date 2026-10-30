"""Independent counters, canonical denominators and honest timing attribution."""
from collections import Counter, defaultdict
from datetime import UTC, datetime
import json
from math import ceil
from pathlib import Path
from app.runtime.diagnostics.memory_pipeline_observation import CAPABILITY
from app.runtime.diagnostics.memory_pipeline_snapshot import snapshot


def capability(directory):
    health = []
    damaged = 0
    for path in (Path(directory) / "memory-pipeline").glob("health-*.json"):
        try:
            row = json.loads(path.read_text())
            if row.get("schema") != CAPABILITY or not isinstance(row.get("heartbeat_at"), str) or not isinstance(row.get("sequence"), int):
                raise ValueError()
            instant = datetime.fromisoformat(row["heartbeat_at"])
            if instant.tzinfo is None or not isinstance(row.get("written", {}), dict):
                raise ValueError()
            for field in ("expected", "written"):
                if not isinstance(row.get(field, {}), dict) or any(not isinstance(count, int) or count < 0 for count in row.get(field, {}).values()):
                    raise ValueError()
            health.append(row)
        except (OSError, ValueError, TypeError, AttributeError):
            damaged += 1
    fresh = any(0 <= (datetime.now(UTC) - datetime.fromisoformat(row["heartbeat_at"])).total_seconds() <= 150 and not row.get("final") for row in health)
    return {"capability": CAPABILITY, "support": "supported" if health else "unavailable",
            "runtime_fresh": fresh, "processes": health, "damaged": damaged,
            "sample_observed": any(sum(row.get("written", {}).values()) > 0 for row in health)}


def read_events(directory):
    events, damaged = [], 0
    size = 0
    for path in sorted((Path(directory) / "memory-pipeline").glob("events-*.jsonl")):
        size += path.stat().st_size
        if size > 64 * 1024 * 1024:
            damaged += 1
            break
        with path.open(encoding="utf-8") as stream:
            for line in stream:
                try:
                    event = json.loads(line)
                    if len(line.encode()) > 16 * 1024 or event.get("schema") != CAPABILITY:
                        raise ValueError()
                    events.append(event)
                except (ValueError, TypeError):
                    damaged += 1
    return events, damaged


def timing(events):
    groups = defaultdict(list)
    for event in events:
        if event.get("span_id"):
            groups[(event["process_instance_id"], event["span_id"])].append(event)
    spans, open_count = [], 0
    for (process, span_id), rows in groups.items():
        starts = [e for e in rows if e["event"] == "stage" and e.get("boundary") == "start"]
        ends = [e for e in rows if e["event"] == "stage" and e.get("boundary") == "end"]
        if not starts or not ends:
            open_count += 1
            continue
        start, end = starts[0], ends[-1]
        entry = {key: start.get(key) for key in ("span_id", "parent_span_id", "operation", "writer", "database_id", "queue_id", "actor_id", "run_id", "item_id")}
        entry.update(process_instance_id=process, start_ns=start["monotonic_ns"], end_ns=end["monotonic_ns"],
                     elapsed_ms=(end["monotonic_ns"] - start["monotonic_ns"]) / 1e6, outcome=end.get("outcome"))
        # Per-attempt intervals. Parent/child durations are never summed.
        attempts = defaultdict(dict)
        for row in rows:
            if row["event"] in {"sqlite", "postgresql_attempt"}:
                attempts[row.get("attempt", 1)][row.get("boundary")] = row["monotonic_ns"]
        entry["attempts"] = []
        for number, marks in attempts.items():
            measured = {"attempt": number, "terminal": "committed" if "committed" in marks else "rolled_back" if "rolled_back" in marks else "incomplete"}
            for label, left, right in (("checkout_ms", "checkout_started", "checkout_complete"),
                ("begin_wait_ms", "begin_started", "acquired"), ("commit_ms", "commit_started", "committed"),
                ("writer_hold_ms", "acquired", "committed" if "committed" in marks else "rolled_back")):
                measured[label] = (marks[right] - marks[left]) / 1e6 if left in marks and right in marks else None
            entry["attempts"].append(measured)
        spans.append(entry)
    values = sorted(row["elapsed_ms"] for row in spans)
    summary = {"n": len(values), "p50_ms": values[(len(values)-1)//2] if values else None,
               "p95_ms": values[max(0, ceil(len(values)*0.95)-1)] if values else None,
               "longest_three": sorted(spans, key=lambda row: row["elapsed_ms"], reverse=True)[:3],
               "over_30s_review_count": sum(value >= 30_000 for value in values), "open_spans": open_count,
               "attribution": "measured_intervals_only_uncovered_gaps_unknown", "nested_spans_additive": False}
    tasks = defaultdict(dict)
    for event in events:
        if event["event"] == "queue" and event.get("task_id"):
            tasks[(event["process_instance_id"], event["queue_id"], event["task_id"])][event.get("boundary")] = event["monotonic_ns"]
    summary["queues"] = [{"process_instance_id": key[0], "queue_id": key[1], "task_id": key[2],
        "wait_ms": (marks["start"]-marks["submit"])/1e6 if "start" in marks and "submit" in marks else None,
        "terminal": "completed" if "end" in marks else "cancelled" if "cancelled" in marks else "incomplete"} for key, marks in tasks.items()]
    summary["per_operation"] = {}
    for operation in {row["operation"] for row in spans}:
        measured = sorted(row["elapsed_ms"] for row in spans if row["operation"] == operation)
        summary["per_operation"][operation] = {"n":len(measured), "p50_ms":measured[(len(measured)-1)//2],
            "p95_ms":measured[ceil(len(measured)*.95)-1], "max_ms":max(measured)}
    # Sweep only SQLite acquisition/hold intervals in one monotonic clock.
    # Bound this diagnostic summary independently of the complete event export.
    # Even overlap is evidence of a candidate, never proof of the lock owner.
    summary["contenders"], summary["contenders_truncated"] = [], False
    intervals = defaultdict(list)
    for (process, span_id), rows in groups.items():
        attempts = defaultdict(dict)
        for row in rows:
            if row["event"] == "sqlite" and row.get("database_id"):
                attempts[(row["database_id"], row.get("attempt", 1))][row.get("boundary")] = row["monotonic_ns"]
        for (database, attempt), marks in attempts.items():
            for kind, left, right in (("wait", "begin_started", "acquired"),
                ("hold", "acquired", "committed" if "committed" in marks else "rolled_back")):
                if left in marks and right in marks and marks[right] > marks[left]:
                    intervals[(process, database)].append((marks[left], marks[right], kind, span_id, attempt))
    for (process, database), ranges in intervals.items():
        active = []
        for current in sorted(ranges):
            active = [row for row in active if row[1] > current[0]]
            for other in active:
                if current[2] == other[2] or current[3] == other[3]:
                    continue
                waiting, holder = (current, other) if current[2] == "wait" else (other, current)
                summary["contenders"].append({"process_instance_id": process, "database_id": database,
                    "span_id": waiting[3], "attempt": waiting[4], "overlap_span_id": holder[3],
                    "overlap_attempt": holder[4], "causality": "overlap_only_not_proven"})
                if len(summary["contenders"]) >= 256:
                    summary["contenders_truncated"] = True
                    break
            if summary["contenders_truncated"]:
                break
            if len(active) >= 256:
                summary["contenders_truncated"] = True
                break
            active.append(current)
        if summary["contenders_truncated"]:
            break
    return spans, summary


def export_memory(directory, destination, database, manifest, *, data_root):
    destination = Path(destination) / "memory-pipeline"
    destination.mkdir(parents=True, exist_ok=False)
    support = capability(directory)
    events, damaged = read_events(directory)
    # The sink is already scoped; verify session and scope again on export.
    events = [row for row in events if row.get("session_id") == manifest["session_id"] and
              row.get("world_id", manifest["world_id"]) == manifest["world_id"] and
              (row.get("actor_id") is None or row["actor_id"] in manifest["actor_ids"])]
    canonical = snapshot(database, manifest, data_root=data_root)
    actual = defaultdict(Counter)
    sequences = defaultdict(list)
    for row in events:
        process = row["process_instance_id"]
        actual[process][f"{row['event']}:{row.get('boundary', '')}"] += 1
        sequences[process].append(row["sequence"])
    gaps, missing = 0, 0
    closed = bool(support["processes"])
    for health in support["processes"]:
        process = health["process_instance_id"]
        expected = Counter(health.get("expected", {}))
        missing += sum((expected - actual[process]).values())
        gaps += max(0, health["sequence"] - len(set(sequences[process])))
        closed &= health.get("final") is True and health.get("queued") == 0
    spans, summary = timing(events)
    candidates = {member["item_id"] for event in events if event["event"] == "embedding_batch" and event.get("boundary") == "candidates" for member in event.get("members", [])}
    persisted = {row["item_id"] for row in events if row["event"] == "result" and row.get("boundary") in {"committed", "current"} and row.get("outcome") in {"indexed", "current"} and row.get("item_id")}
    canonical_ids = {row["id"] for row in canonical["items"]}
    loss = sum(h.get("dropped", 0) + h.get("failed", 0) + h.get("truncated", 0) for h in support["processes"])
    unknown = not support["processes"] or not closed or canonical["status"] != "ok" or canonical["truncated"] or canonical.get("changed_during_snapshot")
    admitted = {row.get("batch_id") for row in events if row["event"] == "embedding_batch" and row.get("boundary") == "admitted"}
    logical = {row.get("batch_id") for row in events if row["event"] == "embedding_http" and row.get("boundary") == "logical_start"}
    unsupported = any(row.get("transport_observable") is False for row in events) or bool(admitted - logical)
    def in_window(value):
        if not value:
            return False
        instant = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if instant.tzinfo is None:
            instant = instant.replace(tzinfo=UTC)
        return datetime.fromisoformat(manifest["started_at"]) <= instant <= datetime.fromisoformat(manifest.get("stopped_at") or manifest["tail_ends_at"])
    expected_runs = {row["id"] for row in canonical["runs"] if in_window(row["created_at"])}
    expected_receipts = {row["sequence"] for row in canonical["receipts"] if in_window(row.get("applied_at"))}
    expected_registered = {row["memory_item_id"] for row in canonical.get("eligibility", []) if in_window(row.get("registered_at"))}
    observed_items = {row["item_id"] for row in events if row.get("item_id")}
    observed_runs = {row["run_id"] for row in events if row.get("run_id")}
    observed_receipts = {row["receipt_sequence"] for row in events if row.get("receipt_sequence")}
    missing_canonical = len(expected_runs - observed_runs) + len(expected_receipts - observed_receipts) + len(expected_registered - observed_items)
    unknown |= bool(canonical.get("unsupported"))
    complete = not (unknown or loss or missing or gaps or damaged or support["damaged"] or summary["open_spans"] or unsupported or missing_canonical)
    coverage = {"schema": CAPABILITY, "memory_pipeline_evidence_complete": complete,
        "status": "COMPLETE" if complete else "PARTIAL", "unknown_denominator": bool(unknown),
        "expected_events": sum(sum(h.get("expected", {}).values()) for h in support["processes"]),
        "observed_events": len(events), "missing_events": missing, "sequence_gaps": gaps, "loss": loss, "damaged": damaged + support["damaged"],
        "canonical_denominator": {"new_runs": len(expected_runs), "applied_receipts": len(expected_receipts),
            "registered_items": len(expected_registered), "missing_observations": missing_canonical,
            "carry_in_items": len(canonical_ids - expected_registered)},
        "final_watermarks": closed, "canonical_items": len(canonical_ids), "frozen_candidates": len(candidates),
        "candidate_missing_canonical": len(candidates - canonical_ids), "candidate_without_persist_evidence": len(candidates - persisted),
        "http_attempts": sum(row["event"] == "embedding_http" and row.get("boundary") == "attempt_start" for row in events),
        "unobserved_transport": unsupported, "writer_coverage": "bounded_helpers_only_other_writers_unknown",
        "storage_correctness": "separate_review", "quality": "not_evaluated", "real_ai": "not_inferred", "timing": summary}
    def write(name, value):
        (destination / name).write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    def jsonl(name, rows):
        (destination / name).write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")
    write("capability-check.json", support); write("coverage.json", coverage)
    (destination / "snapshots").mkdir()
    write("snapshots/canonical-final.json", canonical)
    jsonl("timeline.jsonl", events)
    jsonl("embedding-batches.jsonl", [row for row in events if row["event"] in {"embedding_batch", "embedding_http", "result"}])
    jsonl("writer-spans.jsonl", [row for row in spans if row["operation"] in {"sqlite_writer", "vec1_writer", "fts_writer"}])
    (destination / "delay-and-batch-review.md").write_text(
        "# 기억 처리 증거 / Memory pipeline evidence\n\n"
        f"기록 상태 / Recording: {coverage['status']}\n\n"
        f"HTTP 시도 / HTTP attempts: {coverage['http_attempts']}; 표본 / Spans: {summary['n']}.\n\n"
        "중첩 구간은 더하지 않습니다. 관측되지 않은 간격과 경쟁자는 미확정입니다. / "
        "Nested durations are not additive; unobserved gaps and contenders remain unknown.\n\n"
        "30초는 검토 기준이며 실패나 제한 시간이 아닙니다. / 30 seconds is a review threshold, not a failure or timeout.\n\n"
        "저장 정합성·AI 품질·실제 후속 검색 소비는 별도로 확인합니다. / "
        "Storage correctness, AI quality and subsequent retrieval use require separate verification.\n", encoding="utf-8")
    return coverage
