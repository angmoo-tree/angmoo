"""Actual model-delivery manifests and same-transaction SNS participation."""
from dataclasses import asdict
from datetime import UTC, datetime
from hashlib import sha256
import json

from app.domains.memory.contracts.activity_situation import DeliveredInputManifest, SituationDraft, CommittedActivityResult, CommittedEffect, stable_digest
from app.domains.memory.policies.situation_output import parse_description
from app.domains.memory.policies.episode_provider_view import episode_provider_reference
from app.domains.memory.repository.situation_admission import admit
from app.domains.social.models.posts import Post
from app.runtime.memory.situation_sources import SituationSources


def freeze_social_input(ctx, snapshot, *, node, payload, transmitted, state):
    if state is None:
        raise ValueError("situation_activity_state_missing")
    reader = SituationSources(ctx.db)
    sources = []
    def add(kind, identifier, delivered, path, role="background", target=None):
        sources.append(reader.describe(snapshot.scope, kind=kind, identifier=str(identifier), delivered=delivered,
            path=path, role=role, ordinal=len(sources), target=target, allow_delivery=True))
    def post(identifier, delivered, path, role, target=None):
        row = ctx.db.get(Post, identifier)
        if row is None:
            raise ValueError("situation_post_missing")
        # Only use the full body range when those exact code points were sent.
        fragment = row.body if row.body and row.body in delivered else delivered
        add("REPLY" if row.reply_to_post_id else "POST", identifier, fragment, path, role, target)
    selected = [(target, f"/selected_targets/{index}") for index, target in enumerate(payload.get("selected_targets", []))]
    selected.extend((row.get("source", {}), f"/assignments/{index}/source") for index, row in enumerate(payload.get("assignments", [])))
    for target, target_path in selected:
        text = target.get("text", "")
        for identifier in target.get("source_ids", []):
            post(identifier, text, target_path + "/text", "core", target["target_id"])
        if target.get("parent_text"):
            for identifier in set(target.get("source_revisions", {})) - set(target.get("source_ids", [])):
                post(identifier, target["parent_text"], target_path + "/parent_text", "core", target["target_id"])
        proposal = target.get("activity_proposal")
        if proposal:
            add("ACTIVITY_PROPOSAL", proposal["proposal_id"], json.dumps(proposal, ensure_ascii=False), target_path + "/activity_proposal")
        relation = state.get("relationship_validation_receipts", {}).get(target["target_id"], {})
        if target.get("relationship"):
            for ref in relation.get("references", []):
                add("RELATIONSHIP", ref["relationship_state_id"], json.dumps(target["relationship"], ensure_ascii=False), target_path + "/relationship")
    context = payload.get("context", payload)
    prefix = "/context" if "context" in payload else ""
    for index, source in enumerate(context.get("source_manifest", [])):
        identifier = source.get("post_id")
        if identifier and not any(row.source_id == identifier for row in sources):
            # The transmitted source projection, not an undisclosed full body.
            post(identifier, json.dumps(source, ensure_ascii=False, default=str), f"{prefix}/source_manifest/{index}", "background")
    today = context.get("today_activity", {})
    for index, record in enumerate(today.get("records", []) if isinstance(today, dict) else []):
        path = f"{prefix}/today_activity/records/{index}"
        kind = record["source_type"].upper()
        if kind == "POST":
            post(record["source_id"], record.get("body") or json.dumps(record, ensure_ascii=False), path, "background")
        else:
            add(kind, record["source_id"], json.dumps(record, ensure_ascii=False), path)
        for key, field in (("source_post_id", "body"), ("target_post_id", "parent_body"), ("root_post_id", "root_body")):
            if record.get(key) and record.get(field):
                post(record[key], record[field], f"{path}/{field}", "background")
    for index, reply in enumerate(context.get("completed_social_replies", [])):
        if reply.get("body"):
            post(reply["post_id"], reply["body"], f"{prefix}/completed_social_replies/{index}/body", "background")
    routine = context.get("routine", {})
    for index, record in enumerate(routine.get("source_events", [])):
        add("SOCIAL_EVENT", record["source_event_id"], record.get("excerpt") or json.dumps(record, ensure_ascii=False),
            f"{prefix}/routine/source_events/{index}")
    previous = routine.get("previous_success") or {}
    previous_post = previous.get("post") or {}
    if previous_post:
        post(previous_post["id"], previous_post["body"], prefix + "/routine/previous_success/post/body", "background")
    if routine.get("activity"):
        identifier = state["lane_data"]["prepared"]["refs"]["item"]
        add("ROUTINE_ACTIVITY", identifier, json.dumps(routine["activity"], ensure_ascii=False), prefix + "/routine/activity")
    for target, relations in context.get("relationships", {}).items():
        for ref in state.get("relationship_validation_receipts", {}).get(target, {}).get("references", []):
            add("RELATIONSHIP", ref["relationship_state_id"], json.dumps(relations, ensure_ascii=False), f"{prefix}/relationships/{target}")
    def images(value, path):
        if isinstance(value, dict):
            if value.get("asset_id"):
                add("IMAGE_ASSET", value["asset_id"], json.dumps(value, ensure_ascii=False), path)
                if value.get("interpretation_id") and value.get("context"):
                    add("IMAGE_INTERPRETATION", value["interpretation_id"], value["context"], path + "/context")
            for key, child in value.items():
                images(child, path + "/" + str(key))
        elif isinstance(value, list):
            for index, child in enumerate(value):
                images(child, path + "/" + str(index))
    images(payload, "")
    revisions = {identifier: (version, digest)
        for value in state.get("memory_validations", {}).values()
        for identifier, version, digest in value.get("item_revisions", [])}
    by_ref = {episode_provider_reference("episode", f"memory-item:{identifier}"): identifier for identifier in revisions}
    by_ref.update({episode_provider_reference("episode", identifier): identifier for identifier in revisions})
    for target, value in context.get("memories", {}).items():
        for index, packet in enumerate(value.get("packets", [])):
            identifier = by_ref.get(packet.get("ref"))
            if identifier is None:
                raise ValueError("situation_memory_identity_missing")
            entry = reader.describe(snapshot.scope, kind="MEMORY_ITEM", identifier=identifier,
                delivered=json.dumps(packet, ensure_ascii=False), path=f"{prefix}/memories/{target}/packets/{index}",
                role="prior", ordinal=len(sources))
            version, digest = revisions[identifier]
            if entry.source_version != str(version) or entry.source_digest != digest:
                raise ValueError("situation_prior_changed")
            sources.append(entry)
    threads = {row.thread_id for row in sources if row.thread_id}
    return DeliveredInputManifest(f"sns:{ctx.run_id}:{node}:{sha256(transmitted.encode()).hexdigest()}", snapshot,
        sha256(transmitted.encode()).hexdigest(), tuple(sources), next(iter(threads)) if len(threads) == 1 else None)


def participant(lane, state, target):
    decision = state["decision"]
    override = decision.get("_situation_overrides", {}).get(target)
    if decision.get("_situation_manifest") is None and override is None:
        return None
    manifest = DeliveredInputManifest.from_dict(override["manifest"] if override else decision["_situation_manifest"])
    raw = override["draft"] if override else decision.get("_situations", {}).get(target)
    draft = SituationDraft(**raw) if raw else parse_description(None, target_key=target)
    if override is None and any(row.get("writer_recovery") for row in state.get("writer_input_receipts", [])):
        # A repaired writer did not produce this description. Never reuse it,
        # even if the repaired body happens to equal the first draft.
        draft = parse_description(None, target_key=target)
    def apply(session, execution, result, occurred_at):
        if execution.status != "succeeded":
            raise ValueError("situation_execution_not_successful")
        action = execution.action_type
        planned = next((row for row in decision.get("decisions", []) if row["target_id"] == target), None)
        expected = "post" if lane.lane == "routine" else ("reply" if planned["action"] == "comment" else planned["action"])
        source_id = str(result.get("social_event_id") if action == "like" else result.get("post_id") or execution.id)
        # The execution owner certifies the concrete effect, not the planner.
        source_type = "POST" if action == "post" else "REPLY" if action in {"comment", "reply"} else "SOCIAL_EVENT"
        original = override["normalized"] if override else decision.get("_situation_normalized_draft", decision.get("provisional_draft")) or {}
        normalized_action = "reply" if action == "comment" else action
        expected_output = {"action": expected, "target": execution.target_post_id if lane.lane == "routine" else state["lane_data"][target]["post_id"]}
        actual_output = {"action": normalized_action, "target": execution.target_post_id}
        if expected in {"reply", "post"}:
            written = original if expected == "post" else next((row for row in original.get("replies", []) if row.get("target_id") == target), {})
            post_row = session.get(Post, source_id)
            expected_output["body"] = written.get("body")
            actual_output["body"] = post_row.body if post_row else None
            if expected == "post":
                expected_output["title"] = written.get("title")
                actual_output["title"] = post_row.title if post_row else None
        planned_digest, final_digest = stable_digest(expected_output), stable_digest(actual_output)
        result_sources = ()
        if expected in {"reply", "post"} and post_row is not None:
            session.flush()
            result_sources = (SituationSources(session).describe(manifest.snapshot.scope,
                kind=source_type, identifier=source_id, delivered=post_row.body,
                path="/committed_result/body", role="committed_result", ordinal=len(manifest.sources), target=target),)
        elif action == "like":
            from app.domains.memory.contracts.provenance import MemorySourceTypeV1
            sources = SituationSources(session)
            evidence = sources.reader.read_evidence(scope=manifest.snapshot.scope,
                source_type=MemorySourceTypeV1.SOCIAL_EVENT, source_id=source_id)
            if evidence is not None:
                result_sources = (sources.describe(manifest.snapshot.scope, kind="SOCIAL_EVENT", identifier=source_id,
                    delivered=evidence.deterministic_summary, path="/committed_result/event", role="committed_result",
                    ordinal=len(manifest.sources), target=target),)
        from sqlalchemy import select
        from app.domains.social.models.activity_thought import SocialActivityThought
        thought_id = session.scalar(select(SocialActivityThought.id).where(
            SocialActivityThought.public_action_execution_id == execution.id))
        value = CommittedActivityResult(state["identity"]["activity_id"], lane.lane, target,
            (expected,), (CommittedEffect("reply" if action == "comment" else action, source_type, source_id, "succeeded"),),
            planned_digest, final_digest, occurred_at,
            counterpart_id=next((row.get("counterpart_id") for row in state.get("candidates", []) if row["target_id"] == target), None))
        from dataclasses import replace
        value = replace(value, result_sources=result_sources, thought_reference=f"social:{thought_id}" if thought_id else None)
        admit(session, manifest=manifest, draft=draft, result=value, now=datetime.now(UTC))
    return apply
