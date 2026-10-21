#!/usr/bin/env python3
"""Release-rendered, standard-library-only first-install entry point.

Download this file from the versioned official GitHub Release before running it.
The release producer binds it to the exact tools ZIP; it never executes a main
branch script or substitutes a different release after a download failure.
"""

from __future__ import annotations

import hashlib
import io
from pathlib import Path
import platform
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import urllib.request
import zipfile

# Filled by scripts.release.prepare, not supplied by environment variables.
RELEASE = "@ANGMOO_RELEASE@"
TOOLS_SHA256 = "@ANGMOO_TOOLS_SHA256@"
TOOLS_SIZE = "@ANGMOO_TOOLS_SIZE@"
REPOSITORY = "angmoo-tree/angmoo"
TOOLS_NAME = "angmoo-termux-tools.zip"
FILES = frozenset({"angmoo.py", "payload.py", "processes.py", "service_logs.py", "log_policy.py", "requirements.txt", "setup.sh", "LICENSE"})
MAX_TOOLS_BYTES = 4 * 1024 * 1024


class InstallError(Exception):
    def __init__(self, code: str, en: str):
        super().__init__(f"{code}: {en}")


def require(value, code: str, en: str) -> None:
    if not value:
        raise InstallError(code, en)


class HTTPSRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        require(newurl.startswith("https://"), "download_redirect_invalid",
                "The release download must use HTTPS.")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def download(name: str, limit: int) -> bytes:
    url = f"https://github.com/{REPOSITORY}/releases/download/release-v{RELEASE}/{name}"
    opener = urllib.request.build_opener(HTTPSRedirects())
    try:
        with opener.open(url, timeout=45) as response:
            raw = response.read(limit + 1)
    except OSError as exc:
        raise InstallError("release_download_failed", "The official release could not be downloaded; retry this installer later.") from exc
    require(len(raw) <= limit, "download_too_large", "The release file exceeds its size limit.")
    return raw


def extract_verified(raw: bytes, checksums: bytes, directory: Path) -> None:
    expected = [line.split() for line in checksums.decode("ascii").splitlines()]
    entries = [parts for parts in expected if len(parts) == 2 and parts[1] == TOOLS_NAME]
    require(entries == [[TOOLS_SHA256, TOOLS_NAME]] and len(raw) == int(TOOLS_SIZE)
            and hashlib.sha256(raw).hexdigest() == TOOLS_SHA256,
            "tools_hash_mismatch", "The tools checksum or size does not match; nothing was installed.")
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        members = archive.infolist()
        require(len(members) == len(FILES) and {item.filename for item in members} == FILES
                and all(stat.S_IFMT(item.external_attr >> 16) in (0, stat.S_IFREG) for item in members)
                and sum(item.file_size for item in members) <= MAX_TOOLS_BYTES,
                "tools_archive_invalid", "The tools archive has unexpected entries.")
        # Only flat, allowlisted regular files are materialized in a private,
        # newly-created directory. Never extract paths or links from the ZIP.
        for item in members:
            (directory / item.filename).write_bytes(archive.read(item))


def install_and_start(directory: Path, home: Path) -> None:
    launcher = home / ".local/bin/angmoo"
    # Keep setup separate from the product: the existing launcher still owns
    # image verification, installation selection, locking, readiness and stop.
    subprocess.run(["sh", str(directory / "setup.sh")], check=True)
    subprocess.run([str(launcher), "install", "--release", RELEASE], check=True)
    subprocess.run([str(launcher), "start"], check=True)


def main() -> int:
    try:
        require(re.fullmatch(r"\d+\.\d+\.\d+", RELEASE) and re.fullmatch(r"[0-9a-f]{64}", TOOLS_SHA256)
                and TOOLS_SIZE.isdigit() and 0 < int(TOOLS_SIZE) <= MAX_TOOLS_BYTES,
                "installer_not_packaged", "Use install-termux.py from the official versioned Release.")
        require(sys.platform in {"linux", "android"} and platform.machine() in {"aarch64", "arm64"},
                "host_not_supported", "This installer requires ARM64 Termux.")
        require(shutil.which("sh") and shutil.which("proot"), "prerequisites_missing",
                "First run: pkg install python curl proot")
        home = Path.home()
        require(not any(p.is_symlink() for p in (home, *home.parents))
                and not str(home.resolve()).startswith(("/sdcard", "/storage", "/mnt/media_rw")),
                "private_storage_required", "Run in Termux private storage.")
        print("Downloading and verifying Angmoo tools.", flush=True)
        checksums = download("RELEASE-SHA256SUMS", 64 * 1024)
        raw = download(TOOLS_NAME, int(TOOLS_SIZE))
        with tempfile.TemporaryDirectory(prefix=".angmoo-install-", dir=home) as staging:
            directory = Path(staging)
            extract_verified(raw, checksums, directory)
            install_and_start(directory, home)
        print("Ready: http://127.0.0.1:3000")
        print("Next start: ~/.local/bin/angmoo start")
        return 0
    except InstallError as exc:
        print(str(exc), file=sys.stderr)
    except subprocess.CalledProcessError as exc:
        print(f"installation_step_failed (exit={exc.returncode}): See the preceding error; later steps were not run.", file=sys.stderr)
    except (OSError, ValueError, zipfile.BadZipFile) as exc:
        print(f"installation_failed ({type(exc).__name__}): Retry after checking the release and local environment.", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
