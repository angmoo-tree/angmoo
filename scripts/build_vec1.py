"""Build pinned public-domain Vec1 source and verified SQLite headers."""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import platform
import random
import shutil
import socket
import ssl
import subprocess
import tempfile
import time
from urllib.error import HTTPError, URLError
from urllib.request import urlopen
import zipfile

SOURCE_REVISION = "8fc7b115a4"
SOURCE_SHA256 = "8571bb4f77f9547d11ad11e2f72e0de7d3b2ab44e7930151998bce9377ed4b86"
SQLITE_SHA256 = "bf3733d7c71b3ab0f6fd8a9ea0052ad87fa037d94333e14ce09878ba3492c3b0"
MAX_BYTES = 20 * 1024 * 1024
DOWNLOAD_BUDGET = 180.0
ATTEMPTS = 3
TRANSIENT_HTTP = frozenset((408, 429, 500, 502, 503, 504))
SOURCE_URL = f"https://sqlite.org/vec1/raw/vec1.c?ci={SOURCE_REVISION}"
SQLITE_URL = "https://sqlite.org/2026/sqlite-amalgamation-3530000.zip"
BUNDLED_SOURCE = Path(__file__).resolve().parent / "vendor" / "vec1" / "vec1.c"


def _verified(data: bytes, digest: str) -> bytes:
    if len(data) > MAX_BYTES:
        raise RuntimeError("vec1_build_source_too_large")
    if hashlib.sha256(data).hexdigest() != digest:
        raise RuntimeError("vec1_build_source_integrity")
    return data


def _transient(error: BaseException) -> bool:
    if isinstance(error, HTTPError):
        return error.code in TRANSIENT_HTTP
    reason = error.reason if isinstance(error, URLError) else error
    if isinstance(reason, ssl.SSLError):
        return False
    return isinstance(reason, (TimeoutError, ConnectionError, socket.gaierror))


def _fetch(url: str, digest: str) -> bytes:
    deadline = time.monotonic() + DOWNLOAD_BUDGET
    for attempt in range(ATTEMPTS):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("vec1_build_download_deadline")
        try:
            with urlopen(url, timeout=min(60.0, remaining)) as response:
                chunks = bytearray()
                while True:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise TimeoutError("vec1_build_download_deadline")
                    # urllib's HTTPS response wraps a SocketIO in a buffered
                    # reader. Bound each underlying read by the remaining
                    # total budget, not by a renewed 60-second allowance.
                    raw = getattr(getattr(response, "fp", None), "raw", None)
                    connection = getattr(raw, "_sock", None)
                    if connection is not None:
                        connection.settimeout(min(60.0, remaining))
                    chunk = response.read(min(64 * 1024, MAX_BYTES + 1 - len(chunks)))
                    if time.monotonic() >= deadline:
                        raise TimeoutError("vec1_build_download_deadline")
                    chunks.extend(chunk)
                    if len(chunks) > MAX_BYTES:
                        raise RuntimeError("vec1_build_source_too_large")
                    if not chunk:
                        return _verified(bytes(chunks), digest)
        except (HTTPError, URLError, TimeoutError, ConnectionError) as error:
            if not _transient(error) or attempt == ATTEMPTS - 1:
                raise
            delay = min(5.0, (2 ** attempt) + random.uniform(0, 0.25))
            if isinstance(error, HTTPError):
                retry_after = error.headers.get("Retry-After", "") if error.headers else ""
                if retry_after.isdigit():
                    delay = min(5.0, max(delay, float(retry_after)))
                error.close()
            remaining = deadline - time.monotonic()
            if remaining <= delay:
                raise TimeoutError("vec1_build_download_deadline") from error
            print(f"vec1_download_retry attempt={attempt + 1} reason={type(error).__name__}")
            time.sleep(delay)
    raise AssertionError("unreachable")


def _cache_path(directory: Path, digest: str) -> Path:
    # Reject redirected cache roots and entries. A shared cache contains only
    # untrusted bytes: every hit is verified against a source-controlled digest.
    if len(digest) != 64 or any(char not in "0123456789abcdef" for char in digest):
        raise ValueError("vec1_cache_digest_invalid")
    absolute = directory.absolute()
    for parent in (absolute, *absolute.parents):
        if parent.is_symlink() or (hasattr(parent, "is_junction") and parent.is_junction()):
            raise ValueError("vec1_cache_path_redirected")
    absolute.mkdir(parents=True, exist_ok=True)
    target = absolute / f"sha256-{digest}.source-v1"
    if target.is_symlink() or not target.resolve().is_relative_to(absolute.resolve()):
        raise ValueError("vec1_cache_path_redirected")
    return target


def download(url: str, digest: str, cache_dir: Path | None = None) -> bytes:
    target = _cache_path(cache_dir, digest) if cache_dir is not None else None
    if target is not None and target.exists():
        try:
            with target.open("rb") as stream:
                return _verified(stream.read(MAX_BYTES + 1), digest)
        except RuntimeError:
            # Do not trust or repeatedly reuse a corrupt entry. Keep it local
            # for diagnosis, then retrieve the same pinned official input.
            quarantine = target.with_name(f"{target.name}.invalid-{time.time_ns()}")
            try:
                target.replace(quarantine)
            except FileNotFoundError:
                pass  # Another writer already quarantined the same entry.
    if url == SOURCE_URL and digest == SOURCE_SHA256:
        # The original Fossil endpoint now redirects to an HTML introduction.
        # Preserve the exact reviewed bytes and digest rather than accepting a
        # different revision or relying on an unreviewed mirror.
        with BUNDLED_SOURCE.open("rb") as stream:
            data = _verified(stream.read(MAX_BYTES + 1), digest)
    else:
        data = _fetch(url, digest)
    if target is not None:
        descriptor, name = tempfile.mkstemp(prefix=".vec1-", suffix=".tmp", dir=target.parent)
        pending = Path(name)
        try:
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            _cache_path(target.parent, digest)
            try:
                # Publish without replacing a winner that another process may
                # already be reading (Windows does not share delete handles).
                os.link(pending, target)
            except FileExistsError:
                with target.open("rb") as stream:
                    _verified(stream.read(MAX_BYTES + 1), digest)
        finally:
            pending.unlink(missing_ok=True)
    return data


def prepare_sources(cache_dir: Path) -> None:
    download(SOURCE_URL, SOURCE_SHA256, cache_dir)
    archive = download(SQLITE_URL, SQLITE_SHA256, cache_dir)
    with zipfile.ZipFile(io.BytesIO(archive)) as packed:
        for name in ("sqlite3.h", "sqlite3ext.h"):
            info = packed.getinfo("sqlite-amalgamation-3530000/" + name)
            if info.file_size > MAX_BYTES:
                raise RuntimeError("vec1_build_header_too_large")
            packed.read(info)  # Validate CRC and the expected archive members.


def build(output: Path, cache_dir: Path | None = None):
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="angmoo-vec1-build-") as directory:
        root = Path(directory)
        (root / "vec1.c").write_bytes(download(SOURCE_URL, SOURCE_SHA256, cache_dir))
        archive = download(SQLITE_URL, SQLITE_SHA256, cache_dir)
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
    parser.add_argument("--output", type=Path)
    parser.add_argument("--source-cache-dir", type=Path)
    parser.add_argument("--prepare-only", action="store_true")
    args = parser.parse_args()
    if args.prepare_only:
        if args.source_cache_dir is None:
            parser.error("--prepare-only requires --source-cache-dir")
        prepare_sources(args.source_cache_dir)
    elif args.output is not None:
        build(args.output.resolve(), args.source_cache_dir)
    else:
        parser.error("--output is required for a build")
