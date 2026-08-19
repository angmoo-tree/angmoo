from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "local-smoke.yml"
CONTAINER_SMOKE = REPO_ROOT / "scripts" / "ci" / "run_l0_container_smoke.py"
EXECUTION_MAP = REPO_ROOT / "docs" / "architecture" / "l3-p1-p4-execution-map.md"
EVIDENCE = REPO_ROOT / "docs" / "architecture" / "l3-closeout-evidence.md"
USER_GUIDE = REPO_ROOT / "docs" / "public" / "l3-local-vertical-loop.md"


def test_l3_representative_suites_are_required_by_local_smoke() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")
    for test_file in (
        "tests/test_world_character_setup_service.py",
        "tests/test_daily_activity_runtime.py",
        "tests/test_routine_post_runtime.py",
        "tests/test_l3_owner_controlled_world_character.py",
        "tests/test_l3_owner_manual_social_inbox.py",
        "tests/test_l3_domain_boundary_map.py",
        "tests/test_l3_closeout_contract.py",
    ):
        assert test_file in workflow


def test_container_gate_owns_l3_migration_round_trip_and_cleanup() -> None:
    smoke = CONTAINER_SMOKE.read_text(encoding="utf-8")

    assert 'L3_PREVIOUS_REVISION = "20260816_0080"' in smoke
    assert "_l3_migration_round_trip" in smoke
    assert "digest_after != digest_before" in smoke
    assert "harness.cleanup(volumes=True)" in smoke
    assert "L3 migration round trip passed" in smoke


def test_l3_docs_separate_implementation_from_final_user_gate() -> None:
    execution_map = EXECUTION_MAP.read_text(encoding="utf-8")
    evidence = EVIDENCE.read_text(encoding="utf-8")
    guide = USER_GUIDE.read_text(encoding="utf-8")

    assert "IN PROGRESS / PR H CLOSEOUT" in execution_map
    assert "PR H LOCAL AND HOSTED TECH PASS" in evidence
    assert "USER SCREEN AND MERGE GATES NOT REACHED" in evidence
    assert "0082 -> 0080 -> 0082" in evidence
    assert "Release tagging remains a separate approval" in evidence
    assert "docker compose up -d" in guide
    assert "docker compose -f compose.yml -f compose.dev.yml up --watch" in guide
    assert "does not guarantee a public reply" in guide
    assert "Cross-World" in guide
