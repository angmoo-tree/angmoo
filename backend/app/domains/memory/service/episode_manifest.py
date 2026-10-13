"""Durable input identity without duplicating originals or private thought text."""

from dataclasses import asdict
from datetime import datetime
from hashlib import sha256

from app.contracts.activity_thought import ActivityThought
from app.contracts.environment import EnvironmentSnapshot
from app.domains.memory.contracts.episode import EpisodeBundle, EpisodeSourceMember, EpisodeSourceUnit, EpisodePriorCandidate
from app.domains.memory.exceptions import MemoryConflictError, MemoryValidationError
from app.domains.memory.policies.episode_bundles import bundle_manifest_hash
from app.domains.memory.service.items import memory_evidence_blocked_code
from app.domains.memory.contracts.provenance import MemorySourceTypeV1
from app.domains.memory.contracts.activity_batch import ACTIVITY_POLICY_VERSION, ACTIVITY_INPUT_VERSION, MemoryActivity


def episode_input_manifest(bundle):
    modern = bundle.policy_version == ACTIVITY_POLICY_VERSION
    excerpt_fields = {"segments", "omitted_characters", "excerpt_policy", "whole_hash"}
    def unit(value):
        return {"key": value.unit_key, "revision": value.unit_revision, "kind": value.kind,
            "occurred_at": value.occurred_at.isoformat(), "thread_id": value.thread_id,
            "coverage": value.coverage, "thought_reference": value.thought_reference,
            "legacy_present": value.legacy_subjective_context is not None,
            "members": [{**{key: part for key, part in asdict(member).items() if key != "text" and (modern or key not in excerpt_fields)},
                         "characters": len(member.text)} for member in value.members]}
    return {"version": ACTIVITY_INPUT_VERSION if modern else "episode-input.v1", "bundle_ref": bundle.bundle_ref,
        **({"policy": bundle.policy_version, "activities": [asdict(a) for a in bundle.activities]} if modern else {}),
        "scope": asdict(bundle.scope), "activation_epoch": bundle.activation_epoch,
        "cutoff_sequence": bundle.cutoff_sequence, "manifest_hash": bundle_manifest_hash(bundle),
        "new": [unit(value) for value in bundle.new_units], "context": [unit(value) for value in bundle.context_units],
        "prior": [asdict(value) for value in bundle.prior_episodes],
        **({"environment": bundle.environment.to_dict()} if bundle.environment is not None else {})}


def restore_episode_input(manifest, *, scope, detail_reader):
    """Re-read exact ranges and thoughts; a changed input cannot reuse a job.

    Persisted manifests are bounded control data. Database exceptions propagate;
    missing/changed source data is a stable conflict, not a new empty prompt.
    """
    modern = isinstance(manifest, dict) and manifest.get("version") == ACTIVITY_INPUT_VERSION
    if (not isinstance(manifest, dict) or manifest.get("version") not in {"episode-input.v1", ACTIVITY_INPUT_VERSION}
        or modern and manifest.get("policy") != ACTIVITY_POLICY_VERSION
        or manifest.get("scope") != asdict(scope)):
        raise MemoryValidationError("episode_manifest_invalid")
    try:
        new, context = manifest["new"], manifest["context"]
        if not isinstance(new, list) or not isinstance(context, list) or not 1 <= len(new) <= (960 if modern else 50) or len(context) > (160 if modern else 5):
            raise ValueError()
        units = [*new, *context]
        if any(not 1 <= len(row["members"]) <= 100 for row in units):
            raise ValueError()
        identities = tuple(dict.fromkeys((m["source_type"], m["source_id"]) for u in units for m in u["members"]))
        references = tuple(dict.fromkeys(u["thought_reference"] for u in units if u["thought_reference"]))
        sources = detail_reader.read_sources(scope=scope, identities=identities)
        thoughts = detail_reader.read_thoughts(scope=scope, references=references)

        def restore(value):
            members = []
            legacy = None
            for frozen in value["members"]:
                identity = frozen["source_type"], frozen["source_id"]
                current = sources.get(identity)
                if current is None or memory_evidence_blocked_code(scope=scope,
                    source_type=MemorySourceTypeV1(identity[0]), source_id=identity[1], evidence=current.evidence):
                    raise MemoryConflictError("episode_manifest_source_unavailable")
                start, count = frozen["start_offset"], frozen["characters"]
                if (type(start) is not int or type(count) is not int or start < 0 or count < 0
                    or start + count > len(current.text)
                    or current.evidence.source_digest != frozen["source_digest"]
                    or frozen["total_characters"] is not None and frozen["total_characters"] != len(current.text)):
                    raise MemoryConflictError("episode_manifest_source_changed")
                fields = {key: part for key, part in frozen.items() if key != "characters"}
                raw = current.text[start:start + count]
                if modern and frozen.get("segments"):
                    fields["segments"] = tuple(tuple(segment) for segment in frozen["segments"])
                    if sha256(current.text.encode("utf-8")).hexdigest() != frozen["whole_hash"]:
                        raise MemoryConflictError("episode_manifest_source_changed")
                    raw = "".join(current.text[left:right] for left, right in fields["segments"])
                    if len(raw) != count:
                        raise MemoryConflictError("episode_manifest_source_changed")
                members.append(EpisodeSourceMember(**fields, text=raw))
                if value["legacy_present"] and current.evidence.actor_world_character_id == scope.subject_world_character_id:
                    legacy = legacy or current.evidence.subjective_context
            ref = value["thought_reference"]
            if ref and ref not in thoughts:
                raise MemoryConflictError("episode_manifest_thought_missing")
            return EpisodeSourceUnit(value["key"], value["revision"], scope, value["kind"],
                datetime.fromisoformat(value["occurred_at"]), tuple(members), value["thread_id"],
                thoughts.get(ref, ActivityThought()), ref, value["coverage"], legacy)

        bundle = EpisodeBundle(manifest["bundle_ref"], scope, tuple(restore(value) for value in new),
            tuple(restore(value) for value in context), tuple(EpisodePriorCandidate(**value) for value in manifest["prior"]),
            manifest["activation_epoch"], manifest["cutoff_sequence"],
            EnvironmentSnapshot.from_dict(manifest["environment"]) if "environment" in manifest else None,
            **({"policy_version": ACTIVITY_POLICY_VERSION, "activities": tuple(MemoryActivity(
                **{**a, "unit_keys": tuple(a["unit_keys"]), "context_keys": tuple(a["context_keys"])})
                for a in manifest["activities"])} if modern else {}))
    except (KeyError, TypeError, ValueError):
        raise MemoryValidationError("episode_manifest_invalid") from None
    if bundle_manifest_hash(bundle) != manifest["manifest_hash"]:
        raise MemoryConflictError("episode_manifest_revision_changed")
    return bundle
