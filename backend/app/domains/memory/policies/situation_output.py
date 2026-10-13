"""Parse the auxiliary output independently from the original activity result."""
from app.domains.memory.contracts.activity_situation import DESCRIPTION_LIMIT, SituationDraft


def parse_description(raw: object, *, target_key: str, ordered: bool = True) -> SituationDraft:
    if not ordered:
        return SituationDraft(target_key, None, "output_order_invalid", "situation_output_order_invalid")
    if raw is None:
        return SituationDraft(target_key, None, "missing", "situation_description_missing")
    if not isinstance(raw, str) or not raw.strip() or len(raw) > DESCRIPTION_LIMIT:
        return SituationDraft(target_key, None, "invalid", "situation_description_invalid")
    try:
        raw.encode("utf-8")
    except UnicodeError:
        return SituationDraft(target_key, None, "invalid", "situation_description_invalid")
    return SituationDraft(target_key, raw, "valid")


def parse_situations(payload: dict, targets: tuple[str, ...], *, base_fields=("decision", "draft")) -> dict[str, SituationDraft]:
    """A duplicate/invalid target cannot discard another target's valid base."""
    keys = list(payload)
    ordered = ("situations" not in payload or
        all(key in payload and keys.index(key) < keys.index("situations") for key in base_fields))
    raw = payload.get("situations")
    if raw is None:
        return {key: parse_description(None, target_key=key) for key in targets}
    if not isinstance(raw, list):
        return {key: parse_description(False, target_key=key) for key in targets}
    result = {}
    for target in targets:
        matches = [row for row in raw if isinstance(row, dict) and row.get("target_id") == target]
        value = matches[0].get("description") if len(matches) == 1 else (False if matches else None)
        result[target] = parse_description(value, target_key=target, ordered=ordered)
    return result


def inspect_situations(payload: dict, targets: tuple[str, ...], *, base_fields=("decision", "draft"), limit=16) -> dict:
    """Bounded structural detail, with canonical status still owned by the parser.

    Description indices identify existing values for an observer to hash. This
    policy returns no copied text and creates no log, sink or persistence work.
    """
    raw = payload.get("situations")
    reason = ("field_absent" if "situations" not in payload else "field_null" if raw is None
        else "field_type_invalid" if not isinstance(raw, list) else "empty_list" if not raw else "present")
    keys = list(payload)
    ordered = "situations" not in payload or all(
        key in keys and keys.index(key) < keys.index("situations") for key in base_fields)
    rows = raw[:limit] if isinstance(raw, list) else []
    bounded = {**payload, "situations": rows} if isinstance(raw, list) else payload
    drafts = parse_situations(bounded, targets[:limit], base_fields=base_fields)
    entries = []
    for target in targets[:limit]:
        matches = [index for index, row in enumerate(rows) if isinstance(row, dict) and row.get("target_id") == target]
        why, index = reason if reason != "present" else "target_missing", None
        if len(matches) > 1:
            why = "target_duplicate"
        elif matches:
            index = matches[0]
            row, description = rows[index], rows[index].get("description")
            why = ("description_absent" if "description" not in row else "description_null" if description is None
                else "description_type_invalid" if not isinstance(description, str)
                else "description_empty" if not description.strip()
                else "description_too_long" if len(description) > DESCRIPTION_LIMIT else "valid")
            if why == "valid":
                try:
                    description.encode("utf-8")
                except UnicodeError:
                    why = "description_unicode_invalid"
        entries.append({"target_key": target, "description_index": index, "match_count": len(matches),
            "reason": why, "status": drafts[target].status})
    return {"field_present": "situations" in payload, "field_reason": reason, "order_valid": ordered,
        "invalid_target_count": sum(not isinstance(row, dict) or not isinstance(row.get("target_id"), str)
            or not row["target_id"] for row in rows),
        "targets_count": len(targets), "entries": entries,
        "entries_truncated": len(targets) > limit or isinstance(raw, list) and len(raw) > limit}
