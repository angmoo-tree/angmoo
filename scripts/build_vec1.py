"""Build the pinned public-domain official Vec1 source; never used at runtime."""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import tempfile
from urllib.request import urlopen
import zipfile

SOURCE_REVISION = "8fc7b115a4"
SOURCE_SHA256 = "8571bb4f77f9547d11ad11e2f72e0de7d3b2ab44e7930151998bce9377ed4b86"
SQLITE_SHA256 = "bf3733d7c71b3ab0f6fd8a9ea0052ad87fa037d94333e14ce09878ba3492c3b0"


def download(url: str, digest: str) -> bytes:
    with urlopen(url, timeout=60) as response:
        data = response.read(20 * 1024 * 1024)
    if hashlib.sha256(data).hexdigest() != digest:
        raise RuntimeError("vec1_build_source_integrity")
    return data


def build(output: Path):
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="angmoo-vec1-build-") as directory:
        root = Path(directory)
        (root / "vec1.c").write_bytes(download(
            f"https://sqlite.org/vec1/raw/vec1.c?ci={SOURCE_REVISION}", SOURCE_SHA256))
        archive = download("https://sqlite.org/2026/sqlite-amalgamation-3530000.zip", SQLITE_SHA256)
        with zipfile.ZipFile(io.BytesIO(archive)) as packed:
            for name in ("sqlite3.h", "sqlite3ext.h"):
                (root / name).write_bytes(packed.read("sqlite-amalgamation-3530000/" + name))
        if os.name == "nt":
            artifact = "vec1.dll"
            command = ["cl", "/O2", "/DNDEBUG", "vec1.c", "/link", "/dll", "/out:" + artifact]
            if shutil.which("cl") is None:
                locator = Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")) / "Microsoft Visual Studio/Installer/vswhere.exe"
                installation = subprocess.check_output([str(locator), "-latest", "-requires", "Microsoft.VisualStudio.Component.VC.Tools.x86.x64", "-property", "installationPath"], text=True).strip()
                setup = Path(installation) / "VC/Auxiliary/Build/vcvars64.bat"
                if not setup.is_file():
                    raise RuntimeError("vec1_build_compiler_missing")
                (root / "compile.cmd").write_text(
                    f'@call "{setup}"\n@if errorlevel 1 exit /b 1\n'
                    'cl /O2 /DNDEBUG vec1.c /link /dll /out:vec1.dll\n', encoding="utf-8")
                command = ["cmd", "/c", "compile.cmd"]
        else:
            artifact = "vec1.so"
            command = ["cc", "-O3", "-DNDEBUG", "vec1.c", "-shared", "-fPIC", "-lm", "-o", artifact]
        subprocess.run(command, cwd=root, check=True)
        data = (root / artifact).read_bytes()
        (output / artifact).write_bytes(data)
        receipt = {
            "schema_revision": 1, "version": "0.7", "source_revision": SOURCE_REVISION,
            "source_sha256": SOURCE_SHA256, "sqlite_headers_sha256": SQLITE_SHA256,
            "filename": artifact, "sha256": hashlib.sha256(data).hexdigest(),
            "platform": platform.system(), "machine": platform.machine(), "simd": "scalar",
        }
        (output / "manifest.json").write_text(json.dumps(receipt, indent=2)+"\n", encoding="utf-8")
        print(json.dumps(receipt))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    build(parser.parse_args().output.resolve())
