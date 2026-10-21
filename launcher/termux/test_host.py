"""Linux host checks with real owned processes; no real user database or AI."""

import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import angmoo
import processes


class HostPlatformTests(unittest.TestCase):
    @unittest.skipUnless(os.name == "posix", "requires POSIX file mode bits")
    def test_tool_import_does_not_broaden_adapter_file_permissions(self):
        import builtins
        original_import = builtins.__import__
        def dependency_import(name, *args, **kwargs):
            if name == "proot_distro.constants":
                os.umask(0o022)
                return SimpleNamespace(IS_TERMUX=True)
            return original_import(name, *args, **kwargs)
        previous = os.umask(0o077)
        try:
            with patch.object(builtins, "__import__", side_effect=dependency_import):
                self.assertTrue(angmoo.is_termux_host())
            self.assertEqual(os.umask(0o077), 0o077)
        finally:
            os.umask(previous)

    def test_android_python_requires_termux_and_pinned_tools(self):
        for termux in (True, False):
            with self.subTest(termux=termux), patch.object(angmoo.sys, "platform", "android"), \
                 patch.object(angmoo.importlib.metadata, "version", return_value=angmoo.PROOT_VERSION), \
                 patch.object(angmoo.shutil, "which", return_value="/termux/proot-distro"), \
                 patch.dict(sys.modules, {"proot_distro.constants": SimpleNamespace(IS_TERMUX=termux)}):
                if termux:
                    self.assertEqual(angmoo.tools(), "/termux/proot-distro")
                else:
                    with self.assertRaisesRegex(ValueError, "host_not_supported"):
                        angmoo.tools()


@unittest.skipUnless(sys.platform in ("linux", "android"), "requires Linux /proc and flock")
class HostTests(unittest.TestCase):
    def test_status_does_not_create_home_or_open_database(self):
        with tempfile.TemporaryDirectory() as root:
            missing = Path(root) / "absent"
            result = subprocess.run([sys.executable, angmoo.__file__, "--home", str(missing), "status"], check=True, capture_output=True, text=True)
            self.assertEqual(json.loads(result.stdout), {"state": "stopped", "log_policy": {"requested_mode": "legacy", "effective_mode": "unknown", "source_confirmation": "legacy"}})
            self.assertFalse(missing.exists())

    def test_flock_excludes_duplicate_owner_and_private_path_rejects_symlinks(self):
        with tempfile.TemporaryDirectory() as directory:
            home = angmoo.private_home(Path(directory) / "profile")
            with angmoo.lock(home):
                with self.assertRaisesRegex(ValueError, "already_running"):
                    angmoo.lock(home)
            with angmoo.lock(home):
                pass
            link = Path(directory) / "link"
            link.symlink_to(home, target_is_directory=True)
            with self.assertRaisesRegex(ValueError, "symlink"):
                angmoo.private_home(link)

    def test_port_conflict_is_not_adopted_or_stopped(self):
        with socket.socket() as owner:
            owner.bind(("127.0.0.1", 0))
            with self.assertRaisesRegex(ValueError, "port_in_use"):
                processes.free_port(owner.getsockname()[1])
            owner.listen()

    def test_stale_identity_cannot_kill_process_then_actual_owner_can_stop_it(self):
        process = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"], start_new_session=True)
        record = processes.identity(process.pid)
        try:
            self.assertEqual(processes.session_members({**record, "start_ticks": "wrong"}), [])
            with self.assertRaisesRegex(ValueError, "process_ownership_changed"):
                processes.stop_child(process, {**record, "start_ticks": "wrong"}, .1)
            self.assertIsNone(process.poll())
            processes.stop_child(process, record, 1)
            self.assertIsNotNone(process.poll())
        finally:
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait()

    def test_drain_deadline_escalates_only_owned_group(self):
        process = subprocess.Popen([sys.executable, "-c", "import signal,time; signal.signal(signal.SIGTERM,signal.SIG_IGN); print('ready',flush=True); time.sleep(60)"], stdout=subprocess.PIPE, start_new_session=True)
        try:
            self.assertEqual(process.stdout.readline().strip(), b"ready")
            started = time.monotonic()
            processes.stop_child(process, processes.identity(process.pid), .1)
            self.assertLess(time.monotonic() - started, 3)
            self.assertEqual(process.returncode, -signal.SIGKILL)
        finally:
            process.stdout.close()

    def test_stop_during_readiness_is_immediate(self):
        class Child:
            def poll(self):
                return None
        with self.assertRaisesRegex(ValueError, "start_cancelled"):
            processes.await_ready(Child(), "http://127.0.0.1:1", "a" * 40, "b" * 32, backend=True, cancelled=lambda: True)

    def test_exited_parent_does_not_leave_child_running(self):
        program = "import subprocess,sys,time; p=subprocess.Popen([sys.executable,'-c','import signal,time; signal.signal(signal.SIGTERM,signal.SIG_IGN); time.sleep(60)']); print(p.pid,flush=True); time.sleep(.2)"
        parent = subprocess.Popen([sys.executable, "-c", program], stdout=subprocess.PIPE, start_new_session=True)
        record = processes.identity(parent.pid)
        child = int(parent.stdout.readline())
        child_record = processes.identity(child)
        parent.wait(timeout=5)
        try:
            self.assertTrue(processes.alive(child_record))
            processes.stop_child(parent, record, .1)
            self.assertFalse(processes.alive(child_record))
            self.assertEqual(processes.session_members(record), [])
        finally:
            if processes.alive(child_record):
                os.kill(child, signal.SIGKILL)
            parent.stdout.close()

    def test_frontend_failure_stops_only_owned_backend(self):
        with tempfile.TemporaryDirectory() as directory:
            home = angmoo.private_home(Path(directory) / "profile")
            unrelated = subprocess.Popen([sys.executable, "-c", "import time;time.sleep(60)"], start_new_session=True)
            previous_handlers = {sig: signal.getsignal(sig) for sig in (signal.SIGTERM, signal.SIGINT)}
            def command(_exe, _config, service, _nonce, *, log_policy=None):
                return [sys.executable, "-c", "import time;time.sleep(60)" if service == "backend" else "raise SystemExit(7)"]
            def readiness(process, _url, _source, _nonce, *, backend, **_):
                self.assertEqual(_["timeout"], angmoo.BACKEND_READINESS_SECONDS if backend else angmoo.FRONTEND_READINESS_SECONDS)
                if not backend:
                    process.wait(timeout=5)
                    raise ValueError("service_exited_before_ready")
            try:
                with angmoo.lock(home) as owned, patch.object(angmoo, "installation", return_value={"manifest": {"source_sha": "a"*40, "version": "0.1.0"}}), patch.object(angmoo, "tools", return_value="proot-distro"), patch.object(angmoo, "free_port"), patch.object(angmoo, "command", side_effect=command), patch.object(angmoo, "await_ready", side_effect=readiness):
                    angmoo.supervise(home, os.dup(owned.fileno()), "b" * 32)
                state = angmoo.read_state(home)
                self.assertEqual(state["state"], "failed")
                self.assertEqual(state["error"], "service_exited_before_ready")
                self.assertEqual(state["primary_failure"]["service"], "frontend")
                self.assertEqual(state["primary_failure"]["returncode"], 7)
                self.assertEqual(state["services"]["backend"]["termination_origin"], "sibling_failure")
                self.assertEqual(state["primary_failure"]["exit_code_scope"], "proot_command")
                self.assertTrue((home / state["log_reference"] / "session.json").is_file())
                self.assertFalse(any(processes.session_members(r) for r in state["children"].values()))
                self.assertIsNone(unrelated.poll())
            finally:
                for sig, handler in previous_handlers.items():
                    signal.signal(sig, handler)
                processes.stop_child(unrelated, processes.identity(unrelated.pid), 1)

    def test_wrong_manifest_and_low_space_preserve_previous_install(self):
        with tempfile.TemporaryDirectory() as directory:
            home = angmoo.private_home(Path(directory) / "profile")
            sentinel = home / "installation.json"
            sentinel.write_text("previous")
            with patch.object(angmoo, "tools", return_value="proot-distro"), patch.object(angmoo, "read_manifest", side_effect=ValueError("manifest_source_invalid")):
                with self.assertRaisesRegex(ValueError, "manifest_source_invalid"):
                    angmoo.install(home, None, home / "candidate.json")
            pair = [{"platform": "linux/arm64", "archive_size": 100}] * 2
            with patch.object(angmoo, "tools", return_value="proot-distro"), patch.object(angmoo, "read_manifest", return_value={"images": pair}), patch.object(angmoo.shutil, "disk_usage", return_value=type("Disk", (), {"free": 0})()), patch.object(angmoo.subprocess, "run") as run:
                with self.assertRaisesRegex(ValueError, "disk_space_low"):
                    angmoo.install(home, None, home / "candidate.json")
                run.assert_not_called()
            self.assertEqual(sentinel.read_text(), "previous")

    def test_two_services_preserve_image_entrypoints_and_isolate_data(self):
        install = {"containers": {"backend": "angmoo-backend-test", "frontend": "angmoo-frontend-test"}, "data_root": "/private/data"}
        backend = angmoo.command("proot-distro", install, "backend", "b" * 32)
        frontend = angmoo.command("proot-distro", install, "frontend", "b" * 32)
        self.assertIn("/private/data:/var/lib/angmoo", backend)
        self.assertNotIn("--bind", frontend)
        self.assertIn("10001:10001", backend)
        self.assertIn("1000:1000", frontend)
        self.assertIn("ANGMOO_API_BASE_URL=http://127.0.0.1:8080", frontend)
        self.assertNotIn("--", backend)  # no replacement guest entrypoint


if __name__ == "__main__":
    unittest.main()
