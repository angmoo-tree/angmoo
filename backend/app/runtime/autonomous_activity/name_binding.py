"""Use the activity's durable names, including after child checkpoint restoration."""
from app.contracts.name_binding import read_name_binding
from app.domains.characters.policies.authored_names import authored_fields, authored_thought
from app.domains.world_characters.activity_models import ActivityGraphRun


def activity_name_binding(ctx):
    row = ctx.db.get(ActivityGraphRun, ctx.run_id)
    return read_name_binding(row.result if row is not None else None)


def decision_names(value, binding, *, candidates=()):
    result = dict(value)
    if binding is None:
        return result
    if isinstance(result.get("state_update"), dict):
        result["state_update"] = authored_fields(result["state_update"], binding,
            fields=("state_note",), limits={"state_note": 280})
    recipients = {row["target_id"]: row.get("counterpart_id") for row in candidates}
    decisions = []
    for row in result.get("decisions", []):
        row = dict(row)
        if "thought" in row:
            row["thought"] = authored_thought(row["thought"], binding,
                recipient_id=recipients.get(row["target_id"]))
        decisions.append(row)
    if "decisions" in result:
        result["decisions"] = decisions
    return result


def social_draft_names(value, binding, *, assignments, combined=False, lane, receipt=None):
    if binding is None or not isinstance(value, dict):
        return value
    collection = "replies" if combined else "reply_task_results"
    identifier = "target_id" if combined else "task_id"
    recipients = {(a["source"]["target_id"] if combined else a["task_id"]):
                  a["source"].get("counterpart_id") for a in assignments}
    result = dict(value)
    if isinstance(value.get(collection), list):
        rows = []
        for index, row in enumerate(value[collection]):
            fields = {}
            rows.append(authored_fields(row, binding, fields=("title", "body"),
                recipient_id=recipients.get(row.get(identifier)),
                limits={"title": 160, "body": 500 if lane == "feed" else 1000}, receipt=fields)
                if isinstance(row, dict) else row)
            if receipt is not None:
                receipt.update({f"{collection}.{index}.{key}": entry for key, entry in fields.items()})
        result[collection] = rows
    return result


def observe_output(tracker, binding, *, lane, fields):
    if binding is not None and getattr(tracker, "observer", None) is not None:
        tracker._notify("name_binding_output", {"lane": lane, "policy_version": binding.policy_version,
            "binding_digest": binding.digest, "profile_version": binding.user_profile_version, "fields": fields})
