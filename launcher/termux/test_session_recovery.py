"""Real host lifecycle regressions; all homes/processes are synthetic."""
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

import angmoo
import processes
import service_logs as logs
import session_recovery as recovery


@unittest.skipUnless(sys.platform in ("linux", "android"), "requires native procfs/flock")
class RecoveryTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="angmoo-log-recovery-test-")
        self.addCleanup(temporary.cleanup)
        self.home = Path(temporary.name)
        self.prior_umask = os.umask(0o077)
        self.addCleanup(os.umask, self.prior_umask)
        self.lock = angmoo.lock(self.home)
        self.addCleanup(self.lock.close)

    def session(self, number=1, **metadata):
        return logs.create_session(self.home, f"{number:032x}", metadata)

    def closed(self, path):
        value = logs.read_session(path)
        value.update(ended_at_utc=logs.utc(), capture_complete=True)
        logs.save_session(path, value)

    def test_failed_child_cleanup_never_records_an_observed_end(self):
        previous = {sig: signal.getsignal(sig) for sig in (signal.SIGTERM, signal.SIGINT)}
        for sig, handler in previous.items():
            self.addCleanup(signal.signal, sig, handler)
        child = self.spawn(stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.addCleanup(child.stderr.close)
        config = {"manifest": {"source_sha": "a" * 40, "version": "0.1.0"},"containers":{"backend":"fixture-backend","frontend":"fixture-frontend"}}
        with (
            patch.object(angmoo, "installation", return_value=config),
            patch.object(angmoo, "tools", return_value="proot-distro"),
            patch.object(angmoo, "free_port"),
            patch.object(angmoo, "command", return_value=["synthetic-child"]),
            patch.object(angmoo.subprocess, "Popen", return_value=child),
            patch.object(angmoo, "await_ready", side_effect=ValueError("service_readiness_timeout")),
            patch.object(angmoo, "stop_child", side_effect=ValueError("process_ownership_changed")),
        ):
            angmoo.supervise(self.home, os.dup(self.lock.fileno()), "d" * 32)
        state = angmoo.read_state(self.home)
        self.assertIsNone(child.poll())
        self.assertEqual(state["primary_failure"]["code"], "service_readiness_timeout")
        self.assertEqual(state["cleanup_failures"][0]["code"], "owned_process_stop_failed")
        self.assertIsNone(state["services"]["backend"]["ended_at_utc"])
        metadata = logs.read_session(self.home / state["log_reference"])
        self.assertIsNone(metadata["ended_at_utc"])
        self.assertEqual(metadata["lifecycle_state"], "running")
        self.assertFalse(metadata["capture_complete"])

    def test_malformed_recovery_cannot_authorize_retention(self):
        self.assertFalse(logs.retention_terminal({"lifecycle_state": "interrupted", "capture_complete": False, "recovery": None}))

    def spawn(self, program="import time; time.sleep(60)", **options):
        child = subprocess.Popen([sys.executable, "-c", program], start_new_session=True, **options)
        def cleanup():
            if child.poll() is None:
                child.kill()
                child.wait(timeout=5)
            if child.stdout:
                child.stdout.close()
        self.addCleanup(cleanup)
        return child

    def test_legacy_four_sessions_recover_without_data_or_fabricated_end(self):
        paths = [self.session(i, primary_failure={"code": "original"}) for i in range(4)]
        self.closed(paths[1])
        self.closed(paths[3])
        originals = [logs.read_session(p) for p in paths]
        result = recovery.recover_sessions(self.home, {"state": "stopped", "nonce": paths[3].name})
        self.assertEqual(result["recovered"], [paths[0].name, paths[2].name])
        for index in (0, 2):
            value = logs.read_session(paths[index])
            self.assertEqual(value["lifecycle_state"], "interrupted")
            self.assertIsNone(value["ended_at_utc"])
            self.assertFalse(value["capture_complete"])
            self.assertEqual(value["started_at_utc"], originals[index]["started_at_utc"])
            self.assertEqual(value["primary_failure"], {"code": "original"})
        new = self.session(4)
        self.assertEqual(logs.read_session(new)["retention_pruned_sessions"], [paths[0].name])
        self.assertFalse((self.home / "data").exists())
        self.assertLess(result["elapsed_ms"], recovery.MAX_SECONDS * 1000)

    def test_active_owner_and_unknown_observation_preserve_files(self):
        child = self.spawn()
        path = self.session(owner_identity=processes.identity(child.pid))
        before = (path / "session.json").read_bytes()
        with self.assertRaisesRegex(ValueError, "log_recovery_active_session"):
            recovery.recover_sessions(self.home, {})
        child.kill()
        child.wait()
        with patch.object(recovery, "observe_identity", return_value={"status": "unknown"}):
            with self.assertRaisesRegex(ValueError, "log_recovery_unverified"):
                recovery.recover_sessions(self.home, {})
        self.assertEqual((path / "session.json").read_bytes(), before)

    def test_recordless_spawn_gap_and_old_alias_are_detected_by_launch(self):
        path = self.session()
        child = self.spawn(env={**os.environ, "ANGMOO_LAUNCH_ID": path.name})
        with self.assertRaisesRegex(ValueError, "log_recovery_active_session"):
            recovery.recover_sessions(self.home, {})
        self.assertIsNone(child.poll())
        self.assertNotIn("lifecycle_state", logs.read_session(path))

    def test_orphan_session_after_sigkill_blocks_until_child_exits(self):
        program = ("import subprocess,sys,time; "
                   "p=subprocess.Popen([sys.executable,'-c','import time; time.sleep(60)']); "
                   "print(p.pid,flush=True); time.sleep(60)")
        parent = self.spawn(program, stdout=subprocess.PIPE)
        record = processes.identity(parent.pid)
        child_pid = int(parent.stdout.readline())
        child_record = processes.identity(child_pid)
        path = self.session(children={"backend": record})
        self.addCleanup(lambda: os.kill(child_pid, signal.SIGKILL) if processes.alive(child_record) else None)
        parent.kill()
        parent.wait()
        with self.assertRaisesRegex(ValueError, "log_recovery_active_session"):
            recovery.recover_sessions(self.home, {})
        os.kill(child_pid, signal.SIGKILL)
        deadline = time.monotonic() + 5
        while processes.alive(child_record) and time.monotonic() < deadline:
            time.sleep(.01)
        self.assertFalse(processes.alive(child_record))
        self.assertEqual(recovery.recover_sessions(self.home, {})["recovered"], [path.name])

    def test_unrelated_home_does_not_block_and_open_legacy_log_handle_does(self):
        path = self.session()
        child = self.spawn(env={**os.environ, "ANGMOO_LAUNCH_ID": "f" * 32})
        self.assertEqual(recovery.recover_sessions(self.home, {})["recovered"], [path.name])
        holder = subprocess.Popen([sys.executable, "-c", "import sys,time; f=open(sys.argv[1],'rb'); print('ready',flush=True); time.sleep(60)",
                                   str(path / "session.json")], stdout=subprocess.PIPE, start_new_session=True)
        try:
            self.assertEqual(holder.stdout.readline().strip(), b"ready")
            with self.assertRaisesRegex(ValueError, "log_recovery_active_session"):
                recovery.recover_sessions(self.home, {})
            self.assertIsNone(child.poll())
        finally:
            holder.kill()
            holder.wait()
            holder.stdout.close()

    def test_bounded_scan_and_permission_error_do_not_mutate(self):
        path = self.session()
        before = (path / "session.json").read_bytes()
        with patch.object(recovery, "MAX_PROCESSES", 0):
            with self.assertRaisesRegex(ValueError, "log_recovery_unverified"):
                recovery.recover_sessions(self.home, {})
        with patch.object(recovery, "scan_processes", side_effect=PermissionError):
            with self.assertRaisesRegex(ValueError, "log_recovery_unverified"):
                recovery.recover_sessions(self.home, {})
        self.assertEqual((path / "session.json").read_bytes(), before)

    def test_invalid_metadata_does_not_adopt_other_launch_owner(self):
        path = self.session(owner_identity={"pid": 12})
        with self.assertRaisesRegex(ValueError, "log_recovery_unverified"):
            recovery.recover_sessions(self.home, {})
        self.assertNotIn("lifecycle_state", logs.read_session(path))

    def test_actual_flock_released_after_kill_and_preparing_record_recovered(self):
        self.lock.close()
        program = ("import sys,time; from pathlib import Path; import angmoo,processes,service_logs; "
                   "h=Path(sys.argv[1]); lock=angmoo.lock(h); "
                   "service_logs.create_session(h,'a'*32,{'lifecycle_state':'preparing','creator_identity':processes.identity(__import__('os').getpid())}); "
                   "print('ready',flush=True); time.sleep(60)")
        parent = subprocess.Popen([sys.executable, "-c", program, str(self.home)], stdout=subprocess.PIPE,
                                  env={**os.environ, "PYTHONPATH": str(Path(angmoo.__file__).parent)}, start_new_session=True)
        try:
            self.assertEqual(parent.stdout.readline().strip(), b"ready")
            with self.assertRaisesRegex(ValueError, "already_running"):
                angmoo.lock(self.home)
            parent.kill()
            parent.wait()
            with angmoo.lock(self.home):
                self.assertEqual(recovery.recover_sessions(self.home, {})["recovered"], ["a" * 32])
        finally:
            if parent.poll() is None:
                parent.kill()
                parent.wait()
            parent.stdout.close()

    def test_recovery_is_idempotent_and_diagnostics_do_not_write(self):
        path = self.session()
        recovery.recover_sessions(self.home, {})
        before = {str(p.relative_to(self.home)): p.read_bytes() for p in self.home.rglob("*") if p.is_file()}
        self.assertEqual(recovery.recover_sessions(self.home, {})["recovered"], [])
        for command in ("status", "diagnostics", "logs"):
            result = subprocess.run([sys.executable, angmoo.__file__, "--home", str(self.home), command], capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr)
        after = {str(p.relative_to(self.home)): p.read_bytes() for p in self.home.rglob("*") if p.is_file()}
        self.assertEqual(before, after)
        self.assertFalse(logs.read_session(path)["capture_complete"])

    def test_tombstone_deletion_crash_resumes_without_losing_receipt(self):
        paths = [self.session(i) for i in range(4)]
        for path in paths:
            self.closed(path)
        original = Path.unlink
        def fail_once(path, *args, **kwargs):
            if path.parent.name.startswith(".pruning-"):
                raise OSError("synthetic storage interruption")
            return original(path, *args, **kwargs)
        with patch.object(Path, "unlink", fail_once):
            with self.assertRaisesRegex(ValueError, "log_retention_write_failed"):
                self.session(4)
        root = self.home / "logs"
        self.assertTrue((root / (".pruning-" + paths[0].name)).is_dir())
        # Cleanup resumes under the same lock. No second deletion or archive.
        new = self.session(5)
        self.assertEqual(logs.read_session(new)["retention_pruned_sessions"], [paths[0].name])
        self.assertFalse(list(root.glob(".pruning-*")))
        receipt = json.loads((root / ".retention.json").read_text())
        self.assertEqual(receipt["phase"], "complete")

    def test_atomic_recovery_write_failure_preserves_original(self):
        path = self.session()
        before = (path / "session.json").read_bytes()
        with patch.object(logs.os, "fsync", side_effect=OSError("synthetic ENOSPC")):
            with self.assertRaisesRegex(ValueError, "log_recovery_write_failed"):
                recovery.recover_sessions(self.home, {})
        self.assertEqual((path / "session.json").read_bytes(), before)
        self.assertEqual(recovery.recover_sessions(self.home, {})["recovered"], [path.name])

    def test_preparing_directory_without_metadata_recovers_from_receipt(self):
        with patch.object(logs, "save_session", side_effect=OSError("synthetic kill before metadata")):
            with self.assertRaisesRegex(ValueError, "log_retention_write_failed"):
                self.session()
        path = self.home / "logs" / f"{1:032x}"
        self.assertFalse((path / "session.json").exists())
        self.assertEqual(recovery.recover_sessions(self.home, {})["recovered"], [path.name])
        self.assertEqual(logs.read_session(path)["lifecycle_state"], "interrupted")
        self.session(2)

    def test_corrupt_closed_timestamp_is_not_prune_permission(self):
        path = self.session(ended_at_utc=12)
        with self.assertRaisesRegex(ValueError, "log_recovery_unverified"):
            recovery.recover_sessions(self.home, {})
        self.assertTrue(path.exists())

    def test_process_that_vanished_after_related_scan_is_unknown(self):
        path = self.session()
        with patch.object(recovery, "scan_processes", return_value={"matches": [{"pid": 123}]}), \
             patch.object(recovery, "observe_identity", return_value={"status": "gone"}):
            with self.assertRaisesRegex(ValueError, "log_recovery_unverified"):
                recovery.recover_sessions(self.home, {})
        self.assertNotIn("lifecycle_state", logs.read_session(path))

    def test_start_recovers_legacy_before_spawn_and_preserves_spawn_failure(self):
        path = self.session()
        config = {"manifest": {"source_sha": "a" * 40, "version": "0.1.0"},"containers":{"backend":"fixture-backend","frontend":"fixture-frontend"}}
        self.lock.close()
        with patch.object(angmoo, "tools"), patch.object(angmoo, "installation", return_value=config), \
             patch.object(angmoo, "free_port"), patch.object(angmoo.subprocess, "Popen", side_effect=OSError("synthetic spawn failure")) as spawn:
            with self.assertRaises(OSError):
                angmoo.start(self.home)
            self.assertEqual(spawn.call_count, 1)
        self.assertEqual(logs.read_session(path)["lifecycle_state"], "interrupted")
        latest = logs.read_session(logs.select_session(self.home))
        self.assertEqual(latest["lifecycle_state"], "closed")
        self.assertEqual(latest["primary_failure"]["phase"], "spawn")

    def test_byte_budget_preserves_existing_limit(self):
        path = self.session()
        self.closed(path)
        file = path / "backend.jsonl"
        file.write_bytes(b"x" * 8192)
        with patch.object(logs, "TOTAL_BYTES", 17 * 1024 * 1024 + 4096):
            newer = self.session(2)
        self.assertFalse(path.exists())
        self.assertEqual(logs.read_session(newer)["retention_pruned_sessions"], [path.name])

    @unittest.skipUnless(hasattr(os, "link"), "requires host hardlink fixture support; checked on Linux")
    def test_hardlink_protection_on_host_filesystem(self):
        newer = self.session()
        os.link(newer / "session.json", newer / "backend.jsonl")
        with self.assertRaisesRegex(ValueError, "log_path_unsafe"):
            self.session(3)
        self.assertTrue((newer / "backend.jsonl").exists())

    def test_multiple_homes_have_independent_locks(self):
        other = self.home / "other"
        other.mkdir(mode=0o700)
        with angmoo.lock(other):
            with self.assertRaisesRegex(ValueError, "already_running"):
                angmoo.lock(self.home)
            path = logs.create_session(other, "c" * 32, {})
            recovery.recover_sessions(other, {})
            self.assertEqual(logs.read_session(path)["lifecycle_state"], "interrupted")

    def test_unknown_files_links_and_unreceipted_pruning_are_preserved(self):
        path = self.session()
        unknown = path / "user-file"
        unknown.write_bytes(b"preserve")
        with self.assertRaisesRegex(ValueError, "log_retention_unknown_file"):
            self.session(2)
        self.assertEqual(unknown.read_bytes(), b"preserve")
        unknown.unlink()
        link = path / "backend.jsonl"
        link.symlink_to(path / "session.json")
        with self.assertRaisesRegex(ValueError, "log_path_unsafe"):
            self.session(2)
        link.unlink()
        pending = self.home / "logs" / (".pruning-" + "f" * 32)
        pending.mkdir(mode=0o700)
        with self.assertRaisesRegex(ValueError, "log_retention_receipt_invalid"):
            self.session(2)
        self.assertTrue(pending.exists())


@unittest.skipUnless(sys.platform in ("linux", "android"), "requires procfs")
class IdentityTests(unittest.TestCase):
    def test_zombie_is_gone_before_parent_reaps_it(self):
        child = subprocess.Popen([sys.executable, "-c", "raise SystemExit(0)"])
        record = processes.identity(child.pid)
        try:
            deadline = time.monotonic() + 5
            while processes.proc_stat(Path(f"/proc/{child.pid}"))[1] != "Z" and time.monotonic() < deadline:
                time.sleep(.01)
            self.assertEqual(processes.observe_identity(record), {"status": "gone", "basis": "zombie"})
        finally:
            child.wait(timeout=5)

    def test_live_reused_boot_changed_and_unreadable(self):
        record = processes.identity(os.getpid())
        self.assertEqual(processes.observe_identity(record)["status"], "alive")
        self.assertEqual(processes.observe_identity({**record, "start_ticks": "0"})["basis"], "pid_reused")
        self.assertEqual(processes.observe_identity({**record, "boot_id": "00000000-0000-0000-0000-000000000000"})["basis"], "different_boot")
        self.assertEqual(processes.observe_identity({"pid": 1})["status"], "unknown")
        with patch.object(processes, "proc_bytes", side_effect=FileNotFoundError):
            self.assertEqual(processes.observe_identity(record)["status"], "unknown")
        with patch.object(processes, "proc_stat", side_effect=PermissionError):
            self.assertEqual(processes.observe_identity(record)["status"], "unknown")


if __name__ == "__main__":
    unittest.main()
