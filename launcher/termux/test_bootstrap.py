"""Offline first-install regressions; no packages, images, user DB or AI calls."""

import contextlib
import hashlib
import io
import os
from pathlib import Path
import shlex
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import urllib.error
import zipfile

import bootstrap


def tools_zip(replace=None, link=None):
    result = io.BytesIO()
    with zipfile.ZipFile(result, "w") as archive:
        for name in sorted(bootstrap.FILES):
            entry = zipfile.ZipInfo(replace if name == "setup.sh" and replace else name)
            entry.external_attr = (stat.S_IFLNK if name == link else stat.S_IFREG) << 16
            archive.writestr(entry, b"synthetic tools")
    return result.getvalue()


class BootstrapTests(unittest.TestCase):
    def setUp(self):
        self.raw = tools_zip()
        self.digest = hashlib.sha256(self.raw).hexdigest()
        self.checksums = f"{self.digest}  {bootstrap.TOOLS_NAME}\n".encode()
        self.bind = patch.multiple(bootstrap, RELEASE="0.1.0", TOOLS_SHA256=self.digest, TOOLS_SIZE=str(len(self.raw)))
        self.bind.start()
        self.addCleanup(self.bind.stop)

    def test_verified_flat_archive_is_extracted(self):
        with tempfile.TemporaryDirectory() as root:
            bootstrap.extract_verified(self.raw, self.checksums, Path(root))
            self.assertEqual({p.name for p in Path(root).iterdir()}, bootstrap.FILES)

    def test_android_python_keeps_native_arm64_release_requirement(self):
        for machine in ("aarch64", "x86_64"):
            with self.subTest(machine=machine), tempfile.TemporaryDirectory() as root, \
                 contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()), \
                 patch.object(bootstrap.sys, "platform", "android"), \
                 patch.object(bootstrap.platform, "machine", return_value=machine), \
                 patch.object(bootstrap.shutil, "which", return_value="tool"), \
                 patch.object(bootstrap.Path, "home", return_value=Path(root)), \
                 patch.object(bootstrap, "download", side_effect=[self.checksums, self.raw]) as download, \
                 patch.object(bootstrap, "install_and_start") as install:
                self.assertEqual(bootstrap.main(), 0 if machine == "aarch64" else 1)
                self.assertEqual(install.call_count, 1 if machine == "aarch64" else 0)
                self.assertEqual(download.call_count, 2 if machine == "aarch64" else 0)

    def test_corrupt_missing_duplicate_or_wrong_checksum_extracts_nothing(self):
        cases = ((self.raw + b"changed", self.checksums),
                 (self.raw, b""), (self.raw, self.checksums * 2),
                 (self.raw, f"{'0' * 64}  {bootstrap.TOOLS_NAME}\n".encode()))
        for raw, checksums in cases:
            with self.subTest(checksums=checksums), tempfile.TemporaryDirectory() as root:
                with self.assertRaisesRegex(bootstrap.InstallError, "tools_hash_mismatch"):
                    bootstrap.extract_verified(raw, checksums, Path(root))
                self.assertEqual(list(Path(root).iterdir()), [])

    def test_valid_hash_does_not_allow_paths_links_or_duplicate_members(self):
        for raw in (tools_zip(replace="../setup.sh"), tools_zip(link="setup.sh"), tools_zip(replace="angmoo.py")):
            digest = hashlib.sha256(raw).hexdigest()
            with self.subTest(digest=digest), tempfile.TemporaryDirectory() as root, patch.multiple(
                bootstrap, TOOLS_SHA256=digest, TOOLS_SIZE=str(len(raw))
            ):
                with self.assertRaisesRegex(bootstrap.InstallError, "tools_archive_invalid"):
                    bootstrap.extract_verified(raw, f"{digest}  {bootstrap.TOOLS_NAME}\n".encode(), Path(root))
                self.assertEqual(list(Path(root).iterdir()), [])

    def test_success_runs_setup_install_start_in_order_without_path_edits(self):
        with patch.object(bootstrap.subprocess, "run") as run:
            root = Path("private")
            bootstrap.install_and_start(root / "stage", root)
        self.assertEqual([call.args[0] for call in run.call_args_list], [
            ["sh", str(root / "stage/setup.sh")],
            [str(root / ".local/bin/angmoo"), "install", "--release", "0.1.0"],
            [str(root / ".local/bin/angmoo"), "start"],
        ])
        self.assertTrue(all(call.kwargs["check"] for call in run.call_args_list))

    def test_setup_or_image_install_failure_never_starts_services(self):
        for successful_steps in (0, 1):
            with self.subTest(successful_steps=successful_steps), patch.object(bootstrap.subprocess, "run") as run:
                run.side_effect = [None] * successful_steps + [subprocess.CalledProcessError(7, "synthetic")]
                with self.assertRaises(subprocess.CalledProcessError):
                    bootstrap.install_and_start(Path("stage"), Path("private"))
                self.assertEqual(run.call_count, successful_steps + 1)

    def test_bad_archive_in_main_preserves_existing_files_and_never_runs_setup(self):
        with tempfile.TemporaryDirectory() as root, contextlib.redirect_stderr(io.StringIO()), contextlib.redirect_stdout(io.StringIO()):
            sentinel = Path(root) / "user-data"
            sentinel.write_bytes(b"preserve")
            with patch.object(bootstrap.sys, "platform", "linux"), patch.object(bootstrap.platform, "machine", return_value="aarch64"), \
                 patch.object(bootstrap.shutil, "which", return_value="tool"), patch.object(bootstrap.Path, "home", return_value=Path(root)), \
                 patch.object(bootstrap, "download", side_effect=[self.checksums, b"corrupt"]), patch.object(bootstrap, "install_and_start") as install:
                self.assertEqual(bootstrap.main(), 1)
                install.assert_not_called()
            self.assertEqual(sentinel.read_bytes(), b"preserve")
            self.assertEqual(list(Path(root).iterdir()), [sentinel])

    def test_unsupported_host_or_unrendered_template_does_not_download(self):
        for fields in ({"RELEASE": "@ANGMOO_RELEASE@"}, {"TOOLS_SIZE": "999999999"}):
            with patch.multiple(bootstrap, **fields), patch.object(bootstrap, "download") as download, contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(bootstrap.main(), 1)
                download.assert_not_called()
        with patch.object(bootstrap.platform, "machine", return_value="x86_64"), patch.object(bootstrap, "download") as download, contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(bootstrap.main(), 1)
            download.assert_not_called()

    def test_missing_release_never_falls_back_to_main_or_another_version(self):
        with patch.object(bootstrap.urllib.request, "build_opener") as factory:
            factory.return_value.open.side_effect = urllib.error.HTTPError("synthetic", 404, "missing", {}, None)
            with self.assertRaisesRegex(bootstrap.InstallError, "release_download_failed"):
                bootstrap.download(bootstrap.TOOLS_NAME, 1024)
            factory.return_value.open.assert_called_once_with(
                "https://github.com/angmoo-tree/angmoo/releases/download/release-v0.1.0/angmoo-termux-tools.zip", timeout=45)

    def test_oversized_download_and_non_https_redirect_are_rejected(self):
        with patch.object(bootstrap.urllib.request, "build_opener") as factory:
            factory.return_value.open.return_value.__enter__.return_value.read.return_value = b"1234"
            with self.assertRaisesRegex(bootstrap.InstallError, "download_too_large"):
                bootstrap.download(bootstrap.TOOLS_NAME, 3)
        with self.assertRaisesRegex(bootstrap.InstallError, "download_redirect_invalid"):
            bootstrap.HTTPSRedirects().redirect_request(None, None, 302, "", {}, "http://example.invalid/file")

    @unittest.skipUnless(os.name == "posix", "requires a real POSIX shell")
    def test_real_setup_and_wrapper_with_offline_packages_and_image_commands(self):
        """Exercise the real shell boundary, not Android or image execution."""
        for install_fails in (False, True):
            with self.subTest(install_fails=install_fails), tempfile.TemporaryDirectory() as root:
                home = Path(root)
                tools = home / ".local/share/angmoo-tools"
                python = tools / "venv/bin/python"
                python.parent.mkdir(parents=True)
                python.write_text(
                    '#!/bin/sh\nif [ "$1" = "-m" ] && [ "$2" = "pip" ]; then\n'
                    '  printf "%s\\n" pip >> "$ANGMOO_TEST_STAGES"\n  exit 0\nfi\n'
                    f'exec {shlex.quote(sys.executable)} "$@"\n', encoding="utf-8")
                python.chmod(0o755)
                fake_bin = home / "bin"
                fake_bin.mkdir()
                (fake_bin / "python").symlink_to(sys.executable)
                proot = fake_bin / "proot"
                proot.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
                proot.chmod(0o755)
                sentinel = home / ".local/share/angmoo/data/existing-data"
                sentinel.parent.mkdir(parents=True)
                sentinel.write_bytes(b"preserve user data")
                shell_config = home / ".bashrc"
                shell_config.write_bytes(b"preserve shell config")
                stages = home / "stages"
                content = {name: b"synthetic" for name in bootstrap.FILES}
                content["setup.sh"] = Path(__file__).with_name("setup.sh").read_bytes()
                content["angmoo.py"] = (
                    'import os, sys\nfrom pathlib import Path\n'
                    'with Path(os.environ["ANGMOO_TEST_STAGES"]).open("a") as output:\n'
                    '    output.write(" ".join(sys.argv[1:]) + "\\n")\n'
                    'if sys.argv[1] == "install" and os.environ["ANGMOO_TEST_FAIL"] == "1":\n'
                    '    raise SystemExit(7)\n'
                ).encode()
                buffer = io.BytesIO()
                with zipfile.ZipFile(buffer, "w") as archive:
                    for name, raw in content.items():
                        archive.writestr(name, raw)
                raw = buffer.getvalue()
                digest = hashlib.sha256(raw).hexdigest()
                checksums = f"{digest}  {bootstrap.TOOLS_NAME}\n".encode()
                env = {"HOME": str(home), "PATH": str(fake_bin) + os.pathsep + os.environ["PATH"],
                       "ANGMOO_TEST_STAGES": str(stages), "ANGMOO_TEST_FAIL": str(int(install_fails))}
                with patch.dict(os.environ, env), patch.object(bootstrap.Path, "home", return_value=home), \
                     patch.object(bootstrap.platform, "machine", return_value="aarch64"), \
                     patch.multiple(bootstrap, TOOLS_SHA256=digest, TOOLS_SIZE=str(len(raw))), \
                     patch.object(bootstrap, "download", side_effect=[checksums, raw]), \
                     contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()) as errors:
                    self.assertEqual(bootstrap.main(), int(install_fails), errors.getvalue())
                expected = ["pip", "install --release 0.1.0"] + ([] if install_fails else ["start"])
                self.assertTrue(stages.exists(), errors.getvalue())
                self.assertEqual(stages.read_text().splitlines(), expected)
                self.assertEqual((tools / "requirements.txt").read_bytes(), content["requirements.txt"])
                self.assertEqual((tools / "LICENSE").read_bytes(), content["LICENSE"])
                self.assertEqual(sentinel.read_bytes(), b"preserve user data")
                self.assertEqual(shell_config.read_bytes(), b"preserve shell config")
                self.assertEqual(list(home.glob(".angmoo-install-*")), [])


if __name__ == "__main__":
    unittest.main()
