"""Evidence for retiring the final import-only Angmoo compatibility surfaces.

Historical Python is parsed, never executed. This closed migration proof does
not create old modules, namespaces or replacement services. Runtime checks use
only the real defining modules and the real composed Chat service instances.
"""
from __future__ import annotations

import ast
import copy
import importlib
import inspect
import subprocess
from collections import Counter
from functools import lru_cache
from pathlib import Path

SOURCE = "e565834291dc901ab1826979644d81cc643f9dfd"
EARLIER_SOURCE = "9c14b6095b972bbbb1f02473725ea7a7983e7d6c"
ROOT = Path(__file__).resolve().parents[2]
MODULES = (
    "app.schemas", "app.schemas.agents", "app.schemas.auth",
    "app.schemas.characters", "app.schemas.messages", "app.schemas.media_security",
    "app.services.messages", "app.services.prompt_safety",
    "app.services.world_character_provider", "app.services.profile_media",
    "app.runtime.chat.sqlalchemy_service",
    "app.domains.characters.public", "app.domains.identity.public",
    "app.domains.routines.public", "app.domains.world_characters.public",
    "app.domains.worlds.public", "app.services.daily_activity_plans",
)
# This additional input was already deleted by the actual Routines move. Its
# old source-purity test still requires the same historical proof, not a stub.
EARLIER_ONLY = "app.services.daily_activity_plans"


def dump(node):
    return ast.dump(node, include_attributes=False)


def module_path(module):
    return "backend/" + module.replace(".", "/") + ("/__init__.py" if module == "app.schemas" else ".py")


def git_bytes(*args, root=ROOT):
    return subprocess.check_output(["git", *args], cwd=root)


def expression_path(node):
    if isinstance(node, ast.Name):
        return (node.id,)
    if isinstance(node, ast.Attribute):
        left = expression_path(node.value)
        return (*left, node.attr) if left else None
    return None


def global_bindings(nodes):
    """Count actual module bindings, including conditional stores/imports."""
    result=Counter()
    for node in nodes:
        if isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef,ast.ClassDef)):
            result[node.name]+=1
        elif isinstance(node,(ast.Import,ast.ImportFrom)):
            for a in node.names:
                if a.name=='*':
                    raise ValueError('ambiguous star import in actual owner')
                result[a.asname or (a.name.split('.')[0] if isinstance(node,ast.Import) else a.name)]+=1
        elif isinstance(node,ast.Name) and isinstance(node.ctx,(ast.Store,ast.Del)):
            result[node.id]+=1
        else:
            if isinstance(node,(ast.ExceptHandler,ast.MatchAs,ast.MatchStar)) and node.name:
                result[node.name]+=1
            if isinstance(node,ast.MatchMapping) and node.rest:
                result[node.rest]+=1
            result.update(global_bindings(list(ast.iter_child_nodes(node))))
    return result


def terminal_definition(source,symbol):
    tree=ast.parse(source)
    if global_bindings(tree.body)[symbol]!=1:
        raise ValueError('actual terminal export must have one unshadowed binding: '+symbol)
    values=[n for n in tree.body if (isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef,ast.ClassDef)) and n.name==symbol) or (isinstance(n,(ast.Assign,ast.AnnAssign)) and any(isinstance(t,ast.Name) and t.id==symbol for t in (n.targets if isinstance(n,ast.Assign) else [n.target])))]
    if len(values)!=1:
        raise ValueError('actual terminal export has no defining role: '+symbol)
    return values[0]


class History:
    def __init__(self, root=ROOT, reader=git_bytes):
        self.root, self.reader = Path(root), reader
        paths = reader("ls-tree", "-r", "--name-only", SOURCE, "--", "backend/app", root=self.root).decode().splitlines()
        self.paths = {}
        for path in paths:
            if path.endswith(".py"):
                module = path.removeprefix("backend/").removesuffix(".py").replace("/", ".")
                self.paths[module.removesuffix(".__init__")] = path
        self.paths[EARLIER_ONLY] = module_path(EARLIER_ONLY)

    @lru_cache(maxsize=None)
    def product_evidence(self):
        spec = importlib.util.spec_from_file_location("product_changes", Path(__file__).with_name("post_refactor_contract_changes.py"))
        changes = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(changes)
        return changes, changes.load(self.root, reader=self.reader)

    @lru_cache(maxsize=None)
    def removed_product_bindings(self):
        changes, records = self.product_evidence()
        return changes.removed_bindings(records)

    def binding_removed(self, module, export):
        owner, tail = self.terminal(self.resolve(module, export))
        return bool(tail) and (self.paths.get(owner), tail[0]) in self.removed_product_bindings()

    @lru_cache(maxsize=None)
    def source(self, module):
        commit = EARLIER_SOURCE if module == EARLIER_ONLY else SOURCE
        return self.reader("show", commit + ":" + self.paths[module], root=self.root).decode("utf-8-sig")

    @lru_cache(maxsize=None)
    def tree(self, module):
        return ast.parse(self.source(module))

    @lru_cache(maxsize=None)
    def validate_owner_all(self,module):
        original=self.tree(module)
        present=any(isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='__all__' for t in n.targets) for n in original.body)
        if present:
            def statements(tree):
                return [dump(n) for n in tree.body if not isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef,ast.ClassDef)) and any((isinstance(x,ast.Name) and x.id=='__all__') or (isinstance(x,ast.alias) and (x.asname or x.name)=='__all__') for x in ast.walk(n))]
            current=ast.parse((self.root/self.paths[module]).read_text(encoding='utf-8-sig'))
            # Routines originally declares its error groups with assignment +
            # +=. Preserve that exact sequence instead of rejecting the original
            # module or permitting arbitrary reassignment/append operations.
            if statements(original)!=statements(current):
                raise ValueError('actual owner advertised exports changed: '+module)

    def reference(self, module, node, bindings):
        parts = expression_path(node)
        if not parts or parts[0] not in bindings:
            raise ValueError("unresolved historical alias in " + module)
        return (*bindings[parts[0]], *parts[1:])

    @lru_cache(maxsize=None)
    def bindings(self, module):
        result, exported, alias = {}, None, None
        pure = module in MODULES
        for node in self.tree(module).body:
            if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
                continue
            additions = {}
            if isinstance(node, ast.ImportFrom):
                if node.level or any(a.name == "*" for a in node.names):
                    if pure:
                        raise ValueError("relative/star import in retired facade: " + module)
                    continue
                additions = {a.asname or a.name: (*node.module.split("."), a.name) for a in node.names}
            elif isinstance(node, ast.Import):
                additions = {a.asname or a.name.split(".")[0]: tuple((a.name if a.asname else a.name.split(".")[0]).split(".")) for a in node.names}
            elif isinstance(node, (ast.Assign, ast.AnnAssign)):
                targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                if len(targets) != 1:
                    if pure:
                        raise ValueError("multiple/rebound historical exports: " + module)
                    continue
                target = targets[0]
                if isinstance(target, ast.Name) and target.id == "__all__":
                    if exported is not None:
                        raise ValueError("reassigned historical __all__: " + module)
                    exported = ast.literal_eval(node.value)
                    if not isinstance(exported, (list, tuple)) or any(not isinstance(x, str) for x in exported) or len(set(exported)) != len(exported):
                        raise ValueError("dynamic/duplicate historical __all__: " + module)
                    continue
                if dump(target) == dump(ast.parse("sys.modules[__name__] = _implementation").body[0].targets[0]):
                    if alias is not None or result.get("sys") != ("sys",) or not isinstance(node.value, ast.Name):
                        raise ValueError("invalid historical sys.modules alias: " + module)
                    alias = self.reference(module, node.value, result)
                    continue
                if isinstance(target, ast.Name):
                    if expression_path(node.value) and expression_path(node.value)[0] in result:
                        additions[target.id] = self.reference(module, node.value, result)
                    elif pure:
                        raise ValueError("implementation in retired facade: " + module)
                    else:
                        additions[target.id] = (*module.split("."), target.id)
                elif pure:
                    raise ValueError("attribute mutation in retired facade: " + module)
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                if pure:
                    raise ValueError("implementation in retired facade: " + module)
                additions[node.name] = (*module.split("."), node.name)
            elif pure:
                raise ValueError("executable statement in retired facade: " + module)
            for name, value in additions.items():
                if pure and name in result:
                    raise ValueError("rebound historical export: " + module + "." + name)
                result[name] = value
        if exported is not None and not set(exported) <= result.keys():
            raise ValueError("missing historical advertised export: " + module)
        if alias is not None:
            if set(result) != {"sys", "_implementation"} or exported is not None:
                raise ValueError("sys.modules alias has additional mutable exports: " + module)
            return {}, alias
        return result, None

    def resolve_parts(self, parts, visited=()):
        # Longest real Python module prefix distinguishes an imported module
        # from an attribute on a class or a composed service instance.
        module = next((".".join(parts[:i]) for i in range(len(parts), 0, -1) if ".".join(parts[:i]) in self.paths), None)
        if module is None:
            return tuple(parts)
        tail = parts[len(module.split(".")):]
        if not tail:
            _, alias = self.bindings(module)
            return self.resolve_parts(alias, (*visited, module)) if alias else tuple(parts)
        key = (module, tail[0])
        if key in visited:
            raise ValueError("cyclic historical export: " + str(key))
        bindings, alias = self.bindings(module)
        if alias:
            return self.resolve_parts((*alias, *tail), (*visited, key))
        value = bindings.get(tail[0])
        if value is None:
            raise ValueError("missing historical export: " + module + "." + tail[0])
        if value == (*module.split("."), tail[0]):
            return (*value, *tail[1:])
        return self.resolve_parts((*value, *tail[1:]), (*visited, key))

    def resolve(self, module, export=None):
        if module not in MODULES:
            raise ValueError("not an approved retired module: " + module)
        parts = (*module.split("."), *(export.split(".") if export else ()))
        return self.resolve_parts(parts)

    def exports(self, module):
        bindings, alias = self.bindings(module)
        if alias:
            target = ".".join(alias)
            return self.exports(target) if target in MODULES else self.bindings(target)[0]
        return bindings

    def terminal(self, parts):
        module = next((".".join(parts[:i]) for i in range(len(parts), 0, -1) if ".".join(parts[:i]) in self.paths), None)
        if module is None:
            # External imported constants/types retain their actual library
            # import, not a fabricated application definition.
            for i in range(len(parts), 0, -1):
                try:
                    importlib.import_module(".".join(parts[:i]))
                except ModuleNotFoundError:
                    continue
                return ".".join(parts[:i]), parts[i:]
            raise ValueError("missing external historical owner: " + ".".join(parts))
        return module, parts[len(module.split(".")):]

    def actual(self, module, export=None):
        owner, tail = self.terminal(self.resolve(module, export))
        if owner in MODULES:
            raise ValueError("historical aggregate is not an actual owner: " + owner)
        value = importlib.import_module(owner)
        if owner.startswith("app.") and Path(value.__file__).resolve() != (self.root / self.paths[owner]).resolve():
            raise ValueError("actual owner imported from a different checkout: " + owner)
        for name in tail:
            value = getattr(value, name)
        return value

    def absent(self, module):
        path = self.root / module_path(module)
        package = self.root / ("backend/" + module.replace(".", "/"))
        if path.exists() or (package.is_dir() and any(package.rglob("*.py"))):
            raise ValueError("retired facade file/package still exists: " + module)

    def validate_sources(self):
        removed = self.removed_product_bindings()
        changes, records = self.product_evidence()
        for commit in (SOURCE, EARLIER_SOURCE):
            if self.reader("merge-base", commit, "HEAD", root=self.root).decode().strip() != commit:
                raise ValueError("retirement source is not an ancestor of this candidate")
            if not any(line.startswith("Signed-off-by: ") for line in self.reader("show", "-s", "--format=%B", commit, root=self.root).decode().splitlines()):
                raise ValueError("retirement requires the original signed source")
        result = {}
        for module in MODULES:
            self.absent(module)
            # Parsing the complete facade rejects added implementation. __all__
            # is checked, but all explicit imports are preserved, including
            # exports that were never advertised in __all__.
            values = self.exports(module)
            result[module] = {name: ".".join(self.resolve(module, name)) for name in values}
            for parts in result[module].values():
                owner, tail = self.terminal(tuple(parts.split(".")))
                if owner in MODULES:
                    raise ValueError("export terminates in a retired facade")
                if owner.startswith("app."):
                    path = self.root / self.paths[owner]
                    if not path.is_file():
                        raise ValueError("actual export owner is absent: " + owner)
                    self.validate_owner_all(owner)
                    if tail:
                        if (self.paths[owner], tail[0]) in removed:
                            continue
                        current_definition=terminal_definition(path.read_text(encoding='utf-8-sig'),tail[0])
                        original_definition=terminal_definition(self.source(owner),tail[0])
                        if current_definition is not None and original_definition is not None and changes.definition_matches(
                            self.root, self.paths[owner], tail[0], original_definition, current_definition, records=records
                        ):
                            continue
                        if type(current_definition) is not type(original_definition):
                            raise ValueError("actual terminal export must have one definition: " + parts)
                        if isinstance(current_definition,(ast.FunctionDef,ast.AsyncFunctionDef)) and (dump(current_definition.args)!=dump(original_definition.args) or [dump(n) for n in current_definition.decorator_list]!=[dump(n) for n in original_definition.decorator_list]):
                            raise ValueError('actual callable binding/signature changed: '+parts)
                        if isinstance(current_definition,ast.ClassDef) and ([dump(n) for n in [*current_definition.bases,*current_definition.keywords,*current_definition.decorator_list]] != [dump(n) for n in [*original_definition.bases,*original_definition.keywords,*original_definition.decorator_list]]):
                            raise ValueError('actual class binding/base/decorator changed: '+parts)
                        # Includes the original five Literal values moved to
                        # actual Character/Routines constants before retirement.
                        if isinstance(current_definition,(ast.Assign,ast.AnnAssign)) and dump(current_definition)!=dump(original_definition):
                            raise ValueError('actual constant/singleton definition changed: '+parts)
                        # A real Chat singleton must remain the same composed
                        # constructor expression; a replacement object is not
                        # equivalent even if it has identically named methods.
                        if len(tail) > 1 and owner == "app.runtime.chat.message_composition":
                            original = [n for n in self.tree(owner).body if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == tail[0] for t in n.targets)]
                            if len(original) != 1 or dump(current_definition) != dump(original[0]):
                                raise ValueError("composed Chat receiver changed: " + parts)
        return result


@lru_cache(maxsize=1)
def history():
    return History()


def same_object(actual, expected):
    if inspect.ismethod(actual) or inspect.ismethod(expected):
        return (inspect.ismethod(actual) and inspect.ismethod(expected)
                and actual.__self__ is expected.__self__
                and actual.__func__ is expected.__func__)
    return actual is expected


def export_matches(module, export, actual):
    """Check one original binding against the actual class/function/receiver."""
    evidence = history()
    evidence.absent(module)
    return same_object(actual, evidence.actual(module, export))


def module_matches(module, actual):
    """A retired sys.modules alias used to name this existing actual module."""
    evidence = history()
    evidence.absent(module)
    return evidence.bindings(module)[1] is not None and evidence.actual(module) is actual


def alias_retired(left, right):
    evidence = history()
    evidence.absent(left)
    evidence.absent(right)
    return evidence.bindings(left)[1] == tuple(right.split(".")) and bool(evidence.exports(right))


def module_retired(module):
    evidence = history()
    evidence.absent(module)
    for name in evidence.exports(module):
        if evidence.binding_removed(module, name):
            continue
        evidence.actual(module, name)
    return bool(evidence.exports(module))


# These exact existing functions contain the compatibility contracts being
# retired. Other functions keep the ordinary frozen behavior checks.
TESTS = {
    "backend/tests/routines/test_daily_activity_runtime.py": ("test_routines_public_uses_frozen_clock_and_writes_no_public_action", "test_owner_controlled_identity_cannot_prepare_or_reconcile_daily_plan"),
    "backend/tests/routines/test_guarded_claim_recovery.py": ("test_guarded_recovery_uses_consumption_owner_and_preserves_admission",),
    "backend/tests/routines/test_activity_limits.py": ("test_world_timezone_change_reschedules_enabled_idle_slots",),
    "backend/tests/characters/test_character_foundation.py": ("test_model_and_schema_compatibility_exports_have_one_identity",),
    "backend/tests/characters/test_character_http_workflows.py": ("test_both_application_factories_install_workflows_and_schema_aliases_keep_identity",),
    "backend/tests/characters/test_creator_http_errors.py": ("test_error_exports_are_same_objects_and_keep_runtime_diagnostics",),
    "backend/tests/identity/test_l1_identity_domain_foundation.py": (
        "test_legacy_model_imports_share_canonical_identity_objects",
        "test_identity_model_table_contracts_are_unchanged",
        "test_legacy_schema_imports_share_canonical_identity_objects",
        "test_credential_imports_share_canonical_identity_objects",
    ),
    "backend/tests/identity/test_l1_identity_architecture.py": (
        "test_identity_domain_is_the_canonical_aggregate_source",
        "test_identity_compatibility_facades_only_point_inward",
    ),
    "backend/tests/chat/test_p8_l_b_chat_domain.py": (
        "test_legacy_message_service_is_the_canonical_runtime_module",
        "test_legacy_model_and_schema_exports_are_canonical_objects",
    ),
    "backend/tests/test_p8_l_b_chat_domain_inventory.py": ("test_p8_l_b_compatibility_facades_preserve_object_identity",),
    "backend/tests/world_characters/test_foundation_identity.py": ("test_provider_compatibility_keeps_monkeypatch_target_and_accounting_types",),
    "backend/tests/world_characters/test_readiness_contract.py": ("test_readiness_keeps_shared_dto_and_world_scope_before_stale_profile",),
    "backend/tests/media/test_media_storage_boundaries.py": ("test_compatibility_exports_use_owner_implementations_and_same_error_classes",),
    "backend/tests/media/test_world_banner_codec.py": ("test_world_banner_uses_shared_sanitized_bytes_and_legacy_exception_contract",),
    "backend/tests/test_l3_domain_boundary_map.py": (
        "test_daily_plan_legacy_path_is_a_thin_domain_facade",
        "test_l3_public_package_anchors_have_no_reverse_dependencies",
    ),
}
SUPPORT_NAMES = ("export_matches", "module_matches", "alias_retired", "module_retired", "historical_imports", "historical_function_names")


def aliases_in(tree):
    aliases = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                if a.asname:
                    aliases[a.asname] = (a.name, "")
        elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
            for a in node.names:
                full = node.module + "." + a.name
                if full in MODULES:
                    aliases[a.asname or a.name] = (full, "")
                elif node.module in MODULES:
                    aliases[a.asname or a.name] = (node.module, a.name)
        elif isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            v = node.value
            if isinstance(v, ast.Call) and ast.unparse(v.func) == "importlib.import_module" and len(v.args) == 1 and isinstance(v.args[0], ast.Constant) and v.args[0].value in MODULES:
                aliases[node.targets[0].id] = (v.args[0].value, "")
    return {name:value for name,value in aliases.items() if value[0] in MODULES}


def module_alias(module):
    return "_actual_" + module.removeprefix("app.").replace(".", "_")


class Rebind(ast.NodeTransformer):
    """Resolve old reads; replace only identity edges involving retired reads."""
    def __init__(self, evidence, aliases):
        self.evidence, self.aliases = evidence, aliases
        self.imports = set()
        self.retired_checks = 0

    def reference(self, node):
        if isinstance(node, ast.Name) and node.id in self.aliases:
            module, export = self.aliases[node.id]
            return module, ast.Constant(value=export) if export else None
        if isinstance(node, ast.Attribute):
            ref = self.reference(node.value)
            if ref:
                module, export = ref
                if export is None:
                    return module, ast.Constant(value=node.attr)
                if isinstance(export, ast.Constant):
                    return module, ast.Constant(value=export.value + "." + node.attr)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "getattr" and len(node.args) == 2 and isinstance(node.args[0], ast.Name):
            ref = self.reference(node.args[0])
            if ref and ref[1] is None:
                return ref[0], node.args[1]
        return None

    def actual(self, ref):
        module, export = ref
        if export is not None and not isinstance(export, ast.Constant):
            raise ValueError("dynamic retired export needs an existing actual comparison operand")
        owner, tail = self.evidence.terminal(self.evidence.resolve(module, export.value if export else None))
        if owner in MODULES:
            raise ValueError("cannot fabricate a replacement aggregate namespace")
        self.imports.add(owner)
        node = ast.Name(id=module_alias(owner), ctx=ast.Load())
        for name in tail:
            node = ast.Attribute(value=node, attr=name, ctx=ast.Load())
        return node

    def check(self, ref, actual):
        module, export = ref
        self.retired_checks += 1
        if export is None:
            return ast.Call(func=ast.Name(id="module_matches",ctx=ast.Load()), args=[ast.Constant(value=module), actual], keywords=[])
        return ast.Call(func=ast.Name(id="export_matches",ctx=ast.Load()), args=[ast.Constant(value=module), copy.deepcopy(export), actual], keywords=[])

    def visit_Compare(self, node):
        values = [node.left, *node.comparators]
        refs = [self.reference(v) for v in values]
        if not any(refs) or not any(isinstance(op,ast.Is) for op in node.ops):
            return self.generic_visit(node)
        checks = []
        for index, op in enumerate(node.ops):
            left,right = values[index:index+2]
            a,b = refs[index:index+2]
            if not isinstance(op,ast.Is) or not (a or b):
                checks.append(ast.Compare(left=self.visit(copy.deepcopy(left)),ops=[copy.deepcopy(op)],comparators=[self.visit(copy.deepcopy(right))]))
                continue
            if a and b and a[1] is None and b[1] is None:
                if self.evidence.bindings(a[0])[1] != tuple(b[0].split(".")):
                    raise ValueError("unproven historical whole-module identity")
                checks.append(ast.Call(func=ast.Name(id="alias_retired",ctx=ast.Load()),args=[ast.Constant(value=a[0]),ast.Constant(value=b[0])],keywords=[]))
                self.retired_checks += 1
                continue
            if a and b:
                actual = self.actual(a)
                checks.extend([self.check(a,copy.deepcopy(actual)),self.check(b,copy.deepcopy(actual))])
            elif a:
                checks.append(self.check(a,self.visit(copy.deepcopy(right))))
            else:
                checks.append(self.check(b,self.visit(copy.deepcopy(left))))
        return checks[0] if len(checks)==1 else ast.BoolOp(op=ast.And(),values=checks)

    def visit_Attribute(self,node):
        ref=self.reference(node)
        return self.actual(ref) if ref else self.generic_visit(node)

    def visit_Name(self,node):
        ref=self.reference(node)
        return self.actual(ref) if ref and isinstance(node.ctx,ast.Load) else node

    def visit_ImportFrom(self,node):
        if not node.module or node.level:
            return node
        node.names=[a for a in node.names if node.module not in MODULES and node.module+"."+a.name not in MODULES]
        return node if node.names else None

    def visit_Import(self,node):
        node.names=[a for a in node.names if a.name not in MODULES]
        return node if node.names else None

    def visit_Assign(self,node):
        if len(node.targets)==1 and isinstance(node.targets[0],ast.Name) and node.targets[0].id in self.aliases and isinstance(node.value,ast.Call) and ast.unparse(node.value.func)=="importlib.import_module":
            return None
        return self.generic_visit(node)


def historical_imports(module):
    evidence=history()
    evidence.absent(module)
    evidence.bindings(module)
    return {n.module for n in evidence.tree(module).body if isinstance(n,ast.ImportFrom) and n.module} | {a.name for n in evidence.tree(module).body if isinstance(n,ast.Import) for a in n.names}


def historical_function_names(module):
    evidence=history()
    evidence.absent(module)
    evidence.bindings(module)
    return {n.name for n in ast.walk(evidence.tree(module)) if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef))}


STRUCTURAL = {
 "test_identity_domain_is_the_canonical_aggregate_source": {
    'assert "app.domains.identity.schemas" in imports["app.schemas"]': 'assert "app.schemas" not in imports and "app.domains.identity.schemas" in historical_imports("app.schemas")',
    'assert "app.schemas.auth" not in imports["app.schemas"]': 'assert "app.schemas.auth" not in imports and "app.schemas.auth" not in historical_imports("app.schemas")',
 },
 "test_identity_compatibility_facades_only_point_inward": {
    'assert imports["app.schemas.auth"] == {"app.domains.identity.schemas"}': 'assert "app.schemas.auth" not in imports and historical_imports("app.schemas.auth") == {"app.domains.identity.schemas"}',
 },
}


def transformed_function(evidence, source, function):
    tree=ast.parse(source)
    definitions={n.name:n for n in tree.body if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef))}
    old=definitions[function]
    # Function-local names override module imports; no sibling lexical scope.
    imports=ast.Module(body=[n for n in tree.body if isinstance(n,(ast.Import,ast.ImportFrom))],type_ignores=[])
    aliases={**aliases_in(imports),**aliases_in(old)}
    transform=Rebind(evidence,aliases)
    value=copy.deepcopy(old)
    if function in STRUCTURAL:
        changes={dump(ast.parse(a).body[0]):ast.parse(b).body[0] for a,b in STRUCTURAL[function].items()}
        present=Counter(dump(n) for n in ast.walk(value))
        if any(present[key]!=1 for key in changes):
            raise ValueError("exact original schema structure fragment missing")
        class Replace(ast.NodeTransformer):
            def visit_Assert(self,node):
                return copy.deepcopy(changes.get(dump(node),node))
        value=Replace().visit(value)
    if function=="test_daily_plan_legacy_path_is_a_thin_domain_facade":
        expected=ast.parse('facade = APP_ROOT / "services" / "daily_activity_plans.py"').body[0]
        if dump(value.body[0])!=dump(expected):
            raise ValueError("daily facade source test no longer matches original")
        value.body[0:2]=ast.parse('assert module_retired("app.services.daily_activity_plans")\nimports = historical_imports("app.services.daily_activity_plans")').body
        class Daily(ast.NodeTransformer):
            def visit_Call(self,node):
                if ast.unparse(node)=="_function_names(facade)":
                    return ast.parse('historical_function_names("app.services.daily_activity_plans")',mode='eval').body
                return self.generic_visit(node)
        value=Daily().visit(value)
    if function=="test_l3_public_package_anchors_have_no_reverse_dependencies":
        loop=next(n for n in value.body if isinstance(n,ast.For) and isinstance(n.target,ast.Name) and n.target.id=="boundary")
        # The remaining pure contract files retain their original current-source
        # check. Retired public surfaces retain the same rule on immutable AST
        # plus complete export/absence proof; no unchecked path is skipped.
        cases=ast.parse('''if boundary in ("worlds", "world_characters", "routines"):
    module = "app.domains." + boundary + ".public"
    assert module_retired(module)
    imports = historical_imports(module)
    assert not {imported for imported in imports if imported in forbidden_prefixes or imported.startswith(tuple(f"{prefix}." for prefix in forbidden_prefixes))}
    continue
''').body
        loop.body=cases+loop.body
    value=transform.visit(value)
    return ast.fix_missing_locations(value),transform


def imports_of(source):
    result={}
    for node in ast.parse(source).body:
        if isinstance(node,ast.Import):
            for a in node.names:
                name=a.asname or a.name.split('.')[0]
                if name in result:
                    raise ValueError('duplicate test import: '+name)
                result[name]=(a.name,'')
        elif isinstance(node,ast.ImportFrom) and node.module:
            for a in node.names:
                if a.name == '*':
                    raise ValueError('retirement test rejects star imports')
                name=a.asname or a.name
                if name in result:
                    raise ValueError('duplicate test import: '+name)
                result[name]=(node.module,a.name)
    return result


def validate_test_function(evidence, path, function, current):
    if path not in TESTS or function not in TESTS[path]:
        raise ValueError('unapproved compatibility test function')
    original=evidence.reader('show',SOURCE+':'+path,root=evidence.root).decode('utf-8-sig')
    expected,rewrite=transformed_function(evidence,original,function)
    tree=ast.parse(current)
    found=[n for n in tree.body if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef)) and n.name==function]
    changes, records = evidence.product_evidence()
    if len(found)!=1 or not changes.definition_matches(evidence.root, path, function, expected, found[0], records=records):
        raise ValueError('retirement changed behavior/fixture/monkeypatch beyond exact binding: '+path+'::'+function)
    # Imports and independently reviewed test functions may move. Executable
    # module scaffolding may not inject a conditional import or mutate a proof
    # predicate before the otherwise unchanged test executes.
    def scaffold(source_tree):
        return [dump(n) for n in source_tree.body if not isinstance(n,(ast.Import,ast.ImportFrom,ast.FunctionDef,ast.AsyncFunctionDef,ast.ClassDef))]
    if scaffold(tree)!=scaffold(ast.parse(original)):
        raise ValueError('retirement changed executable test module scaffolding: '+path)
    bindings=imports_of(current)
    counts=global_bindings(tree.body)
    needed={module_alias(module):(module,'') for module in rewrite.imports}
    used={n.id for n in ast.walk(expected) if isinstance(n,ast.Name) and isinstance(n.ctx,ast.Load)}
    needed.update({name:('compatibility_retirement_support',name) for name in SUPPORT_NAMES if name in used})
    for name,value in needed.items():
        if bindings.get(name)!=value:
            raise ValueError('retirement test primitive has wrong import: '+name)
        if counts[name]!=1:
            raise ValueError('retirement primitive has ambiguous lexical binding: '+name)
        # A module assignment, function definition, fixture parameter or a
        # lexical store must not turn an evidence predicate into a constant.
        for node in tree.body:
            if isinstance(node,(ast.Import,ast.ImportFrom)):
                continue
            if isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef,ast.ClassDef)) and node.name!=function:
                if node.name==name:
                    raise ValueError('retirement primitive is shadowed: '+name)
                # Class bodies and declaration decorators/defaults execute at
                # import time. They must not mutate these newly introduced
                # proof bindings while leaving the checked function intact.
                declarations = ([node] if isinstance(node,ast.ClassDef) else [*node.decorator_list,node.args])
                for declaration in declarations:
                    if any((isinstance(n,ast.Name) and n.id==name)
                           or (isinstance(n,ast.alias) and (n.asname or n.name.split('.')[0])==name)
                           or (isinstance(n,ast.Global) and name in n.names)
                           for n in ast.walk(declaration)):
                        raise ValueError('retirement primitive is used by executable declaration: '+name)
                continue
            if any((isinstance(n,ast.Name) and isinstance(n.ctx,(ast.Store,ast.Del)) and n.id==name) or (isinstance(n,ast.arg) and n.arg==name) for n in ast.walk(node)):
                raise ValueError('retirement primitive is rebound: '+name)
    return original,expected


def active_consumers(root):
    def retired(name):
        return name in MODULES or any(name.startswith(module+'.') for module in MODULES)

    for directory in ('backend/app','backend/tests','backend/scripts','scripts'):
        for path in (Path(root)/directory).rglob('*.py'):
            if '__pycache__' in path.parts:
                continue
            tree=ast.parse(path.read_text(encoding='utf-8-sig'))
            if path.is_relative_to(Path(root)/'backend'):
                package='.'.join(path.relative_to(Path(root)/'backend').parent.parts)
                for node in ast.walk(tree):
                    if isinstance(node,ast.ImportFrom) and node.level:
                        try:
                            node.module=importlib.util.resolve_name('.'*node.level+(node.module or ''),package)
                        except (ImportError,ValueError):
                            continue
                        node.level=0
            if aliases_in(tree):
                raise ValueError('retired facade has an actual static/dynamic consumer: '+str(path))
            importers={'import_module','__import__'}
            for node in ast.walk(tree):
                if isinstance(node,ast.ImportFrom) and node.module in ('importlib','builtins'):
                    importers.update(a.asname or a.name for a in node.names if a.name in ('import_module','__import__'))
            for node in ast.walk(tree):
                if isinstance(node,ast.ImportFrom) and node.module and (retired(node.module) or any(retired(node.module+'.'+a.name) for a in node.names)):
                    raise ValueError('retired facade has an actual import consumer: '+str(path))
                if isinstance(node,ast.Import) and any(retired(a.name) for a in node.names):
                    raise ValueError('retired facade has an actual module consumer: '+str(path))
                if isinstance(node,ast.Call) and isinstance(node.func,(ast.Name,ast.Attribute)) and (node.func.id if isinstance(node.func,ast.Name) else node.func.attr) in importers and node.args:
                    def literal(value):
                        if isinstance(value,ast.Constant) and isinstance(value.value,str):
                            return value.value
                        if isinstance(value,ast.BinOp) and isinstance(value.op,ast.Add):
                            return literal(value.left)+literal(value.right)
                        return ''
                    names=[literal(node.args[0])]
                    if isinstance(node.args[0],ast.Name):
                        names.extend(literal(n.value) for n in ast.walk(tree) if isinstance(n,(ast.Assign,ast.AnnAssign)) and any(isinstance(t,ast.Name) and t.id==node.args[0].id for t in (n.targets if isinstance(n,ast.Assign) else [n.target])))
                    if any(retired(name) for name in names):
                        raise ValueError('retired facade has an actual dynamic import: '+str(path))


def validate(enabled, files, snapshots, root=ROOT, reader=git_bytes):
    if not enabled:
        return None
    if enabled is not True:
        raise ValueError('compatibility retirement must be the closed reviewed operation')
    evidence=History(root,reader)
    exports=evidence.validate_sources()
    support=Path(root)/'backend/tests/compatibility_retirement_support.py'
    if not support.is_file() or dump(ast.parse(support.read_text(encoding='utf-8-sig')))!=dump(ast.parse(support_source())):
        raise ValueError('retirement test support must execute the exact real evidence predicates')
    tracked=set().union(*(set(s.get('tracked_files',{})) for s in snapshots))
    for module in MODULES:
        path=module_path(module)
        if path not in tracked:
            raise ValueError('retirement original source is not protected: '+path)
        target=files.get(path)
        # The file map cannot substitute an empty marker or an unrelated role.
        owners={evidence.paths[owner] for parts in exports[module].values() for owner,_ in [evidence.terminal(tuple(parts.split('.')))] if owner in evidence.paths and owner not in MODULES}
        if target not in owners:
            raise ValueError('retirement file map does not point to an actual export owner: '+path)
    active_consumers(root)
    tests={}
    for path,functions in TESTS.items():
        current=(Path(root)/path).read_text(encoding='utf-8-sig')
        for function in functions:
            tests[(path,function)]=validate_test_function(evidence,path,function,current)
    renames={old.removeprefix('backend/').removesuffix('.py').replace('/','.').removesuffix('.__init__'):new.removeprefix('backend/').removesuffix('.py').replace('/','.').removesuffix('.__init__') for old,new in files.items() if old.startswith('backend/app/') and old.endswith('.py') and new.startswith('backend/app/') and new.endswith('.py')}
    return {'history':evidence,'exports':exports,'tests':tests,'renames':renames}


def support_source():
    return '''"""Real Git-AST retirement predicates; no old application module is loaded."""
import importlib.util
from pathlib import Path

_source = Path(__file__).resolve().parents[2] / "scripts/ci/compatibility_facade_retirement.py"
_spec = importlib.util.spec_from_file_location("compatibility_facade_retirement", _source)
proof = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(proof)
export_matches = proof.export_matches
module_matches = proof.module_matches
alias_retired = proof.alias_retired
module_retired = proof.module_retired
historical_imports = proof.historical_imports
historical_function_names = proof.historical_function_names
'''


def required_fragments(values, source, function, path, proof):
    if proof is None or (path,function) not in proof['tests']:
        return values
    # Transform the original frozen fragments, not today's assertion list.
    # The complete reviewed current function has separately been compared to
    # its signed pre-retirement function, including every non-assert statement.
    tree=ast.parse(source)
    old=next(n for n in tree.body if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef)) and n.name==function)
    module_imports=ast.Module(body=[n for n in tree.body if isinstance(n,(ast.Import,ast.ImportFrom))],type_ignores=[])
    aliases={**aliases_in(module_imports),**aliases_in(old)}
    changes={dump(ast.parse(a).body[0]):b for a,b in STRUCTURAL.get(function,{}).items()}
    result=[]
    for value in values:
        node=ast.parse(value)
        canonical=copy.deepcopy(node)
        for part in ast.walk(canonical):
            if isinstance(part,ast.Constant) and isinstance(part.value,str) and part.value not in MODULES:
                part.value=proof.get('renames',{}).get(part.value,part.value)
        if len(canonical.body)==1 and dump(canonical.body[0]) in changes:
            result.append(changes[dump(canonical.body[0])]);continue
        if function=='test_daily_plan_legacy_path_is_a_thin_domain_facade':
            if dump(node.body[0])==dump(ast.parse('assert not _function_names(facade)').body[0]):
                result.append('assert not historical_function_names("app.services.daily_activity_plans")');continue
        rewritten=Rebind(proof['history'],aliases).visit(node)
        result.append(ast.unparse(ast.fix_missing_locations(rewritten)).strip())
    return result
