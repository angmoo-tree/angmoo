"""Pure bounded observation and durable budgets for the authorized NG retest.

This module reads no credentials and performs no network I/O. The opt-in server
owns its use; offline tests exercise the same guard and candidate recorder.
"""
from __future__ import annotations
import base64
from datetime import UTC, datetime
import json
import os
from pathlib import Path
import threading

CASES = {
    "NG01": ("krea-v2/turbo", False), "NG02": ("krea-v2/turbo", True),
    "NG03": ("z-image-turbo", False), "NG04": ("nano-banana-2", False), "NG05": ("nano-banana-2", True),
}


def atomic_json(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf8") as output:
        json.dump(value, output, ensure_ascii=False, indent=2)
        output.flush(); os.fsync(output.fileno())
    temporary.replace(path)


class RetestGuard:
    def __init__(self, evidence: Path, private: Path):
        self.evidence, self.private = evidence, private
        self.counter = evidence / "request-counters.json"
        self.active = evidence / "active-case.json"
        self.lock = threading.RLock()
        if not self.counter.exists():
            atomic_json(self.counter, {"text_requests": 0, "image_submissions": 0, "requests": []})

    def before(self, request):
        host, path = request.url.host, request.url.path
        if host in {"127.0.0.1", "localhost"}:
            return None
        if request.method != "POST":
            if host != "api.nano-gpt.com":
                raise RuntimeError("retest_external_host_denied")
            return None
        text = host == "generativelanguage.googleapis.com" and path.endswith("/models/gemini-3.1-flash-lite:generateContent")
        image = host == "api.nano-gpt.com" and path == "/api/v1/images"
        if not (text or image):
            raise RuntimeError("retest_external_submission_denied")
        with self.lock:
            case = json.loads(self.active.read_text("utf8"))["id"] if self.active.exists() else "SETUP"
            value = json.loads(self.counter.read_text("utf8"))
            record = {"index": len(value["requests"]), "kind": "text" if text else "image", "case": case,
                "at": datetime.now(UTC).isoformat(), "status": "reserved_before_send"}
            if text:
                if value["text_requests"] >= 10:
                    raise RuntimeError("retest_text_budget_exhausted")
                value["text_requests"] += 1
                record["model"] = "gemini-3.1-flash-lite"
            else:
                if case not in CASES or value["image_submissions"] >= 5 or any(r["kind"] == "image" and r["case"] == case for r in value["requests"]):
                    raise RuntimeError("retest_duplicate_or_budget_denied")
                body = json.loads(request.content)
                model, reference = CASES[case]
                expected_options = {"resolution": "1024*1024"} if case == "NG03" else {"resolution": "1k", "aspect_ratio": "1:1"}
                if body.get("model") != model or type(body.get("n")) is not int or body["n"] != 1 or any(body.get(k) != v for k, v in expected_options.items()):
                    raise RuntimeError("retest_baseline_denied")
                if set(body) - {"model", "n", "prompt", "input_references", *expected_options}:
                    raise RuntimeError("retest_wire_option_denied")
                refs = body.get("input_references", [])
                if not isinstance(refs, list) or len(refs) != int(reference):
                    raise RuntimeError("retest_reference_denied")
                reference_mime = None
                if refs:
                    url = refs[0].get("image_url", {}).get("url", "")
                    reference_mime = next((mime for mime in ("image/png", "image/jpeg", "image/webp") if url.startswith(f"data:{mime};base64,")), None)
                    if not reference_mime:
                        raise RuntimeError("retest_reference_mime_denied")
                value["image_submissions"] += 1
                record.update(model=model, options=expected_options, n=1, reference_count=len(refs), reference_mime=reference_mime)
            value["requests"].append(record)
            # Reservation reaches disk before the remote transport sees it.
            atomic_json(self.counter, value)
            return record["index"]

    def after(self, index, response):
        if index is None:
            return
        with self.lock:
            value = json.loads(self.counter.read_text("utf8"))
            value["requests"][index].update(status="response_received", http_status=response.status_code)
            atomic_json(self.counter, value)

    def observe_image(self, response):
        """Called after ImageHttp's bounded read; never store the raw body."""
        with self.lock:
            case = json.loads(self.active.read_text("utf8"))["id"]
            value = json.loads(self.counter.read_text("utf8"))
            attempts = [r for r in value["requests"] if r["kind"] == "image" and r["case"] == case]
            if len(attempts) != 1:
                raise RuntimeError("retest_observation_attempt_missing")
            shape = {"case": case, "attempt": attempts[0]["index"], "http_status": response.status_code,
                "json": False, "data_list": False, "image_count": None, "b64_present": False,
                "declared_mime_present": False, "declared_mime": None, "candidate_retained": False}
            candidate = None
            try:
                body = response.json(); shape["json"] = True
                if isinstance(body, dict) and isinstance(body.get("data"), list):
                    items = body["data"]; shape.update(data_list=True, image_count=len(items))
                    if len(items) == 1 and isinstance(items[0], dict):
                        item = items[0]; encoded = item.get("b64_json"); declared = item.get("media_type")
                        shape["b64_present"] = isinstance(encoded, str)
                        shape["declared_mime_present"] = "media_type" in item
                        shape["declared_mime"] = declared if declared in ("image/png", "image/jpeg", "image/webp") else None
                        if isinstance(encoded, str) and len(encoded) <= 4 * ((12 * 1024 * 1024 + 2) // 3):
                            content = base64.b64decode(encoded, validate=True)
                            shape.update(encoded_length=len(encoded), decoded_length=len(content))
                            if 0 < len(content) <= 12 * 1024 * 1024:
                                candidate = content
            except (ValueError, TypeError, UnicodeError):
                pass
            if candidate is not None:
                root = self.private / "received-candidates"; root.mkdir(parents=True, exist_ok=True)
                candidate_path = root / f"{case}-{attempts[0]['index']}.candidate"
                with candidate_path.open("xb") as output:
                    output.write(candidate); output.flush(); os.fsync(output.fileno())
                atomic_json(candidate_path.with_suffix(".json"), {"case": case, "attempt": shape["attempt"],
                    "declared_mime": shape["declared_mime"], "declaration_valid": declared is None or declared == "" or shape["declared_mime"] is not None})
                shape["candidate_retained"] = True
            # Only the canonical parser supplies success; observation cannot
            # turn malformed candidates into assets or attach to any post.
            from app.integrations.image_api import parse_image_result
            from app.domains.media.generation_contracts import ImageSubmissionError
            from app.integrations.media.images import inspect_image_bytes
            try:
                result = parse_image_result(response)
                info = inspect_image_bytes(result.content, max_bytes=12 * 1024 * 1024, declared_mime=result.content_type)
                shape.update(stage="validated", format=info.format, mime=info.content_type,
                    width=info.width, height=info.height, byte_size=info.byte_size)
            except ImageSubmissionError as exc:
                shape.update(stage=exc.stage, error=exc.code)
            path = self.evidence / "response-shapes.json"
            shapes = json.loads(path.read_text("utf8")) if path.exists() else []
            shapes.append(shape); atomic_json(path, shapes)
            return shape
