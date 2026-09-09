"""A retired import path cannot replace its original object/behavior contract."""
from __future__ import annotations

import ast
import sys
from types import MethodType

import pytest

from compatibility_retirement_support import proof


@pytest.fixture(scope="module")
def evidence():
    return proof.History()


def test_all_original_explicit_exports_resolve_to_actual_owners(evidence):
    exports = evidence.validate_sources()
    assert set(exports) == set(proof.MODULES)
    assert sum(len(values) for values in exports.values()) == 802
    public = [name for name in exports if name.endswith(".public")]
    assert sum(len(exports[name]) for name in public) == 165
    for module, values in exports.items():
        assert values
        for name in values:
            if evidence.binding_removed(module, name):
                # Exact committed product deletion is checked separately from
                # unchanged refactor exports; never fabricate a substitute.
                continue
            # Resolves the real modules only; it never imports a retired name.
            actual = evidence.actual(module, name)
            assert proof.same_object(actual, evidence.actual(module, name))
    assert not set(proof.MODULES).intersection(sys.modules)


@pytest.mark.parametrize("suffix", [".py", "/__init__.py", "/nested/consumer.py"])
def test_retired_file_or_package_cannot_be_reintroduced(tmp_path, suffix):
    module = "app.services.messages"
    target = tmp_path / ("backend/" + module.replace(".", "/") + suffix)
    target.parent.mkdir(parents=True)
    target.write_text("# Even an empty compatibility placeholder is forbidden.\n")
    evidence = object.__new__(proof.History)
    evidence.root = tmp_path
    with pytest.raises(ValueError, match="still exists"):
        evidence.absent(module)


@pytest.mark.parametrize("addition", [
    "def forwarded(*args):\n    return _implementation.send_message(*args)\n",
    "_implementation = object()\n",
    "_implementation.send_message = lambda: None\n",
    "from app.domains.chat.service.messages import *\n",
    "print('an import side effect is implementation')\n",
])
def test_historical_module_alias_rejects_implementation_or_rebinding(evidence, addition):
    module = "app.services.messages"
    candidate = object.__new__(proof.History)
    candidate.tree = lambda name: ast.parse(evidence.source(module) + addition)
    with pytest.raises(ValueError):
        candidate.bindings(module)


def test_all_is_not_permission_to_drop_unadvertised_exports(evidence):
    module = "app.domains.routines.public"
    names = evidence.exports(module)
    advertised = next(ast.literal_eval(n.value) for n in evidence.tree(module).body
                      if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "__all__" for t in n.targets))
    unadvertised = set(names) - set(advertised)
    assert unadvertised
    for name in unadvertised:
        assert evidence.actual(module, name) is not None


@pytest.mark.parametrize("path,function,old,new", [
    ("backend/tests/world_characters/test_readiness_contract.py",
     "test_readiness_keeps_shared_dto_and_world_scope_before_stale_profile",
     "assert writes == []", "assert True"),
    ("backend/tests/media/test_world_banner_codec.py",
     "test_world_banner_uses_shared_sanitized_bytes_and_legacy_exception_contract",
     "match='Invalid image payload'", "match='.*'"),
    ("backend/tests/world_characters/test_foundation_identity.py",
     "test_provider_compatibility_keeps_monkeypatch_target_and_accounting_types",
     "monkeypatch.setattr(_actual_domains_world_characters_client, 'DirectLlmWorldCharacterSetupProvider', sentinel)",
     "monkeypatch.setattr(_actual_domains_world_characters_client, 'DirectLlmWorldCharacterSetupProvider', original)"),
    ("backend/tests/identity/test_l1_identity_domain_foundation.py",
     "test_identity_model_table_contracts_are_unchanged",
     "'password_hash',", ""),
    ("backend/tests/routines/test_guarded_claim_recovery.py",
     "test_guarded_recovery_uses_consumption_owner_and_preserves_admission",
     "match='owner_controlled_automation_disabled'", "match='.*'"),
])
def test_retirement_rejects_changed_business_fixture_and_provider_behavior(evidence, path, function, old, new):
    source = (proof.ROOT / path).read_text(encoding="utf-8")
    assert old in source
    proof.validate_test_function(evidence, path, function, source)
    with pytest.raises(ValueError, match="changed behavior"):
        proof.validate_test_function(evidence, path, function, source.replace(old, new, 1))


@pytest.mark.parametrize("change", [
    "drop", "true", "self", "wrong-import", "shadow", "conditional-import",
    "mutate-code", "setattr-code", "except-binding", "match-binding", "star-import",
    "class-global-import", "class-mutation", "decorator-mutation", "default-mutation",
])
def test_exact_original_identity_edges_cannot_be_dropped_or_faked(evidence, change):
    path = "backend/tests/media/test_media_storage_boundaries.py"
    function = "test_compatibility_exports_use_owner_implementations_and_same_error_classes"
    source = (proof.ROOT / path).read_text(encoding="utf-8")
    tree = ast.parse(source)
    target = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == function)
    if change == "drop":
        target.body.pop()
    elif change == "true":
        target.body[0] = ast.parse("assert True").body[0]
    elif change == "self":
        target.body[0] = ast.parse("assert character_media.save_profile_media is character_media.save_profile_media").body[0]
    elif change == "wrong-import":
        next(n for n in tree.body if isinstance(n, ast.ImportFrom) and n.module == "compatibility_retirement_support").module = "fake_retirement"
    elif change == "shadow":
        tree.body.append(ast.parse("export_matches = lambda *args: True").body[0])
    else:
        injection = {
            "conditional-import": "if True:\n    from fake_retirement import export_matches",
            "mutate-code": "export_matches.__code__ = (lambda *args: True).__code__",
            "setattr-code": "setattr(export_matches, '__code__', (lambda *args: True).__code__)",
            "except-binding": "try:\n    pass\nexcept Exception as export_matches:\n    pass",
            "match-binding": "match object():\n    case export_matches:\n        pass",
            "star-import": "from fake_retirement import *",
            "class-global-import": "class Mutator:\n    global export_matches\n    from fake_retirement import export_matches",
            "class-mutation": "class Mutator:\n    export_matches.__code__ = (lambda *args: True).__code__",
            "decorator-mutation": "@setattr(export_matches, '__code__', (lambda *args: True).__code__)\ndef fake():\n    pass",
            "default-mutation": "def fake(value=setattr(export_matches, '__code__', (lambda *args: True).__code__)):\n    pass",
        }[change]
        tree.body.extend(ast.parse(injection).body)
    with pytest.raises(ValueError):
        proof.validate_test_function(evidence, path, function, ast.unparse(tree))


def test_bound_method_requires_original_receiver_and_original_function():
    class Owner:
        def run(self):
            return "original"

    first, second = Owner(), Owner()
    assert first.run is not first.run
    assert proof.same_object(first.run, first.run)
    assert not proof.same_object(first.run, second.run)
    assert not proof.same_object(first.run, MethodType(lambda self: "original", first))
    assert not proof.same_object(first.run, Owner.run)


def test_real_chat_aggregate_alias_keeps_composed_receiver_and_function():
    from app.runtime.chat.message_composition import message_service
    from app.domains.chat.service.messages import MessageService

    assert proof.export_matches("app.services.messages", "send_message", message_service.send_message)
    assert proof.export_matches("app.runtime.chat.sqlalchemy_service", "send_message", message_service.send_message)
    assert not proof.export_matches("app.services.messages", "send_message", MessageService.send_message)
    assert not proof.export_matches("app.services.messages", "send_message", lambda: None)
    assert proof.alias_retired("app.services.messages", "app.runtime.chat.sqlalchemy_service")


def test_real_schema_binding_rejects_equal_looking_different_class():
    from app.domains.identity.schemas import LoginCreate

    class CopiedLoginCreate(LoginCreate):
        pass

    assert proof.export_matches("app.schemas.auth", "LoginCreate", LoginCreate)
    assert not proof.export_matches("app.schemas.auth", "LoginCreate", CopiedLoginCreate)


@pytest.mark.parametrize("source", [
    "from app.schemas import LoginCreate\n",
    "from app import schemas\n",
    "import app.domains.worlds.public\n",
    "import importlib\nvalue = importlib.import_module('app.services.messages')\n",
    "import importlib\nimportlib.import_module('app.schemas')\n",
    "module = 'app.services.' + 'messages'\n__import__(module)\n",
    "from importlib import import_module as load\nload('app.schemas.auth')\n",
    "from builtins import __import__ as load\nload('app.services.messages')\n",
    "from app.schemas.unlisted_child import Value\n",
    "import app.schemas.unlisted_child\n",
    "from app.schemas import unlisted_child\n",
])
def test_actual_consumer_cannot_keep_using_retired_path(tmp_path, source):
    path = tmp_path / "backend/app/consumer.py"
    path.parent.mkdir(parents=True)
    path.write_text(source)
    with pytest.raises(ValueError, match="consumer|dynamic import"):
        proof.active_consumers(tmp_path)


@pytest.mark.parametrize("path,source", [
    ("backend/app/consumer.py", "from . import schemas\n"),
    ("backend/app/runtime/consumer.py", "from ..services import messages\n"),
])
def test_relative_import_does_not_hide_retired_application_consumer(tmp_path, path, source):
    target=tmp_path/path
    target.parent.mkdir(parents=True)
    target.write_text(source)
    with pytest.raises(ValueError, match="consumer"):
        proof.active_consumers(tmp_path)


@pytest.mark.parametrize("extra", [
    "Actual = object()",
    "from another import Actual",
    "if True:\n    Actual = object()",
    "from another import *",
    "try:\n    pass\nexcept Exception as Actual:\n    pass",
    "match object():\n    case Actual:\n        pass",
])
def test_actual_owner_export_cannot_be_rebound_after_its_definition(extra):
    original = "class Actual:\n    pass\n"
    assert isinstance(proof.terminal_definition(original, "Actual"), ast.ClassDef)
    with pytest.raises(ValueError):
        proof.terminal_definition(original + extra, "Actual")


def test_every_original_function_matches_exact_binding_only_transformation(evidence):
    for path, functions in proof.TESTS.items():
        source = (proof.ROOT / path).read_text(encoding="utf-8")
        for function in functions:
            proof.validate_test_function(evidence, path, function, source)
