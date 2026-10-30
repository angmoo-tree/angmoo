"""Actual model-delivery manifests and same-transaction SNS participation."""
from dataclasses import asdict
from datetime import UTC, datetime
from hashlib import sha256
import json

from app.domains.memory.contracts.activity_situation import (
    DeliveredInputManifest, SituationDraft, CommittedActivityResult, CommittedEffect, stable_digest,
    FinalDeliveredFragment, RelationshipDeliveryBasis,
)
from app.domains.memory.policies.situation_output import parse_description
from app.domains.memory.policies.episode_provider_view import episode_provider_reference
from app.domains.memory.repository.situation_admission import admit
from app.domains.social.models.posts import Post
from app.runtime.memory.situation_sources import SituationSources
from app.runtime.memory.captured_delivery import captured_entry
from app.domains.social.contracts.today_activity import validate_today_activity_payload


def freeze_social_input(ctx, snapshot, *, node, payload, transmitted, state):
    validate_today_activity_payload(payload)
    if state is None:
        raise ValueError("situation_activity_state_missing")
    from app.runtime.autonomous_activity.initial_input import assert_integrity
    try:
        assert_integrity(state)
    except ValueError as exc:
        raise ValueError("situation_initial_input_invalid") from exc
    identity = state.get("identity", {})
    if (identity.get("activity_id"), identity.get("world_id"), identity.get("actor_id")) != (
            ctx.run_id, snapshot.scope.world_id, snapshot.scope.subject_world_character_id):
        raise ValueError("situation_activity_scope_invalid")
    if ctx.user_id != snapshot.scope.owner_id:
        raise ValueError("situation_activity_scope_invalid")
    reader = SituationSources(ctx.db)
    sources = []
    payload_digest = sha256(transmitted.encode()).hexdigest()
    if json.JSONDecoder().raw_decode(transmitted)[0] != payload:
        raise ValueError("situation_final_payload_mismatch")
    context = payload.get("context", payload)
    today = context.get("today_activity", {})
    metadata = dict(state.get("lane_data", {}).get("_reference_sources", {}))
    original_context = state.get("decision_context") or state.get("shared_context", {})
    # Optional budgeting can omit a whole unit, but cannot replace its content
    # or attach a known identifier to an unrelated payload.
    for key, identity_key in (("source_manifest", "post_id"), ("completed_social_replies", "post_id")):
        originals = {row[identity_key]: json.loads(json.dumps(row, default=str))
                     for row in original_context.get(key, [])}
        for row in context.get(key, []):
            if row != originals.get(row.get(identity_key)):
                raise ValueError("situation_source_not_admitted")
    frozen_today = {(record["source_type"], record["source_id"]): record
                    for record in original_context.get("today_activity", {}).get("records", [])}
    for record in today.get("records", []) if isinstance(today, dict) else []:
        expected = frozen_today.get((record.get("source_type"), record.get("source_id")))
        if expected is None or json.loads(json.dumps(expected, default=str)) != record:
            raise ValueError("situation_source_not_admitted")
    # These IDs and metadata are code-owned first-read projections. Provider
    # responses never supply provenance or substitute a currently edited row.
    for record in original_context.get("today_activity", {}).get("records", []):
        base = {"world_id": snapshot.scope.world_id, "actor": record.get("actor_world_character_id"),
            "created_at": record.get("occurred_at"), "revision": record.get("source_revision", "initial-input.v1")}
        metadata.setdefault(record["source_id"], {**base, "kind": record["source_type"].upper()})
        for key in ("source_post_id", "target_post_id", "root_post_id", "parent_post_id"):
            if record.get(key):
                authors = dict(record.get("source_authors", []))
                metadata.setdefault(record[key], {**base, "kind": "POST",
                    "revision": "initial-input.v1", "actor": authors.get(record[key])})
    for source in original_context.get("source_manifest", []):
        metadata.setdefault(source["post_id"], {"kind": "POST", "world_id": snapshot.scope.world_id,
            "actor": source["target_ref"], "revision": source["revision"], "created_at": source.get("created_at")})
    for reply in original_context.get("completed_social_replies", []):
        metadata.setdefault(reply["post_id"], {"kind": "REPLY", "world_id": snapshot.scope.world_id,
            "actor": snapshot.scope.subject_world_character_id, "revision": "initial-input.v1"})
    previous = (original_context.get("routine", {}).get("previous_success") or {}).get("post") or {}
    if previous:
        metadata.setdefault(previous["id"], {"kind": "POST", "world_id": snapshot.scope.world_id,
            "actor": snapshot.scope.subject_world_character_id, "revision": "initial-input.v1", "created_at": previous.get("created_at")})
    def add(kind, identifier, delivered, path, role="background", target=None, basis=None,
            version="initial-input.v1", source_digest=None, actor=None, occurred_at=None):
        delivery = FinalDeliveredFragment.capture(payload, path=path, text=delivered, payload_digest=payload_digest)
        if kind in {"IMAGE_ASSET", "IMAGE_INTERPRETATION"}:
            entry = reader.describe(snapshot.scope, kind=kind, identifier=str(identifier), delivered=delivered,
                path=path, role=role, ordinal=len(sources), target=target, delivery=delivery)
        else:
            entry = captured_entry(snapshot.scope, kind=kind, identifier=identifier, delivery=delivery,
                ordinal=len(sources), role=role, target=target, basis=basis, version=version,
                source_digest=source_digest, actor=actor, occurred_at=occurred_at)
        sources.append(entry)
    def relation(ref, delivered, path):
        basis = RelationshipDeliveryBasis(ref["relationship_state_id"], snapshot.scope.subject_world_character_id,
            ref["target_world_character_id"], ref["relationship_version"], ref["view_version"], ref["facts_digest"])
        add("RELATIONSHIP", basis.state_id, delivered, path, basis=basis)
    def post(identifier, delivered, path, role, target=None):
        reference = metadata.get(identifier)
        if reference is None or reference["world_id"] != snapshot.scope.world_id:
            raise ValueError("situation_initial_post_binding_missing")
        body = reference.get("body")
        fragment = body if body and body in delivered else delivered
        if target is not None and path.endswith("/text") and reference.get("views"):
            from app.runtime.memory.captured_delivery import candidate_fragment
            candidate = next(row for row in state["candidates"] if row["target_id"] == target)
            fragment = candidate_fragment(reference, candidate, delivered)
            if not fragment:
                return  # This source was completely outside the delivered budget.
        add(reference["kind"], identifier, fragment, path, role, target,
            version=reference["revision"], actor=reference.get("actor"), occurred_at=reference.get("created_at"))
    selected = [(target, f"/selected_targets/{index}") for index, target in enumerate(payload.get("selected_targets", []))]
    selected.extend((row.get("source", {}), f"/assignments/{index}/source") for index, row in enumerate(payload.get("assignments", [])))
    for target, target_path in selected:
        original = next((row for row in state.get("candidates", [])
                         if row["target_id"] == target.get("target_id")), None)
        if original is None or any(target.get(key) != original.get(key) for key in (
                "text", "source_ids", "source_revisions", "relationship") if key in target):
            raise ValueError("situation_source_not_admitted")
        if "parent_text" in target and target["parent_text"] != original.get("parent_text", ""):
            raise ValueError("situation_source_not_admitted")
        text = target.get("text", "")
        for identifier in target.get("source_ids", []):
            post(identifier, text, target_path + "/text", "core", target["target_id"])
        if target.get("parent_text"):
            for identifier in set(target.get("source_revisions", {})) - set(target.get("source_ids", [])):
                post(identifier, target["parent_text"], target_path + "/parent_text", "core", target["target_id"])
        proposal = target.get("activity_proposal")
        if proposal:
            add("ACTIVITY_PROPOSAL", proposal["proposal_id"], json.dumps(proposal, ensure_ascii=False), target_path + "/activity_proposal")
        relationship_receipt = state.get("relationship_validation_receipts", {}).get(target["target_id"], {})
        if target.get("relationship"):
            for ref in relationship_receipt.get("references", []):
                relation(ref, json.dumps(target["relationship"], ensure_ascii=False), target_path + "/relationship")
    prefix = "/context" if "context" in payload else ""
    for index, source in enumerate(context.get("source_manifest", [])):
        identifier = source.get("post_id")
        if identifier and not any(row.source_id == identifier for row in sources):
            # The transmitted source projection, not an undisclosed full body.
            post(identifier, json.dumps(source, ensure_ascii=False, default=str), f"{prefix}/source_manifest/{index}", "background")
    for index, record in enumerate(today.get("records", []) if isinstance(today, dict) else []):
        path = f"{prefix}/today_activity/records/{index}"
        kind = record["source_type"].upper()
        if kind == "POST":
            post(record["source_id"], record.get("body") or json.dumps(record, ensure_ascii=False), path, "background")
        else:
            reference = metadata.get(record["source_id"])
            if reference is None or reference["kind"] != kind:
                raise ValueError("situation_initial_today_binding_missing")
            add(kind, record["source_id"], json.dumps(record, ensure_ascii=False), path,
                version=reference["revision"], actor=reference.get("actor"), occurred_at=reference.get("created_at"))
        for key, field in (("source_post_id", "body"), ("parent_post_id", "parent_body"), ("root_post_id", "root_body")):
            if record.get(key) and record.get(field):
                post(record[key], record[field], f"{path}/{field}", "background")
    for index, reply in enumerate(context.get("completed_social_replies", [])):
        if reply.get("body"):
            post(reply["post_id"], reply["body"], f"{prefix}/completed_social_replies/{index}/body", "background")
    routine = context.get("routine", {})
    from app.runtime.autonomous_activity.routine_sources import input_source_bindings
    records = routine.get("source_events", [])
    bindings = input_source_bindings(ctx, scope=snapshot.scope, records=records, state=state)
    for index, (record, (kind, identifier)) in enumerate(zip(records, bindings, strict=True)):
        add(kind, identifier, record.get("excerpt") or json.dumps(record, ensure_ascii=False),
            f"{prefix}/routine/source_events/{index}", actor=record.get("actor_world_character_id"),
            occurred_at=record.get("occurred_at"))
    previous = routine.get("previous_success") or {}
    previous_post = previous.get("post") or {}
    if previous_post:
        if previous_post != (original_context.get("routine", {}).get("previous_success") or {}).get("post"):
            raise ValueError("situation_source_not_admitted")
        post(previous_post["id"], previous_post["body"], prefix + "/routine/previous_success/post/body", "background")
    if routine.get("activity"):
        identifier = state["lane_data"]["prepared"]["refs"]["item"]
        add("ROUTINE_ACTIVITY", identifier, json.dumps(routine["activity"], ensure_ascii=False), prefix + "/routine/activity")
    for target, relations in context.get("relationships", {}).items():
        for ref in state.get("relationship_validation_receipts", {}).get(target, {}).get("references", []):
            relation(ref, json.dumps(relations, ensure_ascii=False), f"{prefix}/relationships/{target}")
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
            version, digest = revisions[identifier]
            add("MEMORY_ITEM", identifier, json.dumps(packet, ensure_ascii=False),
                f"{prefix}/memories/{target}/packets/{index}", role="prior", version=version, source_digest=digest)
    threads = {row.thread_id for row in sources if row.thread_id}
    return DeliveredInputManifest(f"sns:{ctx.run_id}:{node}:{sha256(transmitted.encode()).hexdigest()}", snapshot,
        payload_digest, tuple(sources), next(iter(threads)) if len(threads) == 1 else None, version=3)


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
        from app.domains.social.utils.situation_output import stored_output
        raw_digest = stable_digest(expected_output)
        # Final base output is already validated. An invalid internal draft is
        # an integrity error, never an empty-string formatting equivalence.
        expected_output = stored_output(expected_output)
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
        thought_row = session.scalar(select(SocialActivityThought).where(
            SocialActivityThought.public_action_execution_id == execution.id))
        thought_id=thought_row.id if thought_row is not None else None
        value = CommittedActivityResult(state["identity"]["activity_id"], lane.lane, target,
            (expected,), (CommittedEffect("reply" if action == "comment" else action, source_type, source_id, "succeeded"),),
            planned_digest, final_digest, occurred_at,
            counterpart_id=next((row.get("counterpart_id") for row in state.get("candidates", []) if row["target_id"] == target), None))
        from dataclasses import replace
        value = replace(value, result_sources=result_sources, thought_reference=f"social:{thought_id}" if thought_id else None,
            thought={"text":thought_row.thought_text,"status":thought_row.status,"truncated":thought_row.truncated}
                if thought_row is not None else None)
        receipt = admit(session, manifest=manifest, draft=draft, result=value, now=datetime.now(UTC))
        from app.runtime.diagnostics.situation_observation import after_receipt_commit
        try:
            after_receipt_commit(session, getattr(lane, "tracker", None), receipt, decision=decision, override=override,
                raw_digest=raw_digest, normalized_digest=planned_digest, actual_digest=final_digest)
        except Exception:
            # Canonical receipts remain authoritative when optional diagnostics
            # cannot be staged. Export compares DB receipts with commit events.
            import logging
            logging.getLogger(__name__).warning("situation_observation_staging_failed")
    return apply
