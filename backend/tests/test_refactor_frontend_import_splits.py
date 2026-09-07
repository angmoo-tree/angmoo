"""A facade split may move imports but cannot weaken the frozen browser oracle."""
from pathlib import Path
import sys
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts/ci"))
from check_refactor_frontend_preservation import verify, rewrite_split_imports


def sources(root):
    for name in ("A", "B"):
        path = root / f"frontend/src/features/example/types/{name.lower()}.ts"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"export type {name} = {{ id: string }};", encoding="utf-8")
    return {"frontend/src/features/example/public.ts": {name: f"frontend/src/features/example/types/{name.lower()}.ts" for name in ("A", "B")}}


def test_split_keeps_type_aliases_and_every_assertion(tmp_path):
    splits = sources(tmp_path)
    original = 'import type { A as LocalA, B } from "../frontend/src/features/example/public";\nexpect(items).toHaveLength(3);\n'
    expected = 'import type { A as LocalA } from "../frontend/src/features/example/types/a";\nimport type { B } from "../frontend/src/features/example/types/b";\nexpect(items).toHaveLength(3);\n'
    path = tmp_path / "browser-tests/example.spec.ts"
    path.parent.mkdir(parents=True)
    path.write_text(expected, encoding="utf-8")
    assert rewrite_split_imports(original, {}, splits, tmp_path) == expected
    assert verify(tmp_path, {"browser-tests/example.spec.ts": original.encode()}, {}, splits) == []
    path.write_text(expected.replace("toHaveLength(3)", "toHaveLength(2)"), encoding="utf-8")
    assert any("frontend_oracle_changed" in e for e in verify(tmp_path, {"browser-tests/example.spec.ts": original.encode()}, {}, splits))


@pytest.mark.parametrize("destination", ["../outside.ts", "frontend/src/features/example/types/missing.ts", "frontend/src/features/example/types/b.ts"])
def test_split_rejects_escape_missing_and_wrong_declaration(tmp_path, destination):
    splits = sources(tmp_path)
    splits["frontend/src/features/example/public.ts"]["A"] = destination
    with pytest.raises(ValueError, match="invalid split import declaration"):
        rewrite_split_imports('import type { A } from "@/features/example/public";', {}, splits, tmp_path)


def test_split_cannot_drop_an_unmapped_binding(tmp_path):
    splits = sources(tmp_path)
    with pytest.raises(ValueError, match="unmapped split import binding"):
        rewrite_split_imports('import type { A, Forgotten } from "@/features/example/public";', {}, splits, tmp_path)
