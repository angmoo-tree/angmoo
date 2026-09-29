"""Explicit newly authored fields. Historical records never enter this policy."""
from app.domains.characters.policies.name_macros import render_names
from hashlib import sha256


def authored_fields(value: dict, binding, *, fields: tuple[str, ...],
                    recipient_id: str | None = None, limits: dict | None = None,
                    receipt: dict | None = None) -> dict:
    result = dict(value)
    if binding is None:
        return result
    for key in fields:
        if isinstance(result.get(key), str):
            rendered = render_names(result[key], binding, output=True, recipient_id=recipient_id,
                                    limit=(limits or {}).get(key))
            if receipt is not None:
                receipt[key] = {**rendered.receipt(), "applied": result[key] != rendered.text,
                    "before_sha256": sha256(result[key].encode()).hexdigest(),
                    "final_sha256": sha256(rendered.text.encode()).hexdigest()}
            result[key] = rendered.text
    return result


def authored_thought(value, binding, *, recipient_id=None):
    if isinstance(value, str):
        return render_names(value, binding, output=True, recipient_id=recipient_id,
                            limit=280).text if binding is not None else value
    if isinstance(value, dict):
        return authored_fields(value, binding, fields=("text",), recipient_id=recipient_id, limits={"text": 280})
    return value


def authored_routine_draft(value, binding, *, receipt=None):
    if not isinstance(value, dict):
        return value
    result = authored_fields(value, binding, fields=("title", "body", "topic_signature", "novelty_basis"),
        limits={"title": 160, "body": 4000, "topic_signature": 300, "novelty_basis": 500}, receipt=receipt)
    for key in ("thought", "_thought"):
        if key in result:
            result[key] = authored_thought(result[key], binding)
    return result
