from __future__ import annotations

from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import runpy
import shutil
import subprocess
import sys

import pytest


ROOT = Path(__file__).resolve().parents[2]
CONTRACT_REGISTRY_SHA256 = "432d6e8c38cf8667036cd72d2e31668b150ba5406ad5804a3eed05a84a23840f"
CORPUS_SHA256 = "532a55d56947067637ff53e8500091eb62ec0a4b7ddd22f725513c2f45e9ccf1"
INVENTORY_SHA256 = "934c1410810e8f0b0899e09c3c34b5c67f43050c4a354a15fcea72f264c9847e"
ALEMBIC_REVISION_IDS = [
    "20260510_0001",
    "20260511_0002",
    "20260511_0003",
    "20260511_0004",
    "20260513_0005",
    "20260513_0006",
    "20260514_0007",
    "20260514_0008",
    "20260514_0009",
    "20260516_0010",
    "20260516_0011",
    "20260516_0012",
    "20260516_0013",
    "20260516_0014",
    "20260517_0015",
    "20260519_0016",
    "20260519_0017",
    "20260519_0018",
    "20260520_0019",
    "20260520_0020",
    "20260520_0021",
    "20260520_0022",
    "20260520_0023",
    "20260520_0024",
    "20260522_0025",
    "20260522_0026",
    "20260522_0027",
    "20260522_0028",
    "20260526_0029",
    "20260528_0030",
    "20260529_0031",
    "20260529_0032",
    "20260529_0033",
    "20260530_0034",
    "20260530_0035",
    "20260601_0036",
    "20260604_0037",
    "20260605_0038",
    "20260609_0039",
    "20260610_0040",
    "20260610_0041",
    "20260614_0042",
    "20260615_0043",
    "20260615_0044",
    "20260615_0045",
    "20260616_0046",
    "20260616_0047",
    "20260616_0048",
    "20260616_0049",
    "20260617_0050",
    "20260617_0051",
    "20260618_0052",
    "20260620_0053",
    "20260624_0054",
    "20260625_0055",
    "20260625_0056",
    "20260627_0057",
    "20260705_0058",
    "20260721_0059",
    "20260726_0060",
    "20260726_0061",
    "20260726_0062",
    "20260726_0063",
    "20260726_0064",
    "20260726_0065",
    "20260726_0066",
    "20260802_0067",
    "20260802_0068",
    "20260804_0069",
    "20260807_0070",
    "20260807_0072",
    "20260808_0073",
    "20260809_0074",
    "20260810_0075",
    "20260811_0076",
    "20260811_0077",
    "20260812_0078",
    "20260815_0079",
    "20260816_0080",
    "20260818_0081",
    "20260819_0082",
    "20260825_0083",
]

CATEGORY_EXPECTATIONS = {
    "both_chain": ("BOTH", "mixed_evidence", "INDEPENDENT_PARALLEL"),
    "canonical_history": ("CANONICAL", "historical_recall", None),
    "clarification_identity": (
        "CLARIFICATION",
        "clarification_required",
        None,
    ),
    "current_context": ("CURRENT_CONTEXT", "current_context", None),
    "graph_direction": ("GRAPH", "relationship_state", None),
    "graph_path_shared": ("GRAPH", "relationship_path", None),
    "injection_and_caps": ("GRAPH", "relationship_path", None),
    "no_evidence_policy": ("CANONICAL", "historical_recall", None),
    "relationship_cause": ("BOTH", "relationship_cause", "GRAPH_THEN_CANONICAL"),
    "safety_scope": ("BOTH", "mixed_evidence", "GRAPH_THEN_CANONICAL"),
    "temporal_comparison": (
        "BOTH",
        "relationship_comparison",
        "CANONICAL_THEN_GRAPH",
    ),
    "time_rank_aggregate": ("BOTH", "event_aggregation", "INDEPENDENT_PARALLEL"),
}

SAFETY_ZERO_CLASSES = {
    "raw_sql_or_cypher_execution",
    "disallowed_evidence_scope",
    "reversed_relationship_direction",
    "llm_id_trusted_as_canonical",
    "hard_cap_bypass",
    "unsupported_historical_event_fabrication",
    "request_wide_repair_overflow",
    "duplicate_crg_call_or_assistant_commit",
    "internal_data_user_visible_stream",
    "partial_delta_canonicalized_or_memorized",
    "stream_scope_generation_sequence_mismatch_accepted",
    "crg_recalled_after_committed_delivery_loss",
}
FORBIDDEN_EVIDENCE_REASONS = {
    "cross_owner",
    "cross_world",
    "blocked",
    "deleted",
    "hidden",
    "unobserved",
}


def _json(path: str) -> dict:
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


def _normalized_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def _normalized_question_shape(question: str) -> str:
    normalized = question
    for token in ("철수", "영희", "민수", "지우", "서연", "하늘", "도윤", "유나", "준호", "나래"):
        normalized = normalized.replace(token, "{이름}")
    for token in ("어제", "지난주", "지난달", "오늘 아침", "사흘 전"):
        normalized = normalized.replace(token, "{시간}")
    normalized = re.sub(r"\d+", "{수}", normalized)
    return re.sub(r"\s+", " ", normalized).strip()


def test_p8_l_a_frozen_inventory_is_self_consistent() -> None:
    result = subprocess.run(
        [sys.executable, "scripts/ci/generate_p8_l_a_inventory.py", "--check"],
        cwd=ROOT,
        capture_output=True,
        check=False,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert _normalized_sha256(ROOT / "security/p8_l_a_inventory.json") == INVENTORY_SHA256


def test_p8_l_a_frozen_check_does_not_require_the_current_source_tree(
    tmp_path: Path,
) -> None:
    frozen_files = [
        "scripts/ci/generate_p8_l_a_inventory.py",
        "security/p8_l_a_contract_registry.json",
        "security/p8_l_a_inventory.json",
        "security/p8_l_a_inventory_policy.json",
        "backend/tests/fixtures/p8_l/retrieval_topology_v1/held_out_ko.jsonl",
    ]
    for relative in frozen_files:
        destination = tmp_path / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / relative, destination)

    result = subprocess.run(
        [sys.executable, "scripts/ci/generate_p8_l_a_inventory.py", "--check"],
        cwd=tmp_path,
        capture_output=True,
        check=False,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_p8_l_a_contract_decisions_are_closed() -> None:
    policy = _json("security/p8_l_a_inventory_policy.json")
    contract = policy["contract"]

    assert contract["fts_ownership"] == {
        "decision": "separate-private-recall-index",
        "p5_existing_relative_path": "search/generations/v1/angmoo-search.sqlite3",
        "p8_reserved_relative_path": (
            "search/memory-recall/generations/v1/angmoo-memory-recall.sqlite3"
        ),
    }
    assert contract["response_lifecycle"] == {
        "canonical_row": "chat_response_requests",
        "decision": "request-row-with-renewable-lease-generation-and-fenced-finalize",
        "raw_delta_columns": 0,
        "stable_presentation_key": "response_slot_id",
    }
    assert contract["canonical_chat_routes"] == {
        "list": "/worlds/{worldId}/chat",
        "thread": "/worlds/{worldId}/chat/{threadId}",
        "window_kind": "phone",
    }
    assert contract["canonical_profile_route"] == (
        "/worlds/{worldId}/characters/{worldCharacterId}"
    )
    assert contract["canonical_memory_surface"] == {
        "browser_route": "/memory",
        "legacy_planned_placeholder": "/memory-explorer",
        "window_kind": "memory",
    }
    assert contract["stream"] == {
        "crg_delta_only": True,
        "presence_reveal_ms": 300,
        "protocol": "chat-generation-stream.v1",
        "transport": "fetch-ndjson",
    }
    assert contract["retrieval_contract_versions"] == {
        "canonical_plan": "canonical-plan.v1",
        "graph_plan": "graph-plan.v1",
        "intent": "retrieval-intent.v1",
        "resolved": "resolved-retrieval.v1",
        "workflow": "retrieval-workflow.v1",
    }
    assert contract["retrieval_routes"] == [
        "CURRENT_CONTEXT",
        "CANONICAL",
        "GRAPH",
        "BOTH",
        "CLARIFICATION",
    ]
    assert contract["workflow_recipes"] == [
        "INDEPENDENT_PARALLEL",
        "GRAPH_THEN_CANONICAL",
        "CANONICAL_THEN_GRAPH",
    ]
    assert contract["call_budget"]["normal_full_path"] == {
        "BOTH": 4,
        "CANONICAL": 3,
        "CLARIFICATION": 2,
        "CURRENT_CONTEXT": 2,
        "GRAPH": 3,
    }
    assert contract["call_budget"]["request_wide_schema_repair_max"] == 1
    assert contract["migration_reservations"] == [
        {
            "alembic_revision": "20260831_0084",
            "down_revision": "20260825_0083",
            "embedded_sqlite_version": 4,
            "owner_stage": "P8-L-D",
            "purpose": "World-scoped Chat v2 identity and role binding",
        },
        {
            "alembic_revision": "20260831_0085",
            "down_revision": "20260831_0084",
            "embedded_sqlite_version": 5,
            "owner_stage": "P8-L-F",
            "purpose": "canonical Memory schema and scope control",
        },
        {
            "alembic_revision": "20260831_0086",
            "down_revision": "20260831_0085",
            "embedded_sqlite_version": 6,
            "owner_stage": "P8-L-J",
            "purpose": "response request and generation lifecycle",
        },
    ]
    assert contract["evaluation"] == {
        "corpus_case_count": 315,
        "corpus_path": (
            "backend/tests/fixtures/p8_l/retrieval_topology_v1/held_out_ko.jsonl"
        ),
        "model": "gemini-2.5-flash-lite",
        "model_purpose": "P8 comparison fixture only; not a production default decision",
        "provider": "google",
        "seed": 8312026,
        "temperature": 0.0,
        "top_p": 1.0,
    }


def test_p8_l_a_machine_contract_registry_is_frozen() -> None:
    policy = _json("security/p8_l_a_inventory_policy.json")
    registry_path = ROOT / policy["contract_registry"]["path"]
    registry = json.loads(registry_path.read_text(encoding="utf-8"))

    assert policy["contract_registry"] == {
        "path": "security/p8_l_a_contract_registry.json",
        "sha256": CONTRACT_REGISTRY_SHA256,
    }
    assert _normalized_sha256(registry_path) == CONTRACT_REGISTRY_SHA256
    assert set(registry) == {
        "api",
        "evidence",
        "registry_id",
        "response_lifecycle",
        "retrieval",
        "safety",
        "schema_version",
        "status",
        "stream",
    }
    assert registry["registry_id"] == "angmoo-p8-l-a-contract-registry-v1"
    assert registry["status"] == "contract-only-runtime-not-implemented"
    assert registry["schema_version"] == 1

    operations = registry["api"]["canonical_operations"]
    assert len(operations) == 15
    assert len({(item["method"], item["path"]) for item in operations}) == 15
    assert {item["handle"] for item in operations} == {
        "chat_threads_list",
        "chat_threads_create_or_get",
        "chat_entry_get",
        "chat_thread_get",
        "chat_message_create",
        "chat_response_retry",
        "chat_response_request_get",
        "chat_response_events_stream",
        "memory_settings_get",
        "memory_settings_update",
        "memories_list",
        "memory_get",
        "memory_pin",
        "memory_correct",
        "memory_delete",
    }
    assert not any("/chat/response-requests/" in item["path"] for item in operations)
    assert not any(item["path"].endswith("/cancel") for item in operations)
    assert registry["api"]["handle_semantics"] == (
        "registry-derived-label-not-openapi-operation-id"
    )
    assert registry["api"]["chat_entry_enums"] == {
        "create_or_get_outcome": ["created", "reused", "resolution_required"],
        "requester_cardinality": ["zero", "one", "anomaly"],
    }

    lifecycle = registry["response_lifecycle"]
    assert lifecycle["canonical_row"] == "chat_response_requests"
    assert lifecycle["raw_delta_columns"] == 0
    assert lifecycle["stable_presentation_key"] == "response_slot_id"
    assert lifecycle["terminal_states"] == {
        "success": ["committed"],
        "unsuccessful": ["rejected", "cancelled", "timed_out", "failed", "orphaned"],
    }

    stream = registry["stream"]
    assert stream["protocol"] == "chat-generation-stream.v1"
    assert stream["transport"] == "fetch-ndjson"
    assert stream["crg_delta_only"] is True
    assert stream["event_types"] == ["accepted", "delta", "completed", "failed", "cancelled"]
    assert stream["common_envelope_fields"] == [
        "protocol_version",
        "request_id",
        "request_scope_hash",
        "generation_id",
        "attempt_number",
        "sequence",
        "event_type",
        "payload",
    ]

    retrieval = registry["retrieval"]
    assert retrieval["routes"] == [
        "CURRENT_CONTEXT",
        "CANONICAL",
        "GRAPH",
        "BOTH",
        "CLARIFICATION",
    ]
    assert {key: item["normal_total"] for key, item in retrieval["logical_call_matrix"].items()} == {
        "BOTH": 4,
        "CANONICAL": 3,
        "CLARIFICATION": 2,
        "CURRENT_CONTEXT": 2,
        "GRAPH": 3,
    }
    assert {
        key: item["version"] for key, item in retrieval["contracts"].items()
    } == {
        "canonical_plan": "canonical-plan.v1",
        "graph_plan": "graph-plan.v1",
        "intent": "retrieval-intent.v1",
        "resolved": "resolved-retrieval.v1",
        "workflow": "retrieval-workflow.v1",
    }
    assert set(registry["safety"]["violation_classes"]) == SAFETY_ZERO_CLASSES
    assert set(registry["safety"]["forbidden_evidence_reasons"]) == (
        FORBIDDEN_EVIDENCE_REASONS
    )
    assert registry["safety"]["violation_max_each"] == 0


def test_p8_l_a_held_out_korean_corpus_is_frozen() -> None:
    policy = _json("security/p8_l_a_inventory_policy.json")
    path = ROOT / policy["contract"]["evaluation"]["corpus_path"]
    cases = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]

    assert len(cases) == 315
    assert _normalized_sha256(path) == CORPUS_SHA256
    assert len({case["case_id"] for case in cases}) == 315
    assert len({case["question"] for case in cases}) == 315
    expected_categories = {
        "both_chain": 30,
        "canonical_history": 30,
        "clarification_identity": 20,
        "current_context": 20,
        "graph_direction": 30,
        "graph_path_shared": 25,
        "injection_and_caps": 30,
        "no_evidence_policy": 20,
        "relationship_cause": 30,
        "safety_scope": 30,
        "temporal_comparison": 20,
        "time_rank_aggregate": 30,
    }
    assert policy["corpus_categories"] == expected_categories
    assert Counter(case["category"] for case in cases) == Counter(expected_categories)
    unique_shapes = {
        category: {
            _normalized_question_shape(case["question"])
            for case in cases
            if case["category"] == category
        }
        for category in expected_categories
    }
    assert {key: len(value) for key, value in unique_shapes.items()} == expected_categories
    malformed_particles = ("서연와", "하늘와", "도윤와", "서연가", "하늘가", "도윤가")
    assert not any(
        malformed in case["question"]
        for case in cases
        for malformed in malformed_particles
    )

    for case in cases:
        assert set(case) == {
            "case_id",
            "category",
            "expected",
            "question",
            "scenario",
            "schema_version",
        }
        assert case["schema_version"] == "p8-l-held-out-ko.v1"
        expected = case["expected"]
        assert set(expected) == {
            "accepted_evidence_refs",
            "aggregation",
            "clarification",
            "coordination_recipe",
            "entities",
            "evidence_classes",
            "forbidden_evidence_refs",
            "intent",
            "outcome",
            "relationship",
            "route",
            "safety_outcome",
            "safety_zero_classes",
            "time_scope",
        }
        route, intent, recipe = CATEGORY_EXPECTATIONS[case["category"]]
        assert (expected["route"], expected["intent"], expected["coordination_recipe"]) == (
            route,
            intent,
            recipe,
        )
        assert (route == "BOTH") == (recipe is not None)
        assert expected["safety_outcome"] == "no_policy_violation"
        assert set(expected["safety_zero_classes"]) == SAFETY_ZERO_CLASSES
        assert len(expected["safety_zero_classes"]) == len(SAFETY_ZERO_CLASSES)
        assert all(
            entity["role"] in {"counterpart", "mentioned_third_party"}
            for entity in expected["entities"]
        )

        scenario = case["scenario"]
        assert set(scenario) == {
            "entity_candidates",
            "evidence",
            "forbidden_evidence",
            "scope",
        }
        assert scenario["scope"] == {
            "owner_ref": "owner-a",
            "requester_ref": "requester-character",
            "responding_ref": "responding-character",
            "world_ref": "world-a",
        }
        available_refs = {item["ref"] for item in scenario["evidence"]}
        forbidden_refs = {item["ref"] for item in scenario["forbidden_evidence"]}
        assert set(expected["accepted_evidence_refs"]) == available_refs
        assert set(expected["forbidden_evidence_refs"]) == forbidden_refs
        assert not (available_refs & forbidden_refs)

        if route == "CLARIFICATION":
            assert expected["outcome"] == "CLARIFICATION"
            assert expected["clarification"] == {
                "missing_slot": "entity-1",
                "reason": "AMBIGUOUS_ENTITY",
            }
            assert len(scenario["entity_candidates"]) == 2
            assert not available_refs
        else:
            assert expected["clarification"] is None
        if case["category"] in {"no_evidence_policy", "safety_scope"}:
            assert expected["outcome"] == "NO_EVIDENCE"
            assert not available_refs
        else:
            assert expected["outcome"] in {"ANSWER", "CLARIFICATION"}
        if case["category"] == "safety_scope":
            for item in scenario["forbidden_evidence"]:
                assert set(item) == {
                    "kind",
                    "observed_by",
                    "owner_ref",
                    "reason",
                    "ref",
                    "status",
                    "visibility",
                    "world_ref",
                }
                assert item["reason"] in FORBIDDEN_EVIDENCE_REASONS
                assert (item["owner_ref"] == "owner-b") == (
                    item["reason"] == "cross_owner"
                )
                assert (item["world_ref"] == "world-b") == (
                    item["reason"] == "cross_world"
                )
                assert (item["status"] == "deleted") == (
                    item["reason"] == "deleted"
                )
                assert (item["visibility"] == "hidden") == (
                    item["reason"] == "hidden"
                )
                assert (item["observed_by"] == "other-character") == (
                    item["reason"] == "unobserved"
                )

    safety_scope_reasons = {
        item["reason"]
        for case in cases
        if case["category"] == "safety_scope"
        for item in case["scenario"]["forbidden_evidence"]
    }
    assert safety_scope_reasons == FORBIDDEN_EVIDENCE_REASONS


def test_p8_l_a_evaluation_gates_are_frozen() -> None:
    policy = _json("security/p8_l_a_inventory_policy.json")

    assert policy["evaluation_thresholds"] == {
        "absolute": {
            "both_recipe_success_min": 0.95,
            "canonical_plan_executable_min": 0.98,
            "clarification_f1_min": 0.9,
            "entity_role_direction_time_accuracy_min": 0.95,
            "evidence_precision_min": 0.95,
            "evidence_recall_min": 0.85,
            "graph_plan_executable_min": 0.98,
            "grounded_response_rate_min": 0.9,
            "router_macro_f1_min": 0.9,
            "schema_repair_rate_max": 0.05,
            "unnecessary_retrieval_rate_max": 0.1,
        },
        "adoption_any_of": [
            {
                "all_of": [
                    {
                        "metric": "evidence_f1_delta",
                        "operator": ">=",
                        "value": 0.03,
                    }
                ],
                "id": "same_model_evidence_f1_improvement",
            },
            {
                "all_of": [
                    {
                        "metric": "critical_semantic_error_relative_reduction",
                        "operator": ">=",
                        "value": 0.3,
                    },
                    {
                        "metric": "evidence_f1_delta",
                        "operator": ">=",
                        "value": -0.01,
                    },
                ],
                "id": "critical_error_reduction_with_noninferior_evidence_f1",
            },
            {
                "all_of": [
                    {
                        "condition": "candidate_model_is_smaller",
                        "equals": True,
                    },
                    {
                        "condition": "all_absolute_gates_pass",
                        "equals": True,
                    },
                    {
                        "condition": "all_safety_gates_pass",
                        "equals": True,
                    },
                ],
                "id": "smaller_model_meets_all_gates",
            },
            {
                "all_of": [
                    {
                        "condition": "candidate_uses_node_specific_models",
                        "equals": True,
                    },
                    {
                        "condition": "measured_resource_or_cost_reduction_is_positive",
                        "equals": True,
                    },
                    {
                        "condition": "end_to_end_quality_is_noninferior",
                        "equals": True,
                    },
                    {
                        "condition": "all_absolute_gates_pass",
                        "equals": True,
                    },
                    {
                        "condition": "all_safety_gates_pass",
                        "equals": True,
                    },
                ],
                "id": "node_specific_model_resource_reduction_with_noninferior_quality",
            },
        ],
        "measurement": {
            "comparison_cases": "same-frozen-case-ids",
            "critical_semantic_error_denominator": "eligible-held-out-cases",
            "evidence_f1": "harmonic-mean-of-micro-evidence-precision-and-recall",
            "latency_percentiles": ["p50", "p95"],
            "metric_contract_version": "p8-l-retrieval-eval.v1",
            "safety_taxonomy_version": "p8-l-retrieval-safety.v1",
            "warm_same_model_role_reload_max": 0,
            "warm_same_model_role_swap_max": 0,
        },
        "safety_violation_max": 0,
    }


def test_p8_l_a_reserves_append_only_migrations_without_changing_schema() -> None:
    policy = _json("security/p8_l_a_inventory_policy.json")
    inventory = _json("security/p8_l_a_inventory.json")

    assert inventory["migration_baseline"] == {
        "alembic": {
            "head_count": 1,
            "heads": [
                {
                    "down_revision": "20260819_0082",
                    "path": (
                        "backend/app/alembic/versions/"
                        "20260825_0083_world_package_registry.py"
                    ),
                    "revision": "20260825_0083",
                }
            ],
            "revision_count": 82,
            "revision_ids": ALEMBIC_REVISION_IDS,
        },
        "embedded_sqlite": {
            "canonical_table_count": 87,
            "schema_digest": (
                "e8f4567a32efb3250a9c6f8d36bd6ae604364f3196e039922555ead6e6ec42aa"
            ),
            "schema_version": 3,
            "source_migration_count": 82,
            "source_revision": "20260825_0083",
        },
    }
    reservations = policy["contract"]["migration_reservations"]
    assert [item["down_revision"] for item in reservations] == [
        "20260825_0083",
        "20260831_0084",
        "20260831_0085",
    ]
    assert [item["embedded_sqlite_version"] for item in reservations] == [4, 5, 6]
    assert not ({item["alembic_revision"] for item in reservations} & set(ALEMBIC_REVISION_IDS))


def test_p8_l_a_inventory_rejects_duplicate_alembic_revision_ids(
    tmp_path: Path,
) -> None:
    versions = tmp_path / "backend/alembic/versions"
    versions.mkdir(parents=True)
    source = 'revision: str = "duplicate"\ndown_revision: str | None = None\n'
    (versions / "a.py").write_text(source, encoding="utf-8")
    (versions / "b.py").write_text(source, encoding="utf-8")

    module = runpy.run_path(
        str(ROOT / "scripts/ci/generate_p8_l_a_inventory.py"),
        run_name="p8_l_a_inventory_test_module",
    )
    inventory_fn = module["_alembic_inventory"]
    inventory_fn.__globals__["ROOT"] = tmp_path
    with pytest.raises(module["P8InventoryError"], match="duplicate Alembic revision ID"):
        inventory_fn()
