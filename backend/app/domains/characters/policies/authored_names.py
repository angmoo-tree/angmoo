"""Explicit newly authored fields. Historical records never enter this policy."""
from app.domains.characters.policies.name_macros import render_names
from app.contracts.name_binding import NameBindingError
from hashlib import sha256


def authored_fields(value: dict, binding, *, fields: tuple[str, ...],
                    recipient_id: str | None = None, limits: dict | None = None,
                    receipt: dict | None = None) -> dict:
    result = dict(value)
    if binding is None:
        return result
    for key in fields:
        if isinstance(result.get(key), str):
            try:
                rendered = render_names(result[key], binding, output=True, recipient_id=recipient_id,
                                        limit=(limits or {}).get(key))
            except NameBindingError as exc:
                raise NameBindingError(exc.code, field_path=key, rendered_chars=exc.rendered_chars,
                                       limit=exc.limit) from exc
            if receipt is not None:
                receipt[key] = {**rendered.receipt(), "applied": result[key] != rendered.text,
                    "input_chars": len(result[key]), "rendered_chars": len(rendered.text),
                    "before_sha256": sha256(result[key].encode()).hexdigest(),
                    "final_sha256": sha256(rendered.text.encode()).hexdigest()}
            result[key] = rendered.text
    return result


def authored_thought(value, binding, *, recipient_id=None):
    if isinstance(value, str):
        return render_names(value, binding, output=True, recipient_id=recipient_id).text if binding is not None else value
    if isinstance(value, dict):
        return authored_fields(value, binding, fields=("text",), recipient_id=recipient_id)
    return value


def authored_routine_draft(value, binding, *, receipt=None):
    if not isinstance(value, dict):
        return value
    result = authored_fields(value, binding, fields=("title", "body", "topic_signature", "novelty_basis"),
        limits={"title": 160, "body": 4000}, receipt=receipt)
    for key in ("thought", "_thought"):
        if key in result:
            result[key] = authored_thought(result[key], binding)
            if receipt is not None and isinstance(value[key], str):
                receipt[key] = {"input_chars": len(value[key]), "rendered_chars": len(result[key])}
    return result
