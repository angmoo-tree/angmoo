from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "local-smoke.yml"
CONTAINER_SMOKE = REPO_ROOT / "scripts" / "ci" / "run_l0_container_smoke.py"
EXECUTION_MAP = REPO_ROOT / "docs" / "architecture" / "l3-p1-p4-execution-map.md"
EVIDENCE = REPO_ROOT / "docs" / "architecture" / "l3-closeout-evidence.md"
PARITY_ORACLE = (
    REPO_ROOT
    / "docs"
    / "architecture"
    / "l3-er-postgres-neo4j-parity-oracle.json"
)
USER_GUIDE = REPO_ROOT / "docs" / "public" / "l3-local-vertical-loop.md"


def test_l3_representative_suites_are_required_by_local_smoke() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")
    for test_file in (
        "tests/world_characters/test_setup_service.py",
        "tests/test_daily_activity_runtime.py",
        "tests/test_routine_post_runtime.py",
        "tests/world_characters/test_owner_identity.py",
        "tests/test_l3_owner_manual_social_inbox.py",
        "tests/test_l3_domain_boundary_map.py",
        "tests/test_l3_closeout_contract.py",
    ):
        assert test_file in workflow


def test_container_gate_owns_embedded_restart_and_cleanup() -> None:
    smoke = CONTAINER_SMOKE.read_text(encoding="utf-8")

    assert 'EMBEDDED_VOLUME = "angmoo_contributor_embedded_data"' in smoke
    assert "_runtime_health" in smoke
    assert "digest_after != digest_before" in smoke
    assert "harness.cleanup(volumes=True)" in smoke
    assert "Embedded container smoke passed" in smoke


def test_l3_docs_record_completed_closeout_and_separate_release_gate() -> None:
    execution_map = EXECUTION_MAP.read_text(encoding="utf-8")
    evidence = EVIDENCE.read_text(encoding="utf-8")
    oracle = PARITY_ORACLE.read_text(encoding="utf-8")
    guide = USER_GUIDE.read_text(encoding="utf-8")

    assert "L3 PASS_P1_P4_LOCAL_VERTICAL_LOOP" in execution_map
    assert "PR A-H MERGED" in execution_map
    assert "L3 PASS_P1_P4_LOCAL_VERTICAL_LOOP" in evidence
    assert "6119129334193b35b8eb737bd79a3c47ce911afe" in evidence
    assert "0082 -> 0080 -> 0082" in evidence
    assert "Release tagging remains a separate approval" in evidence
    assert '"oracle_version": "l3-er-postgres-neo4j-v1"' in oracle
    assert '"public_anonymous_clone": true' in oracle
    assert '"provider_calls": 0' in oracle
    assert '"credentials_included": false' in oracle
    assert "docker compose up -d" in guide
    assert "docker compose -f compose.yml -f compose.dev.yml up --watch" in guide
    assert "does not guarantee a public reply" in guide
    assert "Cross-World" in guide
