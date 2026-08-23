"""Side-effect-free local data path resolver for current and embedded runtimes."""

from __future__ import annotations

from pathlib import Path

from app.domains.runtime.ports.runtime_data_path import RuntimeDataPaths


class StaticRuntimeDataPath:
    def __init__(self, root: Path) -> None:
        self._root = root.expanduser().resolve()

    def resolve(self) -> RuntimeDataPaths:
        return RuntimeDataPaths(
            root=self._root,
            app=self._root / "app",
            canonical=self._root / "canonical",
            graph=self._root / "graph",
            search=self._root / "search",
            media=self._root / "media",
            secrets=self._root / "secrets",
            runtime=self._root / "runtime",
            logs=self._root / "logs",
            webview=self._root / "webview",
        )


__all__ = ["StaticRuntimeDataPath"]
