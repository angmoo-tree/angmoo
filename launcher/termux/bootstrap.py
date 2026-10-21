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
FILES = frozenset({"angmoo.py", "payload.py", "processes.py", "requirements.txt", "setup.sh", "LICENSE"})
MAX_TOOLS_BYTES = 4 * 1024 * 1024


class InstallError(Exception):
    def __init__(self, code: str, en: str, ko: str):
        super().__init__(f"{code}: {en} / {ko}")


def require(value, code: str, en: str, ko: str) -> None:
    if not value:
        raise InstallError(code, en, ko)


class HTTPSRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        require(newurl.startswith("https://"), "download_redirect_invalid",
                "The release download must use HTTPS.", "배포물은 HTTPS로 내려받아야 합니다.")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def download(name: str, limit: int) -> bytes:
    url = f"https://github.com/{REPOSITORY}/releases/download/release-v{RELEASE}/{name}"
    opener = urllib.request.build_opener(HTTPSRedirects())
    try:
        with opener.open(url, timeout=45) as response:
            raw = response.read(limit + 1)
    except OSError as exc:
        raise InstallError("release_download_failed", "The official release could not be downloaded; retry this installer later.",
                           "공식 배포물을 내려받지 못했습니다. 나중에 설치기를 다시 실행하세요.") from exc
    require(len(raw) <= limit, "download_too_large", "The release file exceeds its size limit.", "배포 파일이 크기 제한을 넘었습니다.")
    return raw


def extract_verified(raw: bytes, checksums: bytes, directory: Path) -> None:
    expected = [line.split() for line in checksums.decode("ascii").splitlines()]
    entries = [parts for parts in expected if len(parts) == 2 and parts[1] == TOOLS_NAME]
    require(entries == [[TOOLS_SHA256, TOOLS_NAME]] and len(raw) == int(TOOLS_SIZE)
            and hashlib.sha256(raw).hexdigest() == TOOLS_SHA256,
            "tools_hash_mismatch", "The tools checksum or size does not match; nothing was installed.",
            "실행기의 해시 또는 크기가 일치하지 않아 설치하지 않았습니다.")
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        members = archive.infolist()
        require(len(members) == len(FILES) and {item.filename for item in members} == FILES
                and all(stat.S_IFMT(item.external_attr >> 16) in (0, stat.S_IFREG) for item in members)
                and sum(item.file_size for item in members) <= MAX_TOOLS_BYTES,
                "tools_archive_invalid", "The tools archive has unexpected entries.", "실행기 압축 파일의 구성이 올바르지 않습니다.")
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
                "installer_not_packaged", "Use install-termux.py from the official versioned Release.",
                "공식 버전별 Release의 install-termux.py를 사용하세요.")
        require(sys.platform == "linux" and platform.machine() in {"aarch64", "arm64"},
                "host_not_supported", "This installer requires ARM64 Termux.", "이 설치기는 ARM64 Termux용입니다.")
        require(shutil.which("sh") and shutil.which("proot"), "prerequisites_missing",
                "First run: pkg install python curl proot", "먼저 실행하세요: pkg install python curl proot")
        home = Path.home()
        require(not any(p.is_symlink() for p in (home, *home.parents))
                and not str(home.resolve()).startswith(("/sdcard", "/storage", "/mnt/media_rw")),
                "private_storage_required", "Run in Termux private storage.", "Termux 내부 전용 저장소에서 실행하세요.")
        print("Downloading and verifying Angmoo tools. / Angmoo 실행기를 내려받고 검증합니다.", flush=True)
        checksums = download("RELEASE-SHA256SUMS", 64 * 1024)
        raw = download(TOOLS_NAME, int(TOOLS_SIZE))
        with tempfile.TemporaryDirectory(prefix=".angmoo-install-", dir=home) as staging:
            directory = Path(staging)
            extract_verified(raw, checksums, directory)
            install_and_start(directory, home)
        print("Ready: http://127.0.0.1:3000 / 준비 완료: 브라우저에서 이 주소를 여세요.")
        print("Next start: ~/.local/bin/angmoo start / 다음 실행: ~/.local/bin/angmoo start")
        return 0
    except InstallError as exc:
        print(str(exc), file=sys.stderr)
    except subprocess.CalledProcessError as exc:
        print(f"installation_step_failed (exit={exc.returncode}): See the preceding error; later steps were not run. / 위 오류를 확인하세요. 후속 단계는 실행하지 않았습니다.", file=sys.stderr)
    except (OSError, ValueError, zipfile.BadZipFile) as exc:
        print(f"installation_failed ({type(exc).__name__}): Retry after checking the release and local environment. / 배포물과 실행 환경을 확인한 뒤 다시 시도하세요.", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
