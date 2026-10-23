"""Real private filesystem/exec regressions; no packages or application calls."""
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import command_registration as command


@unittest.skipUnless(os.name == "posix", "requires POSIX ownership, flock and exec")
class RegistrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.home = self.root / "home"
        self.home.mkdir()
        self.prefix = self.root / "usr"
        (self.prefix / "bin").mkdir(parents=True)
        self.env = patch.dict(os.environ, HOME=str(self.home),
                              PATH=str(self.prefix / "bin") + ":/usr/bin:/bin")
        self.env.start()
        self.addCleanup(self.env.stop)
        self.tools = self.home / ".local/share/angmoo-tools"
        (self.tools / "venv/bin").mkdir(parents=True)
        (self.tools / "venv/bin/python").symlink_to(sys.executable)
        (self.tools / "angmoo.py").write_text("import sys\nraise SystemExit(0)\n")
        self.wrapper = self.home / ".local/bin/angmoo"
        self.wrapper.parent.mkdir(parents=True)
        self.wrapper.write_bytes(command.WRAPPER)
        self.wrapper.chmod(0o755)
        self.link = self.prefix / "bin/angmoo"

    def test_registration_is_idempotent_and_does_not_run_dependencies_or_services(self):
        data = self.home / "custom-data"
        data.write_bytes(b"preserve data and configuration")
        shell = self.home / ".bashrc"
        shell.write_bytes(b"keep my shell")
        before = {p.relative_to(self.home): p.read_bytes() for p in self.home.rglob("*")
                  if p.is_file() and not p.is_symlink()}
        with patch.object(command.subprocess, "run") as execute:
            for _ in range(2):
                self.assertTrue(command.setup(self.root, self.home, self.prefix, register_only=True))
            execute.assert_not_called()
        self.assertTrue(self.link.is_symlink())
        self.assertTrue(command.verify(self.home, self.prefix))
        for relative, raw in before.items():
            self.assertEqual((self.home / relative).read_bytes(), raw)

    def test_foreign_entries_and_symlink_loops_are_preserved(self):
        for kind in ("file", "directory", "link", "loop"):
            with self.subTest(kind=kind):
                if kind == "file":
                    self.link.write_bytes(b"user command")
                elif kind == "directory":
                    self.link.mkdir()
                else:
                    self.link.symlink_to(self.link if kind == "loop" else self.root / "other")
                with self.assertRaisesRegex(command.RegistrationError, "command_name_conflict"):
                    command.setup(self.root, self.home, self.prefix, register_only=True)
                self.assertTrue(os.path.lexists(self.link))
                if kind == "directory":
                    self.link.rmdir()
                else:
                    self.link.unlink()

    def test_modified_wrapper_is_not_overwritten_before_dependencies(self):
        self.wrapper.write_bytes(b"user wrapper")
        with patch.object(command.subprocess, "run") as execute:
            with self.assertRaisesRegex(command.RegistrationError, "command_wrapper_conflict"):
                command.setup(self.root, self.home, self.prefix)
            execute.assert_not_called()
        self.assertEqual(self.wrapper.read_bytes(), b"user wrapper")

    def test_dangling_registration_needs_a_complete_existing_install(self):
        self.link.symlink_to(self.wrapper)
        self.wrapper.unlink()
        with self.assertRaisesRegex(command.RegistrationError, "existing_installation_incomplete"):
            command.setup(self.root, self.home, self.prefix, register_only=True)
        self.assertTrue(self.link.is_symlink())
        self.assertFalse(self.wrapper.exists())

    def test_competing_creation_never_replaces_a_foreign_command(self):
        original = Path.symlink_to
        def race(path, target, *args, **kwargs):
            if path == self.link:
                path.write_bytes(b"competing command")
                raise FileExistsError()
            return original(path, target, *args, **kwargs)
        with patch.object(Path, "symlink_to", race):
            with self.assertRaisesRegex(command.RegistrationError, "command_name_conflict"):
                command.register(self.home, self.prefix)
        self.assertEqual(self.link.read_bytes(), b"competing command")

    def test_concurrent_setup_reports_busy_without_reclaiming_lock(self):
        with command.installation_lock(self.tools):
            with self.assertRaisesRegex(command.RegistrationError, "setup_busy"):
                command.setup(self.root, self.home, self.prefix, register_only=True)
        self.assertFalse(os.path.lexists(self.link))

    def test_competing_same_target_link_is_rechecked_and_reused(self):
        original = Path.symlink_to
        def race(path, target, *args, **kwargs):
            if path == self.link:
                original(path, target, *args, **kwargs)
                raise FileExistsError()
            return original(path, target, *args, **kwargs)
        with patch.object(Path, "symlink_to", race):
            self.assertTrue(command.register(self.home, self.prefix))
        self.assertEqual(self.link.resolve(), self.wrapper)

    def test_shadowed_command_and_missing_prefix_path_are_not_success(self):
        other = self.root / "other-bin"
        other.mkdir()
        (other / "angmoo").write_text("#!/bin/sh\nexit 0\n")
        (other / "angmoo").chmod(0o755)
        for path, error in ((str(other) + ":" + os.environ["PATH"], "command_path_conflict"),
                            (str(other), "termux_prefix_not_on_path")):
            with patch.dict(os.environ, PATH=path):
                with self.assertRaisesRegex(command.RegistrationError, error):
                    command.register(self.home, self.prefix)

    def test_native_host_checks_interpreter_prefix_and_private_home(self):
        executable = self.prefix / "bin/python"
        executable.write_bytes(b"native interpreter identity fixture")
        with patch.object(command.sys, "platform", "android"), \
                patch.object(command.sys, "base_prefix", str(self.prefix)), \
                patch.object(command.sys, "executable", str(executable)), \
                patch.dict(os.environ, PREFIX=str(self.prefix)):
            self.assertEqual(command.native_prefix(self.home), self.prefix)
            with patch.object(command.sys, "base_prefix", "/usr"):
                with self.assertRaisesRegex(command.RegistrationError, "termux_host_python_required"):
                    command.native_prefix(self.home)
            with patch.dict(os.environ, PREFIX="relative"):
                with self.assertRaisesRegex(command.RegistrationError, "termux_prefix_invalid"):
                    command.native_prefix(self.home)

    def test_real_exec_preserves_arguments_exit_and_signals(self):
        self.assertTrue(command.register(self.home, self.prefix))
        (self.tools / "angmoo.py").write_text(
            "import json,sys\nprint(json.dumps(sys.argv[1:]))\nraise SystemExit(7)\n")
        import json
        args = ["--home", "space and 한글", "status"]
        result = subprocess.run(["sh", "-c", 'exec angmoo "$@"', "fixture", *args],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 7)
        self.assertEqual(json.loads(result.stdout), args)
        (self.tools / "angmoo.py").write_text(
            "import sys,time\nprint('ready',flush=True)\ntime.sleep(20)\n")
        child = subprocess.Popen([str(self.link)], stdout=subprocess.PIPE, text=True)
        try:
            self.assertEqual(child.stdout.readline().strip(), "ready")
            child.send_signal(signal.SIGTERM)
            self.assertEqual(child.wait(timeout=3), -signal.SIGTERM)
        finally:
            if child.poll() is None:
                child.kill()
                child.wait()
            child.stdout.close()

    def test_symlinked_private_directory_is_rejected(self):
        self.wrapper.unlink()
        self.wrapper.parent.rmdir()
        self.wrapper.parent.symlink_to(self.prefix / "bin", target_is_directory=True)
        with self.assertRaisesRegex(command.RegistrationError, "unsafe_tools_directory"):
            command.preflight(self.home, self.prefix)

    def test_permission_failure_does_not_claim_registration(self):
        with patch.object(Path, "symlink_to", side_effect=PermissionError("fixture")):
            with self.assertRaises(PermissionError):
                command.register(self.home, self.prefix)
        self.assertFalse(os.path.lexists(self.link))


if __name__ == "__main__":
    unittest.main()
