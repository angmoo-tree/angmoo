"""Whole-tree frontend rules enabled after the partial AR-F scopes are closed."""
from __future__ import annotations

import posixpath
from pathlib import Path
import re

from refactor_boundaries import check_frontend_edges, feature, is_test_path


COMMON = ("components/", "hooks/", "lib/", "config/", "types/", "utils/", "styles/", "stores/", "assets/")
IMPORT = re.compile(r"(?:from\s+|import\s*\(|require\s*\(|import\s+)\s*['\"]([^'\"]+)['\"]")
COMPUTED_IMPORT = re.compile(r"\b(?:import|require)\s*\(\s*(?!['\"])[^\s]")
SERVER = {"next/headers", "next/server", "server-only", "fs", "fs/promises", "path", "child_process", "worker_threads", "net", "tls", "os", "http", "https"}


def check_completed_frontend(source_root: Path) -> list[str]:
    roots = [source_root, source_root.parent / "static-shell" / "app"]
    files = {}
    for root in roots:
        if root.exists():
            for path in root.rglob("*"):
                if path.is_file() and path.suffix in {".ts", ".tsx", ".js", ".jsx", ".mts", ".css"}:
                    key = (path.relative_to(source_root).as_posix() if root == source_root
                           else "static-shell/app/" + path.relative_to(root).as_posix())
                    if path.suffix != ".css":
                        key = key.rsplit(".", 1)[0]
                    files[key] = path
    features = sorted({feature(key) for key in files if feature(key) is not None})
    common = sorted(key for key in files if key.startswith(COMMON))
    edges, external, errors, clients = [], {}, [], set()
    for key, path in sorted(files.items()):
        text = path.read_text(encoding="utf-8")
        owner = feature(key)
        parts = key.split("/")
        if not key.startswith((*COMMON, "app/", "composition/", "features/", "testing/", "static-shell/app/", "shared/")):
            errors.append(f"[frontend_unclassified_source] {key}")
        if key.startswith("shared/") or (owner and (key.endswith("/public") or len(parts) > 2 and parts[2] in {"ui", "model"})):
            errors.append(f"[frontend_completed_legacy_file] {key}")
        if not is_test_path(key) and COMPUTED_IMPORT.search(text):
            errors.append(f"[frontend_computed_import] {key}")
        if re.match(r"\s*['\"]use client['\"]", text) or key.startswith(("composition/", "static-shell/")):
            clients.add(key)
        for imported in IMPORT.findall(text):
            if imported.startswith("@/"):
                target = imported[2:]
            elif imported.startswith("."):
                target = posixpath.normpath(posixpath.join(posixpath.dirname(key), imported))
                # static-shell imports ../src using a different physical root.
                if key.startswith("static-shell/"):
                    absolute = (path.parent / imported).resolve()
                    if absolute.is_relative_to(source_root.resolve()):
                        target = absolute.relative_to(source_root.resolve()).as_posix()
            else:
                external.setdefault(key, set()).add(imported.removeprefix("node:"))
                continue
            if target.endswith((".ts", ".tsx", ".js", ".jsx", ".mts")):
                target = target.rsplit(".", 1)[0]
            if target not in files and target + "/index" in files:
                target += "/index"
            edges.append((key, target))
            if key.startswith(("composition/", "static-shell/")) and target.startswith("app/"):
                errors.append(f"[frontend_composition_imports_app] {key} -> {target}")
            if key.startswith(COMMON) and target.startswith("static-shell/"):
                errors.append(f"[frontend_common_imports_static] {key} -> {target}")
    errors.extend(check_frontend_edges(edges, {"features": features, "common": common, "bridges": [], "complete": True}))
    graph = {}
    for source, target in edges:
        graph.setdefault(source, set()).add(target)
    # Server helpers are legal under lib/server or the Next app, but never
    # transitively reachable from a common browser screen or client component.
    for entry in sorted(clients):
        todo, visited = [entry], set()
        while todo:
            node = todo.pop()
            if node in visited:
                continue
            visited.add(node)
            forbidden = external.get(node, set()) & SERVER
            if node.startswith("lib/server/") or forbidden:
                errors.append(f"[frontend_client_imports_server] {entry} -> {node}: {sorted(forbidden)}")
            todo.extend(graph.get(node, ()))
    return sorted(set(errors))
