"""Explicit, bounded provider acceptance probe. Never run automatically in CI.

The synthetic fixture assembles the final Routine envelope using production
code. This probes schema acceptance and application validation, not AI quality.
The caller must supply the same durable receipt on every invocation. Each
condition is marked attempted *before* sending; unknown outcomes cannot retry.
"""
import argparse
from dataclasses import asdict
from datetime import UTC, datetime
import hashlib
from importlib.metadata import version
import json
from pathlib import Path
import re
import subprocess
import sys
from time import monotonic

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "backend"), str(ROOT / "backend/tests")]

from app.providers.contracts import ProviderRequest
from app.providers.gemini import _generate_content_sync, prepare_generate_request
from app.runtime.autonomous_activity.generation_contracts import parse_routine_draft
from routine_posts.google_wire_fixture import routine_request, valid_output

COUNTS = (0, 1, 3, 5, 7, 8)


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=True).encode()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--key-file", type=Path)
    parser.add_argument("--execute-approved-six", action="store_true")
    args = parser.parse_args()
    receipt = args.receipt.resolve()
    receipt.parent.mkdir(parents=True, exist_ok=True)
    source = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    relevant = (
        "backend/app/contracts/routine_output.py",
        "backend/app/domains/routine_posts/schemas.py",
        "backend/app/domains/routine_posts/service/evidence.py",
        "backend/app/runtime/autonomous_activity/routine.py",
        "backend/app/runtime/autonomous_activity/combined_provider.py",
        "backend/app/runtime/autonomous_activity/provider.py",
        "backend/app/runtime/autonomous_activity/generation_contracts.py",
        "backend/app/providers/gemini.py",
        "backend/app/integrations/direct_llm.py",
        "backend/uv.lock",
        "backend/tests/routine_posts/google_wire_fixture.py",
        "scripts/verify_routine_google_acceptance.py",
    )
    implementation = {path: hashlib.sha256((ROOT / path).read_bytes()).hexdigest()
                      for path in relevant}
    state = json.loads(receipt.read_text("utf-8")) if receipt.exists() else {
        "version": 1, "attempt_limit": 6, "attempts": [], "conditions": [],
        "status": "PROVIDER_ACCEPTANCE_NOT_RUN",
    }
    if len(state["attempts"]) > 6 or any(row["count"] not in COUNTS for row in state["attempts"]):
        raise SystemExit("Invalid durable acceptance ledger")

    def save():
        temporary = receipt.with_suffix(".tmp")
        temporary.write_text(json.dumps(state, indent=2), encoding="utf-8")
        temporary.replace(receipt)

    # Never store the supplied file path, key, request body or returned prose.
    key = None
    if args.execute_approved_six:
        if args.key_file is None:
            raise SystemExit("An explicitly supplied key file is required")
        try:
            key = args.key_file.read_text("utf-8-sig").strip()
        except OSError:
            raise SystemExit("The supplied key file could not be read") from None
        if not re.fullmatch(r"[A-Za-z0-9_-]{16,256}", key):
            raise SystemExit("The supplied key file must contain one API key")

    for count in COUNTS:
        with routine_request(count) as assembled:
            expected = valid_output(count)
            assembled["validator"](expected)
            user = ("Synthetic schema acceptance fixture, not a product activity. "
                    "Use the supplied permitted event IDs and one effect for each. "
                    "Return this permitted JSON object without additional prose:\n" +
                    json.dumps(expected, ensure_ascii=True))
            request = ProviderRequest(api_key=key or "synthetic", model="gemini-3.5-flash-lite",
                system_prompt=assembled["system"], user_prompt=user,
                response_mime_type="application/json", response_schema=assembled["schema"],
                max_output_tokens=8192, thinking_level="medium", sdk_attempts=1,
                timeout_seconds=90)
            prepared = prepare_generate_request(request)
            config = prepared.config.model_dump(by_alias=True, exclude_none=True)
            assert config["responseJsonSchema"] == assembled["schema"]
            assert "maxItems" not in assembled["schema"]["properties"]["decision"]["properties"]["source_event_effects"]
            condition = {"count": count, "source": source, "model": request.model,
                "implementation_sha256": digest(implementation),
                "sdk": version("google-genai"), "thinking": "medium", "output_cap": 8192,
                "sdk_attempts": 1, "timeout_seconds": 90,
                "schema_sha256": digest(assembled["schema"]), "config_sha256": digest(config),
                "system_sha256": hashlib.sha256(request.system_prompt.encode()).hexdigest(),
                "input_sha256": hashlib.sha256(user.encode()).hexdigest(),
                "synthetic_only": True, "probe": "schema acceptance with permitted synthetic output example"}
            prior = next((row for row in state["conditions"] if row["count"] == count), None)
            if prior and prior != condition:
                raise SystemExit("Acceptance input changed; do not reuse or reset the receipt")
            if prior is None:
                state["conditions"].append(condition)
            state["implementation"] = implementation
            save()
            if not args.execute_approved_six:
                continue
            if any(row["count"] == count for row in state["attempts"]):
                continue
            if len(state["attempts"]) >= 6:
                raise SystemExit("Approved provider attempt limit reached")
            row = {"count": count, "started_at": datetime.now(UTC).isoformat(),
                   "status": "ATTEMPTED_OUTCOME_UNKNOWN"}
            state["attempts"].append(row)
            save()
            started = monotonic()
            try:
                response = _generate_content_sync(request)
                row["provider_accepted"] = True
                value = response.parsed if isinstance(response.parsed, dict) else json.loads(response.text)
                row["json_received"] = True
                validated = assembled["validator"](value)
                parse_routine_draft(value["draft"], image_enabled=True)
                row.update(status="PASS", server_validated=True,
                    effects=len(validated["plan"]["source_event_effects"]),
                    response_sha256=digest(value), finish_reason=response.finish_reason,
                    usage=asdict(response.usage))
            except Exception as exc:
                # Exception messages may include request bodies or credentials.
                code = getattr(exc, "code", None)
                row.update(status="FAIL", exception_kind=type(exc).__name__,
                           http_code=code if isinstance(code, int) else None)
            finally:
                row["elapsed_ms"] = (monotonic() - started) * 1000
                save()
                print(json.dumps({k: row[k] for k in ("count", "status", "elapsed_ms")}), flush=True)
    if args.execute_approved_six:
        state["status"] = ("PASS" if len(state["attempts"]) == 6 and
                           all(row["status"] == "PASS" for row in state["attempts"]) else "FAIL")
        save()
    print(json.dumps({"status": state["status"], "attempts": len(state["attempts"])}))


if __name__ == "__main__":
    main()
