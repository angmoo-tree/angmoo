from __future__ import annotations

import ast
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[1]
APP_ROOT = BACKEND_ROOT / "app"
PUBLIC_RUNTIME_FILES = (
    APP_ROOT / "api" / "v1" / "routes" / "agent_runs.py",
    APP_ROOT / "api" / "v1" / "routes" / "agents.py",
    APP_ROOT / "services" / "agent_creation_drafts.py",
    APP_ROOT / "services" / "agent_runs.py",
    APP_ROOT / "services" / "agent_writing.py",
    APP_ROOT / "services" / "agents.py",
    APP_ROOT / "services" / "auth.py",
    APP_ROOT / "services" / "langgraph_resident.py",
    APP_ROOT / "services" / "resident_contracts.py",
)


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
    return imported


def test_public_langgraph_entrypoint_has_no_openclaw_or_provider_sdk_imports():
    imports = _imports(APP_ROOT / "services" / "langgraph_resident.py")

    assert not {name for name in imports if "openclaw" in name.lower()}
    assert not {name for name in imports if name == "google" or name.startswith("google.")}


def test_public_runtime_modules_do_not_import_private_openclaw_modules():
    violations: dict[str, list[str]] = {}
    for path in PUBLIC_RUNTIME_FILES:
        private_imports = sorted(
            name for name in _imports(path) if "openclaw" in name.lower()
        )
        if private_imports:
            violations[str(path.relative_to(APP_ROOT))] = private_imports

    assert violations == {}


def test_public_runtime_modules_do_not_import_subprocess_launchers():
    violations: dict[str, list[str]] = {}
    for path in PUBLIC_RUNTIME_FILES:
        launcher_imports = sorted(
            name
            for name in _imports(path)
            if name == "subprocess"
            or name.startswith("subprocess.")
            or name == "asyncio.subprocess"
        )
        if launcher_imports:
            violations[str(path.relative_to(APP_ROOT))] = launcher_imports

    assert violations == {}


def test_crud_modules_do_not_import_services():
    violations: dict[str, list[str]] = {}
    for path in sorted((APP_ROOT / "cruds").glob("*.py")):
        service_imports = sorted(
            name for name in _imports(path) if name == "app.services" or name.startswith("app.services.")
        )
        if service_imports:
            violations[path.name] = service_imports

    assert violations == {}


def test_provider_sdk_imports_are_confined_to_provider_adapters_and_oauth():
    allowed = {
        "providers/gemini.py",
        "services/auth.py",
    }
    violations: dict[str, list[str]] = {}
    for path in sorted(APP_ROOT.rglob("*.py")):
        google_imports = sorted(
            name
            for name in _imports(path)
            if name == "google" or name.startswith("google.")
        )
        relative = path.relative_to(APP_ROOT).as_posix()
        if google_imports and relative not in allowed:
            violations[relative] = google_imports

    assert violations == {}


def test_secret_decryption_is_confined_to_credential_resolver():
    allowed = {
        "core/security.py",
        "core/startup_security.py",
        "credentials/resolver.py",
    }
    violations: list[str] = []
    for path in sorted(APP_ROOT.rglob("*.py")):
        relative = path.relative_to(APP_ROOT).as_posix()
        if relative in allowed:
            continue
        if "decrypt_secret(" in path.read_text(encoding="utf-8"):
            violations.append(relative)

    assert violations == []


def test_plaintext_credential_reveal_calls_are_explicitly_allowlisted():
    allowed: dict[str, set[str]] = {
        "services/agent_creation_drafts.py": {"_decrypt_draft_api_key"},
        "services/agent_runs.py": {"_ensure_slot_auth_profile"},
        "services/agents.py": {
            "run_first_greeting",
            "analyze_tendency",
            "_bind_slot_auth_profile",
        },
        "services/character_lore.py": {
            "_google_embedding_credential_for_character",
            "_google_api_key_for_character",
        },
        "services/langgraph_resident.py": {"_decrypt_api_key"},
        "services/messages.py": {"_resolve_message_credential"},
        "services/post_image_generation.py": {
            "_ensure_visual_identity",
            "_refine_image_prompt",
            "_image_key_for_source",
        },
        "services/service_image_key.py": {
            "get_service_image_api_key",
            "get_replicate_image_api_key",
            "get_profile_image_api_key",
        },
        "services/world_character_provider.py": {
            "generate_community_profile",
            "generate_repertoire",
        },
    }
    observed: dict[str, set[str]] = {}

    for path in sorted(APP_ROOT.rglob("*.py")):
        relative = path.relative_to(APP_ROOT).as_posix()
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        function_stack: list[str] = []

        class RevealVisitor(ast.NodeVisitor):
            def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
                function_stack.append(node.name)
                self.generic_visit(node)
                function_stack.pop()

            def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
                function_stack.append(node.name)
                self.generic_visit(node)
                function_stack.pop()

            def visit_Call(self, node: ast.Call) -> None:
                if isinstance(node.func, ast.Attribute) and node.func.attr == "reveal":
                    observed.setdefault(relative, set()).add(
                        function_stack[-1] if function_stack else "<module>"
                    )
                self.generic_visit(node)

        RevealVisitor().visit(tree)

    assert observed == allowed


def test_public_read_schemas_do_not_expose_secret_storage_fields():
    forbidden = {"encrypted_api_key", "ciphertext", "raw_key", "api_key"}
    violations: dict[str, list[str]] = {}
    for path in sorted((APP_ROOT / "schemas").glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in tree.body:
            if not isinstance(node, ast.ClassDef) or not node.name.endswith("Read"):
                continue
            fields = {
                child.target.id
                for child in node.body
                if isinstance(child, ast.AnnAssign)
                and isinstance(child.target, ast.Name)
            }
            exposed = sorted(fields & forbidden)
            if exposed:
                violations[f"{path.name}:{node.name}"] = exposed

    assert violations == {}
