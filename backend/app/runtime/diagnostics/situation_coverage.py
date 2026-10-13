"""Independent auxiliary completeness, never an SNS/AI quality verdict."""
from collections import Counter
from datetime import datetime
from app.core.calendar import utc_instant
from app.runtime.diagnostics.situation_observation import CAPABILITY, SITUATION_EVENTS


def canonical_receipts(db, manifest, included):
    inventory = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if not {"memory_situation_receipts", "memory_scope_settings"} <= inventory:
        return [], {"canonical_receipt_support": "unsupported"}
    rows, baseline = [], []
    start = utc_instant(datetime.fromisoformat(manifest["started_at"]))
    tail = utc_instant(datetime.fromisoformat(manifest["tail_ends_at"]))
    for activity in sorted(included):
        for row in db.execute("SELECT r.sequence,r.logical_activity_id,r.lane,r.target_key,r.state,r.description_status,r.error_code,r.captured_at "
            "FROM memory_situation_receipts r JOIN memory_scope_settings s ON s.id=r.scope_setting_id "
            "WHERE s.world_id=? AND r.logical_activity_id=? AND s.subject_world_character_id IN (" +
            ",".join("?" for _ in manifest["actor_ids"]) + ") ORDER BY r.sequence LIMIT 1000",
            (manifest["world_id"], activity, *manifest["actor_ids"])):
            captured = utc_instant(datetime.fromisoformat(row["captured_at"]))
            if captured < start:
                baseline.append(dict(row))
            elif captured < tail:
                rows.append(dict(row))
    return rows, {"canonical_receipt_support": "supported", "canonical_states": dict(Counter(row["state"] for row in rows)),
        "canonical_baseline_states": dict(Counter(row["state"] for row in baseline)), "window_receipt_count": len(rows),
        "admission_description_missing": sum(row["description_status"] == "missing" for row in rows),
        "current_blocked_count": sum(row["state"] == "blocked" for row in rows)}


def coverage(manifest, events, receipts, *, damaged, dropped, canonical):
    evidence = [row for row in events if row.get("event_type") in SITUATION_EVENTS]
    supported = CAPABILITY in manifest.get("capabilities", [])
    def key(row):
        details = row.get("details", {})
        return (row.get("activity_id"), row.get("lane"), row.get("node"), details.get("provider_call_order"),
            details.get("json_attempt"), details.get("call_order"), details.get("stage_attempt_id"), details.get("input_payload_hash"))
    shapes = {key(row) for row in evidence if row["event_type"] == "situation_output_shape"}
    parsed = {key(row) for row in evidence if row["event_type"] == "situation_output_parsed"}
    outputs = {(row.get("activity_id"), row.get("node")) for row in events
        if row.get("event_type") == "input_manifest" and row.get("details", {}).get("situation_expected") is True}
    calls = [row for row in events if row.get("event_type") == "llm_call" and row.get("details", {}).get("status") == "ok"
        and row.get("details", {}).get("call_type") == "generate_content"
        and (row.get("activity_id"), row.get("node")) in outputs]
    expected_physical = {(row.get("activity_id"), row.get("node"), row.get("details", {}).get("provider_call_order")) for row in calls}
    observed_physical = {(value[0], value[2], value[3]) for value in shapes}
    valid_logical = {(row.get("activity_id"), row.get("node"), row.get("details", {}).get("call_order")) for row in events
        if row.get("event_type") == "llm_json_attempt" and row.get("details", {}).get("status") == "valid"
        and (row.get("activity_id"), row.get("node")) in outputs}
    observed_valid = {(row.get("activity_id"), row.get("node"), row.get("details", {}).get("call_order")) for row in evidence
        if row["event_type"] == "situation_output_parsed"}
    committed = [row for row in evidence if row["event_type"] == "situation_receipt_committed"]
    sequences = {row.get("details", {}).get("receipt_sequence") for row in committed}
    expected_sequences = {row["sequence"] for row in receipts}
    ambiguous = sum(not all(row.get("details", {}).get(name) is not None for name in
        ("provider_call_order", "json_attempt", "stage_attempt_id", "input_payload_hash")) for row in evidence)
    # A resumed stage can restart tracker counters. Equal numeric call orders
    # cannot join different stage/payload attempts, nor a superseded Writer.
    physical_attempts = {}
    for value in shapes:
        physical_attempts.setdefault((value[0], value[2], value[3]), set()).add(value)
    ambiguous += sum(len(values) > 1 for values in physical_attempts.values())
    ambiguous += len(parsed - shapes)
    ambiguous += sum(key(row) not in parsed for row in committed)
    truncated = sum(row.get("details", {}).get("entries_truncated") is True or row.get("details", {}).get("truncated") is True for row in evidence)
    shape_missing = len(expected_physical - observed_physical)
    parsed_missing = len(valid_logical - observed_valid)
    missing_commit = len(expected_sequences - sequences)
    complete = supported and canonical.get("canonical_receipt_support") == "supported" and not (
        damaged or dropped or ambiguous or truncated or shape_missing or parsed_missing or missing_commit)
    return evidence, {"capability": CAPABILITY, "support": "supported" if supported else "unsupported",
        "situation_evidence_complete": complete if supported else "unsupported", "expected_shape": len(expected_physical),
        "observed_shape": len(shapes), "shape_missing": shape_missing, "expected_parsed": len(valid_logical),
        "observed_parsed": len(parsed), "parsed_missing": parsed_missing, "expected_committed": len(expected_sequences),
        "observed_committed": len(sequences), "commit_event_missing": missing_commit,
        "diagnostic_loss_not_admission_failure": missing_commit, "correlation_ambiguous": ambiguous,
        "truncated": truncated, "damaged": damaged, "dropped": dropped,
        "writer_replaced": sum(row.get("details", {}).get("writer_replaced") is True for row in committed), **canonical}
