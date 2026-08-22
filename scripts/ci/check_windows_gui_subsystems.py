#!/usr/bin/env python3
"""Verify packaged Windows executables do not allocate console windows."""

from __future__ import annotations

import argparse
import struct
from pathlib import Path

IMAGE_SUBSYSTEM_WINDOWS_GUI = 2


def _read_pe_subsystem(path: Path) -> int:
    with path.open("rb") as executable:
        if executable.read(2) != b"MZ":
            raise SystemExit(f"not a PE executable: {path}")
        executable.seek(0x3C)
        pe_offset_data = executable.read(4)
        if len(pe_offset_data) != 4:
            raise SystemExit(f"truncated DOS header: {path}")
        pe_offset = struct.unpack("<I", pe_offset_data)[0]
        executable.seek(pe_offset)
        if executable.read(4) != b"PE\0\0":
            raise SystemExit(f"invalid PE signature: {path}")
        executable.seek(pe_offset + 4 + 20)
        optional_header = executable.read(70)
        if len(optional_header) != 70:
            raise SystemExit(f"truncated PE optional header: {path}")
        return struct.unpack_from("<H", optional_header, 68)[0]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("executables", nargs="+", type=Path)
    args = parser.parse_args()

    for executable in args.executables:
        if not executable.is_file():
            raise SystemExit(f"Windows executable is missing: {executable}")
        subsystem = _read_pe_subsystem(executable)
        if subsystem != IMAGE_SUBSYSTEM_WINDOWS_GUI:
            raise SystemExit(
                f"{executable} uses PE subsystem {subsystem}; "
                f"expected {IMAGE_SUBSYSTEM_WINDOWS_GUI} (WINDOWS_GUI)"
            )
        print(f"windows-gui-subsystem: PASS {executable}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
