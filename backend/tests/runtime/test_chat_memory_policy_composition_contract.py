"""The Memory-policy port cannot authorize other Chat construction changes."""
import ast
import importlib.util
from pathlib import Path

import pytest


_path = Path(__file__).resolve().parents[3] / "scripts/ci/chat_forwarder_retirement.py"
_spec = importlib.util.spec_from_file_location("chat_memory_policy_proof", _path)
proof = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(proof)

SOURCE = "backend/app/runtime/chat/message_composition.py"
BEFORE = '''from app.runtime.chat import generation_workflows
generation_service = GenerationService(thread_service, settings_service, generation_workflows)
message_service = MessageService(thread_service, settings_service)
'''
AFTER = BEFORE.replace(
    "settings_service, generation_workflows)",
    "settings_service, generation_workflows, memory_policy=generation_workflows.capture_memory_policy)",
)


def signed_change(path, name, before, after):
    return (path == SOURCE and name == "generation_service"
            and proof.dump(before) == proof.dump(ast.parse(BEFORE).body[1])
            and proof.dump(after) == proof.dump(ast.parse(AFTER).body[1]))


def test_exact_committed_policy_port_preserves_existing_services():
    proof.validate_situation_policy_composition(SOURCE, BEFORE, AFTER, signed_change)


def test_unchanged_construction_requires_no_new_evidence():
    proof.validate_situation_policy_composition(SOURCE, BEFORE, BEFORE, lambda *args: False)


def test_unrecorded_policy_port_fails_closed():
    with pytest.raises(ValueError, match="service construction"):
        proof.validate_situation_policy_composition(SOURCE, BEFORE, AFTER, lambda *args: False)


@pytest.mark.parametrize("current", [
    AFTER.replace("capture_memory_policy", "capture_another_policy"),
    AFTER.replace("memory_policy=", "other_policy="),
    AFTER.replace("memory_policy=generation_workflows.capture_memory_policy", "memory_policy=lambda *_: None"),
    AFTER.replace("GenerationService(", "FakeService("),
    AFTER.replace("thread_service, settings_service, generation_workflows", "settings_service, thread_service, generation_workflows"),
    AFTER.replace("from app.runtime.chat", "from another_owner"),
    AFTER.replace("message_service = MessageService(thread_service, settings_service)", "message_service = thread_service"),
    AFTER + "generation_service = None\n",
    AFTER + "generation_workflows.capture_memory_policy = lambda *_: None\n",
], ids=["wrong-port", "wrong-keyword", "fake-policy", "fake-service", "old-arguments",
        "foreign-import", "other-service", "shadow-service", "shadow-policy"])
def test_arbitrary_approved_delta_cannot_change_the_di_frame(current):
    with pytest.raises(ValueError, match="service construction"):
        proof.validate_situation_policy_composition(SOURCE, BEFORE, current, lambda *args: True)
