"""The approved local font/codec fixtures must not widen the design asset gate."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import shutil

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "creator_design_contract", REPO_ROOT / "scripts/ci/check_frontend_design_contract.py"
)
assert SPEC is not None and SPEC.loader is not None
checker = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(checker)


@pytest.fixture
def reviewed_assets(tmp_path, monkeypatch):
    policy = json.loads((REPO_ROOT / "security/frontend_design_policy.json").read_text(encoding="utf-8"))
    files = {"security/license_policy.json"}
    for item in policy["reviewed_local_fonts"]:
        files.update(item[field] for field in ("path", "stylesheet", "source_notice", "public_notice"))
    files.update(item["path"] for item in policy["diagnostic_fixture_assets"])
    for relative in files:
        destination = tmp_path / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(REPO_ROOT / relative, destination)
    monkeypatch.setattr(checker, "ROOT", tmp_path)
    return tmp_path, policy


def test_exact_reviewed_assets_are_accepted(reviewed_assets):
    _, policy = reviewed_assets
    fonts, stylesheets, photos = checker._reviewed_local_assets(policy)
    assert fonts == {policy["reviewed_local_fonts"][0]["path"]}
    assert stylesheets == {policy["reviewed_local_fonts"][0]["stylesheet"]}
    assert photos == {item["path"] for item in policy["diagnostic_fixture_assets"]}


@pytest.mark.parametrize("replacement", [
    'url("https://example.invalid/font.ttf")',
    'url("../../assets/fonts/quicksand/unreviewed.ttf")',
])
def test_remote_or_different_font_url_is_rejected(reviewed_assets, replacement):
    root, policy = reviewed_assets
    stylesheet = root / policy["reviewed_local_fonts"][0]["stylesheet"]
    stylesheet.write_text(stylesheet.read_text(encoding="utf-8").replace(
        'url("../../assets/fonts/quicksand/Quicksand-wght.ttf")', replacement
    ), encoding="utf-8")
    with pytest.raises(ValueError, match="exact local asset"):
        checker._reviewed_local_assets(policy)


def test_font_digest_is_required(reviewed_assets):
    root, policy = reviewed_assets
    (root / policy["reviewed_local_fonts"][0]["path"]).write_bytes(b"unreviewed-font")
    with pytest.raises(ValueError, match="licensed asset digest"):
        checker._reviewed_local_assets(policy)


def test_extra_font_face_is_rejected(reviewed_assets):
    root, policy = reviewed_assets
    stylesheet = root / policy["reviewed_local_fonts"][0]["stylesheet"]
    stylesheet.write_text(stylesheet.read_text(encoding="utf-8") +
        '\n@font-face { src: url("https://example.invalid/font.ttf"); }\n', encoding="utf-8")
    with pytest.raises(ValueError, match="exact local asset"):
        checker._reviewed_local_assets(policy)


def test_public_notice_must_match_original(reviewed_assets):
    root, policy = reviewed_assets
    (root / policy["reviewed_local_fonts"][0]["public_notice"]).write_bytes(b"not-the-OFL")
    with pytest.raises(ValueError, match="original OFL notice"):
        checker._reviewed_local_assets(policy)


def test_diagnostic_photo_tampering_is_rejected(reviewed_assets):
    root, policy = reviewed_assets
    (root / policy["diagnostic_fixture_assets"][0]["path"]).write_bytes(b"changed-photo")
    with pytest.raises(ValueError, match="exact reviewed synthetic fixture"):
        checker._reviewed_local_assets(policy)


def test_real_unc_path_stays_forbidden_but_regex_escape_is_not_a_path():
    assert checker.ABSOLUTE_WINDOWS_UNC_PATH.search(r'"\\server\share\Angmoo"')
    assert not checker.ABSOLUTE_WINDOWS_UNC_PATH.search(r'/[.*+?^${}()|[\]\\]/g')
