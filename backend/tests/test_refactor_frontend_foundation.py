"""Final frontend guards must cover new files, not just migrated-name lists."""
from __future__ import annotations

from pathlib import Path
import sys
import subprocess

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts/ci"))
from frontend_completed_boundaries import check_completed_frontend
from check_refactor_frontend_preservation import mapped, verify, verify_retirements
from refactor_boundaries import validate_scope
from check_windows_host_tauri_dev_contract import check_workflow_triggers
import check_refactor_frontend_preservation as frontend_stock


def write(root, path, text):
    target = root / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")


@pytest.mark.parametrize("autocrlf", ["true", "false"])
def test_committed_frontend_bytes_ignore_host_line_endings(monkeypatch, autocrlf):
    monkeypatch.setenv("GIT_CONFIG_COUNT", "1")
    monkeypatch.setenv("GIT_CONFIG_KEY_0", "core.autocrlf")
    monkeypatch.setenv("GIT_CONFIG_VALUE_0", autocrlf)
    source = "browser-tests/playwright.config.ts"
    canonical = subprocess.check_output(["git", "show", f"{frontend_stock.BASE}:{source}"], cwd=ROOT)
    assert frontend_stock.committed_files(ROOT)[source] == canonical


@pytest.mark.parametrize("statement", [
    'import type { X } from "@/features/new/types/x";',
    'export { X } from "../../new/types/x";',
    'const x = import("@/features/new/types/x");',
    'const x = require("../../new/types/x");',
])
def test_unknown_feature_cannot_hide_cross_feature_import(tmp_path, statement):
    write(tmp_path, "features/unlisted/components/card.tsx", statement)
    write(tmp_path, "features/new/types/x.ts", "export type X = string;")
    assert any("refactor_cross_feature" in e for e in check_completed_frontend(tmp_path))


@pytest.mark.parametrize("source,target,expected", [
    ("composition/screens/a.tsx", "@/app/a", "frontend_composition_imports_app"),
    ("components/ui/new.tsx", "@/features/chat/components/chat", "refactor_common_imports_application"),
    ("features/chat/components/chat.tsx", "@/composition/a", "refactor_feature_imports_composition"),
    ("lib/new.ts", "@/testing", "refactor_production_imports_test"),
])
def test_final_reverse_edges_are_rejected(tmp_path, source, target, expected):
    write(tmp_path, source, f'import "{target}";')
    write(tmp_path, "testing/index.ts", "export const fixture = 1;")
    assert any(expected in e for e in check_completed_frontend(tmp_path))


def test_final_valid_actual_files_and_server_route_are_allowed(tmp_path):
    write(tmp_path, "app/page.tsx", 'import "@/composition/screens/chat";')
    write(tmp_path, "composition/screens/chat.tsx", 'import "@/features/chat/components/chat";')
    write(tmp_path, "features/chat/components/chat.tsx", 'import "@/components/ui/button";')
    write(tmp_path, "components/ui/button.tsx", "export const Button = 1;")
    write(tmp_path, "app/api/route.ts", 'import "@/lib/server/proxy";')
    write(tmp_path, "lib/server/proxy.ts", 'import "node:fs";')
    assert check_completed_frontend(tmp_path) == []


def test_transitive_server_dependency_cannot_enter_shared_screen(tmp_path):
    write(tmp_path, "composition/screens/chat.tsx", 'import "@/features/chat/api/request";')
    write(tmp_path, "features/chat/api/request.ts", 'import "@/lib/client";')
    write(tmp_path, "lib/client.ts", 'import "@/lib/server/proxy";')
    write(tmp_path, "lib/server/proxy.ts", 'import "next/headers";')
    assert any("frontend_client_imports_server" in e for e in check_completed_frontend(tmp_path))


def test_static_shell_is_checked_outside_src(tmp_path):
    write(tmp_path, "frontend/src/app/private.ts", "export const x = 1;")
    write(tmp_path, "frontend/static-shell/app/page.tsx", 'import "../../src/app/private";')
    assert any("frontend_composition_imports_app" in e
               for e in check_completed_frontend(tmp_path / "frontend/src"))


@pytest.mark.parametrize("path", ["features/unlisted/ui/x.tsx", "features/unlisted/model/x.ts", "features/unlisted/public.ts", "shared/ui/orphan.tsx"])
def test_unreferenced_legacy_file_is_not_invisible(tmp_path, path):
    write(tmp_path, path, "export const x = 1;")
    assert any("frontend_completed_legacy_file" in e for e in check_completed_frontend(tmp_path))


def test_calculated_dynamic_import_fails_closed(tmp_path):
    write(tmp_path, "features/new/components/a.tsx", "const x = import(destination);")
    assert any("frontend_computed_import" in e for e in check_completed_frontend(tmp_path))


def test_complete_scope_rejects_transition_bridges():
    assert validate_scope({"complete": True, "bridges": [{}]}, frontend=True)


@pytest.mark.parametrize("changed", ["test.skip('works', () => expect(1).toBe(1));", "test('works', () => expect(1).toBe(0));", "test('works', () => {});"])
def test_browser_oracle_cannot_be_skipped_weakened_or_deleted(tmp_path, changed):
    path = "browser-tests/flow.spec.ts"
    original = b"test('works', () => expect(1).toBe(1));"
    write(tmp_path, path, changed)
    assert any("frontend_oracle_changed" in e for e in verify(tmp_path, {path: original}, {}))


def test_missing_source_fails_and_exact_source_move_passes(tmp_path):
    old, new = "frontend/src/features/chat/ui/chat.tsx", "frontend/src/features/chat/components/chat.tsx"
    write(tmp_path, new, "export const Chat = 1;")
    frozen = {old: b"export const Chat = 1;"}
    assert verify(tmp_path, frozen, {})
    assert verify(tmp_path, frozen, {old: new}) == []


def test_path_moves_preserve_entire_browser_assertion(tmp_path):
    path = "browser-tests/flow.spec.ts"
    old, new = "frontend/src/features/chat/ui/chat.tsx", "frontend/src/features/chat/components/chat.tsx"
    original = b'import "@/features/chat/ui/chat"; expect(1).toBe(1);'
    write(tmp_path, path, 'import "@/features/chat/components/chat"; expect(1).toBe(1);')
    assert verify(tmp_path, {path: original}, {old: new}) == []


def retirement_example(root):
    old = "frontend/src/features/old/public.ts"
    view = "frontend/src/composition/screens/view.tsx"
    contract = "frontend/src/features/current/types/read.ts"
    frozen = {old: b'export { View, type Read } from "./implementation";\n'}
    write(root, view, "export function View() { return null; }")
    write(root, contract, "export type Read = { id: string };")
    record = {"reason": "Each caller now uses the actual owner", "verification": ["typecheck", "browser parity"],
              "export_destinations": {"View": view, "Read": contract}}
    return old, view, contract, frozen, {old: view}, {"stage": {"frontend_retirements": {old: record}}}


def test_retired_facade_preserves_each_export_at_its_actual_owner(tmp_path):
    _, _, _, frozen, moves, details = retirement_example(tmp_path)
    assert verify_retirements(tmp_path, frozen, moves, details) == []


@pytest.mark.parametrize("case,expected", [
    ("omit_type", "export_coverage"),
    ("import_only", "missing_export"),
    ("still_present", "source_still_exists"),
    ("unrelated", "unrelated_target"),
    ("implementation", "not_static_facade"),
    ("outside", "missing_export"),
])
def test_facade_retirement_cannot_hide_removed_or_unrelated_code(tmp_path, case, expected):
    old, view, contract, frozen, moves, details = retirement_example(tmp_path)
    record = details["stage"]["frontend_retirements"][old]
    if case == "omit_type":
        del record["export_destinations"]["Read"]
    elif case == "import_only":
        write(tmp_path, contract, 'import type { Read } from "elsewhere";')
    elif case == "still_present":
        write(tmp_path, old, frozen[old].decode())
    elif case == "unrelated":
        moves[old] = "frontend/src/unrelated.ts"
        write(tmp_path, moves[old], "export const placeholder = 1;")
    elif case == "implementation":
        frozen[old] += b"export function importantBehavior() { return 1; }"
    elif case == "outside":
        record["export_destinations"]["Read"] = "../outside.ts"
    assert any(expected in error for error in verify_retirements(tmp_path, frozen, moves, details))


@pytest.mark.parametrize("source,spec", [
    ("frontend/src/app/page.tsx", "@/features/old/public"),
    ("frontend/src/app/page.tsx", "../features/old/public.ts"),
    ("frontend/static-shell/app/page.tsx", "../../src/features/old/public"),
])
def test_retired_facade_rejects_remaining_web_or_static_consumer(tmp_path, source, spec):
    _, _, _, frozen, moves, details = retirement_example(tmp_path)
    write(tmp_path, source, f'import type {{ Read }} from "{spec}";')
    assert any("active_import" in error for error in verify_retirements(tmp_path, frozen, moves, details))


@pytest.mark.parametrize("target", ["../outside.ts", "/absolute.ts", "frontend/../outside.ts"])
def test_preservation_moves_stay_inside_repository(target):
    with pytest.raises(ValueError):
        mapped("old.ts", {"old.ts": target})


@pytest.mark.parametrize("event", ["push", "pull_request"])
@pytest.mark.parametrize("missing", ["frontend/**", "browser-tests/**", "security/frontend*"])
def test_frontend_only_change_reaches_each_host_event(event, missing):
    document = yaml.safe_load((ROOT / ".github/workflows/windows-host-tauri-dev.yml").read_text(encoding="utf-8"))
    document[True][event]["paths"].remove(missing)
    errors = check_workflow_triggers(yaml.safe_dump(document))
    assert f"Hosted Windows {event} paths must include {missing}" in errors


def test_browser_relative_source_move_preserves_assertions_and_rejects_weakened_expectation(tmp_path):
    path = "browser-tests/flow.spec.ts"
    old = "frontend/src/features/characters/model/presentation.ts"
    new = "frontend/src/features/characters/utils/presentation.ts"
    original = b'import { present } from "../frontend/src/features/characters/model/presentation"; expect(present()).toBe(2);'
    moved = 'import { present } from "../frontend/src/features/characters/utils/presentation"; expect(present()).toBe(2);'
    write(tmp_path, path, moved)
    assert verify(tmp_path, {path: original}, {old: new}) == []
    write(tmp_path, path, moved.replace("toBe(2)", "toBe(0)"))
    assert any("frontend_oracle_changed" in error for error in verify(tmp_path, {path: original}, {old: new}))
