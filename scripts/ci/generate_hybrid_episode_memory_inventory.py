"""Verify the current hybrid/episode/consolidation closure and frozen predecessor."""

import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
OUTPUT = ROOT / "docs/architecture/hybrid-episode-memory-inventory.json"
PREDECESSOR = "docs/architecture/p8-l-r-memory-batch-inventory.json"
PREDECESSOR_SHA256 = "3529d4d33a9d7fa75d556423f9a85a2749130259ed54f0b2cbe43ce06903b213"


def record(path):
    return {"path": path.relative_to(ROOT).as_posix(), "sha256": hashlib.sha256(
        path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()}


def build_inventory():
    from app.config import Settings
    from app.contracts.activity_thought import MAX_THOUGHT_CHARACTERS
    from app.domains.memory.contracts import embedding, episode, episode_packet
    from app.runtime.persistence.sqlite_schema import SQLITE_SCHEMA_VERSION
    from app.runtime.migrations.sqlite_versions.registry import load_sqlite_manifest

    predecessor = record(ROOT / PREDECESSOR)
    if predecessor["sha256"] != PREDECESSOR_SHA256:
        raise ValueError("frozen Memory batch predecessor drift")
    manifest = load_sqlite_manifest(SQLITE_SCHEMA_VERSION)
    files = set()
    for pattern in (
        "backend/app/contracts/activity*.py", "backend/app/domains/memory/**/*.py",
        "backend/app/domains/chat/**/*.py", "backend/app/domains/social/**/*.py",
        "backend/app/domains/routine_posts/**/*.py", "backend/app/runtime/memory/*.py",
        "backend/app/runtime/chat/*.py", "backend/app/runtime/social/*.py",
        "backend/app/runtime/resident/*.py", "backend/app/runtime/social_snapshot.py",
        "backend/app/integrations/llm/*.py", "backend/app/runtime/contributor_backend.py",
        "backend/app/runtime/migrations/sqlite_versions/**/*.py",
        "backend/app/runtime/migrations/sqlite_versions/manifests/v*.json",
        "backend/alembic/versions/202609*.py", "backend/app/config.py",
        "backend/app/runtime/persistence/*.py", "backend/app/domains/runtime/constants.py",
        "backend/tests/memory/*.py", "backend/tests/chat/*.py",
        "backend/tests/migrations/*.py", "backend/tests/routines/test_activity_thought_output.py",
        "frontend/src/features/memory/**/*.*", "frontend/src/features/chat/**/*.*",
        "browser-tests/memory-batch-fixture.ts", "backend/security/*route_security_inventory.json",
        "scripts/ci/generate_hybrid_episode_memory_inventory.py",
        "scripts/ci/generate_p8_l_r_memory_batch_inventory.py",
        "docs/operations/episode-memory.md", "docs/operations/memory-consolidation-scheduling.md",
        "docs/operations/chat-hybrid-memory-recall-validation.md",
    ):
        files.update(p for p in ROOT.glob(pattern) if p.is_file() and "__pycache__" not in p.parts)
    return {
        "schema_version": 1, "owner_stage": "HYBRID-EPISODE-CONSOLIDATION",
        "predecessor": predecessor,
        "schema": {"embedded_schema_version": SQLITE_SCHEMA_VERSION,
                   "schema_digest": manifest.schema_digest,
                   "canonical_table_count": manifest.canonical_table_count,
                   "source_revision": manifest.source_revision},
        "defaults": {name: Settings.model_fields[name].default for name in (
            "ACTIVITY_THOUGHT_POLICY", "MEMORY_GENERATION_POLICY", "MEMORY_RECALL_REPRESENTATION")},
        "bounds": {"thought_characters": MAX_THOUGHT_CHARACTERS,
                   "chat_new_turns": episode.MAX_NEW_CHAT_TURNS,
                   "chat_context_turns": episode.MAX_CONTEXT_CHAT_TURNS,
                   "episode_characters": episode.MAX_EPISODE_CHARACTERS,
                   "chat_packet_count": episode_packet.CHAT_PACKET_LIMIT,
                   "chat_packet_characters": episode_packet.CHAT_PACKET_CHARACTERS,
                   "sns_packet_count": episode_packet.SNS_PACKET_LIMIT,
                   "sns_packet_characters": episode_packet.SNS_PACKET_CHARACTERS},
        "embedding": {"model": embedding.EMBEDDING_MODEL, "dimensions": embedding.EMBEDDING_DIMENSIONS},
        "contract": {"canonical_store": "sqlite", "retrieval": "fts5+vec1-flat+rrf",
                     "index_unit": "episode-or-legacy-summary", "legacy_originals_preserved": True,
                     "thought_extra_generation_calls": 0, "thought_when_memory_off": True,
                     "batch_triggers": ["manual", "scheduled", "shutdown"],
                     "scheduled_occurrence_idempotency": True, "daily_total_limit": False,
                     "accepted_request_cutoff": True, "background_concurrency": 1},
        "files": [record(p) for p in sorted(files)],
        "separate_gates": ["user_acceptance", "local_regression", "remote_ci",
                           "main_merge", "windows_installer_artifacts", "installed_user_check"],
    }


def render():
    return json.dumps(build_inventory(), ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def verify():
    if not OUTPUT.is_file() or OUTPUT.read_text(encoding="utf-8") != render():
        raise ValueError("hybrid episode inventory drift: review contracts before --write")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--write", action="store_true")
    mode.add_argument("--check", action="store_true")
    args = parser.parse_args()
    if args.write:
        OUTPUT.write_text(render(), encoding="utf-8", newline="\n")
    else:
        verify()
    print("Hybrid episode memory inventory passed")


if __name__ == "__main__":
    main()
