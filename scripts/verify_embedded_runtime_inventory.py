"""Generate and verify the deterministic L3-ER0 embedded-runtime inventory."""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
from pathlib import Path
import re
import sys
import tomllib
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[1]
ARCHITECTURE = ROOT / "docs" / "architecture"
BASELINE_COMMIT = "db1c32510f66cee20a3e64a01e85c5ea8753d77e"

POSTGRES_OUTPUT = ARCHITECTURE / "postgres-sql-inventory.json"
MIGRATION_OUTPUT = ARCHITECTURE / "migration-conversion-inventory.json"
NEO4J_OUTPUT = ARCHITECTURE / "neo4j-query-corpus.json"
NEXT_OUTPUT = ARCHITECTURE / "next-static-compatibility.json"
RUNTIME_OUTPUT = ARCHITECTURE / "embedded-runtime-inventory.json"
OUTPUTS = (
    POSTGRES_OUTPUT,
    MIGRATION_OUTPUT,
    NEO4J_OUTPUT,
    NEXT_OUTPUT,
    RUNTIME_OUTPUT,
)

TEXT_SUFFIXES = {".py", ".sh", ".ps1", ".toml", ".yml", ".yaml"}
POSTGRES_MARKERS = {
    "advisory_lock": re.compile(r"pg_(?:try_)?advisory|advisory[_ -]lock", re.I),
    "driver_or_url": re.compile(r"psycopg|postgresql(?:\+psycopg)?://|postgresql", re.I),
    "jsonb": re.compile(r"\bJSONB\b|postgresql\.JSONB"),
    "pgvector": re.compile(r"pgvector|\bVector\s*\(", re.I),
    "row_lock": re.compile(r"with_for_update|FOR\s+UPDATE", re.I),
    "skip_locked": re.compile(r"skip_locked|SKIP\s+LOCKED", re.I),
}

PARITY_WORKLOADS = (
    {
        "phase": "P1",
        "contract": "World create/update/readiness/publish/archive with provider calls and public writes both zero",
        "tests": [
            "backend/tests/worlds/test_creator_routes.py",
            "backend/tests/worlds/test_definition_contract.py",
            "backend/tests/test_world_foundation.py",
        ],
    },
    {
        "phase": "P2",
        "contract": "WorldCharacter setup uses three physical provider requests and persists 40 candidates, ten per daypart",
        "tests": [
            "backend/tests/world_characters/test_setup_contracts.py",
            "backend/tests/world_characters/test_setup_service.py",
            "backend/tests/world_characters/test_owner_identity.py",
        ],
    },
    {
        "phase": "P3",
        "contract": "Daily plan selects four deterministic items with zero provider calls and no missed-slot catch-up",
        "tests": [
            "backend/tests/test_daily_activity_runtime.py",
            "backend/tests/test_agent_activity_limits.py",
        ],
    },
    {
        "phase": "P4",
        "contract": "Routine continuation publishes atomically with normal two-call and repair-bounded three-call behavior",
        "tests": [
            "backend/tests/test_routine_post_runtime.py",
            "backend/tests/test_l3_owner_manual_social_inbox.py",
        ],
    },
    {
        "phase": "P5",
        "contract": "World-scoped keyword feed and reaction intent preserve provider and public-write boundaries",
        "tests": [
            "backend/tests/test_world_feed_search.py",
            "backend/tests/test_feed_reaction_intent.py",
        ],
    },
    {
        "phase": "P6",
        "contract": "Successful social events create directional relationship state and evidence once; failed writes create none",
        "tests": [
            "backend/tests/test_social_event_runtime.py",
            "backend/tests/test_activity_proposal_runtime.py",
        ],
    },
    {
        "phase": "P7",
        "contract": "Graph projection is replayable, World-isolated, idempotent, outage-tolerant, and query-template compatible",
        "tests": [
            "backend/tests/test_graph_projection_commands.py",
            "backend/tests/test_graph_projection_replay.py",
            "backend/tests/test_graph_projection_worker.py",
            "backend/tests/test_relationship_graph_repository.py",
            "backend/tests/test_relationship_graph_api.py",
        ],
    },
)


def _relative(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_file(path: Path) -> str:
    # Git may materialize text as CRLF on Windows and LF on Linux. Inventory
    # hashes describe source content, not the checkout's line-ending policy.
    canonical = path.read_bytes().replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    return _sha256_bytes(canonical)


def _json(payload: object) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _text_files(roots: Iterable[Path]) -> list[Path]:
    files: set[Path] = set()
    for root in roots:
        if root.is_file():
            files.add(root)
            continue
        if not root.exists():
            continue
        files.update(
            path
            for path in root.rglob("*")
            if path.is_file()
            and path.suffix.lower() in TEXT_SUFFIXES
            and "__pycache__" not in path.parts
        )
    return sorted(files, key=_relative)


def _line_numbers(text: str, pattern: re.Pattern[str]) -> list[int]:
    return [
        number
        for number, line in enumerate(text.splitlines(), start=1)
        if pattern.search(line)
    ]


def _postgres_owner(path: str) -> tuple[str, str, str]:
    if path == (
        "backend/app/domains/memory/infrastructure/consolidation_repository.py"
    ):
        return (
            "P8-L-O",
            "P8-L-O consolidation/hot brief",
            "retain while same-scope maintenance serialization and exact hot-brief "
            "source-version fencing are required",
        )
    if path.startswith("backend/app/domains/memory/") or path == (
        "scripts/ci/generate_p8_l_g_memory_write_inventory.py"
    ):
        return (
            "P8-L-G",
            "P8-L-G memory write/lifecycle",
            "retain only while cross-provider same-scope serialization or its "
            "negative inventory guard is required",
        )
    if "/alembic/versions/" in path:
        return (
            "ER2",
            "ER2 PR G",
            "SQLite migration parity and synthetic upgrade/rollback/restore PASS",
        )
    if path.startswith("compose") or path.startswith("scripts/ci/"):
        return (
            "ER7",
            "ER7 PR P",
            "embedded canonical rollback window PASS and user-approved legacy-default removal",
        )
    return (
        "ER2-ER7 legacy evidence",
        "ER2 PR D/E/G; Legacy Removal PR",
        "historical revision, serialized compatibility value, or negative reintroduction guard only",
    )


def build_postgres_inventory() -> dict[str, Any]:
    roots = (
        ROOT / "backend" / "app",
        ROOT / "backend" / "alembic",
        ROOT / "backend" / "scripts",
        ROOT / "scripts" / "ci",
        ROOT / "compose.yml",
        ROOT / "compose.dev.yml",
        ROOT / "compose.ci.yml",
        ROOT / "Dockerfile.backend",
        ROOT / "backend" / "pyproject.toml",
    )
    entries: list[dict[str, Any]] = []
    for path in _text_files(roots):
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        matches = {
            marker: _line_numbers(text, pattern)
            for marker, pattern in POSTGRES_MARKERS.items()
        }
        matches = {marker: lines for marker, lines in matches.items() if lines}
        if not matches:
            continue
        relative = _relative(path)
        owner, transition_pr, removal_condition = _postgres_owner(relative)
        entries.append(
            {
                "markers": matches,
                "owner": owner,
                "path": relative,
                "removal_condition": removal_condition,
                "source_sha256": _sha256_file(path),
                "transition_pr": transition_pr,
            }
        )
    return {
        "baseline_commit": BASELINE_COMMIT,
        "entries": entries,
        "entry_count": len(entries),
        "marker_counts": {
            marker: sum(marker in entry["markers"] for entry in entries)
            for marker in sorted(POSTGRES_MARKERS)
        },
        "purpose": (
            "Residual PostgreSQL markers retained only as historical schema "
            "evidence, serialized compatibility values, and negative "
            "reintroduction guards"
        ),
        "schema_version": 1,
    }


def _assignment_literals(tree: ast.AST) -> dict[str, object]:
    values: dict[str, object] = {}
    for node in getattr(tree, "body", []):
        name: str | None = None
        value: ast.expr | None = None
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            target = node.targets[0]
            if isinstance(target, ast.Name):
                name, value = target.id, node.value
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            name, value = node.target.id, node.value
        if name is None or value is None:
            continue
        try:
            values[name] = ast.literal_eval(value)
        except (ValueError, TypeError):
            continue
    return values


def build_migration_inventory() -> dict[str, Any]:
    directory = ROOT / "backend" / "alembic" / "versions"
    entries: list[dict[str, Any]] = []
    for path in sorted(directory.glob("*.py")):
        text = path.read_text(encoding="utf-8")
        tree = ast.parse(text, filename=str(path))
        values = _assignment_literals(tree)
        # This inventory preserves PostgreSQL-era schema provenance. It is not
        # an executable import source or the current SQLite forward chain.
        if values.get("revision") == "20260825_0083":
            continue
        markers = sorted(
            marker for marker, pattern in POSTGRES_MARKERS.items() if pattern.search(text)
        )
        down_revision = values.get("down_revision")
        if isinstance(down_revision, tuple):
            down_revision = list(down_revision)
        entries.append(
            {
                "down_revision": down_revision,
                "manual_review_markers": markers,
                "owner": "ER2",
                "path": _relative(path),
                "removal_condition": "preserve immutable historical revision identity; do not execute as the current SQLite runtime chain",
                "revision": values.get("revision"),
                "source_sha256": _sha256_file(path),
                "strategy": "translate-and-validate" if markers else "schema-parity-review",
                "transition_pr": "ER2 PR G",
            }
        )
    return {
        "baseline_commit": BASELINE_COMMIT,
        "entries": entries,
        "migration_count": len(entries),
        "purpose": "PostgreSQL-era Alembic provenance retained as immutable historical evidence",
        "schema_version": 1,
    }


def _literal_string(node: ast.AST) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        left = _literal_string(node.left)
        right = _literal_string(node.right)
        if left is not None and right is not None:
            return left + right
    return None


def _literal_strings(node: ast.AST) -> list[str] | None:
    single = _literal_string(node)
    if single is not None:
        return [single]
    if isinstance(node, (ast.Tuple, ast.List)):
        values = [_literal_string(item) for item in node.elts]
        if all(value is not None for value in values):
            return [value for value in values if value is not None]
    return None


def _query_category(name: str, query: str) -> str:
    if query.lstrip().upper().startswith(("CREATE CONSTRAINT", "CREATE INDEX")):
        return "ddl"
    if "DETACH DELETE" in query.upper():
        return "delete"
    if name in {"_EVENT_WITH_TARGET", "_EVENT_WITHOUT_TARGET", "_RELATIONSHIP", "_SOURCE_EXCLUSION"}:
        return "write"
    if name.startswith(("_DIRECT", "_SHARED", "_RANK", "_EVIDENCE", "_VISUALIZATION")):
        return "typed-read"
    return "digest-or-maintenance"


def build_neo4j_inventory() -> dict[str, Any]:
    # ER7 removes the live Neo4j adapter and Python driver.  The ER3 corpus is
    # retained as immutable parity evidence, not regenerated from a server
    # runtime that is no longer part of Angmoo.
    return json.loads(NEO4J_OUTPUT.read_text(encoding="utf-8"))


def _next_route(path: Path) -> str:
    relative = path.relative_to(ROOT / "frontend" / "src" / "app")
    parts = list(relative.parts[:-1])
    visible = [part for part in parts if not (part.startswith("(") and part.endswith(")"))]
    return "/" + "/".join(visible) if visible else "/"


def build_next_inventory() -> dict[str, Any]:
    config = ROOT / "frontend" / "next.config.ts"
    config_text = config.read_text(encoding="utf-8")
    hooks: list[dict[str, Any]] = []
    for name in ("headers", "redirects", "rewrites"):
        matches = [
            number
            for number, line in enumerate(config_text.splitlines(), start=1)
            if re.search(rf"async\s+{name}\s*\(", line)
        ]
        if matches:
            hooks.append(
                {
                    "compatibility": "requires-static-or-sidecar-adapter",
                    "hook": name,
                    "line": matches[0],
                    "owner": "ER5",
                    "path": _relative(config),
                    "removal_condition": "static export and Tauri API/media routing parity PASS",
                    "transition_pr": "ER5 PR K",
                }
            )

    routes: list[dict[str, Any]] = []
    app_root = ROOT / "frontend" / "src" / "app"
    runtime_patterns = {
        "cookies": re.compile(r"\bcookies\s*\("),
        "headers": re.compile(r"\bheaders\s*\("),
        "redirect": re.compile(r"\bredirect\s*\("),
        "server_action": re.compile(r"['\"]use server['\"]"),
    }
    for path in sorted((*app_root.rglob("page.tsx"), *app_root.rglob("route.ts")), key=_relative):
        text = path.read_text(encoding="utf-8")
        blockers = sorted(
            name for name, pattern in runtime_patterns.items() if pattern.search(text)
        )
        routes.append(
            {
                "blockers": blockers,
                "kind": "route-handler" if path.name == "route.ts" else "page",
                "owner": "ER5",
                "path": _relative(path),
                "removal_condition": "same frontend source passes browser dev and Tauri static release",
                "route": _next_route(path),
                "source_sha256": _sha256_file(path),
                "transition_pr": "ER5 PR K",
            }
        )
    output_match = re.search(r"output:\s*[\"']([^\"']+)[\"']", config_text)
    return {
        "baseline_commit": BASELINE_COMMIT,
        "config_hooks": hooks,
        "current_output_mode": output_match.group(1) if output_match else None,
        "purpose": "L3-ER0 Next.js static-export compatibility inventory",
        "route_count": len(routes),
        "routes": routes,
        "schema_version": 1,
    }


def _dependency_inventory() -> dict[str, Any]:
    pyproject_path = ROOT / "backend" / "pyproject.toml"
    package_path = ROOT / "frontend" / "package.json"
    pyproject = tomllib.loads(pyproject_path.read_text(encoding="utf-8"))
    package = json.loads(package_path.read_text(encoding="utf-8"))
    dockerfiles: list[dict[str, str]] = []
    for path in (ROOT / "Dockerfile.backend", ROOT / "Dockerfile.frontend"):
        images = [
            line.split(None, 1)[1].strip()
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.upper().startswith("FROM ")
        ]
        dockerfiles.append({"path": _relative(path), "base_images": images})
    return {
        "backend": {
            "dependencies": sorted(pyproject["project"]["dependencies"]),
            "python": pyproject["project"]["requires-python"],
            "source": _relative(pyproject_path),
        },
        "docker": dockerfiles,
        "frontend": {
            "dependencies": dict(sorted(package.get("dependencies", {}).items())),
            "dev_dependencies": dict(sorted(package.get("devDependencies", {}).items())),
            "package_manager": package.get("packageManager"),
            "source": _relative(package_path),
        },
        "future_native_owners": {
            "LadybugDB": "ER1 PR C compatibility spike; ER3 PR H/I",
            "Rust_Tauri": "ER1 PR C compatibility spike; ER5 PR L/M",
        },
        "license_evidence": ["THIRD_PARTY_NOTICES.md", "LICENSE"],
    }


def _coupling_entry(path: str, component: str, markers: list[str]) -> dict[str, Any]:
    source = ROOT / path
    return {
        "component": component,
        "markers": markers,
        "owner": "ER4",
        "path": path,
        "removal_condition": "in-process singleton, drain, backlog recovery, aggregate status, and legacy regression PASS",
        "source_sha256": _sha256_file(source),
        "transition_pr": "ER4 PR J",
    }


def _runtime_coupling() -> list[dict[str, Any]]:
    entries = (
        ("compose.yml", "shared", ["two-service topology", "embedded data volume", "backend health dependency"]),
        ("compose.dev.yml", "shared", ["frontend HMR", "backend reload", "contributor logs"]),
        ("backend/app/runtime/single_backend_components.py", "shared", ["in-process scheduler/projector ownership", "bounded drain"]),
        ("backend/app/services/resident_tick_scheduler.py", "scheduler", ["singleton process lock", "database lease", "heartbeat", "bounded drain"]),
        ("backend/app/domains/runtime/infrastructure/sqlalchemy_scheduler_lease.py", "scheduler", ["lease repository", "fencing epoch"]),
        ("backend/app/runtime/graph_projection/worker.py", "projector", ["outbox claim", "thread pool", "bounded drain", "degraded state"]),
        ("backend/app/runtime/graph_projection/process_client.py", "projector", ["graph client construction"]),
        ("backend/app/public_main.py", "api", ["typed RuntimeConfig", "FastAPI lifespan", "component ownership"]),
        ("backend/app/runtime/shutdown.py", "shared", ["cooperative signal bridge"]),
    )
    return [_coupling_entry(*entry) for entry in entries]


def _behavior_file_hashes() -> list[dict[str, str]]:
    paths = (
        "compose.yml",
        "compose.dev.yml",
        "compose.ci.yml",
        "Dockerfile.backend",
        "Dockerfile.frontend",
        "frontend/next.config.ts",
        "backend/app/main.py",
        "backend/app/services/resident_tick_scheduler.py",
        "backend/app/runtime/graph_projection/worker.py",
    )
    return [
        {"path": path, "sha256": _sha256_file(ROOT / path)}
        for path in paths
    ]


def build_runtime_inventory() -> dict[str, Any]:
    oracle = ARCHITECTURE / "l3-er-postgres-neo4j-parity-oracle.json"
    workload_entries: list[dict[str, Any]] = []
    for workload in PARITY_WORKLOADS:
        missing = [path for path in workload["tests"] if not (ROOT / path).is_file()]
        workload_entries.append({**workload, "missing_tests": missing})
    return {
        "baseline_commit": BASELINE_COMMIT,
        "behavior_critical_file_hashes": _behavior_file_hashes(),
        "dependencies": _dependency_inventory(),
        "parity": {
            "oracle_path": _relative(oracle),
            "oracle_sha256": _sha256_file(oracle),
            "workloads": workload_entries,
        },
        "purpose": "L3-ER0 runtime coupling, dependency, behavior, and parity inventory",
        "runtime_coupling": _runtime_coupling(),
        "schema_version": 1,
    }


def rendered_outputs() -> dict[Path, str]:
    return {
        POSTGRES_OUTPUT: _json(build_postgres_inventory()),
        MIGRATION_OUTPUT: _json(build_migration_inventory()),
        NEO4J_OUTPUT: _json(build_neo4j_inventory()),
        NEXT_OUTPUT: _json(build_next_inventory()),
        RUNTIME_OUTPUT: _json(build_runtime_inventory()),
    }


def validate(payloads: dict[Path, str]) -> list[str]:
    errors: list[str] = []
    parsed = {path: json.loads(text) for path, text in payloads.items()}
    migrations = parsed[MIGRATION_OUTPUT]
    if migrations["migration_count"] != 87:
        errors.append(f"expected 87 Alembic migrations, found {migrations['migration_count']}")
    migration_paths = [entry["path"] for entry in migrations["entries"]]
    if len(migration_paths) != len(set(migration_paths)):
        errors.append("a migration appears more than once")
    revisions = [entry["revision"] for entry in migrations["entries"]]
    if any(revision is None for revision in revisions) or len(revisions) != len(set(revisions)):
        errors.append("migration revisions must be present and unique")

    for output in (POSTGRES_OUTPUT, MIGRATION_OUTPUT, NEO4J_OUTPUT, NEXT_OUTPUT):
        entries = parsed[output].get("entries") or parsed[output].get("queries") or parsed[output].get("routes")
        if entries is None:
            continue
        for entry in entries:
            for key in ("owner", "transition_pr", "removal_condition"):
                if not entry.get(key):
                    errors.append(f"{_relative(output)} entry {entry.get('path') or entry.get('name')} lacks {key}")

    graph = parsed[NEO4J_OUTPUT]
    required_templates = {
        "direct_relationship",
        "shared_neighbors_outgoing",
        "shared_neighbors_incoming",
        "shared_neighbors_either",
        "ranked_related_positive",
        "ranked_related_tense",
        "ranked_related_recent",
        "relationship_evidence",
    }
    templates = {item["template"] for item in graph["typed_query_templates"]}
    missing_templates = sorted(required_templates - templates)
    if missing_templates:
        errors.append(f"Neo4j typed query corpus is incomplete: {missing_templates}")
    categories = {entry["category"] for entry in graph["queries"]}
    if not {"ddl", "write", "typed-read", "delete"} <= categories:
        errors.append(f"Neo4j query categories are incomplete: {sorted(categories)}")

    runtime = parsed[RUNTIME_OUTPUT]
    expected_phases = {f"P{number}" for number in range(1, 8)}
    workloads = runtime["parity"]["workloads"]
    phases = {item["phase"] for item in workloads}
    if phases != expected_phases:
        errors.append(f"P1-P7 workload corpus mismatch: {sorted(phases)}")
    for workload in workloads:
        if workload["missing_tests"]:
            errors.append(f"{workload['phase']} workload has missing tests: {workload['missing_tests']}")

    oracle = json.loads(
        (ARCHITECTURE / "l3-er-postgres-neo4j-parity-oracle.json").read_text(encoding="utf-8")
    )
    if oracle.get("oracle_version") != "l3-er-postgres-neo4j-v1":
        errors.append("unexpected L3 parity oracle schema/version")
    if oracle.get("privacy", {}).get("credentials_included") is not False:
        errors.append("parity oracle must exclude credentials")
    if (
        oracle.get("closeout", {})
        .get("exact_main_clean_clone", {})
        .get("provider_calls")
        != 0
    ):
        errors.append("parity oracle must record zero provider calls")

    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true", help="write all generated inventories")
    parser.add_argument("--check", action="store_true", help="compare generated inventories with source control")
    args = parser.parse_args()
    if not args.write and not args.check:
        parser.error("use --write or --check")

    try:
        payloads = rendered_outputs()
        errors = validate(payloads)
        if args.write:
            ARCHITECTURE.mkdir(parents=True, exist_ok=True)
            for path, text in payloads.items():
                path.write_text(text, encoding="utf-8", newline="\n")
        if args.check:
            for path, text in payloads.items():
                if not path.is_file():
                    errors.append(f"missing generated inventory: {_relative(path)}")
                elif path.read_text(encoding="utf-8") != text:
                    errors.append(f"stale generated inventory: {_relative(path)}")
    except (OSError, SyntaxError, ValueError, KeyError, StopIteration) as exc:
        errors = [f"inventory generation failed: {exc}"]

    if errors:
        for error in errors:
            print(f"ER0 inventory error: {error}", file=sys.stderr)
        return 1

    payloads_json = {path: json.loads(text) for path, text in payloads.items()}
    print(
        "ER0 inventory passed: "
        f"postgres_files={payloads_json[POSTGRES_OUTPUT]['entry_count']} "
        f"migrations={payloads_json[MIGRATION_OUTPUT]['migration_count']} "
        f"neo4j_queries={payloads_json[NEO4J_OUTPUT]['query_count']} "
        f"next_routes={payloads_json[NEXT_OUTPUT]['route_count']} "
        f"parity_workloads={len(payloads_json[RUNTIME_OUTPUT]['parity']['workloads'])}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
