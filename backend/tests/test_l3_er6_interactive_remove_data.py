from __future__ import annotations

import hashlib
import os
from pathlib import Path
import shutil
import subprocess

import pytest


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
HOOKS_PATH = REPOSITORY_ROOT / "desktop" / "src-tauri" / "installer-hooks.nsh"
OWNED_DATA_CHILDREN = (
    "canonical",
    "graph",
    "search",
    "media",
    "secrets",
    "runtime",
    "logs",
    "webview",
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _is_reparse(path: Path) -> bool:
    return path.is_symlink() or bool(
        getattr(os.path, "isjunction", lambda _path: False)(path)
    )


def _build_fixture(tmp_path: Path) -> tuple[Path, tuple[Path, ...]]:
    root = tmp_path / "Angmoo"
    for child in OWNED_DATA_CHILDREN:
        target = root / child / "synthetic-proof.txt"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(f"synthetic-{child}\n", encoding="utf-8")
    (root / "localappdata-migration-v1.json").write_text(
        '{"synthetic_fixture":true}\n', encoding="utf-8"
    )
    outside = (
        tmp_path / "Angmoo-DO-NOT-DELETE" / "outside-localappdata-sentinel.txt",
        tmp_path / "outside-temp-sentinel.txt",
        tmp_path / "outside-documents-sentinel.txt",
    )
    for index, sentinel in enumerate(outside):
        sentinel.parent.mkdir(parents=True, exist_ok=True)
        sentinel.write_text(f"outside-{index}\n", encoding="utf-8")
    return root, outside


def _snapshot(root: Path, outside: tuple[Path, ...]) -> dict[str, str]:
    paths = [path for path in root.rglob("*") if path.is_file()]
    paths.extend(outside)
    return {str(path): _sha256(path) for path in paths}


def _full_delete_authorized(
    *, silent: bool, update: bool, checkbox: bool, final_yes: bool
) -> bool:
    return not silent and not update and checkbox and final_yes


def _apply_synthetic_delete(root: Path, *, confirmed: bool) -> None:
    """Model the reviewed NSIS allow-list against pytest's isolated tmp root."""

    if not confirmed:
        return
    targets = (root, *(root / child for child in OWNED_DATA_CHILDREN))
    if any(path.exists() and _is_reparse(path) for path in targets):
        raise RuntimeError("reparse_target_rejected_before_delete")
    for child in OWNED_DATA_CHILDREN:
        target = root / child
        if target.exists():
            shutil.rmtree(target)
    (root / "localappdata-migration-v1.json").unlink(missing_ok=True)
    try:
        root.rmdir()
    except OSError:
        # Unknown siblings are never recursively removed by the uninstaller.
        pass


def _make_directory_reparse(link: Path, target: Path) -> None:
    if os.name == "nt":
        result = subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(link), str(target)],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            pytest.skip(f"junction_unavailable: {result.stderr or result.stdout}")
    else:
        link.symlink_to(target, target_is_directory=True)


def test_confirmed_state_is_ordered_after_all_validations() -> None:
    hooks = HOOKS_PATH.read_text(encoding="utf-8")
    warning = hooks.index("Permanently delete every Angmoo World")
    final_validation = hooks.index(
        '!insertmacro ANGMOO_VERIFY_NOT_REPARSE "$LOCALAPPDATA\\com.angmoo.desktop" angmoo_legacy'
    )
    confirmed = hooks.index("StrCpy $AngmooFullDeleteConfirmed 1")
    first_delete = hooks.index('RMDir /r "$LOCALAPPDATA\\Angmoo\\canonical"')
    post = hooks.split("!macro NSIS_HOOK_POSTUNINSTALL", 1)[1]

    assert warning < final_validation < confirmed < first_delete
    assert "${If} $AngmooFullDeleteConfirmed = 1" in post
    assert "$DeleteAppDataCheckboxState" not in post


@pytest.mark.parametrize(
    ("silent", "update", "checkbox", "final_yes"),
    (
        (True, False, True, True),
        (False, True, True, True),
        (False, False, False, False),
        (False, False, True, False),
    ),
)
def test_preserve_and_cancel_paths_change_no_fixture_bytes(
    tmp_path: Path,
    silent: bool,
    update: bool,
    checkbox: bool,
    final_yes: bool,
) -> None:
    root, outside = _build_fixture(tmp_path)
    before = _snapshot(root, outside)

    _apply_synthetic_delete(
        root,
        confirmed=_full_delete_authorized(
            silent=silent,
            update=update,
            checkbox=checkbox,
            final_yes=final_yes,
        ),
    )

    assert _snapshot(root, outside) == before


def test_confirmed_delete_removes_only_owned_data_and_marker(tmp_path: Path) -> None:
    root, outside = _build_fixture(tmp_path)
    outside_hashes = {path: _sha256(path) for path in outside}

    _apply_synthetic_delete(root, confirmed=True)

    assert not root.exists()
    assert {path: _sha256(path) for path in outside} == outside_hashes


def test_unknown_product_child_is_not_recursively_deleted(tmp_path: Path) -> None:
    root, outside = _build_fixture(tmp_path)
    unknown = root / "future-unreviewed-child" / "proof.txt"
    unknown.parent.mkdir()
    unknown.write_text("preserve\n", encoding="utf-8")
    unknown_hash = _sha256(unknown)

    _apply_synthetic_delete(root, confirmed=True)

    assert root.is_dir()
    assert _sha256(unknown) == unknown_hash
    assert all(path.exists() for path in outside)


def test_reparse_trap_fails_before_any_child_delete(tmp_path: Path) -> None:
    root, outside = _build_fixture(tmp_path)
    trapped = root / "media"
    shutil.rmtree(trapped)
    outside_media = tmp_path / "Angmoo-DO-NOT-DELETE" / "outside-media"
    outside_media.mkdir()
    outside_proof = outside_media / "proof.txt"
    outside_proof.write_text("outside-media\n", encoding="utf-8")
    _make_directory_reparse(trapped, outside_media)
    canonical_proof = root / "canonical" / "synthetic-proof.txt"

    with pytest.raises(RuntimeError, match="reparse_target_rejected_before_delete"):
        _apply_synthetic_delete(root, confirmed=True)

    assert canonical_proof.exists()
    assert (root / "localappdata-migration-v1.json").exists()
    assert outside_proof.read_text(encoding="utf-8") == "outside-media\n"
    assert all(path.exists() for path in outside)
