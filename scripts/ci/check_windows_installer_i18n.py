#!/usr/bin/env python3
"""Check installer-only translations and the executable final-delete warning."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RESOURCE_INCLUDE = '!include /CHARSET=UTF8 "${ANGMOO_INSTALLER_HOOK_DIR}\\installer-languages.nsh"'
LANG_STRING = re.compile(
    r'^LangString (Angmoo[A-Za-z0-9]+) (1033|1042) '
    r'"((?:\$\\"|[^"])*)"$'
)
MESSAGE_BOX = re.compile(
    r'^MessageBox (\S+) "\$\((Angmoo[A-Za-z0-9]+)\)"(?: (.*))?$'
)
VARIABLE = re.compile(r'\$(?![\\($])([A-Za-z_][A-Za-z0-9_.]*|[0-9])')
MUI_TEXT_OVERRIDES = {
    "MUI_WELCOMEPAGE_TEXT", "MUI_PAGE_HEADER_SUBTEXT", "MUI_LICENSEPAGE_TEXT_BOTTOM"
}


def commands(source: str) -> list[str]:
    """Read this owner's NSIS commands, excluding comments and joining continuations."""
    result: list[str] = []
    pending = ""
    for line in source.splitlines():
        line = line.strip()
        if not line or line.startswith((";", "#")):
            continue
        if line.endswith("\\"):
            pending += line[:-1].rstrip() + " "
            continue
        result.append(pending + line)
        pending = ""
    if pending:
        raise ValueError("unfinished NSIS continuation")
    return result


def translations(source: str) -> dict[str, dict[str, str]]:
    definitions: dict[str, dict[str, str]] = {}
    guards = {
        "!ifndef ANGMOO_INSTALLER_LANGUAGES_INCLUDED",
        "!define ANGMOO_INSTALLER_LANGUAGES_INCLUDED",
        "!endif",
    }
    for command in commands(source):
        if command in guards:
            continue
        match = LANG_STRING.fullmatch(command)
        if match is None:
            raise ValueError("unsupported installer language resource command")
        name, language_id, text = match.groups()
        language = {"1033": "ENGLISH", "1042": "KOREAN"}[language_id]
        if not text.strip():
            raise ValueError(f"empty translation: {name}/{language}")
        pair = definitions.setdefault(name, {})
        if language in pair:
            raise ValueError(f"duplicate translation: {name}/{language}")
        if "$" + "{" in text:
            raise ValueError(f"macro argument in runtime translation: {name}")
        variables = set(VARIABLE.findall(text))
        if variables - {"AngmooMessagePath"}:
            raise ValueError(f"unapproved runtime variable: {name}")
        pair[language] = text
    for name, pair in definitions.items():
        if set(pair) != {"ENGLISH", "KOREAN"}:
            raise ValueError(f"missing translation: {name}")
        if set(VARIABLE.findall(pair["ENGLISH"])) != set(
            VARIABLE.findall(pair["KOREAN"])
        ):
            raise ValueError(f"translation variable mismatch: {name}")
        if not re.search("[가-힣]", pair["KOREAN"]):
            raise ValueError(f"Korean translation is not Korean: {name}")
    return definitions


def validate_full_delete_confirmation(hooks: str) -> None:
    active = "\n".join(commands(hooks))
    try:
        pre = active.split("!macro NSIS_HOOK_PREUNINSTALL\n", 1)[1].split(
            "\n!macroend", 1
        )[0]
        warning = (
            'MessageBox MB_YESNO|MB_ICONSTOP "$(AngmooConfirmFullDelete)" '
            "IDNO angmoo_keep_local_data"
        )
        if pre.count(warning) != 1:
            raise ValueError("executable final-delete warning missing")
        silent = pre.index("IfSilent angmoo_keep_local_data 0")
        update = pre.index("${If} $UpdateMode = 1")
        checkbox = pre.index("${If} $DeleteAppDataCheckboxState <> 1")
        warned = pre.index(warning)
        validated = pre.index(
            '!insertmacro ANGMOO_VERIFY_NOT_REPARSE '
            '"$LOCALAPPDATA\\com.angmoo.desktop" angmoo_legacy'
        )
        confirmed = pre.index("StrCpy $AngmooFullDeleteConfirmed 1")
        deleted = pre.index('RMDir /r "$LOCALAPPDATA\\Angmoo\\canonical"')
        if not silent < update < checkbox < warned < validated < confirmed < deleted:
            raise ValueError("final-delete approval and validation order drifted")
    except (IndexError, ValueError) as error:
        raise ValueError(f"final-delete safety: {error}") from error


def validate(
    config: dict, hooks: str, resource: str, *, generated: str | None = None
) -> dict[str, dict[str, str]]:
    nsis = config["bundle"]["windows"]["nsis"]
    if nsis["languages"] != ["English", "Korean"]:
        raise ValueError("installer languages must be English then Korean")
    if nsis["displayLanguageSelector"] is not True:
        raise ValueError("interactive language selection must be enabled")
    active = commands(hooks)
    if "!define MUI_LANGDLL_ALWAYSSHOW" not in active:
        raise ValueError("interactive reinstall must allow a new language choice")
    if active.count(RESOURCE_INCLUDE) != 1:
        raise ValueError("installer language include missing or duplicated")
    include = active.index(RESOURCE_INCLUDE)
    first_macro = next(index for index, line in enumerate(active) if line.startswith("!macro "))
    if include >= first_macro:
        raise ValueError("language resources must be global NSIS declarations")
    definitions = translations(resource)
    references: set[str] = set()
    for command in active:
        override = re.fullmatch(
            r'!define (MUI_\w+) "\$\((Angmoo[A-Za-z0-9]+)\)"',
            command,
        )
        if any(command.startswith(f"!define {name} ") for name in MUI_TEXT_OVERRIDES):
            if override is None:
                raise ValueError("literal or invalid MUI page translation")
            references.add(override[2])
    for command in active:
        if not command.startswith("MessageBox "):
            continue
        match = MESSAGE_BOX.fullmatch(command)
        if match is None:
            raise ValueError("literal or invalid installer MessageBox")
        references.add(match[2])
    if not references or references != set(definitions):
        raise ValueError("missing or unused installer translation reference")
    path_message = definitions.get("AngmooReparseRejected", {})
    if any("$AngmooMessagePath" not in text for text in path_message.values()):
        raise ValueError("reparse warning must display the actual path")
    if 'StrCpy $AngmooMessagePath "${Target}"' not in active:
        raise ValueError("reparse warning dedicated path assignment missing")
    if "Var AngmooMessagePath" not in active:
        raise ValueError("reparse warning dedicated variable missing")
    validate_full_delete_confirmation(hooks)
    if generated is not None:
        generated_commands = commands(generated)
        welcome = generated_commands.index("!insertmacro MUI_PAGE_WELCOME")
        license_page = generated_commands.index('!insertmacro MUI_PAGE_LICENSE "${LICENSE}"')
        directory = generated_commands.index("!insertmacro MUI_PAGE_DIRECTORY")
        if not welcome < license_page < directory:
            raise ValueError("license header override requires the pinned page order")
        english = generated_commands.index('!insertmacro MUI_LANGUAGE "English"')
        korean = generated_commands.index('!insertmacro MUI_LANGUAGE "Korean"')
        preinstall = generated_commands.index("!insertmacro NSIS_HOOK_PREINSTALL")
        if not english < korean < preinstall:
            raise ValueError("generated language registration order drifted")
        if '!define DISPLAYLANGUAGESELECTOR "true"' not in generated_commands:
            raise ValueError("generated installer disabled language selection")
        if "!insertmacro MUI_LANGDLL_DISPLAY" not in generated_commands:
            raise ValueError("generated language dialog missing")
        if "!insertmacro MUI_UNGETLANGUAGE" not in generated_commands:
            raise ValueError("generated uninstaller language restore missing")
    return definitions


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--generated", type=Path)
    args = parser.parse_args()
    owner = args.root / "desktop" / "src-tauri"
    try:
        definitions = validate(
            json.loads((owner / "tauri.conf.json").read_text(encoding="utf-8")),
            (owner / "installer-hooks.nsh").read_text(encoding="utf-8"),
            (owner / "installer-languages.nsh").read_text(encoding="utf-8"),
            generated=(
                args.generated.read_text(encoding="utf-8") if args.generated else None
            ),
        )
    except (ValueError, KeyError) as error:
        raise SystemExit(f"windows-installer-i18n: {error}") from error
    print(f"windows-installer-i18n: PASS ({len(definitions)} bilingual resources)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
