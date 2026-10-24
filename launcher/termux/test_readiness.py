"""Service readiness belongs to the verified installed manifest, not this tool's version."""
import io
import json
import unittest
from unittest.mock import Mock, patch

import processes


class ReadinessTests(unittest.TestCase):
    source = "a" * 40
    nonce = "b" * 32

    def payload(self, version):
        return {"version": version, "source_sha": self.source, "launch_id": self.nonce,
                "status": "ok", "persistence": "sqlite", "graph": "ladybug"}

    def response(self, payload):
        return patch.object(processes.urllib.request, "urlopen",
                            side_effect=lambda *_args, **_kwargs: io.BytesIO(json.dumps(payload).encode()))

    def test_current_and_previous_installed_versions_use_the_same_readiness_path(self):
        for version in ("0.1.0", "0.1.1", "0.1.2", "0.1.3"):
            for backend in (True, False):
                with self.subTest(version=version, backend=backend), self.response(self.payload(version)):
                    self.assertTrue(processes.ready("http://fixture", self.source, self.nonce,
                                                   expected_version=version, backend=backend))
                    observations = []
                    processes.await_ready(Mock(poll=lambda: None), "http://fixture", self.source, self.nonce,
                                          expected_version=version, backend=backend, observe=observations.append)
                    self.assertEqual(observations, [{"ready": True, "code": "ready"}])

    def test_mismatched_or_missing_identity_is_never_ready(self):
        for version in ("0.1.0", "0.1.1", "0.1.2", "0.1.3"):
            for key, wrong in (("version", "0.1.1" if version == "0.1.0" else "0.1.0"),
                               ("source_sha", "c" * 40), ("launch_id", "d" * 32)):
                for value in (wrong, None):
                    payload = self.payload(version)
                    if value is None: payload.pop(key)
                    else: payload[key] = value
                    with self.subTest(expected=version, key=key, value=value), self.response(payload):
                        self.assertEqual(processes.probe_ready("http://fixture", self.source, self.nonce,
                            expected_version=version, backend=True), {"ready": False, "code": key + "_mismatch"})

    def test_backend_health_and_user_cancellation_are_preserved(self):
        payload = self.payload("0.1.1")
        payload["status"] = "degraded"
        with self.response(payload):
            self.assertEqual(processes.probe_ready("http://fixture", self.source, self.nonce,
                expected_version="0.1.1", backend=True)["code"], "backend_not_ready")
        with patch.object(processes.urllib.request, "urlopen") as request:
            with self.assertRaisesRegex(ValueError, "start_cancelled"):
                processes.await_ready(Mock(poll=lambda: None), "http://fixture", self.source, self.nonce,
                    expected_version="0.1.1", backend=True, cancelled=lambda: True)
            request.assert_not_called()


if __name__ == "__main__":
    unittest.main()
