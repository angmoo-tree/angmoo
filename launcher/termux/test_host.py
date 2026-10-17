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

import angmoo
import processes


@unittest.skipUnless(sys.platform == "linux", "requires Linux /proc and flock")
class HostTests(unittest.TestCase):
    def test_status_does_not_create_home_or_open_database(self):
        with tempfile.TemporaryDirectory() as root:
            missing = Path(root) / "absent"
            result = subprocess.run([sys.executable, angmoo.__file__, "--home", str(missing), "status"], check=True, capture_output=True, text=True)
            self.assertEqual(json.loads(result.stdout), {"state": "stopped"})
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
