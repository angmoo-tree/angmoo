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
