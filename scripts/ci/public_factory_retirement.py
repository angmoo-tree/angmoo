"""Strict retirement proof for the frozen one-way G06 public factory facade.

This is not a general alias or assertion allowlist. It only interprets the
protected public_main facade and its dedicated factory/cold-process tests.
"""
from __future__ import annotations
import ast
import copy
from collections import Counter
from pathlib import Path

FACADE_SOURCE = '90d7fd7f2332b2b27cf2f1bd92ed0e206427e6f7'
FACTORY_SOURCE = '924a8361867bd0228943082227221d78507f9027'
OLD = 'backend/app/public_main.py'
MAIN = 'backend/app/main.py'
TEST = 'backend/tests/runtime/test_app_factory_ownership.py'
BUNDLE_TEST = 'test_single_factory_keeps_both_health_contracts_and_shared_types'
COLD_TEST = 'test_both_module_imports_are_lazy_and_explicit_factory_still_prepares_media'
BUNDLE = ('HostedBackendExtension', 'PublicRuntimeConfigurationError', 'HostedExtensionConfigurationError', 'create_app', 'create_lifespan')
PUBLIC_BINDINGS = {'HostedBackendExtension': 'HostedBackendExtension', 'HostedExtensionConfigurationError': 'HostedExtensionConfigurationError', 'HostedLifecycleHook': 'HostedLifecycleHook', 'LifespanHandler': 'LifespanHandler', 'PublicRuntimeConfigurationError': 'PublicRuntimeConfigurationError', 'Settings': 'Settings', 'health': 'health', 'main': 'main', 'runtime_health': 'runtime_health', 'settings': 'settings', 'validate_public_runtime_settings': 'validate_public_runtime_settings', 'create_app': 'create_public_app', 'create_lifespan': 'create_public_lifespan', 'app': 'public_app', 'lifespan': 'public_lifespan'}
ABSENT = "assert not Path(main.__file__).with_name('public_main.py').exists()"
PROFILE_ASSERTS = ("assert main.create_public_app.keywords == {'profile': 'public'}", "assert main.create_public_lifespan.keywords['component_manager_factory']() is None", "assert main.create_app.__kwdefaults__['profile'] == 'full'")


def dump(node):
    return ast.dump(node, include_attributes=False)


def counts(body):
    result = Counter()
    def visit(n):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            result[n.name] += 1
            return
        if isinstance(n, (ast.Import, ast.ImportFrom)):
            for a in n.names:
                if a.name == '*':
                    raise ValueError('public factory proof rejects star imports')
                result[a.asname or (a.name.split('.')[0] if isinstance(n, ast.Import) else a.name)] += 1
            return
        if isinstance(n, ast.ExceptHandler) and n.name:
            result[n.name] += 1
        if isinstance(n, (ast.MatchAs, ast.MatchStar)) and n.name:
            result[n.name] += 1
        if isinstance(n, ast.MatchMapping) and n.rest:
            result[n.rest] += 1
        if isinstance(n, ast.Name) and isinstance(n.ctx, (ast.Store, ast.Del)):
            result[n.id] += 1
        for c in ast.iter_child_nodes(n):
            visit(c)
    for n in body:
        visit(n)
    return result


def definitions(tree):
    result = {}
    for n in tree.body:
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            result[n.name] = n
        elif isinstance(n, (ast.Assign, ast.AnnAssign)):
            for t in n.targets if isinstance(n, ast.Assign) else [n.target]:
                if isinstance(t, ast.Name):
                    result[t.id] = n.value
        elif isinstance(n, ast.ImportFrom):
            for a in n.names:
                result[a.asname or a.name] = n
    return result


def facade_exports(source):
    tree = ast.parse(source)
    aliases, exports = {}, None
    for n in tree.body:
        if isinstance(n, ast.Expr) and isinstance(n.value, ast.Constant) and isinstance(n.value.value, str):
            continue
        if isinstance(n, ast.ImportFrom) and n.level == 0 and n.module == 'app.main':
            for a in n.names:
                name = a.asname or a.name
                if a.name == '*' or name in aliases:
                    raise ValueError('frozen public facade has duplicate/dynamic exports')
                aliases[name] = a.name
        elif isinstance(n, ast.Assign) and len(n.targets) == 1 and isinstance(n.targets[0], ast.Name) and n.targets[0].id == '__all__' and exports is None:
            exports = ast.literal_eval(n.value)
        elif dump(n) == dump(ast.parse("if __name__ == '__main__':\n main()").body[0]):
            continue
        else:
            raise ValueError('frozen public facade contains implementation or reassignment')
    if aliases != PUBLIC_BINDINGS or not isinstance(exports, list) or Counter(exports) != Counter(aliases.keys()):
        raise ValueError('frozen public facade must retain its exact one-way exports')
    return aliases


def validate_main(source, frozen):
    tree, before = ast.parse(source), ast.parse(frozen)
    bindings, original = definitions(tree), definitions(before)
    totals = counts(tree.body)
    names = set(PUBLIC_BINDINGS.values()) | {'partial', 'FastAPI', 'create_app', 'create_lifespan', 'lifespan'}
    if any(totals[n] != 1 for n in names):
        raise ValueError('actual main exports and factories must have one unshadowed binding')
    for module, name in [('functools', 'partial'), ('fastapi', 'FastAPI')]:
        if not any(isinstance(n, ast.ImportFrom) and n.level == 0 and n.module == module and any(a.name == name and a.asname in (None, name) for a in n.names) for n in tree.body):
            raise ValueError('actual factory primitives must retain their real imports')
    expected = {
        'create_public_app': "partial(create_app, profile='public')",
        'create_public_lifespan': 'partial(create_lifespan, component_manager_factory=lambda: None)',
        'lifespan': 'create_lifespan()',
        'public_lifespan': 'create_public_lifespan()',
        'app': 'create_app(lifespan_handler=lifespan, prepare_media_directories=False)',
        'public_app': 'create_public_app(lifespan_handler=public_lifespan, prepare_media_directories=False)',
    }
    for name, expression in expected.items():
        if dump(bindings[name]) != dump(ast.parse(expression, mode='eval').body):
            raise ValueError('actual full/public default or export changed: ' + name)
    for name in ('create_app', 'create_lifespan'):
        n, old = bindings[name], original[name]
        if not isinstance(n, ast.FunctionDef) or n.decorator_list or dump(n.args) != dump(old.args):
            raise ValueError('actual factory arguments/defaults changed: ' + name)
        if any(counts(n.body)[x] for x in ('FastAPI', 'partial', 'create_app', 'create_lifespan')):
            raise ValueError('factory shadows its actual construction primitives')
    factory = bindings['create_app']
    defaults = dict(zip([x.arg for x in factory.args.kwonlyargs], factory.args.kw_defaults))
    if dump(defaults.get('profile')) != dump(ast.Constant(value='full')) or dump(defaults.get('prepare_media_directories')) != dump(ast.Constant(value=True)):
        raise ValueError('canonical factory defaults must remain full and explicit-media')
    if sum(isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == 'FastAPI' for n in ast.walk(factory)) != 1:
        raise ValueError('canonical factory must contain its single actual FastAPI creation')
    for name in BUNDLE[:3]:
        if not isinstance(bindings[name], ast.ClassDef) or dump(bindings[name]) != dump(original[name]):
            raise ValueError('shared actual factory type changed: ' + name)


def import_scope(source, *, needs_public):
    tree = ast.parse(source)
    expected = {'main': ('app', 'main'), 'Path': ('pathlib', 'Path')}
    if needs_public:
        expected['public_main'] = ('app', 'public_main')
    total = counts(tree.body)
    for name, (module, imported) in expected.items():
        if total[name] != 1 or not any(isinstance(n, ast.ImportFrom) and n.level == 0 and n.module == module and any(a.name == imported and a.asname in (None, name) for a in n.names) for n in tree.body):
            raise ValueError('factory test import binding missing or shadowed: ' + name)
    for name in ('sys', 'subprocess'):
        used = any(isinstance(n, ast.Name) and n.id == name and isinstance(n.ctx, ast.Load) for n in ast.walk(tree))
        if used and (total[name] != 1 or not any(isinstance(n, ast.Import) and any(a.name == name and a.asname in (None, name) for a in n.names) for n in tree.body)):
            raise ValueError('cold process primitive import missing or shadowed: ' + name)
    protected = set(expected) | {'public_main', 'subprocess', 'sys'}
    for n in ast.walk(tree):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
            args = [a.arg for a in [*n.args.posonlyargs, *n.args.args, *n.args.kwonlyargs]] + ([n.args.vararg.arg] if n.args.vararg else []) + ([n.args.kwarg.arg] if n.args.kwarg else [])
            if protected.intersection(args) or protected.intersection(k for k,v in counts(n.body).items() if v):
                raise ValueError('factory test lexical scope shadows a protected import')
    return tree


class Rebind(ast.NodeTransformer):
    def visit_ImportFrom(self, n):
        if n.level == 0 and n.module == 'app':
            n.names = [a for a in n.names if a.name != 'public_main']
            if not n.names:
                return None
        return n
    def visit_Attribute(self, n):
        if isinstance(n.value, ast.Name) and n.value.id == 'public_main':
            if n.attr not in PUBLIC_BINDINGS:
                raise ValueError('unresolved frozen public export: ' + n.attr)
            return ast.copy_location(ast.Attribute(value=ast.Name(id='main', ctx=ast.Load()), attr=PUBLIC_BINDINGS[n.attr], ctx=n.ctx), n)
        return self.generic_visit(n)


def alias_assert(name):
    return ast.parse(f'assert public_main.{name} is main.{PUBLIC_BINDINGS[name]}').body[0]


def replace_bundle(function):
    expected = Counter(dump(alias_assert(name)) for name in BUNDLE)
    actual = Counter(dump(n) for n in function.body if isinstance(n, ast.Assert))
    if any(actual[key] != count for key,count in expected.items()):
        raise ValueError('retirement requires the exact complete five-identity bundle')
    body, placed = [], False
    for n in function.body:
        if dump(n) in expected:
            if not placed:
                body.append(ast.parse(ABSENT).body[0])
                body.extend(ast.parse(s).body[0] for s in PROFILE_ASSERTS)
                placed = True
        else:
            body.append(n)
    function.body = body
    return function


def embedded(function):
    assigned = [n for n in function.body if isinstance(n, ast.Assign) and len(n.targets) == 1 and isinstance(n.targets[0], ast.Name) and n.targets[0].id == 'source']
    if len(assigned) != 1 or counts(function.body)['source'] != 1 or not isinstance(assigned[0].value, ast.Constant) or not isinstance(assigned[0].value.value, str):
        raise ValueError('cold source must be one unchanged literal binding')
    calls = [n for n in ast.walk(function) if isinstance(n, ast.Call) and dump(n.func) == dump(ast.parse('subprocess.run', mode='eval').body)]
    if len(calls) != 1 or not calls[0].args or not isinstance(calls[0].args[0], ast.List) or len(calls[0].args[0].elts) != 4:
        raise ValueError('cold source must feed its original subprocess invocation')
    if [dump(x) for x in calls[0].args[0].elts[:3]] != [dump(x) for x in ast.parse('[sys.executable, "-c", source]', mode='eval').body.elts]:
        raise ValueError('cold source is not the actual Python -c input')
    if any(isinstance(n, ast.Name) and n.id == 'source' and isinstance(n.ctx, ast.Load) for n in ast.walk(function) if n not in calls[0].args[0].elts):
        raise ValueError('cold literal is used outside its verified subprocess argument')
    return assigned[0]


def validate_tests(frozen, current):
    oldtree = import_scope(frozen, needs_public=True)
    newtree = import_scope(current, needs_public=False)
    old, new = definitions(oldtree), definitions(newtree)
    bundle = Rebind().visit(replace_bundle(copy.deepcopy(old[BUNDLE_TEST])))
    if dump(bundle) != dump(new[BUNDLE_TEST]):
        raise ValueError('factory identity retirement changed unrelated profile/OpenAPI behavior')
    before, after = copy.deepcopy(old[COLD_TEST]), copy.deepcopy(new[COLD_TEST])
    old_source, new_source = embedded(before), embedded(after)
    old_code = import_scope(old_source.value.value, needs_public=True)
    new_code = import_scope(new_source.value.value, needs_public=False)
    identity = dump(alias_assert('app'))
    if sum(dump(n) == identity for n in old_code.body) != 1:
        raise ValueError('cold source lacks its exact single facade app identity')
    old_code.body = [ast.parse(ABSENT).body[0] if dump(n) == identity else n for n in old_code.body]
    old_code = Rebind().visit(old_code)
    if dump(old_code) != dump(new_code):
        raise ValueError('embedded cold behavior changed beyond exact import/symbol retirement')
    # Canonicalize only the already-proven literal; compare every outer argument,
    # environment, working directory, timeout, guard and return-code assertion.
    old_source.value = ast.Constant(value='<verified identical embedded AST>')
    new_source.value = ast.Constant(value='<verified identical embedded AST>')
    if dump(before) != dump(after):
        raise ValueError('cold subprocess connection or outer behavior changed')
    # The rest of this dedicated file (including real lifespan/failed-start
    # tests and monkeypatch targets) admits only the same export rebinding.
    replace_bundle(old[BUNDLE_TEST])
    embedded(old[COLD_TEST]).value = ast.Constant(value='<verified identical embedded AST>')
    embedded(new[COLD_TEST]).value = ast.Constant(value='<verified identical embedded AST>')
    if dump(Rebind().visit(oldtree)) != dump(newtree):
        raise ValueError('dedicated factory tests changed beyond the proven retirement')


def active_consumers(root):
    for directory in ('backend/app', 'backend/tests', 'backend/scripts', 'scripts'):
        for path in (root/directory).rglob('*.py'):
            if '__pycache__' in path.parts:
                continue
            tree = ast.parse(path.read_text(encoding='utf-8-sig'))
            for n in ast.walk(tree):
                if isinstance(n, ast.Import) and any(a.name == 'app.public_main' or a.name.startswith('app.public_main.') for a in n.names):
                    raise ValueError('retired public facade has a static consumer: ' + str(path))
                if isinstance(n, ast.ImportFrom) and ((n.module is not None and (n.module == 'app.public_main' or n.module.startswith('app.public_main.'))) or (n.module == 'app' and any(a.name == 'public_main' for a in n.names)) or (n.level and (n.module == 'public_main' or (n.module is None and any(a.name == 'public_main' for a in n.names))))):
                    raise ValueError('retired public facade has a from-import consumer: ' + str(path))
                if isinstance(n, ast.Call) and isinstance(n.func, (ast.Name, ast.Attribute)) and (n.func.id if isinstance(n.func, ast.Name) else n.func.attr) in ('import_module', '__import__') and n.args:
                    def literal(value):
                        if isinstance(value, ast.Constant) and isinstance(value.value,str): return value.value
                        if isinstance(value,ast.BinOp) and isinstance(value.op,ast.Add): return literal(value.left)+literal(value.right)
                        return ''
                    value = literal(n.args[0])
                    unresolved_prefix = (isinstance(n.args[0], ast.BinOp) and value.startswith('app.') and 'app.public_main'.startswith(value))
                    bindings = [a.value for a in ast.walk(tree) if isinstance(a, (ast.Assign, ast.AnnAssign)) and any(isinstance(t, ast.Name) and isinstance(n.args[0], ast.Name) and t.id == n.args[0].id for t in (a.targets if isinstance(a, ast.Assign) else [a.target]))]
                    if value.startswith('app.public_main') or unresolved_prefix or any(literal(v).startswith('app.public_main') for v in bindings):
                        raise ValueError('retired public facade has a dynamic consumer: ' + str(path))


def validate(enabled, files, snapshots, root, git_bytes):
    if not enabled:
        return None
    if enabled is not True or files.get(OLD) != MAIN:
        raise ValueError('public facade retirement requires its exact actual main file mapping')
    if (root/OLD).exists() or (root/'backend/app/public_main').exists():
        raise ValueError('retired public facade file/package still exists')
    # Existing-file revisions are intentionally not repeated in the additions
    # ledger. Resolve these two already-reviewed, signed source commits rather
    # than pretending #263 contained the later pure facade or rewriting it.
    for path in (OLD, MAIN):
        if not any(path in snapshot.get('tracked_files', {}) for snapshot in snapshots):
            raise ValueError('retirement original source is not protected: ' + path)
    for commit in (FACADE_SOURCE, FACTORY_SOURCE):
        if git_bytes('merge-base', commit, 'HEAD', root=root).decode().strip() != commit:
            raise ValueError('retirement source must be an ancestor of this candidate')
        message = git_bytes('show', '-s', '--format=%B', commit, root=root).decode()
        if not any(line.startswith('Signed-off-by: ') for line in message.splitlines()):
            raise ValueError('retirement requires the original signed source commit')
    if git_bytes('merge-base', FACADE_SOURCE, FACTORY_SOURCE, root=root).decode().strip() != FACADE_SOURCE:
        raise ValueError('G5 must descend from the original G06 facade source')
    introduced = git_bytes('diff-tree', '--no-commit-id', '--name-only', '--diff-filter=A', '-r', FACADE_SOURCE, root=root).decode().splitlines()
    if TEST not in introduced:
        raise ValueError('dedicated factory test must originate in the signed G06 source')
    def source(commit, path):
        return git_bytes('show', commit + ':' + path, root=root).decode('utf-8-sig')
    facade = source(FACADE_SOURCE, OLD)
    aliases = facade_exports(facade)
    if source(FACTORY_SOURCE, OLD) != facade:
        raise ValueError('G5 changed the protected one-way facade')
    oldmain, oldtest = source(FACTORY_SOURCE, MAIN), source(FACTORY_SOURCE, TEST)
    validate_main(oldmain, source(FACADE_SOURCE, MAIN))
    validate_main((root/MAIN).read_text(encoding='utf-8-sig'),oldmain)
    validate_tests(oldtest,(root/TEST).read_text(encoding='utf-8-sig'))
    active_consumers(root)
    return {'exports':aliases,'frozen_main':oldmain,'frozen_facade':facade}


def required_fragments(values, source, function, proof):
    if proof is None:
        return values
    import_scope(source, needs_public=True)
    if function == BUNDLE_TEST:
        # The original complete bundle was independently validated against the
        # current full function, including all unrelated original assertions.
        expected = Counter(dump(alias_assert(name)) for name in BUNDLE)
        present = Counter(dump(ast.parse(s).body[0]) for s in values)
        if any(present[x] != count for x,count in expected.items()):
            raise ValueError('protected identity bundle is incomplete or altered')
        values = [s for s in values if dump(ast.parse(s).body[0]) not in expected]
        values = [*values,ABSENT,*PROFILE_ASSERTS]
    return [ast.unparse(Rebind().visit(ast.parse(s))).strip() for s in values]
