"""Only the obsolete, commit-proven Phone interception module may retire."""
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def _module(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts/ci" / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


changes = _module("native_chrome_changes", "post_refactor_contract_changes.py")
preservation = _module("native_chrome_preservation", "check_refactor_preservation.py")


@pytest.mark.parametrize("case", ["valid", "changed_preimage", "still_committed", "resurrected", "active_import", "missing_owner", "unrelated_source"])
def test_native_retirement_requires_exact_deletion_and_surviving_behavior(tmp_path, case):
    source = "desktop/src-tauri/src/phone_resize.rs"
    owners = ["desktop/src-tauri/src/lib.rs", "desktop/src-tauri/src/window_policy.rs",
              "backend/tests/test_l3_er5_tauri_product_shell_contract.py"]
    record = {"id": "retire-native-phone", "implementation_commit": "a" * 40,
              "reason": "standard OS geometry", "review": "approved C07-C09",
              "source_blobs": {owner: "b" * 40 for owner in owners},
              "retired_native_chrome": [{"source": source, "before_sha256": changes.text_digest("old interception")} ]}
    if case == "missing_owner":
        del record["source_blobs"][owners[2]]
    if case == "unrelated_source":
        record["retired_native_chrome"][0]["source"] = "desktop/src-tauri/src/desktop_runtime.rs"
    manifest = tmp_path / changes.MANIFEST
    manifest.parent.mkdir()
    manifest.write_text(json.dumps({"schema_version": 1, "records": [record]}))
    if case in {"resurrected", "active_import"}:
        path = tmp_path / (source if case == "resurrected" else owners[0])
        path.parent.mkdir(parents=True)
        path.write_text("old interception" if case == "resurrected" else "mod phone_resize;")

    def reader(*args, root):
        if args[0] in {"log", "merge-base"}:
            return b""
        if args[0] == "rev-parse":
            return record["source_blobs"][args[1].split(":", 1)[1]].encode()
        if args[0] == "ls-tree":
            return b"tracked" if case == "still_committed" else b""
        return b"wrong preimage" if case == "changed_preimage" else b"old interception"

    if case == "valid":
        assert changes.load(tmp_path, reader=reader) == [record]
    else:
        with pytest.raises(ValueError):
            changes.load(tmp_path, reader=reader)


def test_source_stock_rejects_every_unlisted_missing_file(tmp_path):
    retired = "desktop/src-tauri/src/phone_resize.rs"
    protected = "desktop/src-tauri/src/desktop_runtime.rs"
    records = [{"retired_native_chrome": [{"source": retired}]}]
    assert preservation.check_sources([retired, protected], {}, tmp_path, approved_changes=records) == [
        f"source missing without a surviving mapped destination: {protected} -> {protected}"
    ]
    assert preservation.check_sources([retired], {}, tmp_path)


@pytest.mark.parametrize("case", ["valid", "unrecorded", "missing_other", "unsafe", "missing_feature", "missing_owner_field", "wrong_baseline"])
def test_inventory_uses_verified_retirement_without_losing_feature_or_path_protection(tmp_path, case):
    native = "desktop/src-tauri/src/phone_resize.rs"
    style = "frontend/src/composition/providers/desktop-window-controls.module.css"
    owners = ["desktop/src-tauri/src/lib.rs", "desktop/src-tauri/src/window_policy.rs",
              "backend/tests/test_l3_er5_tauri_product_shell_contract.py",
              "frontend/src/composition/providers/desktop-window-bridge.tsx",
              "frontend/src/composition/navigation/desktop-navigation-toolbar.tsx"]
    record = {"id": "inventory-chrome", "implementation_commit": "a" * 40,
              "reason": "preserve original inventory and validate explicit chrome deletion",
              "review": "C21/P17 inventory regression", "source_blobs": {owner: "b" * 40 for owner in owners},
              "retired_native_chrome": [{"source": native, "before_sha256": changes.text_digest("old native")}],
              "retired_frontend_styles": [{"source": style, "before_sha256": changes.text_digest("old style"),
                                          "consumer": owners[3], "replacement": owners[4]}]}
    manifest = tmp_path / changes.MANIFEST
    manifest.parent.mkdir()
    manifest.write_text(json.dumps({"schema_version": 1, "records": [record]}))

    def reader(*args, root):
        if args[0] in {"log", "merge-base", "ls-tree"}:
            return b""
        if args[0] == "rev-parse":
            return b"b" * 40
        return b"old native" if args[1].endswith(native) else b"old style"

    verified = changes.load(tmp_path, reader=reader)
    (tmp_path / "owned.py").write_text("value = 1\n")
    inventory = {"baseline_commit": "c" * 40, "items": [
        {"id": identifier, "owner": "retained owner", "stage": "retained stage", "status": "MOVED",
         "preserved_contracts": ["retained behavior"], "current_paths": ["owned.py"],
         "target_paths": ["owned.py"], "verification": {"source": "retained evidence"},
         "disposition": "PRESERVE_AND_MOVE_WITH_CONSUMERS"}
        for identifier in [*(f"K{i:02}" for i in range(1, 24)), *(f"G{i:02}" for i in range(1, 14))]
    ]}
    items = {item["id"]: item for item in inventory["items"]}
    items["K12"]["current_paths"].append(native)
    items["K13"]["current_paths"].append(style)
    items["K23"]["current_paths"].append(native)
    if case == "unrecorded":
        verified = []
    elif case == "missing_other":
        items["K12"]["current_paths"].append("desktop/src-tauri/src/desktop_runtime.rs")
    elif case == "unsafe":
        items["K12"]["current_paths"].append("../outside.rs")
    elif case == "missing_feature":
        inventory["items"].remove(items["K23"])
    elif case == "missing_owner_field":
        del items["K12"]["owner"]
    elif case == "wrong_baseline":
        inventory["baseline_commit"] = "d" * 40
    errors = preservation.check_inventory(inventory, {"commit": "c" * 40}, tmp_path, approved_changes=verified)
    if case == "valid":
        assert errors == []
    elif case == "unrecorded":
        assert errors == [f"K12: missing or unsafe path {native}", f"K13: missing or unsafe path {style}",
                          f"K23: missing or unsafe path {native}"]
    elif case == "missing_other":
        assert errors == ["K12: missing or unsafe path desktop/src-tauri/src/desktop_runtime.rs"]
    elif case == "unsafe":
        assert errors == ["K12: missing or unsafe path ../outside.rs"]
    elif case == "missing_feature":
        assert errors == ["K01-K23/G01-G13 coverage is incomplete or duplicated"]
    elif case == "missing_owner_field":
        assert errors == ["K12: missing owner"]
    else:
        assert errors == ["feature inventory baseline commit differs"]
