"""Safe auxiliary diagnostics. Never a business receipt or a commit owner."""
from contextvars import ContextVar
from hashlib import sha256
import re
from sqlalchemy import event
from app.domains.memory.contracts.activity_situation import DESCRIPTION_LIMIT, stable_digest
from app.domains.memory.policies.situation_output import inspect_situations
from app.domains.social.utils.situation_output import NORMALIZATION_REVISION

CAPABILITY = "situation-observation.v1"
SITUATION_EVENTS = frozenset({"situation_output_shape", "situation_output_parsed", "situation_receipt_committed"})
stage_attempt = ContextVar("situation_stage_attempt", default=None)
_SAFE_ID = re.compile(r"[A-Za-z0-9_.:@/-]{1,64}\Z")


async def in_stage(callback, state, attempt_id):
    token = stage_attempt.set(attempt_id)
    try:
        return await callback(state)
    finally:
        stage_attempt.reset(token)


def shape(value, *, identifier=False):
    result = {"type": type(value).__name__}
    if isinstance(value, (str, list, dict)):
        result["length"] = len(value)
    if isinstance(value, str):
        if identifier and _SAFE_ID.fullmatch(value):
            result["safe_id"] = value
        if len(value) <= DESCRIPTION_LIMIT:
            try:
                result["sha256"] = sha256(value.encode("utf-8")).hexdigest()
            except UnicodeEncodeError:
                result["unicode_invalid"] = True
    return result


def output_shape(payload, targets, *, base_fields=("decision", "draft"), locale=None):
    """Safe projection of Memory's structural detail; never a second parser."""
    facts = inspect_situations(payload, targets, base_fields=base_fields, locale=locale)
    raw = payload.get("situations")
    entries = []
    for row in facts["entries"]:
        index = row["description_index"]
        description = raw[index].get("description") if index is not None else None
        entries.append({"target": shape(row["target_key"], identifier=True), "description": shape(description),
            "match_count": row["match_count"], "reason": row["reason"], "status": row["status"]})
    return {**facts, "field": shape(raw), "entries": entries}


def safe_event(payload):
    """Re-allowlist at the sink, even if an internal caller supplies extra data."""
    scalars = {"node", "lane", "stage_attempt_id", "call_order", "provider_call_order", "json_attempt",
        "input_payload_hash", "writer_replaced", "receipt_sequence", "receipt_state", "description_status",
        "error_code", "target_key", "raw_expected_digest", "normalized_expected_digest", "actual_digest",
        "normalization_changed", "rules_revision", "field_present", "field_reason", "order_valid",
        "invalid_target_count", "targets_count", "entries_truncated", "selected_final", "writer_selected",
        "manifest_digest", "content_digest", "receipt_state_version", "effect_identity_digest", "result_source_id"}
    result = {key: value for key, value in payload.items() if key in scalars and (value is None or isinstance(value, (bool, int))
        or isinstance(value, str) and (_SAFE_ID.fullmatch(value) or re.fullmatch(r"[a-f0-9]{64}", value)))}
    def safe_shape(raw):
        return {key: value for key, value in raw.items() if key in {"type", "length", "sha256", "safe_id", "unicode_invalid"}
            and (isinstance(value, (bool, int)) or isinstance(value, str) and _SAFE_ID.fullmatch(value))}
    if isinstance(payload.get("field"), dict):
        result["field"] = safe_shape(payload["field"])
    entries = []
    for row in (payload.get("entries") or [])[:16]:
        entries.append({key: safe_shape(value) if key in {"target", "description"} and isinstance(value, dict) else value
            for key, value in row.items() if key in {"target", "description", "match_count", "reason", "status"}
            and (isinstance(value, (dict, int)) or isinstance(value, str) and _SAFE_ID.fullmatch(value))})
    result["entries"] = entries
    return result


def after_receipt_commit(session, tracker, receipt, *, decision, override, raw_digest, normalized_digest, actual_digest):
    if getattr(tracker, "observer", None) is None:
        return
    attempt = override.get("attempt", {}) if override else decision.get("_situation_attempt", {})
    result = getattr(receipt, "result", {}) or {}
    sources = [source for source in result.get("result_sources", []) if source.get("role") == "committed_result"]
    details = {**attempt, "lane": receipt.lane, "receipt_sequence": receipt.sequence,
        "receipt_state": receipt.state, "description_status": receipt.description_status, "target_key": receipt.target_key,
        "error_code": receipt.error_code, "writer_replaced": attempt.get("writer_replaced") is True,
        "writer_selected": override is not None, "selected_final": True,
        "manifest_digest": getattr(receipt, "manifest_id", None), "content_digest": getattr(receipt, "content_digest", None),
        "receipt_state_version": getattr(receipt, "state_version", None),
        "effect_identity_digest": stable_digest(result["effects"]) if result.get("effects") else None,
        "result_source_id": sources[0].get("source_id") if len(sources) == 1 else None,
        "entries": [{"target": shape(receipt.target_key, identifier=True), "description": shape(getattr(receipt, "description", None)),
            "status": receipt.description_status}],
        "raw_expected_digest": raw_digest, "normalized_expected_digest": normalized_digest, "actual_digest": actual_digest,
        "normalization_changed": raw_digest != normalized_digest, "rules_revision": NORMALIZATION_REVISION}
    pending = session.info.setdefault("situation_diagnostics", {})
    pending[receipt.sequence] = (tracker, safe_event(details), session.get_nested_transaction() or session.get_transaction())
    if not session.info.get("situation_diagnostics_installed"):
        session.info["situation_diagnostics_installed"] = True
        def committed(db):
            if not db.in_nested_transaction():
                for observer, value, _transaction in db.info.pop("situation_diagnostics", {}).values():
                    try:
                        observer._notify("situation_receipt_committed", value)
                    except Exception:
                        pass
        def rollback(db, previous):
            staged = db.info.get("situation_diagnostics", {})
            for sequence, (_tracker, _value, transaction) in list(staged.items()):
                while transaction is not None:
                    if transaction is previous:
                        staged.pop(sequence, None)
                        break
                    transaction = transaction.parent
        event.listen(session, "after_commit", committed)
        event.listen(session, "after_soft_rollback", rollback)
