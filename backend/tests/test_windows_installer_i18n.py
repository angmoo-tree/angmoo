from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
CHECKER = ROOT / "scripts/ci/check_windows_installer_i18n.py"
spec = importlib.util.spec_from_file_location("installer_i18n", CHECKER)
assert spec is not None and spec.loader is not None
checker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(checker)


@pytest.fixture
def owner() -> tuple[dict, str, str]:
    directory = ROOT / "desktop/src-tauri"
    return (
        json.loads((directory / "tauri.conf.json").read_text(encoding="utf-8")),
        (directory / "installer-hooks.nsh").read_text(encoding="utf-8"),
        (directory / "installer-languages.nsh").read_text(encoding="utf-8"),
    )


def test_actual_installer_references_bilingual_resources(owner) -> None:
    config, hooks, resource = owner
    definitions = checker.validate(config, hooks, resource)
    assert definitions["AngmooRestoreFailed"] != definitions["AngmooUpgradeFailedRestored"]
    assert "$AngmooMessagePath" in definitions["AngmooReparseRejected"]["KOREAN"]
    # Warnings retain state differences and the full account-wide deletion scope.
    warning = definitions["AngmooConfirmFullDelete"]
    assert "This cannot be undone" in warning["ENGLISH"]
    assert "이 작업은 되돌릴 수 없어요" in warning["KOREAN"]
    assert {"memories", "chats", "images"} <= set(
        warning["ENGLISH"].replace(",", "").split()
    )


@pytest.mark.parametrize("mutation", (
    "missing_korean", "duplicate", "wrong_reference", "literal",
    "unapproved_register", "variable_mismatch", "include_in_section",
    "choice_not_shown_again", "untranslated_korean", "unreferenced", "literal_welcome",
    "literal_license_subtitle", "literal_license_consent",
))
def test_language_checker_rejects_broken_contract(owner, mutation: str) -> None:
    config, hooks, resource = owner
    korean = next(line for line in resource.splitlines() if line.startswith(
        "LangString AngmooReparseRejected 1042"
    ))
    english = next(line for line in resource.splitlines() if line.startswith(
        "LangString AngmooReparseRejected 1033"
    ))
    if mutation == "missing_korean":
        resource = resource.replace(korean, "")
    elif mutation == "duplicate":
        resource += "\n" + english
    elif mutation == "wrong_reference":
        hooks = hooks.replace("$(AngmooRuntimeNotClosed)", "$(AngmooTypo)")
    elif mutation == "literal":
        hooks = hooks.replace("$(AngmooRuntimeNotClosed)", "English only")
    elif mutation == "literal_welcome":
        hooks = hooks.replace("$(AngmooWelcomeText)", "English only")
    elif mutation == "literal_license_subtitle":
        hooks = hooks.replace("$(AngmooLicenseSubtitle)", "English only")
    elif mutation == "literal_license_consent":
        hooks = hooks.replace("$(AngmooLicenseBottomText)", "English only")
    elif mutation == "unapproved_register":
        resource = resource.replace("$AngmooMessagePath", "$R7")
    elif mutation == "variable_mismatch":
        resource = resource.replace(korean, korean.replace("$AngmooMessagePath", "path"))
    elif mutation == "include_in_section":
        hooks = hooks.replace(checker.RESOURCE_INCLUDE, "")
        hooks = hooks.replace("!macro NSIS_HOOK_PREINSTALL",
            "!macro NSIS_HOOK_PREINSTALL\n" + checker.RESOURCE_INCLUDE)
    elif mutation == "choice_not_shown_again":
        hooks = hooks.replace("!define MUI_LANGDLL_ALWAYSSHOW", "")
    elif mutation == "untranslated_korean":
        resource = resource.replace(korean, english.replace("1033", "1042"))
    elif mutation == "unreferenced":
        resource += (
            '\nLangString AngmooUnused 1033 "Unused"\n'
            'LangString AngmooUnused 1042 "미사용"\n'
        )
    with pytest.raises(ValueError):
        checker.validate(config, hooks, resource)


@pytest.mark.parametrize("mutation", ("no_dialog", "reversed", "third_language"))
def test_language_settings_are_explicit(owner, mutation: str) -> None:
    config, hooks, resource = owner
    nsis = config["bundle"]["windows"]["nsis"]
    if mutation == "no_dialog":
        nsis["displayLanguageSelector"] = False
    elif mutation == "reversed":
        nsis["languages"].reverse()
    else:
        nsis["languages"].append("French")
    with pytest.raises(ValueError):
        checker.validate(config, hooks, resource)


@pytest.mark.parametrize("mutation", ("comment_only", "no_no_branch", "early_confirmation"))
def test_final_delete_requires_executed_warning_and_late_confirmation(owner, mutation) -> None:
    _, hooks, _ = owner
    if mutation == "comment_only":
        hooks = hooks.replace('  MessageBox MB_YESNO|MB_ICONSTOP', '; MessageBox MB_YESNO|MB_ICONSTOP')
    elif mutation == "no_no_branch":
        hooks = hooks.replace("IDNO angmoo_keep_local_data", "IDNO wrong_branch")
    else:
        hooks = hooks.replace("  StrCpy $AngmooFullDeleteConfirmed 1", "")
        hooks = hooks.replace(
            "!macro NSIS_HOOK_PREUNINSTALL",
            "!macro NSIS_HOOK_PREUNINSTALL\n  StrCpy $AngmooFullDeleteConfirmed 1",
        )
    with pytest.raises(ValueError, match="final-delete safety"):
        checker.validate_full_delete_confirmation(hooks)


def test_generated_order_and_uninstaller_restore_are_verified(owner) -> None:
    config, hooks, resource = owner
    generated = (
        "!insertmacro MUI_PAGE_WELCOME\n"
        '!insertmacro MUI_PAGE_LICENSE "${LICENSE}"\n'
        "!insertmacro MUI_PAGE_DIRECTORY\n"
        '!define DISPLAYLANGUAGESELECTOR "true"\n'
        '!insertmacro MUI_LANGUAGE "English"\n'
        '!insertmacro MUI_LANGUAGE "Korean"\n'
        "!insertmacro MUI_LANGDLL_DISPLAY\n"
        "!insertmacro NSIS_HOOK_PREINSTALL\n"
        "!insertmacro MUI_UNGETLANGUAGE\n"
    )
    checker.validate(config, hooks, resource, generated=generated)
    with pytest.raises(ValueError, match="uninstaller"):
        checker.validate(config, hooks, resource, generated=generated.replace(
            "!insertmacro MUI_UNGETLANGUAGE", ""
        ))
    with pytest.raises(ValueError, match="order"):
        checker.validate(config, hooks, resource, generated=(
            "!insertmacro NSIS_HOOK_PREINSTALL\n" + generated
        ))
    with pytest.raises(ValueError, match="page order"):
        checker.validate(config, hooks, resource, generated=generated.replace(
            "!insertmacro MUI_PAGE_DIRECTORY\n", ""
        ).replace("!insertmacro MUI_PAGE_WELCOME\n",
                  "!insertmacro MUI_PAGE_DIRECTORY\n!insertmacro MUI_PAGE_WELCOME\n"))
