"""Frozen-source and renamed-document compatibility; no GitHub writes."""
from pathlib import Path
import shutil
import zipfile

import pytest

from scripts.release.prepare import (
    LEGACY_TERMUX_FILES, localized_sources, package_termux_tools, reviewed_notes,
)

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize("modern", [False, True])
def test_fixed_product_tools_match_their_own_bootstrap_allowlist(tmp_path, modern):
    tools = tmp_path / "launcher/termux"
    tools.mkdir(parents=True)
    names = {*LEGACY_TERMUX_FILES, "LICENSE"}
    if modern:
        names.add("command_registration.py")
    for name in names - {"LICENSE"}:
        (tools / name).write_text("frozen source " + name)
    (tmp_path / "LICENSE").write_text("frozen license")
    (tools / "bootstrap.py").write_text("FILES=frozenset(" + repr(names) + ")\n")
    destination = tmp_path / "tools.zip"
    package_termux_tools(destination, tmp_path)
    with zipfile.ZipFile(destination) as archive:
        assert set(archive.namelist()) == names
        assert archive.read("angmoo.py") == b"frozen source angmoo.py"
    original = destination.read_bytes()
    package_termux_tools(destination, tmp_path)
    assert destination.read_bytes() == original


def test_mixed_tools_are_rejected_without_executing_product_source(tmp_path):
    shutil.copytree(ROOT / "launcher/termux", tmp_path / "launcher/termux")
    shutil.copyfile(ROOT / "LICENSE", tmp_path / "LICENSE")
    helper = tmp_path / "launcher/termux/command_registration.py"
    helper.unlink()
    with pytest.raises(ValueError, match="termux_tools_profile_mixed"):
        package_termux_tools(tmp_path / "missing.zip", tmp_path)
    bootstrap = tmp_path / "launcher/termux/bootstrap.py"
    bootstrap.write_text("raise RuntimeError('must not execute')\nFILES=frozenset(make_files())\n")
    with pytest.raises(ValueError, match="termux_tools_profile_invalid"):
        package_termux_tools(tmp_path / "dynamic.zip", tmp_path)


@pytest.mark.parametrize("stem", ["termux", "notes"])
@pytest.mark.parametrize("modern", [False, True])
def test_localized_sources_keep_both_languages(stem, modern):
    english = stem + (".md" if modern else ".en.md")
    pair, selected_modern = localized_sources({english, stem + ".ko.md", "unrelated.md"}, stem)
    assert pair == {"en": english, "ko": stem + ".ko.md"}
    assert selected_modern is modern


@pytest.mark.parametrize("names", [set(), {"notes.md"}, {"notes.ko.md"},
    {"notes.md", "notes.en.md", "notes.ko.md"}])
def test_partial_or_ambiguous_language_layout_is_rejected(names):
    with pytest.raises(ValueError, match="localized_source_layout_invalid"):
        localized_sources(names, "notes")


def test_reviewed_notes_use_only_requested_ref_and_propagate_transport_failure():
    class Evidence:
        def main_source(self, source):
            assert source == "a" * 40
        def read(self, path):
            assert path == "contents/docs/releases/0.1.0?ref=" + "a" * 40
            return [{"type": "file", "name": name} for name in ("notes.md", "notes.ko.md")]
    assert reviewed_notes(Evidence(), "a" * 40, "docs/releases/0.1.0")[1] is True
    class Failure(Evidence):
        def read(self, path):
            raise OSError("transport fixture")
    with pytest.raises(OSError, match="transport fixture"):
        reviewed_notes(Failure(), "a" * 40, "docs/releases/0.1.0")
