"""Routine's auxiliary bounds; visible post content retains its strict policy."""
from app.contracts.authored_output import normalize_auxiliary_text

TOPIC_SIGNATURE_LIMIT = 300
NOVELTY_BASIS_LIMIT = 500


def normalize_topic_signature(value: object) -> str:
    return normalize_auxiliary_text(value, field="topic_signature", limit=TOPIC_SIGNATURE_LIMIT)[0]


def normalize_novelty_basis(value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("routine_novelty_basis_invalid")
    return normalize_auxiliary_text(value, field="novelty_basis", limit=NOVELTY_BASIS_LIMIT)[0]


def normalize_routine_auxiliary(payload: dict, *, name_receipt: dict | None = None) -> tuple[dict, dict]:
    result, receipts = dict(payload), {}
    for field, limit in (("topic_signature", TOPIC_SIGNATURE_LIMIT), ("novelty_basis", NOVELTY_BASIS_LIMIT)):
        raw = result.get(field)
        if field == "novelty_basis":
            normalize_novelty_basis(raw)
        value, receipt = normalize_auxiliary_text(raw, field=field, limit=limit,
            input_chars=(name_receipt or {}).get(field, {}).get("input_chars"))
        result[field] = value
        receipts[field] = receipt.to_dict()
    return result, receipts
