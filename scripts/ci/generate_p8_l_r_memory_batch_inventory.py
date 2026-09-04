"""Generate/check the current Memory v2 runtime closure, freezing Today v8."""

import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
OUTPUT = ROOT / "docs/architecture/p8-l-r-memory-batch-inventory.json"
PREDECESSOR = ROOT / "docs/architecture/p8-l-r-today-sns-activity-inventory.json"
PREDECESSOR_SHA256 = "2120ef3cccb09753119deebd7025f1f9a01d316c518c5d2eda053c5221cbf5ec"

from app.domains.memory.domain import batch_policy as policy
from app.domains.memory.infrastructure.batch_models import MEMORY_BATCH_TABLES
from app.runtime.migrations.sqlite_versions.registry import load_sqlite_manifest


def record(path):
    data = path.read_bytes().replace(b"\r\n", b"\n")
    return {
        "path": path.relative_to(ROOT).as_posix(),
        "sha256": hashlib.sha256(data).hexdigest(),
    }


def build_inventory():
    predecessor = record(PREDECESSOR)
    if predecessor["sha256"] != PREDECESSOR_SHA256:
        raise ValueError("frozen Today predecessor drift")
    manifest = load_sqlite_manifest(9)
    files = set()
    for pattern in (
        "backend/app/domains/memory/**/*.py",
        "backend/app/runtime/memory/*.py",
        "backend/app/runtime/memory_selection_provider.py",
        "backend/app/runtime/memory_privacy.py",
        "backend/app/integrations/llm/memory_selection.py",
        "backend/app/runtime/migrations/sqlite_versions/v8_to_v9_memory_batch.py",
        "backend/app/runtime/migrations/sqlite_versions/manifests/v9.json",
        "backend/app/runtime/persistence/sqlite_schema.py",
        "backend/app/public_main.py",
        "backend/app/runtime/desktop_sidecar.py",
        "backend/app/runtime/single_backend_components.py",
        "backend/app/api/v1/routes/memory.py",
        "backend/app/services/auth.py",
        "backend/app/services/agents.py",
        "backend/tests/test_p8_l_r_memory_batch*.py",
        "desktop/src-tauri/src/shutdown_runtime.rs",
        "desktop/src-tauri/src/lib.rs",
        "desktop/src-tauri/src/desktop_runtime.rs",
        "frontend/src/features/memory/**/*.*",
        "frontend/src/shared/runtime/desktop-shutdown-overlay.tsx",
        "frontend/src/shared/runtime/desktop-runtime-gate.tsx",
        "frontend/src/shared/desktop/product-window.ts",
        "browser-tests/memory-batch-fixture.ts",
        ".github/workflows/windows-installer.yml",
        "scripts/ci/*windows_installer_supported_upgrade*",
        "docs/architecture/p8-l-r-memory-batch.md",
        "scripts/ci/generate_p8_l_r_memory_batch_inventory.py",
    ):
        files.update(
            path
            for path in ROOT.glob(pattern)
            if path.is_file() and "__pycache__" not in path.parts
        )
    return {
        "schema_version": 1,
        "owner_stage": "P8-L-R-MEMORY-BATCH",
        "predecessor": predecessor,
        "schema": {
            "embedded_schema_version": 9,
            "schema_digest": manifest.schema_digest,
            "canonical_table_count": manifest.canonical_table_count,
            "source_revision": manifest.source_revision,
            "new_tables": list(MEMORY_BATCH_TABLES),
        },
        "bounds": {
            "candidates": policy.MAX_SELECTION_CANDIDATES,
            "input_characters": policy.MAX_SELECTION_INPUT_CHARACTERS,
            "input_utf8_bytes": policy.MAX_SELECTION_INPUT_UTF8_BYTES,
            "input_normalized_byte_token_bound": policy.MAX_SELECTION_INPUT_TOKEN_BOUND,
            "input_native_tokenizer": False,
            "output_tokens": policy.MAX_SELECTION_OUTPUT_TOKENS,
            "durable_attempts": policy.MAX_BATCH_ATTEMPTS,
            "shutdown_seconds": policy.MEMORY_SHUTDOWN_SECONDS,
            "shutdown_batches": 8,
            "installation_concurrency": 1,
        },
        "contract": {
            "per_activity_memory_ai_calls": 0,
            "default_new_paid_consent": False,
            "ai_failure_accept_all": False,
            "app_off_os_wake": False,
            "canonical_ids_in_provider_contract": False,
            "chat_router_changed": False,
            "shared_maintenance_queue": True,
            "legacy_summary_mode_unchanged": True,
        },
        "files": [record(path) for path in sorted(files)],
        "separate_gates": [
            "real_provider_selection_quality",
            "installed_runtime_user_verification",
            "user_merge_approval",
            "post_merge_actions",
        ],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--write", action="store_true")
    mode.add_argument("--check", action="store_true")
    args = parser.parse_args()
    rendered = (
        json.dumps(build_inventory(), ensure_ascii=False, indent=2, sort_keys=True)
        + "\n"
    )
    if args.write:
        OUTPUT.write_text(rendered, encoding="utf-8", newline="\n")
    elif not OUTPUT.is_file() or OUTPUT.read_text(encoding="utf-8") != rendered:
        raise SystemExit("Memory batch inventory drift: run --write")
    print("P8-L-R Memory batch inventory is current")


if __name__ == "__main__":
    main()
