"""The reviewed Chat retirement cannot hide behavior or another deleted layer."""

import ast
import importlib.util
from pathlib import Path
import shutil
import subprocess

import pytest


REPO = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("chat_forwarder_test_proof", REPO / "scripts/ci/chat_forwarder_retirement.py")
proof = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(proof)


@pytest.fixture(scope="module")
def signed_reader():
    cache = {}

    def read(*args, root):
        if args not in cache:
            cache[args] = subprocess.check_output(["git", *args], cwd=REPO)
        return cache[args]

    return read


@pytest.fixture()
def candidate(tmp_path):
    files = [
        *(f"backend/app/domains/chat/service/{role}.py" for role in proof.OWNER_CLASSES),
        "backend/app/domains/chat/repository/response_lifecycle.py",
        "backend/app/domains/chat/dependencies.py",
        "backend/app/runtime/chat/message_composition.py",
        "backend/app/runtime/chat/generation_workflows.py",
        "backend/app/domains/social/repository/blocks.py",
        "backend/app/api/v1/routes/world_chat_response.py",
        *(path for path, _ in proof.TESTS.values()),
    ]
    for path in files:
        target = tmp_path / path
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(REPO / path, target)
    moves = {
        "backend/app/domains/chat/application/messages.py": "backend/app/domains/chat/service/threads.py",
        "backend/app/domains/chat/ports/runtime.py": "backend/app/domains/chat/dependencies.py",
        "backend/app/domains/chat/application/generation_lifecycle.py": "backend/app/domains/chat/repository/response_lifecycle.py",
        "backend/app/runtime/chat/world_generation.py": "backend/app/domains/chat/service/generation.py",
    }
    return tmp_path, moves


def rewrite(root, path, old, new):
    file = root / path
    source = file.read_text()
    assert old in source
    file.write_text(source.replace(old, new), encoding="utf-8")


def test_exact_original_layers_and_actual_owner_tests_are_verified(candidate, signed_reader):
    root, moves = candidate
    result = proof.validate(True, moves, [], root, signed_reader)
    assert set(result) == {function for _, function in proof.TESTS.values()}
    for key, (path, function) in proof.TESTS.items():
        old = signed_reader("show", f"{proof.ANCHOR}:{path}", root=root).decode()
        original = proof.definition(old, function, ast.FunctionDef)
        required = proof.required_fragments(proof.fragments(original), old, path, function, path, function, result)
        current = proof.definition((root / path).read_text(), function, ast.FunctionDef)
        assert required == proof.fragments(current)
        assert len(required) >= len(proof.fragments(original))


@pytest.mark.parametrize("mutation", [
    "retained_file", "copied_class", "backend_script_import", "root_script_dynamic_import",
    "owner_stub", "composition_rebind", "route_binding_rebind", "delegate_missing_result",
    "delegate_missing_failure_finalization", "delegate_fake_owner", "asyncio_reimport",
    "durable_count_removed", "path_reimport", "path_function", "file_shadow",
    "route_self_identity", "unsafe_disposition", "missing_disposition", "unrelated_disposition",
    "asyncio_attribute", "asyncio_setattr", "asyncio_nested_import", "module_side_effect",
    "star_import", "retained_package",
    "relative_import", "exported_uow_stub", "block_query_binding", "block_query_body",
])
def test_retirement_rejects_reintroduced_layers_and_weakened_actual_checks(candidate, signed_reader, mutation):
    root, moves = candidate
    delegate = proof.TESTS["delegate"][0]
    owner = proof.TESTS["owner"][0]
    routes = proof.TESTS["routes"][0]
    if mutation == "retained_file":
        path = root / next(iter(proof.OLD))
        path.parent.mkdir(parents=True)
        path.write_text("# even an empty former module cannot remain\n")
    elif mutation == "copied_class":
        (root / "backend/app/copied.py").write_text("class ChatService:\n    pass\n")
    elif mutation == "backend_script_import":
        path = root / "backend/scripts/run.py"
        path.parent.mkdir(parents=True)
        path.write_text("from app.compatibility.chat_service import ChatService\n")
    elif mutation == "root_script_dynamic_import":
        path = root / "scripts/run.py"
        path.parent.mkdir(parents=True)
        path.write_text("import importlib\nimportlib.import_module('app.runtime.chat.world_generation')\n")
    elif mutation == "owner_stub":
        rewrite(root, "backend/app/domains/chat/service/messages.py", "content = data.content.strip()", "return 'sent'\n        content = data.content.strip()")
    elif mutation == "composition_rebind":
        rewrite(root, "backend/app/runtime/chat/message_composition.py", "message_service = MessageService(thread_service, settings_service)", "message_service = thread_service")
    elif mutation == "block_query_binding":
        rewrite(root, "backend/app/runtime/chat/message_composition.py", "from app.domains.social.repository.blocks import world_character_pair_is_blocked", "from app.domains.social.repository.blocks import write_pair_is_blocked as world_character_pair_is_blocked")
    elif mutation == "block_query_body":
        rewrite(root, "backend/app/domains/social/repository/blocks.py", "return db.scalar(", "return False\n    return db.scalar(")
    elif mutation == "route_binding_rebind":
        with (root / "backend/app/api/v1/routes/world_chat_response.py").open("a") as stream:
            stream.write("\ngeneration_service = evidence_service\n")
    elif mutation == "delegate_missing_result":
        rewrite(root, delegate, 'assert asyncio.run(messages.send_message(db, user, "thread-1", data)) == "sent"', 'assert True')
    elif mutation == "delegate_missing_failure_finalization":
        rewrite(root, delegate, 'assert caught.value is failure', 'assert caught.value is caught.value')
    elif mutation == "delegate_fake_owner":
        rewrite(root, delegate, "messages = MessageService(threads, settings)", "messages = threads")
    elif mutation == "asyncio_reimport":
        with (root / delegate).open("a") as stream:
            stream.write("\nimport fake_asyncio as asyncio\n")
    elif mutation == "durable_count_removed":
        rewrite(root, owner, 'assert first.user_message.id == replay.user_message.id', 'assert True')
    elif mutation == "path_reimport":
        with (root / owner).open("a") as stream:
            stream.write("\nfrom fake_path import Path\n")
    elif mutation == "path_function":
        with (root / owner).open("a") as stream:
            stream.write("\ndef Path(*args):\n    return None\n")
    elif mutation == "file_shadow":
        with (root / owner).open("a") as stream:
            stream.write("\nfrom fake_path import fake as __file__\n")
    elif mutation == "route_self_identity":
        rewrite(root, routes, "assert world_chat_response.generation_service is message_composition.generation_service", "assert message_composition.generation_service is message_composition.generation_service")
    elif mutation == "unsafe_disposition":
        moves[next(iter(moves))] = "../unrelated.py"
    elif mutation == "missing_disposition":
        moves.pop(next(iter(moves)))
    elif mutation == "unrelated_disposition":
        moves[next(iter(moves))] = "backend/app/domains/chat/dependencies.py"
    elif mutation == "asyncio_attribute":
        with (root / delegate).open("a") as stream:
            stream.write("\ndef change():\n    asyncio.run = lambda value: 'sent'\n")
    elif mutation == "asyncio_setattr":
        with (root / delegate).open("a") as stream:
            stream.write("\ndef change():\n    setattr(asyncio, 'run', lambda value: 'sent')\n")
    elif mutation == "asyncio_nested_import":
        with (root / delegate).open("a") as stream:
            stream.write("\ndef change():\n    import fake_asyncio as asyncio\n")
    elif mutation == "module_side_effect":
        with (root / delegate).open("a") as stream:
            stream.write("\nexec('asyncio = None')\n")
    elif mutation == "star_import":
        with (root / delegate).open("a") as stream:
            stream.write("\nfrom fake_asyncio import *\n")
    elif mutation == "retained_package":
        path = (root / next(iter(proof.OLD))).with_suffix("") / "__init__.py"
        path.parent.mkdir(parents=True)
        path.write_text("# a package is the same importable module\n")
    elif mutation == "relative_import":
        (root / "backend/app/consumer.py").write_text("from .compatibility import chat_service\n")
    elif mutation == "exported_uow_stub":
        path = root / "backend/app/runtime/chat/generation_workflows.py"
        tree = ast.parse(path.read_text())
        target = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "SqlAlchemyResponseWorkflowUnitOfWork")
        target.body = [ast.Pass()]
        path.write_text(ast.unparse(tree))
    with pytest.raises(ValueError):
        proof.validate(True, moves, [], root, signed_reader)


@pytest.mark.parametrize("mutation", ["unsigned", "not_ancestor", "wrong_path_blob", "altered_blob"])
def test_retirement_requires_original_signed_source_provenance(candidate, signed_reader, mutation):
    root, moves = candidate

    def reader(*args, root):
        original = signed_reader(*args, root=root)
        if mutation == "unsigned" and args[:3] == ("show", "-s", "--format=%B"):
            return b"unreviewed source\n"
        if mutation == "not_ancestor" and args[0] == "merge-base":
            return b"0" * 40 + b"\n"
        if mutation == "wrong_path_blob" and args[0] == "rev-parse":
            return b"0" * 40 + b"\n"
        if mutation == "altered_blob" and args[:2] == ("cat-file", "blob"):
            return original + b"\nchanged = True\n"
        return original

    with pytest.raises(ValueError):
        proof.validate(True, moves, [], root, reader)


def test_original_node_expectations_cannot_be_substituted(candidate, signed_reader):
    root, moves = candidate
    result = proof.validate(True, moves, [], root, signed_reader)
    path, function = proof.TESTS["delegate"]
    old = signed_reader("show", f"{proof.ANCHOR}:{path}", root=root).decode()
    original = proof.fragments(proof.definition(old, function, ast.FunctionDef))
    with pytest.raises(ValueError, match="reviewed original"):
        proof.required_fragments(["assert True"], old, path, function, path, function, result)
    with pytest.raises(ValueError, match="exact existing test node"):
        proof.required_fragments(original, old, path, function, "backend/tests/other.py", function, result)
    assert proof.required_fragments(original, old, "backend/tests/other.py", function, path, function, result) == original


def test_retirement_flag_cannot_be_a_truthy_configuration(candidate, signed_reader):
    root, moves = candidate
    assert proof.validate(False, moves, [], root, signed_reader) is None
    with pytest.raises(ValueError, match="exact reviewed boolean"):
        proof.validate("approved", moves, [], root, signed_reader)
