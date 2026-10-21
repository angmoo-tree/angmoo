"""Linux pipe, privacy, retention and failure evidence contracts; no product DB."""
import contextlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

import processes
import service_logs as logs


@unittest.skipUnless(sys.platform == "linux", "real nonblocking Linux pipes")
class LogTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name)
        self.path = logs.create_session(self.home, "b" * 32, {})

    def test_split_secret_stderr_traceback_and_exit_are_preserved_safely(self):
        capture = logs.Capture(self.path)
        child = subprocess.Popen([sys.executable, "-c",
            "import os,time; os.write(1,b'api_'); time.sleep(.05); "
            "os.write(1,b'key=private-canary\\n  secret-continuation\\nnormal\\n'); "
            "os.write(2,b'Traceback (most recent call last):\\nRuntimeError: synthetic failure\\n'); "
            "raise SystemExit(7)"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        capture.attach("backend", child)
        self.assertEqual(child.wait(timeout=5), 7)
        summary = capture.close()
        text = "\n".join(row["message"] for row in logs.tail(self.path))
        self.assertNotIn("private-canary", text)
        self.assertNotIn("secret-continuation", text)
        self.assertIn("RuntimeError: synthetic failure", text)
        self.assertIn("normal", text)
        self.assertTrue(summary["capture_complete"])
        self.assertTrue(all(p.stat().st_mode & 0o077 == 0 for p in self.path.iterdir()))

    def test_oversized_line_does_not_leak_suffix_or_grow_memory(self):
        capture = logs.Capture(self.path)
        child = subprocess.Popen([sys.executable, "-c",
            "import os; os.write(1,b'x'*100000+b'private-canary\\nnext\\n')"], stdout=subprocess.PIPE)
        capture.attach("backend", child)
        child.wait(timeout=5)
        summary = capture.close()
        text = json.dumps(logs.tail(self.path))
        self.assertNotIn("private-canary", text)
        self.assertIn("next", text)
        self.assertEqual(summary["truncated_records"], 1)
        self.assertFalse(summary["capture_complete"])

    def test_rotation_is_bounded_and_reports_pruned_segments(self):
        capture = logs.Capture(self.path, limit=1200)
        for index in range(50):
            capture.emit("backend", "stdout", f"line {index}: " + "x" * 200)
        summary = capture.close()
        self.assertGreater(summary["retention_pruned_segments"], 0)
        self.assertFalse(summary["capture_complete"])
        self.assertLessEqual(len(list(self.path.glob("backend.jsonl*"))), 3)
        self.assertTrue(all(p.stat().st_size <= 1200 for p in self.path.glob("backend.jsonl*")))
        self.assertIn("line 49", logs.tail(self.path)[-1]["message"])

    def test_queue_overflow_and_disk_failure_are_explicit(self):
        capture = logs.Capture(self.path, queue_bytes=10)
        capture.emit("backend", "stderr", "synthetic")
        summary = capture.close()
        self.assertEqual(summary["dropped_records"], 1)
        self.assertFalse(summary["capture_complete"])
        with patch.object(logs.RotatingFile, "write", side_effect=OSError(28, "synthetic disk full")):
            capture = logs.Capture(self.path)
            capture.emit("backend", "stderr", "synthetic")
            summary = capture.close()
        self.assertEqual(summary["logging_error"], "OSError")
        self.assertEqual(summary["dropped_records"], 1)

    def test_read_only_missing_logs_and_symlink_refusal(self):
        absent = self.home / "absent"
        with self.assertRaisesRegex(ValueError, "logs_missing"):
            logs.select_session(absent)
        self.assertFalse(absent.exists())
        link = self.path / "backend.jsonl"
        link.symlink_to(self.path / "session.json")
        with self.assertRaisesRegex(ValueError, "log_path_unsafe"):
            logs.tail(self.path)

    def test_completed_session_retention_and_active_session_protection(self):
        for number in range(1, 5):
            metadata = logs.read_session(self.path)
            metadata["ended_at_utc"] = logs.utc()
            logs.save_session(self.path, metadata)
            self.path = logs.create_session(self.home, f"{number:032x}", {})
        self.assertEqual(len(list((self.home / "logs").iterdir())), 4)
        self.assertFalse((self.home / "logs" / ("b" * 32)).exists())
        oldest = min((self.home / "logs").iterdir(), key=lambda p: p.stat().st_mtime_ns)
        data = logs.read_session(oldest)
        data["ended_at_utc"] = None
        logs.save_session(oldest, data)
        # Updating metadata changes directory mtime; explicitly locate it first.
        with patch.object(logs, "SESSION_LIMIT", 1):
            with self.assertRaisesRegex(ValueError, "log_retention_active_session"):
                logs.create_session(self.home, "a" * 32, {})

    def test_follow_interrupt_does_not_signal_service(self):
        with patch.object(logs.time, "sleep", side_effect=KeyboardInterrupt), contextlib.redirect_stdout(io.StringIO()) as out:
            logs.show_logs(self.home, "all", None, 20, True)
        self.assertIn("service is unchanged", out.getvalue())

    def test_readiness_classifies_connection_timeout_and_identity(self):
        import urllib.error
        for reason, code in ((TimeoutError(), "timeout"), (ConnectionRefusedError(111, "refused"), "connection_error")):
            with patch.object(processes.urllib.request, "urlopen", side_effect=urllib.error.URLError(reason)):
                self.assertEqual(processes.probe_ready("http://localhost", "a", "b", backend=True)["code"], code)
        response = io.BytesIO(json.dumps({"source_sha": "different"}).encode())
        with patch.object(processes.urllib.request, "urlopen", return_value=response):
            self.assertEqual(processes.probe_ready("http://localhost", "a", "b", backend=True)["code"], "source_sha_mismatch")


if __name__ == "__main__":
    unittest.main()
