from __future__ import annotations

import ctypes
import os
from pathlib import Path
import subprocess


class WindowsAsciiPathAlias:
    """Expose a Unicode data directory through a temporary ASCII drive path.

    LadybugDB 0.19.1's Windows native module cannot open a path containing
    characters outside the active ANSI code page. ``subst`` keeps the files in
    their canonical Unicode directory while giving the isolated graph sidecar
    a short ASCII path. The alias is process-owned and always removed on close.
    """

    def __init__(self, target: Path) -> None:
        self.target = target.resolve()
        self.drive: str | None = None
        self.used = False
        self.released = False

    @staticmethod
    def _logical_drive_mask() -> int:
        return int(ctypes.windll.kernel32.GetLogicalDrives())

    @classmethod
    def _available_drive(cls) -> str:
        mask = cls._logical_drive_mask()
        for letter in "ZYXWVUTSRQPONMLKJIHGFED":
            index = ord(letter) - ord("A")
            if not mask & (1 << index):
                return f"{letter}:"
        raise RuntimeError("windows_ascii_drive_alias_unavailable")

    def __enter__(self) -> Path:
        self.target.mkdir(parents=True, exist_ok=True)
        if os.name != "nt" or str(self.target).isascii():
            return self.target
        drive = self._available_drive()
        completed = subprocess.run(
            ["subst", drive, str(self.target)],
            check=False,
            capture_output=True,
            text=True,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        if completed.returncode != 0:
            raise RuntimeError("windows_ascii_drive_alias_create_failed")
        self.drive = drive
        self.used = True
        return Path(f"{drive}\\")

    def close(self) -> None:
        drive = self.drive
        if drive is None:
            self.released = True
            return
        completed = subprocess.run(
            ["subst", drive, "/D"],
            check=False,
            capture_output=True,
            text=True,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        if completed.returncode != 0:
            raise RuntimeError("windows_ascii_drive_alias_remove_failed")
        self.drive = None
        self.released = True

    def __exit__(self, *_: object) -> None:
        self.close()
