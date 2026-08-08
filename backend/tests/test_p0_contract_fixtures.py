from pathlib import Path

import pytest

from app.contracts.core_experience import CONTRACT_VERSION, load_fixture_package


FIXTURE_ROOT = (
    Path(__file__).parent / "fixtures" / "core_experience" / "p0-contract-v1"
)


def test_p0_contract_fixture_package_is_complete_and_hashed() -> None:
    package = load_fixture_package(FIXTURE_ROOT)

    assert package.manifest.contract_version == CONTRACT_VERSION
    assert len(package.fixtures) == 26
    assert len({fixture.fixture_id for fixture in package.fixtures}) == 26
    assert {fixture.required_phase for fixture in package.fixtures} >= {
        "P1",
        "P2",
        "P3",
        "P4",
        "P6",
        "P7",
        "P8",
        "P9",
        "P10",
    }


@pytest.mark.parametrize(
    "fixture_id",
    [
        "world_open_join_success",
        "world_cross_scope_rejected",
        "world_switch_locked_joint_rejected",
        "world_minimal_publish_ready",
        "world_enriched_publish_ready",
        "world_draft_incomplete",
        "world_private_nonmember_hidden",
        "world_definition_prompt_injection_data_only",
        "world_semantic_change_hash_changes",
        "world_banner_only_hash_stable",
        "world_generation_context_sanitized",
        "repertoire_4x10_success",
        "repertoire_count_failed",
        "repertoire_duplicate_failed",
        "episode_post_success",
        "fictional_interaction_rejected",
        "started_episode_revision_rejected",
        "relationship_direction_preserved",
        "provider_timeout_no_fact",
        "outbox_duplicate_idempotent",
        "neo4j_down_fallback",
        "memory_opt_out_blocked",
        "memory_deleted_blocked",
        "proactive_off_blocked",
        "proactive_duplicate_quiet_blocked",
        "quota_atomic_race",
    ],
)
def test_p0_fixture_has_required_negative_variants(fixture_id: str) -> None:
    package = load_fixture_package(FIXTURE_ROOT)
    fixture = next(item for item in package.fixtures if item.fixture_id == fixture_id)

    assert set(fixture.variants) == {
        "missing_required_field",
        "length_or_enum_exceeded",
        "foreign_key_missing",
        "duplicate_idempotency",
        "deleted_source",
        "inactive_membership",
        "stale_contract_hash",
    }
