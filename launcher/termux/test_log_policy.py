import contextlib
from datetime import datetime, timezone
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

import angmoo
import log_policy as policy
import service_logs as logs


class PolicyTests(unittest.TestCase):
    def test_options_are_finite_and_restart_validates_before_stop(self):
        self.assertEqual(policy.duration("basic"), 0)
        self.assertEqual(policy.duration("detailed"), 900)
        for value in ("1m", "15m", "60m"):
            self.assertEqual(policy.duration("detailed", value), int(value[:-1]) * 60)
        for mode, value in (("basic", "1m"), ("detailed", "0m"), ("detailed", "61m"), ("detailed", "1h"), ("detailed", "01m"), ("detailed", "infinity")):
            with self.subTest(mode=mode, value=value), self.assertRaisesRegex(ValueError, "log_options_invalid"):
                policy.duration(mode, value)
        with patch.object(sys, "argv", ["angmoo", "restart", "--log-duration", "15m"]), patch.object(angmoo, "stop") as stop, patch.object(angmoo, "private_home") as home, contextlib.redirect_stderr(io.StringIO()) as error:
            self.assertEqual(angmoo.main(), 1)
            stop.assert_not_called(); home.assert_not_called()
            self.assertIn("log_options_invalid", error.getvalue())

    def test_startup_time_shared_and_expiry_never_reenters_on_clock_rollback(self):
        wall = [1000.0]; mono = [50.0]
        value = policy.new_policy("a" * 32, "detailed", 900, now=datetime.fromtimestamp(wall[0], timezone.utc))
        clock = policy.PolicyClock(value, monotonic=lambda: mono[0], wall=lambda: wall[0])
        wall[0] += 180; mono[0] += 180
        backend = json.loads(clock.envelope("backend"))
        wall[0] += 170; mono[0] += 170
        frontend = json.loads(clock.envelope("frontend"))
        self.assertEqual(backend["remaining_seconds"], 720)
        self.assertEqual(frontend["remaining_seconds"], 550)
        self.assertEqual(backend["detailed_until_utc"], frontend["detailed_until_utc"])
        wall[0] += 901
        self.assertEqual(clock.remaining(), 0)
        wall[0] = 900
        self.assertEqual(clock.remaining(), 0)
        self.assertEqual(policy.duration("basic"), 0)

    def test_ack_is_bound_to_service_launch_and_exact_fields(self):
        value = policy.new_policy("b" * 32, "detailed", 60)
        ack = {"event": "service_log_policy_applied", "profile_version": policy.VERSION,
               "service": "backend", "launch_id": "b" * 32, "effective_mode": "detailed", "detailed_until_utc": value["detailed_until_utc"]}
        self.assertEqual(policy.acknowledge(json.dumps(ack), "backend", "b" * 32, value), ack)
        for extra in ({"service": "frontend"}, {"launch_id": "a"*32}, {"body": "private"}, {"profile_version": "future"}):
            self.assertIsNone(policy.acknowledge(json.dumps({**ack, **extra}), "backend", "b" * 32, value))
        self.assertEqual(policy.describe(None)["effective_mode"], "unknown")

    def test_fixed_host_errors_are_english_but_raw_user_paths_are_preserved(self):
        self.assertTrue(all(isinstance(v, str) and not any("가" <= c <= "힣" for c in v) for v in angmoo.MESSAGES.values()))
        self.assertEqual(logs.redact("오류 /private/한글 파일.png"), "오류 /private/한글 파일.png")


@unittest.skipUnless(sys.platform in ("linux", "android"), "POSIX selector pipes")
class CaptureWaitTests(unittest.TestCase):
    def test_idle_selector_blocks_and_attach_and_close_wake_without_polling(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = logs.create_session(Path(temporary), "a" * 32, {})
            selected = []
            original = logs.selectors.DefaultSelector
            class Observed(original):
                def select(self, timeout=None):
                    selected.append(timeout)
                    return super().select(timeout)
            with patch.object(logs.selectors, "DefaultSelector", Observed):
                capture = logs.Capture(path)
                time.sleep(.12)
                self.assertEqual(selected, [None])
                child = subprocess.Popen([sys.executable, "-c", "print('after attach')"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                capture.attach("backend", child)
                child.wait(timeout=3)
                summary = capture.close()
            self.assertTrue(summary["capture_complete"])
            self.assertIn("after attach", str(logs.tail(path)))
            with self.assertRaisesRegex(ValueError, "log_capture_closed"):
                capture.attach("backend", child)
            self.assertFalse(capture.writer.is_alive() or capture.drainer.is_alive())

    def test_active_source_ack_persists_once_and_unknown_pipe_does_not_confirm(self):
        with tempfile.TemporaryDirectory() as temporary:
            value = policy.new_policy("b" * 32, "basic", 0)
            path = logs.create_session(Path(temporary), "b" * 32, {"log_policy": value})
            capture = logs.Capture(path, policy=value)
            ack = {"event": "service_log_policy_applied", "profile_version": policy.VERSION, "service": "backend", "launch_id": "b" * 32, "effective_mode": "basic", "detailed_until_utc": None}
            capture.emit("supervisor", "stdout", json.dumps(ack))
            capture.emit("backend", "stdout", json.dumps(ack))
            self.assertTrue(capture.close()["capture_complete"])
            self.assertEqual(json.loads((path / "policy-state.json").read_text()), {"backend": ack})
            self.assertEqual(angmoo.policy_status(path, value)["sources"]["frontend"], {"state": "unconfirmed"})

    def test_close_is_bounded_with_live_pipe_and_has_no_fd_or_thread_leak(self):
        before = len(os.listdir("/proc/self/fd"))
        with tempfile.TemporaryDirectory() as temporary:
            path = logs.create_session(Path(temporary), "c" * 32, {})
            capture = logs.Capture(path)
            child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(10)"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            try:
                capture.attach("backend", child)
                started = time.monotonic(); result = capture.close()
                self.assertLess(time.monotonic() - started, 3)
                self.assertFalse(result["capture_complete"])
                self.assertFalse(capture.writer.is_alive() or capture.drainer.is_alive())
            finally:
                child.terminate(); child.wait(timeout=3)
        self.assertEqual(len(os.listdir("/proc/self/fd")), before)

    def test_idle_writer_does_not_flush_and_dirty_flush_is_not_deferred_by_input(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = logs.create_session(Path(temporary), "d" * 32, {})
            flushes = []
            original = logs.RotatingFile.flush
            def flush(file):
                flushes.append(time.monotonic())
                return original(file)
            with patch.object(logs.RotatingFile, "flush", flush):
                capture = logs.Capture(path)
                time.sleep(.2); self.assertEqual(flushes, [])
                started = time.monotonic()
                for index in range(24):
                    capture.emit("backend", "stdout", str(index)); time.sleep(.05)
                self.assertTrue(flushes)
                self.assertLess(flushes[0] - started, 1.15)
                capture.close()


if __name__ == "__main__":
    unittest.main()
