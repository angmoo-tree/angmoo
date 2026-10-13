from __future__ import annotations

import hashlib
import importlib.util
from io import BytesIO
from pathlib import Path
import subprocess
import sys
import pytest

from PIL import Image, PngImagePlugin


REPO_ROOT = Path(__file__).resolve().parents[2]
SCANNER_PATH = REPO_ROOT / "scripts" / "security_secret_scan.py"
SPEC = importlib.util.spec_from_file_location("angmoo_security_secret_scan", SCANNER_PATH)
assert SPEC is not None and SPEC.loader is not None
scanner = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = scanner
SPEC.loader.exec_module(scanner)


class BatchProcess:
    def __init__(self, output, returncode=0):
        self.requests = []
        owner = self
        class Sink(BytesIO):
            def write(self, value):
                owner.requests.append(value)
                return super().write(value)
        class BoundedOutput(BytesIO):
            def read(self, size=-1):
                assert size >= 0, "whole-history reads are forbidden"
                return super().read(size)
        self.stdin = Sink()
        self.stdout = BoundedOutput(output)
        self.returncode = returncode
        self.finished = False
        self.killed = False
    def wait(self):
        self.finished = True
        return self.returncode
    def poll(self):
        return self.returncode if self.finished else None
    def kill(self):
        self.killed = True
        self.returncode = -9


def test_batch_stream_drains_each_object_and_checks_every_path(monkeypatch, tmp_path):
    first, second = "1" * 40, "2" * 40
    sensitive = b"GOOGLE_API_KEY=AIza12345678901234567890\n"
    harmless = b"no credential\n"
    output = (f"{first} blob {len(sensitive)}\n".encode() + sensitive + b"\n"
              + f"{second} blob {len(harmless)}\n".encode() + harmless + b"\n")
    process = BatchProcess(output)
    monkeypatch.setattr(scanner.subprocess, "Popen", lambda *args, **kwargs: process)
    allow = (scanner.AllowEntry(path="safe.env", rule="google-api-key", value="AIza12345678901234567890"),
             scanner.AllowEntry(path="safe.env", rule="sensitive-env-assignment", value="AIza12345678901234567890"))
    report = scanner._scan_git_blobs(tmp_path, [scanner.GitBlob(first, "safe.env"),
        scanner.GitBlob(first, "unsafe.env"), scanner.GitBlob(second, "other.txt")], allowlist=allow, asset_manifest={})
    assert process.requests == [(first + "\n").encode(), (second + "\n").encode()]
    assert report.files_scanned == 3
    assert report.fatal_findings and all(f.source == "unsafe.env" for f in report.fatal_findings)
    assert not process.killed and process.stdin.closed and process.stdout.closed


@pytest.mark.parametrize("output", [
    b"", b"1" * 40 + b" missing\n", b"2" * 40 + b" blob 1\na\n",
    b"1" * 40 + b" blob -1\n", b"1" * 40 + b" blob wrong\n",
    b"1" * 40 + b" blob 8\nshort", b"1" * 40 + b" blob 1\na!",
])
def test_batch_stream_rejects_invalid_or_truncated_objects_and_closes_process(monkeypatch, tmp_path, output):
    process = BatchProcess(output)
    monkeypatch.setattr(scanner.subprocess, "Popen", lambda *args, **kwargs: process)
    with pytest.raises(RuntimeError):
        scanner._scan_git_blobs(tmp_path, [scanner.GitBlob("1" * 40, "source.txt")], allowlist=(), asset_manifest={})
    assert process.killed and process.stdin.closed and process.stdout.closed


def test_batch_stream_requires_successful_git_exit(monkeypatch, tmp_path):
    oid = "1" * 40
    process = BatchProcess(f"{oid} blob 1\na\n".encode(), returncode=1)
    monkeypatch.setattr(scanner.subprocess, "Popen", lambda *args, **kwargs: process)
    with pytest.raises(RuntimeError, match="git cat-file failed"):
        scanner._scan_git_blobs(tmp_path, [scanner.GitBlob(oid, "source.txt")], allowlist=(), asset_manifest={})
    assert process.stdin.closed and process.stdout.closed


def _git(repo: Path, *args: str) -> None:
    result = subprocess.run(
        ["git", *args],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr


def _init_repo(repo: Path) -> None:
    repo.mkdir()
    _git(repo, "init")
    _git(repo, "config", "user.email", "scanner@example.test")
    _git(repo, "config", "user.name", "Scanner Test")


def _png_bytes(
    *, software: str | None = None, author: str | None = None
) -> bytes:
    image = Image.new("RGB", (2, 2), (20, 40, 60))
    output = BytesIO()
    pnginfo = None
    if software is not None:
        pnginfo = PngImagePlugin.PngInfo()
        pnginfo.add_text("Software", software)
    if author is not None:
        pnginfo = pnginfo or PngImagePlugin.PngInfo()
        pnginfo.add_text("Author", author)
    image.save(output, format="PNG", pnginfo=pnginfo)
    return output.getvalue()


def test_exact_allowlist_is_scoped_to_path_rule_and_value() -> None:
    value = "AIza12345678901234567890"
    allowlist = (
        scanner.AllowEntry(path="tests/safe.env", rule="google-api-key", value=value),
        scanner.AllowEntry(
            path="tests/safe.env",
            rule="sensitive-env-assignment",
            value=value,
        ),
    )

    allowed = list(
        scanner.scan_text(
            "tests/safe.env",
            f"GOOGLE_API_KEY={value}",
            allowlist=allowlist,
        )
    )
    wrong_path = list(
        scanner.scan_text(
            "tests/other.env",
            f"GOOGLE_API_KEY={value}",
            allowlist=allowlist,
        )
    )

    assert not allowed
    assert {finding.rule for finding in wrong_path} == {
        "google-api-key",
        "sensitive-env-assignment",
    }



def test_credentialed_database_url_stops_before_json_delimiters() -> None:
    value = "postgresql+psycopg://user:" + "password@localhost:5432/database"
    rule = next(rule for rule in scanner.RULES if rule.name == "credentialed-database-url")
    match = rule.pattern.search(f'{{"value": "{value}"}},')

    assert match is not None
    assert scanner._match_value(rule, match) == value

def test_path_normalization_preserves_leading_dot_file_names() -> None:
    assert scanner.normalize_path("./.gitleaks.toml") == ".gitleaks.toml"


def test_public_email_rule_skips_only_reserved_domains() -> None:
    reserved = list(
        scanner.scan_text(
            "fixture.txt",
            "a@example.com b@subdomain.test c@synthetic.invalid d@fixture.example",
            strict_public=True,
        )
    )
    real = list(
        scanner.scan_text(
            "fixture.txt",
            "privacy@angmoo.com",
            strict_public=True,
        )
    )

    assert reserved == []
    assert [finding.rule for finding in real] == ["email-address"]


def test_root_scan_includes_json_lock_svg_and_public_pii(tmp_path: Path) -> None:
    (tmp_path / "config.json").write_text(
        '{"token":"sk-123456789012345678901234"}', encoding="utf-8"
    )
    (tmp_path / "pnpm-lock.yaml").write_text(
        "key: AIza12345678901234567890", encoding="utf-8"
    )
    (tmp_path / "icon.svg").write_text(
        '<svg><metadata>private author</metadata><image href="https://example.test/a.png"/></svg>',
        encoding="utf-8",
    )
    (tmp_path / "profile.txt").write_text(
        "contact=person@real-domain.com", encoding="utf-8"
    )

    report = scanner.scan_root(tmp_path)
    rules = {finding.rule for finding in report.fatal_findings}

    assert "openai-api-key" in rules
    assert "google-api-key" in rules
    assert "svg-metadata" in rules
    assert "svg-embedded-remote-content" in rules
    assert "email-address" in rules
    assert report.files_scanned == 4


def test_root_scan_requires_exact_asset_hash_and_rejects_sensitive_metadata(
    tmp_path: Path,
) -> None:
    image_path = tmp_path / "logo.png"
    clean = _png_bytes()
    image_path.write_bytes(clean)
    manifest = {
        "logo.png": scanner.AssetEntry(
            path="logo.png",
            sha256=hashlib.sha256(clean).hexdigest(),
            media_type="image/png",
        )
    }

    clean_report = scanner.scan_root(tmp_path, asset_manifest=manifest)
    assert not clean_report.fatal_findings

    with_metadata = _png_bytes(software="private-tool")
    image_path.write_bytes(with_metadata)
    manifest["logo.png"] = scanner.AssetEntry(
        path="logo.png",
        sha256=hashlib.sha256(with_metadata).hexdigest(),
        media_type="image/png",
    )
    metadata_report = scanner.scan_root(tmp_path, asset_manifest=manifest)
    assert metadata_report.fatal_findings == []
    assert {finding.rule for finding in metadata_report.findings} == {
        "asset-tool-metadata"
    }

    private_metadata = _png_bytes(author="private-author")
    image_path.write_bytes(private_metadata)
    manifest["logo.png"] = scanner.AssetEntry(
        path="logo.png",
        sha256=hashlib.sha256(private_metadata).hexdigest(),
        media_type="image/png",
    )
    private_metadata_report = scanner.scan_root(tmp_path, asset_manifest=manifest)
    assert {finding.rule for finding in private_metadata_report.fatal_findings} == {
        "asset-sensitive-metadata"
    }

    manifest["logo.png"] = scanner.AssetEntry(
        path="logo.png",
        sha256="0" * 64,
        media_type="image/png",
    )
    mismatch_report = scanner.scan_root(tmp_path, asset_manifest=manifest)
    assert "asset-sha256-mismatch" in {
        finding.rule for finding in mismatch_report.fatal_findings
    }


def test_root_scan_rejects_archives_unclassified_binary_and_generated_directories(
    tmp_path: Path,
) -> None:
    (tmp_path / "backup.zip").write_bytes(b"PK\x03\x04private")
    (tmp_path / "unknown.bin").write_bytes(b"\x00\x01\x02")
    node_modules = tmp_path / "node_modules"
    node_modules.mkdir()
    (node_modules / "secret.txt").write_text("hidden", encoding="utf-8")

    report = scanner.scan_root(tmp_path)
    rules = {finding.rule for finding in report.fatal_findings}

    assert "forbidden-public-file" in rules
    assert "unclassified-binary" in rules
    assert "forbidden-export-directory" in rules


def test_root_scan_fails_closed_when_a_file_cannot_be_read(
    tmp_path: Path, monkeypatch
) -> None:
    blocked = tmp_path / "blocked.txt"
    blocked.write_text("safe", encoding="utf-8")
    original = Path.read_bytes

    def _read_bytes(path: Path) -> bytes:
        if path == blocked:
            raise PermissionError("blocked")
        return original(path)

    monkeypatch.setattr(Path, "read_bytes", _read_bytes)
    report = scanner.scan_root(tmp_path)

    assert [finding.rule for finding in report.fatal_findings] == ["file-read-failed"]


def test_git_tree_scans_committed_blob_instead_of_worktree_file(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)
    tracked = repo / "config.json"
    tracked.write_text('{"token":"sk-123456789012345678901234"}', encoding="utf-8")
    _git(repo, "add", "config.json")
    _git(repo, "commit", "-m", "add secret fixture")
    tracked.write_text("safe worktree content", encoding="utf-8")

    report = scanner.scan_git_tree(repo, "HEAD")

    assert {finding.rule for finding in report.fatal_findings} == {"openai-api-key"}
    assert report.findings[0].ref is not None
    assert report.findings[0].ref.startswith("blob=")


def test_unlimited_history_scan_finds_secret_deleted_from_head(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)
    tracked = repo / "old.env"
    tracked.write_text(
        "PROVIDER_API_KEY=AIza12345678901234567890", encoding="utf-8"
    )
    _git(repo, "add", "old.env")
    _git(repo, "commit", "-m", "add historical fixture")
    tracked.unlink()
    _git(repo, "add", "-u")
    _git(repo, "commit", "-m", "remove historical fixture")

    head = scanner.scan_git_tree(repo, "HEAD")
    history = scanner.scan_history(repo, None)

    assert not head.fatal_findings
    assert "google-api-key" in {finding.rule for finding in history.fatal_findings}


def test_report_output_never_contains_matched_secret(capsys) -> None:
    secret = "sk-123456789012345678901234"
    report = scanner.scan_blob("config.json", secret.encode("utf-8"))

    scanner.print_report(report)
    output = capsys.readouterr().out

    assert secret not in output
    assert "config.json" in output
    assert "rule=openai-api-key" in output
