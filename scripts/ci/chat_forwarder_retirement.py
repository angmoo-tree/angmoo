"""Exact retirement proof for the three historical Chat forwarding classes.

The old layers only called the already-existing owner services/repository. This
proof validates those original bodies and preserves actual owner behavior tests;
it cannot approve a generic deleted class, proxy, or weakened assertion.
"""
from __future__ import annotations

import ast
from collections import Counter
import hashlib
import importlib.util
from pathlib import Path


ANCHOR = "fd312e6a55d264f4ef704ee866f6819322119858"
OLD = {
    "backend/app/compatibility/chat_service.py": "1c76bce094d542c22b7d6a49fbb8ba88923f1018",
    "backend/app/compatibility/chat_runtime_contract.py": "8c8ba2de74fa783322f73c03db5aa726a3eda8dd",
    "backend/app/compatibility/chat_generation_lifecycle.py": "16349e33da9ecf43d72f09ceac80bcc336184e1d",
    "backend/app/runtime/chat/world_generation.py": "dc3a4ba58771ab9f01694c6150ff9a7256d92a84",
}
ROUTE_FACADES = {
    "backend/app/api/v1/routes/messages.py": "434f364dd808e5b9aa4eb3ff762c0a1c9e360182",
    "backend/app/api/v1/routes/world_chat.py": "d4b661fbfb8197f73c6ba741846c1e9da08287a3",
    "backend/app/api/v1/routes/world_chat_response.py": "b396dacec9f442d13f360952424ad8ee22b50a03",
}
TARGETS = {
    "backend/app/compatibility/chat_service.py": "backend/app/domains/chat/service/threads.py",
    "backend/app/compatibility/chat_runtime_contract.py": "backend/app/domains/chat/dependencies.py",
    "backend/app/compatibility/chat_generation_lifecycle.py": "backend/app/domains/chat/repository/response_lifecycle.py",
    "backend/app/runtime/chat/world_generation.py": "backend/app/domains/chat/service/generation.py",
}
ORIGINAL_PATHS = {
    "backend/app/compatibility/chat_service.py": "backend/app/domains/chat/application/messages.py",
    "backend/app/compatibility/chat_runtime_contract.py": "backend/app/domains/chat/ports/runtime.py",
    "backend/app/compatibility/chat_generation_lifecycle.py": "backend/app/domains/chat/application/generation_lifecycle.py",
    "backend/app/runtime/chat/world_generation.py": "backend/app/runtime/chat/world_generation.py",
}
TESTS = {
    "delegate": ("backend/tests/chat/test_p8_l_b_chat_domain.py", "test_application_service_delegates_through_runtime_port"),
    "owner": ("backend/tests/chat/test_response_lifecycle_owner.py", "test_http_generation_accept_and_replay_use_the_durable_owner"),
    "routes": ("backend/tests/chat/test_service_ownership.py", "test_routes_call_actual_owner_services_without_runtime_port_chain"),
}
DELEGATE_AST = "f3bd4311e82ac1b2dbd8d5469c75809910f4d06b73e42a9c2bbea4657d9f7cd1"
SERVICE_OWNERS = {
    "get_world_chat_entry": "threads", "list_world_threads": "threads",
    "get_world_thread": "threads", "create_or_get_world_thread": "threads",
    "update_world_thread_model": "threads", "accept_world_message": "generation",
    "retry_world_response": "generation", "get_world_response_request": "generation",
    "get_latest_world_response_request": "generation", "get_world_response_evidence": "evidence",
    "stream_world_response": "generation", "list_threads": "threads", "get_thread": "threads",
    "create_or_get_thread": "threads", "update_thread": "threads", "delete_thread": "threads",
    "send_message": "messages", "retry_message": "messages", "get_user_settings": "settings",
    "update_user_settings": "settings", "get_character_message_settings": "settings",
    "update_character_message_settings": "settings",
}
OWNER_CLASSES = {"threads": "ThreadService", "messages": "MessageService", "settings": "MessageSettingsService",
                 "generation": "GenerationService", "evidence": "EvidenceService"}
LIFECYCLE = {
    "accept": "create_request", "acquire_lease": "acquire_lease", "renew_lease": "renew_lease",
    "request_cancel": "request_cancel", "recover_expired_requests": "recover_expired_requests",
    "transition": "transition", "accept_event": "accept_event", "mark_terminal": "mark_terminal",
    "finalize": "finalize_response",
}
GENERATION_EXPORTS = {
    "RESPONSE_REQUEST_DEADLINE_SECONDS": ("backend/app/domains/chat/service/generation.py", "RESPONSE_REQUEST_DEADLINE_SECONDS"),
    "SqlAlchemyResponseWorkflowUnitOfWork": ("backend/app/runtime/chat/generation_workflows.py", "SqlAlchemyResponseWorkflowUnitOfWork"),
    **{name: ("backend/app/domains/chat/service/generation.py", "GenerationService") for name in (
        "accept_world_message", "get_latest_world_response_request", "get_world_response_request",
        "retry_world_response", "stream_world_response",
    )},
}


def dump(node):
    return ast.dump(node, include_attributes=False)


def fragments(node):
    result = []
    for child in ast.walk(node):
        if isinstance(child, ast.Assert):
            result.append(ast.unparse(child))
        elif isinstance(child, (ast.With, ast.AsyncWith)):
            for item in child.items:
                call = item.context_expr
                if isinstance(call, ast.Call) and isinstance(call.func, ast.Attribute) and call.func.attr in {"raises", "warns"}:
                    result.append(ast.unparse(call))
    return result


def definition(source, name, kind):
    matches = [n for n in ast.parse(source).body if isinstance(n, kind) and n.name == name]
    if len(matches) != 1:
        raise ValueError("Chat retirement requires one exact definition: " + name)
    return matches[0]


def meaningful_body(node):
    return [n for n in node.body if not (isinstance(n, ast.Expr) and isinstance(n.value, ast.Constant) and isinstance(n.value.value, str))]


def class_methods(source, name):
    cls = definition(source, name, ast.ClassDef)
    methods = {n.name: n for n in cls.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
    if len(methods) != sum(isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) for n in cls.body):
        raise ValueError("Chat retirement rejects duplicate methods")
    return methods


def verify_forwarder(source, name, attribute, parameter, targets):
    methods = class_methods(source, name)
    if set(methods) != {"__init__", *targets}:
        raise ValueError("Chat retirement unexpected forwarding surface")
    init = meaningful_body(methods["__init__"])
    expected = ast.parse(f"self.{attribute} = {parameter}").body
    if dump(ast.Module(body=init, type_ignores=[])) != dump(ast.Module(body=expected, type_ignores=[])):
        raise ValueError("Chat retirement constructor has behavior")
    for method, target in targets.items():
        node = methods[method]
        body = meaningful_body(node)
        if len(body) != 1 or not isinstance(body[0], (ast.Return, ast.Expr)):
            raise ValueError("Chat retirement method contains policy or side effects")
        call = body[0].value
        if isinstance(node, ast.AsyncFunctionDef):
            if not isinstance(call, ast.Await):
                raise ValueError("Chat retirement async forwarding lost await")
            call = call.value
        if not isinstance(call, ast.Call) or dump(call.func) != dump(ast.parse(f"self.{attribute}.{target}", mode="eval").body):
            raise ValueError("Chat retirement forwarding target changed")
        args = [a.arg for a in node.args.args][1:]
        kwargs = [a.arg for a in node.args.kwonlyargs]
        if [dump(a) for a in call.args] != [dump(ast.Name(id=a, ctx=ast.Load())) for a in args]:
            raise ValueError("Chat retirement forwarding arguments changed")
        if [(k.arg, dump(k.value)) for k in call.keywords] != [(a, dump(ast.Name(id=a, ctx=ast.Load()))) for a in kwargs]:
            raise ValueError("Chat retirement forwarding keywords changed")
    return methods


def protected_import(source, local, module, symbol=None):
    tree = ast.parse(source)
    found = 0
    total = 0
    for node in tree.body:
        if not isinstance(node, (ast.Import, ast.ImportFrom, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and not (isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str)):
            raise ValueError("Chat retirement test module contains executable binding changes")
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            total += sum((a.asname or (a.name.split('.')[0] if isinstance(node, ast.Import) else a.name)) == local for a in node.names)
        if isinstance(node, ast.Import) and symbol is None:
            found += sum(a.name == module and (a.asname or a.name.split('.')[0]) == local for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module == module:
            found += sum(a.name == symbol and (a.asname or a.name) == local for a in node.names)
        elif isinstance(node, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
            raise ValueError("Chat retirement test imports may not be rebound at module scope")
    if found != 1 or total != 1:
        raise ValueError("Chat retirement actual import missing or duplicated: " + local)
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and any(a.name == "*" for a in node.names):
            raise ValueError("Chat retirement rejects star import binding ambiguity")
        if isinstance(node, (ast.Import, ast.ImportFrom)) and node not in tree.body and any((a.asname or (a.name.split('.')[0] if isinstance(node, ast.Import) else a.name)) == local for a in node.names):
            raise ValueError("Chat retirement import shadowed in a nested scope")
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and node.name == local:
            raise ValueError("Chat retirement import shadowed by a definition")
        if isinstance(node, ast.Name) and isinstance(node.ctx, (ast.Store, ast.Del)) and node.id == local:
            raise ValueError("Chat retirement import shadowed by assignment")
        if isinstance(node, ast.arg) and node.arg == local:
            raise ValueError("Chat retirement import shadowed by an argument")
        if isinstance(node, ast.Attribute) and isinstance(node.ctx, (ast.Store, ast.Del)):
            base = node.value
            while isinstance(base, ast.Attribute):
                base = base.value
            if isinstance(base, ast.Name) and base.id == local:
                raise ValueError("Chat retirement imported binding attribute changed")
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in {"setattr", "delattr"} and node.args and isinstance(node.args[0], ast.Name) and node.args[0].id == local:
            raise ValueError("Chat retirement imported binding mutated dynamically")


def validate(enabled, file_moves, snapshots, root: Path, git_bytes):
    if enabled is False or enabled is None:
        return None
    if enabled is not True:
        raise ValueError("Chat forwarding retirement must be the exact reviewed boolean")
    spec = importlib.util.spec_from_file_location("product_changes", Path(__file__).with_name("post_refactor_contract_changes.py"))
    changes = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(changes)
    records = changes.load(root)

    def matches(path, symbol, original, actual):
        return changes.definition_matches(root, path, symbol, original, actual, records=records)
    if git_bytes("merge-base", ANCHOR, "HEAD", root=root).decode().strip() != ANCHOR:
        raise ValueError("Chat forwarding proof source must be an ancestor")
    if "Signed-off-by:" not in git_bytes("show", "-s", "--format=%B", ANCHOR, root=root).decode():
        raise ValueError("Chat forwarding proof source must be signed")

    def before(path):
        return git_bytes("show", f"{ANCHOR}:{path}", root=root).decode("utf-8-sig")

    old_sources = {}
    for path, expected_blob in OLD.items():
        if git_bytes("rev-parse", f"{ANCHOR}:{path}", root=root).decode().strip() != expected_blob:
            raise ValueError("Chat forwarding proof anchor path drift")
        raw = git_bytes("cat-file", "blob", expected_blob, root=root)
        if hashlib.sha1(f"blob {len(raw)}\0".encode() + raw).hexdigest() != expected_blob:
            raise ValueError("Chat forwarding source blob drift")
        if (root / path).exists() or (root / path).with_suffix("").exists():
            raise ValueError("Chat forwarding file was retained or recreated: " + path)
        # The compatibility names were intermediate renames of these protected
        # original sources, not independent new implementations or checkpoints.
        target = file_moves.get(ORIGINAL_PATHS[path])
        if target != TARGETS[path] or not (root / target).is_file() or not (root / target).resolve().is_relative_to(root.resolve()):
            raise ValueError("Chat forwarding disposition is absent or unsafe")
        old_sources[path] = raw.decode("utf-8-sig")
    verify_forwarder(old_sources["backend/app/compatibility/chat_service.py"], "ChatService", "_runtime", "runtime", {name: name for name in SERVICE_OWNERS})
    verify_forwarder(old_sources["backend/app/compatibility/chat_generation_lifecycle.py"], "GenerationLifecycleService", "_repository", "repository", LIFECYCLE)
    protocol = class_methods(old_sources["backend/app/compatibility/chat_runtime_contract.py"], "ChatRuntimePort")
    if set(protocol) != set(SERVICE_OWNERS) or any(len(meaningful_body(n)) != 1 or not isinstance(meaningful_body(n)[0], ast.Expr) or not isinstance(meaningful_body(n)[0].value, ast.Constant) or meaningful_body(n)[0].value.value is not Ellipsis for n in protocol.values()):
        raise ValueError("Chat runtime protocol contained implementation")
    aggregate = ast.parse(old_sources["backend/app/runtime/chat/world_generation.py"])
    if any(not isinstance(n, (ast.Import, ast.ImportFrom, ast.Assign, ast.Expr)) for n in aggregate.body):
        raise ValueError("World generation aggregate contained actual implementation")
    for n in aggregate.body:
        if isinstance(n, ast.Assign) and not (isinstance(n.value, (ast.Attribute, ast.List))):
            raise ValueError("World generation aggregate computed an export")
    exported = [n for n in aggregate.body if isinstance(n, ast.Assign) and len(n.targets) == 1 and isinstance(n.targets[0], ast.Name) and n.targets[0].id == "__all__"]
    if len(exported) != 1 or set(ast.literal_eval(exported[0].value)) != set(GENERATION_EXPORTS):
        raise ValueError("World generation historical advertised surface changed")
    for path, name in set(GENERATION_EXPORTS.values()):
        def owned(source):
            return [n for n in ast.parse(source).body if (isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and n.name == name) or (isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == name for t in n.targets))]
        original, actual = owned(before(path)), owned((root / path).read_text(encoding="utf-8-sig"))
        if len(original) != 1 or len(actual) != 1 or not matches(TARGETS["backend/app/runtime/chat/world_generation.py"], name, original[0], actual[0]):
            raise ValueError("World generation advertised owner changed: " + name)
    # Existing owner bodies must still execute their original logic. Import-only
    # edits are permitted; stubs or copies of the retired forwarding class are not.
    for role, cls in OWNER_CLASSES.items():
        path = f"backend/app/domains/chat/service/{role}.py"
        old, current = class_methods(before(path), cls), class_methods((root / path).read_text(encoding="utf-8-sig"), cls)
        for name, owner in SERVICE_OWNERS.items():
            if owner == role and (name not in current or not matches(path, cls + "." + name, old[name], current[name])):
                raise ValueError("Chat actual owner method changed: " + name)
    repository = "backend/app/domains/chat/repository/response_lifecycle.py"
    old, current = class_methods(before(repository), "SqlAlchemyResponseLifecycleRepository"), class_methods((root / repository).read_text(encoding="utf-8-sig"), "SqlAlchemyResponseLifecycleRepository")
    for name in LIFECYCLE.values():
        if name not in current or not matches(repository, "SqlAlchemyResponseLifecycleRepository." + name, old[name], current[name]):
            raise ValueError("Chat durable command changed: " + name)
    composition = "backend/app/runtime/chat/message_composition.py"
    expected_composition = ast.parse(before(composition))
    # B6 already replaced the Runtime re-export with this same Social query.
    # Prove the signed re-export and the entire actual query module before
    # allowing precisely that one import change; construction stays exact.
    block_query = "world_character_pair_is_blocked"
    block_module = "app.domains.social.repository.blocks"
    old_block_module = "app.runtime.relationships.sqlalchemy_social_event"
    protected_import(before("backend/app/runtime/relationships/sqlalchemy_social_event.py"), block_query, block_module, block_query)
    block_path = "backend/app/domains/social/repository/blocks.py"
    if dump(ast.parse(before(block_path))) != dump(ast.parse((root / block_path).read_text(encoding="utf-8-sig"))):
        raise ValueError("Chat original Social block query changed")
    imports = [n for n in expected_composition.body if isinstance(n, ast.ImportFrom) and n.module == old_block_module and [(a.name, a.asname) for a in n.names] == [(block_query, None)]]
    if len(imports) != 1:
        raise ValueError("Chat historical Social block query import changed")
    imports[0].module = block_module
    if dump(expected_composition) != dump(ast.parse((root / composition).read_text(encoding="utf-8-sig"))):
        raise ValueError("Chat actual service construction changed")
    # These three original route files only imported the actual HTTP endpoints
    # and the service instances whose construction was proved above. Retire the
    # import surface only after proving the complete original HTTP/DI modules;
    # the replacement test uses their real Request dependency getters.
    for route, expected_blob in ROUTE_FACADES.items():
        if git_bytes("rev-parse", f"{ANCHOR}:{route}", root=root).decode().strip() != expected_blob:
            raise ValueError("Chat route facade anchor path drift")
        raw = git_bytes("cat-file", "blob", expected_blob, root=root)
        if hashlib.sha1(f"blob {len(raw)}\0".encode() + raw).hexdigest() != expected_blob:
            raise ValueError("Chat route facade original blob drift")
        if (root / route).exists() or (root / route).with_suffix("").exists():
            raise ValueError("Chat route facade was retained or recreated")
        actual_route = route.replace("/api/v1/routes/", "/domains/chat/router/")
        if file_moves.get(route) != actual_route or not (root / actual_route).is_file():
            raise ValueError("Chat route facade requires its exact actual HTTP disposition")
        actual_module = actual_route.removeprefix("backend/").removesuffix(".py").replace("/", ".")
        for node in meaningful_body(ast.parse(raw.decode("utf-8-sig"))):
            if not isinstance(node, ast.ImportFrom) or node.level or any(a.name == "*" for a in node.names):
                raise ValueError("Chat historical route facade contained implementation")
            if node.module not in {actual_module, "app.runtime.chat.message_composition"}:
                # This one original export was already retired with the exact
                # world_generation forwarding proof above; no other alias is allowed.
                if not (route.endswith("/world_chat_response.py") and node.module == "app.runtime.chat" and [(a.name, a.asname) for a in node.names] == [("world_generation", "chat_service")]):
                    raise ValueError("Chat historical route facade binding changed")
        if dump(ast.parse(before(actual_route))) != dump(ast.parse((root / actual_route).read_text(encoding="utf-8-sig"))):
            raise ValueError("Chat actual HTTP endpoint or dependency binding changed")
    dependency = "backend/app/domains/chat/dependencies.py"
    if dump(ast.parse(before(dependency))) != dump(ast.parse((root / dependency).read_text(encoding="utf-8-sig"))):
        raise ValueError("Chat actual Request dependency control or binding changed")
    forbidden = {path.removeprefix("backend/").removesuffix(".py").replace("/", ".") for path in (*OLD, *ROUTE_FACADES)}
    for directory in (root / "backend/app", root / "backend/tests", root / "backend/scripts", root / "scripts"):
        for path in directory.rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8-sig"))
            for n in ast.walk(tree):
                if isinstance(n, ast.Import) and any(a.name in forbidden for a in n.names):
                    raise ValueError("Chat retired module still imported: " + path.as_posix())
                if isinstance(n, ast.ImportFrom):
                    module = n.module or ""
                    if n.level:
                        parts = path.relative_to(root).as_posix().removeprefix("backend/").split("/")[:-1]
                        base = parts[:len(parts) - n.level + 1]
                        module = ".".join([*base, *([module] if module else [])])
                    if module in forbidden or any(module + "." + a.name in forbidden for a in n.names):
                        raise ValueError("Chat retired module still imported: " + path.as_posix())
                if isinstance(n, ast.ClassDef) and n.name in {"ChatService", "ChatRuntimePort", "GenerationLifecycleService"}:
                    raise ValueError("Chat forwarding class was copied or recreated")
                if isinstance(n, ast.Call) and any(isinstance(a, ast.Constant) and a.value in forbidden for a in n.args if isinstance(a, ast.Constant) and isinstance(a.value, str)):
                    raise ValueError("Chat retired module loaded dynamically")
    result = {}
    for key, (path, function) in TESTS.items():
        old_source, source = before(path), (root / path).read_text(encoding="utf-8-sig")
        frozen = definition(old_source, function, ast.FunctionDef)
        actual = definition(source, function, ast.FunctionDef)
        if key == "delegate":
            protected_import(source, "asyncio", "asyncio")
            protected_import(source, "policies", "app.domains.chat", "policies")
            if hashlib.sha256(dump(actual).encode()).hexdigest() != DELEGATE_AST:
                raise ValueError("Chat actual owner spy/arguments/results/finalization test changed")
        elif key == "owner":
            protected_import(source, "Path", "pathlib", "Path")
            protected_import(source, "generation_service", "app.runtime.chat.message_composition", "generation_service")
            protected_import(source, "GenerationService", "app.domains.chat.service.generation", "GenerationService")
            if any((isinstance(n, ast.Name) and isinstance(n.ctx, (ast.Store, ast.Del)) and n.id == "__file__") or (isinstance(n, ast.alias) and (n.asname or n.name) == "__file__") for n in ast.walk(ast.parse(source))):
                raise ValueError("Chat retirement absence path was shadowed")
            expected = ast.parse(ast.unparse(frozen)).body[0]
            # Only the old constructor tripwire is replaced by absence and the
            # concrete owner check; the same SQLite/replay transaction remains.
            expected.body = expected.body[2:]
            expected = ast.parse(ast.unparse(expected).replace("world_generation.accept_world_message", "generation_service.accept_world_message")).body[0]
            expected.body[:0] = ast.parse("backend = Path(__file__).resolve().parents[2]\nassert not (backend / 'app/compatibility/chat_generation_lifecycle.py').exists()\nassert type(generation_service) is GenerationService").body
            if dump(actual) != dump(expected):
                raise ValueError("Chat durable owner retirement weakened the existing transaction test")
        else:
            for role in ("threads", "settings", "messages"):
                protected_import(source, OWNER_CLASSES[role], "app.domains.chat.service." + role, OWNER_CLASSES[role])
            expected = ast.parse(ast.unparse(frozen)).body[0]
            expected = ast.parse(ast.unparse(expected).replace("from app.runtime.chat import message_composition, world_generation", "from app.runtime.chat import message_composition\n    from app.domains.chat.service.generation import GenerationService").replace("assert world_chat_response.chat_service is world_generation", "assert world_chat_response.generation_service is message_composition.generation_service\n    assert world_chat_response.evidence_service is message_composition.evidence_service\n    assert type(world_chat_response.generation_service) is GenerationService")).body[0]
            # Preserve all six instance-identity and four concrete-type checks.
            # Only the removed module attributes become the exact real getters
            # on the unchanged canonical HTTP modules, configured by production.
            expected = ast.parse(ast.unparse(expected).replace("from app.api.v1.routes import messages, world_chat, world_chat_response", "from fastapi import FastAPI, Request\n    from app.domains.chat.router import messages, world_chat, world_chat_response")).body[0]
            expected.body[4:4] = ast.parse("app = FastAPI()\nmessage_composition.configure_chat_services(app)\nrequest = Request({'type': 'http', 'app': app})").body
            getters = {
                ("messages", "thread_service"): "get_thread_service",
                ("messages", "settings_service"): "get_settings_service",
                ("messages", "message_service"): "get_message_service",
                ("world_chat", "chat_service"): "get_thread_service",
                ("world_chat_response", "generation_service"): "get_generation_service",
                ("world_chat_response", "evidence_service"): "get_evidence_service",
            }

            class ActualRequestGetter(ast.NodeTransformer):
                def visit_Attribute(self, node):
                    self.generic_visit(node)
                    getter = getters.get((node.value.id, node.attr)) if isinstance(node.value, ast.Name) else None
                    if getter is None:
                        return node
                    return ast.Call(func=ast.Attribute(value=node.value, attr=getter, ctx=ast.Load()), args=[ast.Name(id="request", ctx=ast.Load())], keywords=[])

            expected = ActualRequestGetter().visit(expected)
            if dump(actual) != dump(expected):
                raise ValueError("Chat actual route owner binding test changed")
        result[function] = {"paths": {path, path.replace("/tests/chat/", "/tests/")}, "current_path": path,
                            "old_function": frozen, "old_fragments": fragments(frozen), "required": fragments(actual)}
    return result


def required_fragments(expected, old_source, old_path, old_function, new_path, new_function, proof):
    entry = proof.get(old_function) if proof else None
    if entry is None or old_path not in entry["paths"]:
        return expected
    if new_path != entry["current_path"] or new_function != old_function:
        raise ValueError("Chat retirement requires its exact existing test node")
    frozen = definition(old_source, old_function, ast.FunctionDef)
    if dump(frozen) != dump(entry["old_function"]) or Counter(expected) != Counter(entry["old_fragments"]):
        raise ValueError("Chat retirement frozen test is not the reviewed original")
    return entry["required"]
