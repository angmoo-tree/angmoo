"""Metadata hooks cannot hide extra registration work or change primitives."""
import ast
import importlib.util
from pathlib import Path

import pytest

spec=importlib.util.spec_from_file_location('registration_preservation',Path(__file__).resolve().parents[2]/'scripts/ci/check_refactor_preservation.py')
checks=importlib.util.module_from_spec(spec)
spec.loader.exec_module(checks)
SOURCE='''
from sqlalchemy import event, inspect
from app.models import Base
def install_canonical_write_fences(target, connection, **kwargs):
    if connection.dialect.name == "sqlite" and "world_deletion_requests" in inspect(connection).get_table_names():
        from app.runtime.world_deletion.fences import install_fences
        install_fences(connection)
def register_models():
    import app.domains.identity.models
    if not event.contains(Base.metadata, "after_create", install_canonical_write_fences):
        event.listen(Base.metadata, "after_create", install_canonical_write_fences)
    return Base.metadata
'''

def evidence(function):
    return [{'definitions':[{'source':'backend/app/runtime/persistence/model_registration.py',
        'symbol':'register_models','after_ast':ast.dump(function,include_attributes=False)}]}]

def test_exact_committed_hook_keeps_direct_owner_registration_and_pure_registry():
    tree=ast.parse(SOURCE)
    function=tree.body[-1]
    imports=checks.validated_registration_owner_imports(tree,function,evidence(function))
    assert [alias.name for node in imports for alias in node.names]==['app.domains.identity.models']
    with pytest.raises(ValueError,match='exact committed hook'):
        checks.validated_registration_owner_imports(tree,function,[])
    plain=ast.parse('def register_models():\n import app.domains.identity.models\n return Base.metadata').body[0]
    assert checks.validated_registration_owner_imports(ast.Module(body=[plain],type_ignores=[]),plain,[])

@pytest.mark.parametrize('old,new',[
    ('after_create','before_create'),
    ('connection.dialect.name == "sqlite"','connection.dialect.name == "postgresql"'),
    ('from sqlalchemy import event, inspect','from unknown import event, inspect'),
    ('    return Base.metadata','    start_engine()\n    return Base.metadata'),
])
def test_approved_source_cannot_expand_hook_scope_or_start_other_work(old,new):
    tree=ast.parse(SOURCE.replace(old,new))
    function=tree.body[-1]
    with pytest.raises(ValueError,match='exact committed hook'):
        checks.validated_registration_owner_imports(tree,function,evidence(function))
