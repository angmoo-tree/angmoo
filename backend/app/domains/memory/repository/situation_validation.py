"""Restore immutable validation context from canonical persisted bindings only."""
from dataclasses import asdict

from app.domains.memory.contracts.activity_situation import (
    DeliveredInputManifest, DeliveredSourceEntry, SituationDraft, SituationValidationContext,
    SITUATION_POLICY, stable_digest,
)
from app.domains.memory.models.activity_situation import MemorySituationManifest
from app.domains.memory.models.items import MemoryScopeSettingModel
from app.domains.memory.policies.situation_output import parse_description


def restore_context(session, receipt):
    if receipt.state == "discarded" or receipt.manifest_id is None:
        raise ValueError("situation_discarded")
    stored = session.get(MemorySituationManifest, receipt.manifest_id, populate_existing=True)
    if stored is None or stable_digest(stored.payload) != stored.content_digest or stored.id != stored.content_digest:
        raise ValueError("situation_manifest_integrity_invalid")
    manifest = DeliveredInputManifest.from_dict(stored.payload)
    snapshot = manifest.snapshot
    setting = session.get(MemoryScopeSettingModel, receipt.scope_setting_id, populate_existing=True)
    if setting is None or (setting.owner_id, setting.world_id, setting.subject_world_character_id) != (
        snapshot.scope.owner_id, snapshot.scope.world_id, snapshot.scope.subject_world_character_id):
        raise ValueError("situation_receipt_scope_mismatch")
    if (receipt.scope_setting_id != stored.scope_setting_id or snapshot.setting_id != receipt.scope_setting_id
            or stored.call_identity != manifest.call_identity or receipt.policy_version != SITUATION_POLICY
            or snapshot.policy_version != receipt.policy_version or snapshot.activation_epoch != receipt.activation_epoch
            or snapshot.scope_version != receipt.scope_version):
        raise ValueError("situation_receipt_scope_mismatch")
    result = dict(receipt.result)
    admission = result.pop("_admission", None)
    draft = (SituationDraft(**admission["draft"]) if admission is not None
        else SituationDraft(receipt.target_key, receipt.description, receipt.description_status))
    if (draft.target_key != receipt.target_key or draft.description != receipt.description
            or draft.status != receipt.description_status
            or stable_digest({"manifest": stored.payload, "draft": asdict(draft), "result": result}) != receipt.content_digest):
        raise ValueError("situation_receipt_integrity_invalid")
    if (result.get("logical_activity_id") != receipt.logical_activity_id or result.get("lane") != receipt.lane
            or result.get("target_key") != receipt.target_key
            or not result.get("planned_effects") or not result.get("effects")
            or result.get("planned_output_digest") != result.get("final_output_digest")
            or sorted(result["planned_effects"]) != sorted(effect["kind"] for effect in result["effects"])
            or any(effect["status"] != "succeeded" for effect in result["effects"])
            or parse_description(receipt.description, target_key=receipt.target_key).status != "valid"):
        raise ValueError("situation_success_binding_invalid")
    sources = tuple(DeliveredSourceEntry.from_dict(value) for value in result.get("result_sources", ()))
    entries = (*manifest.sources, *sources)
    if manifest.version == 2:
        committed = {(source.source_type, source.source_id) for source in sources if source.role == "committed_result"}
        effects = {(effect["source_type"], effect["source_id"]) for effect in result["effects"]}
        if (not manifest.sources or committed != effects
            or any(source.delivery_payload_digest != manifest.payload_digest for source in manifest.sources)):
            raise ValueError("situation_execution_binding_invalid")
    if (len({entry.ordinal for entry in entries}) != len(entries)
            or any(entry.world_id != snapshot.scope.world_id or entry.thread_id not in {None, manifest.private_thread_id}
                for entry in entries)
            or any(entry.role not in {"committed_result", "thought"} or entry.target_key != receipt.target_key for entry in sources)):
        raise ValueError("situation_source_binding_invalid")
    if admission is not None and (admission.get("manifest_digest") != stored.content_digest
            or admission.get("result_digest") != stable_digest(result)):
        raise ValueError("situation_execution_binding_invalid")
    return SituationValidationContext(manifest, receipt.sequence, stored.content_digest, sources,
        receipt.target_key, receipt.logical_activity_id, receipt.lane)
