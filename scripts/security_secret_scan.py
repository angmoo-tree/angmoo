"""Scan Git objects or an export root for secrets, PII, and unsafe assets.

Only paths, line numbers, rule names, and Git object IDs are reported. Matched
values and source lines are never printed.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass, field
import hashlib
from io import BytesIO
import json
import mimetypes
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys
from typing import Iterable

try:
    from PIL import ExifTags, Image, UnidentifiedImageError
except ImportError:  # pragma: no cover - verified by the strict asset tests
    Image = None
    ExifTags = None

    class UnidentifiedImageError(Exception):
        pass


DEFAULT_REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ALLOWLIST = DEFAULT_REPO_ROOT / "backend" / "security" / "secret_scan_allowlist.json"
DEFAULT_ASSET_MANIFEST = DEFAULT_REPO_ROOT / "backend" / "security" / "asset_manifest.json"


@dataclass(frozen=True)
class Rule:
    name: str
    pattern: re.Pattern[str]
    env_only: bool = False
    public_only: bool = False


@dataclass(frozen=True)
class Finding:
    source: str
    rule: str
    line: int | None = None
    ref: str | None = None
    fatal: bool = True


@dataclass(frozen=True)
class AllowEntry:
    path: str
    rule: str
    value: str


@dataclass(frozen=True)
class AssetEntry:
    path: str
    sha256: str
    media_type: str


@dataclass
class ScanReport:
    findings: list[Finding] = field(default_factory=list)
    files_scanned: int = 0
    binary_files_audited: int = 0

    @property
    def fatal_findings(self) -> list[Finding]:
        return [finding for finding in self.findings if finding.fatal]

    def extend(self, findings: Iterable[Finding]) -> None:
        self.findings.extend(findings)


RULES = (
    Rule(
        "private-key-block",
        re.compile(r"-----BEGIN (?:RSA |DSA |EC |OPENSSH |PGP )?PRIVATE KEY-----"),
    ),
    Rule("openai-api-key", re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b")),
    Rule("google-api-key", re.compile(r"\bAIza[0-9A-Za-z_-]{20,}\b")),
    Rule("github-token", re.compile(r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9_]{20,}\b")),
    Rule("github-pat", re.compile(r"\bgithub_pat_[A-Za-z0-9_]{30,}\b")),
    Rule("slack-token", re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{20,}\b")),
    Rule(
        "jwt-token",
        re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b"),
    ),
    Rule(
        "credentialed-database-url",
        re.compile(
            r"\b(?:postgres(?:ql)?(?:\+[^:]+)?|mysql(?:\+[^:]+)?|redis)://"
            r"[^\s/:@]+:[^\s/@]+@[^\s]+",
            re.IGNORECASE,
        ),
    ),
    Rule(
        "sensitive-env-assignment",
        re.compile(
            r"(?m)^[ \t]*([A-Z0-9_]*(?:SECRET|TOKEN|PASSWORD|API_KEY|PRIVATE_KEY|DATABASE_URL)"
            r"[A-Z0-9_]*)[ \t]*=[ \t]*([^ \t\r\n#]{12,})"
        ),
        env_only=True,
    ),
    Rule(
        "email-address",
        re.compile(r"(?<![A-Za-z0-9._%+-])[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}(?![A-Za-z0-9.-])"),
        public_only=True,
    ),
)

TEXT_SUFFIXES = {
    ".cfg",
    ".conf",
    ".css",
    ".csv",
    ".env",
    ".example",
    ".gitignore",
    ".html",
    ".ini",
    ".js",
    ".json",
    ".jsx",
    ".lock",
    ".md",
    ".mjs",
    ".py",
    ".sql",
    ".svg",
    ".toml",
    ".ts",
    ".tsx",
    ".txt",
    ".yaml",
    ".yml",
}
TEXT_NAMES = {
    "dockerfile",
    "license",
    "notice",
    "readme",
    "security",
}
ASSET_SUFFIXES = {
    ".bmp",
    ".gif",
    ".ico",
    ".jpeg",
    ".jpg",
    ".otf",
    ".png",
    ".svg",
    ".ttf",
    ".webp",
    ".woff",
    ".woff2",
}
RASTER_SUFFIXES = {".bmp", ".gif", ".ico", ".jpeg", ".jpg", ".png", ".webp"}
FORBIDDEN_PUBLIC_SUFFIXES = {
    ".7z",
    ".bak",
    ".database",
    ".db",
    ".dump",
    ".key",
    ".p12",
    ".pem",
    ".pfx",
    ".sqlite",
    ".sqlite3",
    ".tar",
    ".tgz",
    ".zip",
}
FORBIDDEN_ROOT_DIRS = {
    ".next",
    ".pytest_cache",
    ".venv",
    "__pycache__",
    "node_modules",
}
SVG_REMOTE_PATTERN = re.compile(
    r"(?:href|xlink:href)\s*=\s*[\"'](?:https?://|data:)", re.IGNORECASE
)
SVG_METADATA_PATTERN = re.compile(r"<metadata(?:\s[^>]*)?>\s*.+?\s*</metadata>", re.IGNORECASE | re.DOTALL)
PRIVATE_IMAGE_METADATA_KEYS = {
    "artist",
    "author",
    "comment",
    "copyright",
    "description",
    "gpsinfo",
    "imagedescription",
    "usercomment",
    "xml:com.adobe.xmp",
}
TOOL_IMAGE_METADATA_KEYS = {"software"}
SAFE_PUBLIC_EMAIL_DOMAINS = {"example.com", "example.net", "example.org"}
SAFE_PUBLIC_EMAIL_SUFFIXES = (".example", ".invalid", ".test")


def normalize_path(value: str) -> str:
    normalized = PurePosixPath(value.replace("\\", "/")).as_posix()
    while normalized.startswith("./"):
        normalized = normalized[2:]
    return normalized


def run_git(repo_root: Path, args: list[str], *, input_bytes: bytes | None = None) -> bytes:
    result = subprocess.run(
        ["git", *args],
        cwd=repo_root,
        input=input_bytes,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        stderr = result.stderr.decode("utf-8", errors="replace").strip()
        raise RuntimeError(stderr or f"git {' '.join(args)} failed")
    return result.stdout


def load_allowlist(path: Path | None) -> tuple[AllowEntry, ...]:
    if path is None or not path.exists():
        return ()
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema_version") != 1:
        raise ValueError("unsupported secret allowlist schema")
    return tuple(
        AllowEntry(
            path=normalize_path(item["path"]),
            rule=str(item["rule"]),
            value=str(item["value"]),
        )
        for item in payload.get("entries", [])
    )


def load_asset_manifest(path: Path | None) -> dict[str, AssetEntry]:
    if path is None or not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema_version") != 1:
        raise ValueError("unsupported asset manifest schema")
    entries: dict[str, AssetEntry] = {}
    for item in payload.get("assets", []):
        entry = AssetEntry(
            path=normalize_path(item["path"]),
            sha256=str(item["sha256"]).lower(),
            media_type=str(item["media_type"]).lower(),
        )
        if entry.path in entries:
            raise ValueError(f"duplicate asset manifest path: {entry.path}")
        entries[entry.path] = entry
    return entries


def is_env_like_path(path: str) -> bool:
    name = PurePosixPath(normalize_path(path)).name.lower()
    return name == ".env" or name.startswith(".env.") or name.endswith(".env") or ".env." in name


def _match_value(rule: Rule, match: re.Match[str]) -> str:
    return match.group(2) if rule.name == "sensitive-env-assignment" else match.group(0)


def _is_allowlisted(
    source: str,
    rule: Rule,
    match: re.Match[str],
    allowlist: tuple[AllowEntry, ...],
) -> bool:
    value = _match_value(rule, match).strip().strip("\"'")
    path = normalize_path(source)
    return any(
        entry.path == path and entry.rule == rule.name and entry.value == value
        for entry in allowlist
    )


def _is_safe_public_email(value: str) -> bool:
    _, _, domain = value.lower().rpartition("@")
    return domain in SAFE_PUBLIC_EMAIL_DOMAINS or domain.endswith(
        SAFE_PUBLIC_EMAIL_SUFFIXES
    )


def scan_text(
    source: str,
    text: str,
    *,
    allowlist: tuple[AllowEntry, ...] = (),
    ref: str | None = None,
    strict_public: bool = False,
) -> Iterable[Finding]:
    for rule in RULES:
        if rule.public_only and not strict_public:
            continue
        if rule.env_only and not is_env_like_path(source):
            continue
        for match in rule.pattern.finditer(text):
            value = _match_value(rule, match).strip().strip("\"'")
            if rule.name == "email-address" and _is_safe_public_email(value):
                continue
            if _is_allowlisted(source, rule, match, allowlist):
                continue
            yield Finding(
                source=normalize_path(source),
                line=text.count("\n", 0, match.start()) + 1,
                rule=rule.name,
                ref=ref,
            )

    if PurePosixPath(normalize_path(source)).suffix.lower() == ".svg":
        for pattern, rule_name in (
            (SVG_REMOTE_PATTERN, "svg-embedded-remote-content"),
            (SVG_METADATA_PATTERN, "svg-metadata"),
        ):
            for match in pattern.finditer(text):
                yield Finding(
                    source=normalize_path(source),
                    line=text.count("\n", 0, match.start()) + 1,
                    rule=rule_name,
                    ref=ref,
                    fatal=strict_public,
                )


def _looks_text(source: str, data: bytes) -> bool:
    path = PurePosixPath(normalize_path(source))
    if path.suffix.lower() in TEXT_SUFFIXES or path.name.lower() in TEXT_NAMES:
        return True
    if b"\0" in data[:8192]:
        return False
    try:
        sample = data[:8192].decode("utf-8")
    except UnicodeDecodeError:
        return False
    if not sample:
        return True
    printable = sum(character.isprintable() or character in "\r\n\t" for character in sample)
    return printable / len(sample) >= 0.90


def _asset_media_type_allowed(path: str, media_type: str) -> bool:
    suffix = PurePosixPath(path).suffix.lower()
    allowed = {
        ".bmp": {"image/bmp"},
        ".gif": {"image/gif"},
        ".ico": {"image/x-icon", "image/vnd.microsoft.icon"},
        ".jpeg": {"image/jpeg"},
        ".jpg": {"image/jpeg"},
        ".otf": {"font/otf", "application/vnd.ms-opentype"},
        ".png": {"image/png"},
        ".svg": {"image/svg+xml"},
        ".ttf": {"font/ttf"},
        ".webp": {"image/webp"},
        ".woff": {"font/woff"},
        ".woff2": {"font/woff2"},
    }
    return media_type in allowed.get(suffix, {mimetypes.guess_type(path)[0] or ""})


def _verify_asset(
    source: str,
    data: bytes,
    *,
    manifest: dict[str, AssetEntry],
    ref: str | None,
    strict_public: bool,
) -> list[Finding]:
    path = normalize_path(source)
    entry = manifest.get(path)
    if entry is None:
        return [
            Finding(
                source=path,
                rule="asset-not-approved-for-public",
                ref=ref,
                fatal=strict_public,
            )
        ]
    digest = hashlib.sha256(data).hexdigest()
    findings: list[Finding] = []
    if digest != entry.sha256:
        findings.append(
            Finding(
                source=path,
                rule="asset-sha256-mismatch",
                ref=ref,
                fatal=strict_public,
            )
        )
    if not _asset_media_type_allowed(path, entry.media_type):
        findings.append(
            Finding(
                source=path,
                rule="asset-media-type-mismatch",
                ref=ref,
                fatal=strict_public,
            )
        )
    return findings


def _scan_raster_metadata(
    source: str,
    data: bytes,
    *,
    ref: str | None,
    strict_public: bool,
) -> list[Finding]:
    path = normalize_path(source)
    if Image is None:
        return [
            Finding(
                source=path,
                rule="asset-metadata-inspector-unavailable",
                ref=ref,
                fatal=strict_public,
            )
        ]
    try:
        with Image.open(BytesIO(data)) as image:
            metadata_keys = {str(key).lower() for key in image.info}
            exif = image.getexif()
            for key in exif:
                name = str(ExifTags.TAGS.get(key, key)).lower()
                metadata_keys.add(name)
    except (OSError, UnidentifiedImageError, ValueError):
        return [
            Finding(
                source=path,
                rule="asset-image-decode-failed",
                ref=ref,
                fatal=strict_public,
            )
        ]
    if metadata_keys.intersection(PRIVATE_IMAGE_METADATA_KEYS):
        return [
            Finding(
                source=path,
                rule="asset-sensitive-metadata",
                ref=ref,
                fatal=strict_public,
            )
        ]
    if metadata_keys.intersection(TOOL_IMAGE_METADATA_KEYS):
        return [
            Finding(
                source=path,
                rule="asset-tool-metadata",
                ref=ref,
                fatal=False,
            )
        ]
    return []


def scan_blob(
    source: str,
    data: bytes,
    *,
    allowlist: tuple[AllowEntry, ...] = (),
    asset_manifest: dict[str, AssetEntry] | None = None,
    ref: str | None = None,
    strict_public: bool = False,
) -> ScanReport:
    asset_manifest = asset_manifest or {}
    report = ScanReport(files_scanned=1)
    path = normalize_path(source)
    suffix = PurePosixPath(path).suffix.lower()

    if suffix in FORBIDDEN_PUBLIC_SUFFIXES:
        report.findings.append(
            Finding(
                source=path,
                rule="forbidden-public-file",
                ref=ref,
                fatal=strict_public or suffix in {".key", ".p12", ".pem", ".pfx"},
            )
        )

    if suffix in ASSET_SUFFIXES:
        report.extend(
            _verify_asset(
                path,
                data,
                manifest=asset_manifest,
                ref=ref,
                strict_public=strict_public,
            )
        )

    if _looks_text(path, data):
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            report.findings.append(
                Finding(source=path, rule="text-decode-failed", ref=ref)
            )
            return report
        report.extend(
            scan_text(
                path,
                text,
                allowlist=allowlist,
                ref=ref,
                strict_public=strict_public,
            )
        )
        return report

    report.binary_files_audited = 1
    if suffix not in ASSET_SUFFIXES and suffix not in FORBIDDEN_PUBLIC_SUFFIXES:
        report.findings.append(
            Finding(
                source=path,
                rule="unclassified-binary",
                ref=ref,
                fatal=strict_public,
            )
        )
    if suffix in RASTER_SUFFIXES:
        report.extend(
            _scan_raster_metadata(
                path,
                data,
                ref=ref,
                strict_public=strict_public,
            )
        )
    return report


def _merge_report(target: ScanReport, current: ScanReport) -> None:
    target.findings.extend(current.findings)
    target.files_scanned += current.files_scanned
    target.binary_files_audited += current.binary_files_audited


def scan_root(
    root: Path,
    *,
    allowlist: tuple[AllowEntry, ...] = (),
    asset_manifest: dict[str, AssetEntry] | None = None,
) -> ScanReport:
    root = root.resolve()
    if not root.is_dir():
        raise ValueError("scan root must be a directory")
    report = ScanReport()
    for current_root, directory_names, file_names in os.walk(root, topdown=True, followlinks=False):
        current = Path(current_root)
        kept_directories: list[str] = []
        for name in directory_names:
            path = current / name
            relative = normalize_path(str(path.relative_to(root)))
            if name == ".git":
                continue
            if path.is_symlink():
                report.findings.append(Finding(relative, "symlink-not-allowed"))
                continue
            if name in FORBIDDEN_ROOT_DIRS:
                report.findings.append(Finding(relative, "forbidden-export-directory"))
                continue
            kept_directories.append(name)
        directory_names[:] = kept_directories

        for name in file_names:
            path = current / name
            relative = normalize_path(str(path.relative_to(root)))
            if path.is_symlink():
                report.findings.append(Finding(relative, "symlink-not-allowed"))
                continue
            try:
                data = path.read_bytes()
            except OSError:
                report.findings.append(Finding(relative, "file-read-failed"))
                continue
            _merge_report(
                report,
                scan_blob(
                    relative,
                    data,
                    allowlist=allowlist,
                    asset_manifest=asset_manifest,
                    strict_public=True,
                ),
            )
    return report


@dataclass(frozen=True)
class GitBlob:
    oid: str
    path: str
    mode: str | None = None


def git_tree_blobs(repo_root: Path, ref: str) -> list[GitBlob]:
    output = run_git(repo_root, ["ls-tree", "-r", "-z", "--full-tree", ref])
    blobs: list[GitBlob] = []
    for raw_entry in output.split(b"\0"):
        if not raw_entry:
            continue
        metadata, separator, raw_path = raw_entry.partition(b"\t")
        if not separator:
            raise RuntimeError("invalid git ls-tree entry")
        mode, object_type, oid = metadata.decode("ascii").split()
        if object_type != "blob":
            continue
        blobs.append(
            GitBlob(
                oid=oid,
                path=raw_path.decode("utf-8", errors="surrogateescape"),
                mode=mode,
            )
        )
    return blobs


def history_blobs(repo_root: Path, limit: int | None) -> list[GitBlob]:
    output = run_git(repo_root, ["rev-list", "--objects", "--all"])
    blobs: list[GitBlob] = []
    seen: set[str] = set()
    for raw_line in output.splitlines():
        oid_bytes, separator, path_bytes = raw_line.partition(b" ")
        if not separator:
            continue
        oid = oid_bytes.decode("ascii")
        if oid in seen:
            continue
        seen.add(oid)
        blobs.append(
            GitBlob(
                oid=oid,
                path=path_bytes.decode("utf-8", errors="surrogateescape"),
            )
        )
        if limit is not None and len(blobs) >= limit:
            break
    return blobs


def _scan_git_blobs(
    repo_root: Path,
    blobs: list[GitBlob],
    *,
    allowlist: tuple[AllowEntry, ...],
    asset_manifest: dict[str, AssetEntry],
) -> ScanReport:
    report = ScanReport()
    entries_by_oid: dict[str, list[GitBlob]] = {}
    for blob in blobs:
        entries_by_oid.setdefault(blob.oid, []).append(blob)
    if not entries_by_oid:
        return report

    process = subprocess.run(
        ["git", "cat-file", "--batch"],
        cwd=repo_root,
        input=("\n".join(entries_by_oid) + "\n").encode("ascii"),
        capture_output=True,
        check=False,
    )
    if process.returncode != 0:
        raise RuntimeError(
            process.stderr.decode("utf-8", errors="replace").strip()
            or "git cat-file failed"
        )
    output = BytesIO(process.stdout)

    while True:
        header = output.readline()
        if not header:
            break
        parts = header.decode("ascii", errors="replace").strip().split()
        if len(parts) < 3:
            raise RuntimeError("invalid git cat-file response")
        oid, object_type, size_text = parts[:3]
        size = int(size_text)
        data = output.read(size)
        output.read(1)
        if object_type != "blob":
            continue
        for entry in entries_by_oid.get(oid, []):
            if entry.mode == "120000":
                report.findings.append(
                    Finding(
                        source=normalize_path(entry.path),
                        rule="git-symlink-entry",
                        ref=f"blob={oid}",
                        fatal=False,
                    )
                )
            _merge_report(
                report,
                scan_blob(
                    entry.path,
                    data,
                    allowlist=allowlist,
                    asset_manifest=asset_manifest,
                    ref=f"blob={oid}",
                    strict_public=False,
                ),
            )

    return report


def scan_git_tree(
    repo_root: Path,
    ref: str,
    *,
    allowlist: tuple[AllowEntry, ...] = (),
    asset_manifest: dict[str, AssetEntry] | None = None,
) -> ScanReport:
    return _scan_git_blobs(
        repo_root,
        git_tree_blobs(repo_root, ref),
        allowlist=allowlist,
        asset_manifest=asset_manifest or {},
    )


def scan_history(
    repo_root: Path,
    limit: int | None,
    *,
    allowlist: tuple[AllowEntry, ...] = (),
    asset_manifest: dict[str, AssetEntry] | None = None,
) -> ScanReport:
    return _scan_git_blobs(
        repo_root,
        history_blobs(repo_root, limit),
        allowlist=allowlist,
        asset_manifest=asset_manifest or {},
    )


def env_like_history_paths(repo_root: Path) -> list[str]:
    output = run_git(
        repo_root,
        ["log", "--all", "--name-only", "--pretty=format:", "--", "*.env*", "*.pem", "*.key"],
    )
    return sorted(
        {
            normalize_path(line.decode("utf-8", errors="replace").strip())
            for line in output.splitlines()
            if line.strip()
        }
    )


def print_report(report: ScanReport) -> None:
    for finding in report.findings:
        location = finding.source
        if finding.line is not None:
            location = f"{location}:{finding.line}"
        ref = f" {finding.ref}" if finding.ref else ""
        severity = "error" if finding.fatal else "audit"
        print(f"{location}: rule={finding.rule}{ref} severity={severity}")
    print(
        "Scan summary: "
        f"files={report.files_scanned} "
        f"binary_audited={report.binary_files_audited} "
        f"findings={len(report.findings)} "
        f"fatal={len(report.fatal_findings)}"
    )


def _resolved_optional_path(value: str | None, default: Path) -> Path | None:
    if value is None:
        return default if default.exists() else None
    return Path(value).resolve()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--git-tree", metavar="REF", help="scan every blob in a Git tree")
    mode.add_argument("--history", action="store_true", help="scan reachable Git history")
    mode.add_argument("--root", type=Path, help="scan every file below an export directory")
    parser.add_argument(
        "--history-limit",
        type=int,
        default=100,
        help="limit unique history blobs; 0 means all reachable blobs",
    )
    parser.add_argument("--repo-root", type=Path, default=DEFAULT_REPO_ROOT)
    parser.add_argument("--allowlist", help="path+rule+exact-value JSON allowlist")
    parser.add_argument("--asset-manifest", help="approved asset path+SHA-256+media type JSON")
    parser.add_argument("--list-env-history", action="store_true")
    parser.add_argument("--no-fail", action="store_true")
    args = parser.parse_args()

    repo_root = args.repo_root.resolve()
    allowlist_path = _resolved_optional_path(args.allowlist, DEFAULT_ALLOWLIST)
    asset_manifest_path = _resolved_optional_path(args.asset_manifest, DEFAULT_ASSET_MANIFEST)
    allowlist = load_allowlist(allowlist_path)
    asset_manifest = load_asset_manifest(asset_manifest_path)

    if args.root is not None:
        report = scan_root(
            args.root,
            allowlist=allowlist,
            asset_manifest=asset_manifest,
        )
    elif args.history:
        limit = None if args.history_limit == 0 else args.history_limit
        if limit is not None and limit < 1:
            parser.error("--history-limit must be 0 or a positive integer")
        report = scan_history(
            repo_root,
            limit,
            allowlist=allowlist,
            asset_manifest=asset_manifest,
        )
    else:
        report = scan_git_tree(
            repo_root,
            args.git_tree or "HEAD",
            allowlist=allowlist,
            asset_manifest=asset_manifest,
        )

    print_report(report)
    if args.list_env_history:
        print("Env/key-like paths in Git history:")
        for path in env_like_history_paths(repo_root):
            print(f"- {path}")
    return 0 if args.no_fail or not report.fatal_findings else 1


if __name__ == "__main__":
    sys.exit(main())
