import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("model_retirement_preservation", ROOT / "scripts/ci/check_refactor_preservation.py")
p = importlib.util.module_from_spec(spec)
spec.loader.exec_module(p)

OLD = "app.models.auth"
OWNER = "app.domains.identity.models"
OWNER_PATH = "backend/app/domains/identity/models.py"
ORIGINAL_PATH = "backend/app/domains/identity/infrastructure/sqlalchemy_auth_models.py"
BASE = "from sqlalchemy.orm import DeclarativeBase\nclass Base(DeclarativeBase):\n    pass\n"
MODEL = "from app.models import Base\nclass User(Base):\n    __tablename__ = 'users'\n"
REGISTRATION = "from app.models import Base\ndef register_models():\n    import app.domains.identity.models\n    return Base.metadata\n"


@pytest.fixture
def candidate(tmp_path, monkeypatch):
    def write(path, text):
        target = tmp_path / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
    write("backend/app/models.py", BASE)
    write(OWNER_PATH, MODEL)
    write("backend/app/runtime/persistence/model_registration.py", REGISTRATION)
    frozen = {
        "backend/app/core/db.py": BASE,
        "backend/app/models/auth.py": f"from {ORIGINAL_PATH[8:-3].replace('/', '.')} import User\n__all__ = ['User']\n",
        ORIGINAL_PATH: MODEL,
    }
    monkeypatch.setattr(p, "git_bytes", lambda *args, **kwargs: frozen[args[-1]].encode())
    snapshots = [{"tracked_files": {name: name for name in frozen}}]
    files = {"backend/app/models/auth.py": OWNER_PATH, ORIGINAL_PATH: OWNER_PATH}
    return tmp_path, write, frozen, snapshots, files


def test_frozen_pure_model_alias_can_retire_only_with_actual_registered_classes(candidate):
    root, _, _, snapshots, files = candidate
    assert p.validated_model_facade_retirements({OLD: OWNER}, files, snapshots, root) == {OLD: OWNER}
    before = f"assert imports[{OLD!r}] == {{{OWNER!r}}}"
    assert p.retired_model_assertion(before, {OLD: OWNER}) == f"assert {OLD!r} not in imports"


@pytest.mark.parametrize("mutation", [
    "remaining_facade", "remaining_import", "relative_import", "changed_class",
    "missing_class", "duplicate_base", "wrong_base", "missing_registration",
    "conditional_registration", "base_rebinding", "frozen_implementation", "wrong_export",
    "class_rebinding", "registration_rebinding", "registration_decorator", "registration_argument",
])
def test_incomplete_or_behavior_changing_model_retirement_is_rejected(candidate, mutation):
    root, write, frozen, snapshots, files = candidate
    if mutation == "remaining_facade":
        write("backend/app/models/auth.py", f"from {OWNER} import User\n")
    elif mutation == "remaining_import":
        write("backend/app/runtime/consumer.py", f"from {OLD} import User\n")
    elif mutation == "relative_import":
        write("backend/app/runtime/consumer.py", "from ..models import auth\n")
    elif mutation == "changed_class":
        write(OWNER_PATH, MODEL.replace("'users'", "'different'"))
    elif mutation == "missing_class":
        write(OWNER_PATH, "from app.models import Base\n")
    elif mutation == "duplicate_base":
        write("backend/app/runtime/duplicate.py", BASE)
    elif mutation == "wrong_base":
        write(OWNER_PATH, MODEL.replace("from app.models import Base", "from other import Base"))
    elif mutation == "missing_registration":
        write("backend/app/runtime/persistence/model_registration.py", REGISTRATION.replace("    import app.domains.identity.models\n", ""))
    elif mutation == "conditional_registration":
        write("backend/app/runtime/persistence/model_registration.py", REGISTRATION.replace("    import", "    if False:\n        import"))
    elif mutation == "base_rebinding":
        write("backend/app/runtime/persistence/model_registration.py", REGISTRATION + "Base = object()\n")
    elif mutation == "frozen_implementation":
        frozen["backend/app/models/auth.py"] += "def behavior():\n    return 1\n"
    elif mutation == "wrong_export":
        frozen["backend/app/models/auth.py"] = frozen["backend/app/models/auth.py"].replace("['User']", "['Other']")
    elif mutation == "class_rebinding":
        write(OWNER_PATH, MODEL + "User = object()\n")
    elif mutation == "registration_rebinding":
        write("backend/app/runtime/persistence/model_registration.py", REGISTRATION + "register_models = lambda: None\n")
    elif mutation == "registration_decorator":
        write("backend/app/runtime/persistence/model_registration.py", REGISTRATION.replace("def register_models", "@decorator\ndef register_models"))
    elif mutation == "registration_argument":
        write("backend/app/runtime/persistence/model_registration.py", REGISTRATION.replace("register_models()", "register_models(skip=False)"))
    with pytest.raises(ValueError):
        p.validated_model_facade_retirements({OLD: OWNER}, files, snapshots, root)


@pytest.mark.parametrize("fragment", [
    "assert imports['app.models.other'] == {'app.domains.identity.models'}",
    "assert imports['app.models.auth'] >= {'app.domains.identity.models'}",
    "assert imports['app.models.auth'] == {'app.domains.identity.models', 'extra'}",
    "assert imports['app.models.auth'] == {'wrong.owner'}",
    "assert len(users) == 1",
    "assert allowed is True",
])
def test_retirement_does_not_authorize_other_assertion_changes(fragment):
    assert p.retired_model_assertion(fragment, {OLD: OWNER}) == fragment


def test_non_model_module_and_unmapped_facade_are_rejected(candidate):
    root, _, _, snapshots, files = candidate
    with pytest.raises(ValueError):
        p.validated_model_facade_retirements({"app.services.auth": OWNER}, files, snapshots, root)
    with pytest.raises(ValueError):
        p.validated_model_facade_retirements({OLD: OWNER}, {}, snapshots, root)
