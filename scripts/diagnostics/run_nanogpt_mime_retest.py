"""Five authorized SNS retests. Default dry run reads no key and opens no API.

Resume/recover-only reconciles existing jobs and pixels. It cannot submit a
completed/started case again; the server's durable guard independently enforces
five image POSTs and ten Gemini requests across process restarts.
"""
from __future__ import annotations
import argparse
import base64
from datetime import UTC, datetime
from hashlib import sha256
import importlib.util
import json
from pathlib import Path
import re
import sqlite3
import sys
import time
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[2]
WORKSPACE = ROOT.parent
sys.path.insert(0, str(ROOT / "backend"))
from nanogpt_retest_support import CASES, atomic_json

APPEARANCE = "adult woman, long pink hair, amber eyes, slender build, black sundress"
STYLE = "anime illustration, clear detailed composition"
NEGATIVE = "blurry, low quality, extra fingers"


class OwnerApi:
    def __init__(self, port):
        import httpx
        origin = "http://127.0.0.1:13000"
        self.client = httpx.Client(base_url=f"http://127.0.0.1:{port}", timeout=650, trust_env=False,
            headers={"Origin": origin, "x-angmoo-frontend-origin": origin})
        state = self.call("GET", "/auth/local/bootstrap")
        if not state.get("owner") and not state.get("owner_user_id") and state.get("status") not in {"claimed", "owner_claimed"}:
            self.call("POST", "/auth/local/bootstrap/challenge")
            self.call("POST", "/auth/local/bootstrap/claim", {"display_name": "NanoGPT SNS 재검증", "local_label": "isolated five-case retest", "privacy_acknowledged": True})
        self.call("POST", "/auth/local/session")

    def response(self, method, path, body=None):
        url = path if path.startswith("/_diagnostics") or path.startswith("/api/") else "/api/v1" + path
        headers = {"Cookie": "; ".join(c.name + "=" + c.value for c in self.client.cookies.jar)} if path.startswith("/_diagnostics") else None
        response = self.client.request(method, url, json=body, headers=headers)
        if response.status_code >= 300:
            try:
                detail = response.json().get("detail")
            except ValueError:
                detail = None
            safe = detail if isinstance(detail, str) and re.fullmatch(r"[a-zA-Z0-9_.:-]{1,120}", detail) else "safe_details_omitted"
            raise RuntimeError(f"local_http_{response.status_code}:{safe}")
        return response

    def call(self, method, path, body=None):
        response = self.response(method, path, body)
        return response.json() if response.content else None


def read_db(private, sql, parameters=()):
    files = list((private / "data/canonical/generations").glob("*/angmoo.sqlite3"))
    if len(files) != 1:
        raise RuntimeError("isolated_database_not_unique")
    with sqlite3.connect("file:" + str(files[0]) + "?mode=ro", uri=True) as db:
        db.row_factory = sqlite3.Row; db.execute("PRAGMA query_only=ON")
        return [dict(row) for row in db.execute(sql, parameters)]


def approved_text_material(identity):
    value = json.loads(identity.read_text("utf-8-sig"))
    if value.get("status") != "identity_verified":
        raise RuntimeError("approved_source_identity_unverified")
    paths = [row for row in value.get("data_paths", []) if row.get("name") == "active-sqlite" and row.get("verified_path")]
    if len(paths) != 1:
        raise RuntimeError("approved_active_database_unverified")
    database = Path(paths[0]["resolved_path"].replace("\\\\?\\UNC\\", "\\\\", 1))
    secret = Path(value["read_root"]) / "secrets/app-secret"
    spec = importlib.util.spec_from_file_location("approved_source_reader", ROOT / "scripts/diagnostics/run_image_recognition_live.py")
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    module.physical_read_path(database); module.physical_read_path(secret)
    with sqlite3.connect("file:" + str(database) + "?mode=ro", uri=True) as db:
        db.execute("PRAGMA query_only=ON")
        characters = db.execute("SELECT id,owner_id FROM characters WHERE name=? AND deleted_at IS NULL", ("미도리야 이즈쿠",)).fetchall()
        if len(characters) != 1:
            raise RuntimeError("approved_character_not_unique")
        char, owner = characters[0]
        credentials = db.execute("SELECT id FROM llm_credentials WHERE character_id=? AND owner_id=? AND provider='google' AND purpose='agent' AND enabled=1", (char, owner)).fetchall()
        if len(credentials) != 1:
            raise RuntimeError("approved_credential_not_unique")
    return module.approved_material(SimpleNamespace(database=database, secret_file=secret,
        character_id=char, owner_id=owner, credential_id=credentials[0][0])).reveal()


def setup(api, args):
    path = args.private_root / "manifest.json"
    manifest = json.loads(path.read_text("utf8")) if path.exists() else {"batch_id": args.evidence.name}
    if "world_id" not in manifest:
        manifest["world_id"] = api.call("POST", "/worlds/default-space/ensure")["id"]
        atomic_json(path, manifest)
    api.call("POST", f"/worlds/{manifest['world_id']}/my-profile/ensure")
    if "character_id" not in manifest:
        draft = api.call("POST", "/agents/drafts", {"target_world_id": manifest["world_id"]})
        fixture = WORKSPACE / ".local-diagnostics/creator-cards-20260927/Seraphina.png"
        draft = api.call("POST", f"/agents/drafts/{draft['id']}/card", {"revision": draft["revision"],
            "data_base64": base64.b64encode(fixture.read_bytes()).decode()})["draft"]
        completed = api.call("POST", f"/agents/drafts/{draft['id']}/complete", {"revision": draft["revision"]})
        manifest["character_id"] = completed.get("character", completed)["id"]
        atomic_json(path, manifest)
    char = manifest["character_id"]
    api.call("PUT", f"/agents/{char}/credential", {"provider": "google", "model": "gemini-3.1-flash-lite",
        "thinking_level": "high", "api_key": approved_text_material(args.evidence / "source-identity.json")})
    api.call("PUT", f"/agents/{char}/settings", {"active_hours_start": "00:00", "active_hours_end": "17:00",
        "max_posts_per_day": 30, "allow_post": True, "allow_reply": False, "allow_like": False,
        "allow_repost": False, "allow_follow": False, "allow_unfollow": False})
    if "reference_asset" not in manifest:
        fixture = WORKSPACE / ".local-diagnostics/creator-cards-20260927/Seraphina.png"
        asset = api.call("POST", "/media/assets", {"scope_kind": "character", "scope_id": char,
            "content_type": "image/png", "data_base64": base64.b64encode(fixture.read_bytes()).decode()})
        manifest["reference_asset"] = asset["id"]; atomic_json(path, manifest)
    return manifest


def usage(key):
    import httpx
    day = datetime.now(UTC).date().isoformat()
    response = httpx.get("https://api.nano-gpt.com/api/v1/usage", headers={"Authorization": "Bearer " + key},
        params={"from": day, "to": day, "groupBy": "day,model"}, timeout=30, trust_env=False)
    record = {"http_status": response.status_code, "at": datetime.now(UTC).isoformat(), "date": day, "scope": "current_key_aggregate"}
    if response.status_code == 200:
        body = response.json()
        fields = {"requests", "costUsd", "refundedUsd", "netCostUsd", "inputTokens", "outputTokens", "totalTokens"}
        record["totals"] = {k: v for k, v in body.get("totals", {}).items() if k in fields and isinstance(v, (int, float))}
    return record


def evidence_for_received(api, args, manifest, result):
    from app.integrations.media.images import inspect_image_bytes
    from app.domains.media.service.assets import prepare_asset_image
    post = result.get("post_id")
    if not post:
        return False
    jobs = read_db(args.private_root, "SELECT j.id,j.status,j.failure_class,j.result_asset_id,i.scene,i.request_json FROM post_image_generation_jobs j JOIN post_image_intents i ON i.id=j.intent_id WHERE j.post_id=?", (post,))
    if len(jobs) != 1:
        result.update(status="FAILED", reason="image_job_not_unique"); return False
    job = jobs[0]; result.update(job_id=job["id"], job_status=job["status"], scene_present=bool(job["scene"].strip()))
    if job["status"] != "succeeded":
        result.update(status="OUTCOME_UNKNOWN" if job["status"] == "outcome_unknown" else "FAILED", reason=job["failure_class"] or job["status"])
        return False
    rows = read_db(args.private_root, "SELECT m.asset_id,m.width,m.height,m.byte_size,a.storage_key,a.content_type,a.content_hash FROM post_media m JOIN media_assets a ON a.id=m.asset_id WHERE m.post_id=?", (post,))
    if len(rows) != 1:
        raise RuntimeError("attachment_count_invalid")
    asset = rows[0]
    file = args.private_root / "data/media/private-image-assets" / asset["storage_key"]
    content = file.read_bytes()
    info = inspect_image_bytes(content, max_bytes=24 * 1024 * 1024, declared_mime=asset["content_type"])
    if file.suffix != "." + info.extension or sha256(content).hexdigest() != asset["content_hash"] or (info.width, info.height, info.byte_size) != (asset["width"], asset["height"], asset["byte_size"]):
        raise RuntimeError("stored_metadata_invalid")
    http = api.response("GET", f"/media/assets/{asset['asset_id']}/content")
    if http.content != content or http.headers.get("content-type") != info.content_type or http.headers.get("x-content-type-options") != "nosniff":
        raise RuntimeError("content_response_invalid")
    before = json.loads((args.evidence / "request-counters.json").read_text("utf8"))["image_submissions"]
    for _ in range(2):
        view = api.call("GET", f"/worlds/{manifest['world_id']}/manual-social/posts/{post}")
        api.call("GET", f"/media/worlds/{manifest['world_id']}/posts/{post}/image-generation")
    api.call("POST", "/_diagnostics/worker-recover")
    after = json.loads((args.evidence / "request-counters.json").read_text("utf8"))["image_submissions"]
    request = json.loads(job["request_json"])
    candidates = list((args.private_root / "received-candidates").glob(result["id"] + "-*.candidate"))
    if len(candidates) != 1:
        raise RuntimeError("private_candidate_not_unique")
    incoming = candidates[0].read_bytes()
    prepared = prepare_asset_image(info.content_type, incoming, max_bytes=12 * 1024 * 1024)
    from io import BytesIO
    from PIL import Image
    with Image.open(BytesIO(incoming)) as image:
        image.load()
        incoming_exif_present = bool(image.getexif())
        incoming_comment_present = "comment" in image.info
    if prepared.content != content or before != after:
        raise RuntimeError("received_or_requery_invariant_invalid")
    from app.domains.media.generation_contracts import compose_positive
    scene_only = result["id"] == "NG03"
    expected_positive = compose_positive(style="" if scene_only else STYLE, appearance="" if scene_only else APPEARANCE, scene=job["scene"])
    expected_reference = "override" if CASES[result["id"]][1] else "none"
    if request["provider"] != "nanogpt" or request["model"] != CASES[result["id"]][0] or not result["scene_present"] or request["positive"] != expected_positive or request["reference"]["source"] != expected_reference:
        raise RuntimeError("routine_request_contract_invalid")
    result.update(status="PASS", reason=None, format=info.format, mime=info.content_type, extension=info.extension,
        width=info.width, height=info.height, byte_size=info.byte_size, content_hash=asset["content_hash"], asset_id=asset["asset_id"],
        private_image_path=str(file), exact_received_bytes=content == incoming, necessary_normalization=prepared.normalized,
        incoming_exif_present=incoming_exif_present,
        incoming_comment_present=incoming_comment_present,
        attachment_count=1, requery_new_image_submissions=after-before, feed_requery=True, worker_requery=True,
        reference_source=request["reference"]["source"], positive_scene_included=job["scene"].strip() in request["positive"])
    return True


def cleanup(api, args, manifest):
    char = manifest["character_id"]
    api.call("POST", f"/agents/{char}/deactivate")
    state = api.call("GET", f"/agents/{char}/generation-settings")
    if state.get("provider") and (state["auto_enabled"] or state["has_api_key"]):
        api.call("PUT", f"/agents/{char}/generation-settings", {"expected_revision": state["revision"],
            "provider": state["provider"], "model": state["model"], "auto_enabled": False, "daily_limit": 5,
            "appearance": state["appearance"], "style": state["style"], "negative": state["negative"],
            "reference_asset_id": state.get("reference_asset_id"), "reference_enabled": state.get("active_profile", {}).get("reference_enabled"),
            "options": state.get("active_profile", {}).get("options", {}), "clear_api_key": True})
    text_sql = ("SELECT count(*) AS rows, coalesce(sum(enabled),0) AS enabled, "
        "coalesce(sum(encrypted_api_key IS NOT NULL),0) AS secrets "
        "FROM llm_credentials WHERE character_id=?")
    text_state = read_db(args.private_root, text_sql, (char,))[0]
    if text_state["enabled"] or text_state["secrets"]:
        api.call("DELETE", f"/agents/{char}/credential")
    state = api.call("GET", f"/agents/{char}/generation-settings")
    credential_state = read_db(args.private_root,
        "SELECT count(*) AS rows, coalesce(sum(enabled),0) AS enabled, "
        "coalesce(sum(encrypted_secret IS NOT NULL),0) AS secrets "
        "FROM media_credentials WHERE character_scope=?", (char,))[0]
    text_state = read_db(args.private_root, text_sql, (char,))[0]
    if state["auto_enabled"] or state["has_api_key"] or credential_state["enabled"] or credential_state["secrets"] or text_state["enabled"] or text_state["secrets"]:
        raise RuntimeError("test_credentials_not_cleared")
    atomic_json(args.evidence / "cleanup.json", {"auto_enabled": state["auto_enabled"], "has_image_key": state["has_api_key"],
        "image_credential_rows": credential_state["rows"],
        "enabled_image_credentials_remaining": credential_state["enabled"],
        "image_secrets_remaining": credential_state["secrets"], "text_credential_rows": text_state["rows"],
        "enabled_text_credentials_remaining": text_state["enabled"], "text_secrets_remaining": text_state["secrets"],
        "original_credentials_unchanged": True, "private_data_preserved": True})


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--private-root", type=Path, required=True)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--port", type=int, default=18388)
    parser.add_argument("--execute-authorized-plan", action="store_true")
    parser.add_argument("--case", choices=list(CASES), action="append")
    parser.add_argument("--recover-only", action="store_true")
    parser.add_argument("--resume-routine", action="store_true", help="Only an unstarted Routine with no image submission")
    parser.add_argument("--cleanup", action="store_true")
    args = parser.parse_args()
    if not args.execute_authorized_plan:
        print(json.dumps({"mode": "dry_run", "cases": list(CASES), "key_reads": 0, "network_calls": 0, "image_limit": 5, "text_limit": 10})); return
    api = OwnerApi(args.port)
    manifest_path = args.private_root / "manifest.json"
    if args.recover_only or args.cleanup:
        manifest = json.loads(manifest_path.read_text("utf8"))
    else:
        manifest = setup(api, args)
    if args.cleanup:
        cleanup(api, args, manifest); return
    path = args.evidence / "case-results.json"
    report = json.loads(path.read_text("utf8")) if path.exists() else {"batch_id": args.evidence.name, "results": []}
    key = None
    if not args.recover_only:
        key = json.loads((WORKSPACE / "angmoo-secrets/image-api-keys.json").read_text("utf-8-sig"))["nanogpt"]
        if not isinstance(key, str) or not key:
            raise RuntimeError("nanogpt_key_missing")
        usage_path = args.evidence / "usage-before.json"
        if not usage_path.exists():
            atomic_json(usage_path, usage(key))
    for case, (model, reference) in CASES.items():
        if args.case and case not in args.case:
            continue
        previous = next((row for row in report["results"] if row["id"] == case), None)
        resume_routine = False
        if previous is not None or args.recover_only:
            counts = json.loads((args.evidence / "request-counters.json").read_text("utf8"))
            case_calls = [row for row in counts["requests"] if row["case"] == case]
            run_path = args.evidence / (case + "-routine-run.json")
            empty_run = not run_path.exists() or json.loads(run_path.read_text("utf8")).get("started_count") == 0
            resume_routine = bool(args.resume_routine and not args.recover_only and previous and not previous.get("post_id")
                and empty_run and len(case_calls) == 1 and case_calls[0]["kind"] == "text")
            if resume_routine:
                previous.setdefault("preflight_history", []).append({"status": previous["status"], "reason": previous.get("reason"), "image_submissions": 0})
                if run_path.exists():
                    run_path.replace(run_path.with_name(case + "-routine-before-due.json"))
            else:
                if previous and previous.get("post_id"):
                    api.call("POST", "/_diagnostics/worker-recover")
                    evidence_for_received(api, args, manifest, previous); atomic_json(path, report)
                continue
        counts = json.loads((args.evidence / "request-counters.json").read_text("utf8"))
        if not resume_routine and any(row["case"] == case for row in counts["requests"]):
            raise RuntimeError("case_already_reserved_requires_recovery")
        result = previous if resume_routine else {"id": case, "original_case_id": case, "batch_id": args.evidence.name, "model": model,
            "reference_preferred": reference, "status": "STARTED", "started_at": datetime.now(UTC).isoformat()}
        result.update(status="STARTED", reason=None)
        if not resume_routine:
            report["results"].append(result)
        atomic_json(path, report)
        atomic_json(args.evidence / "active-case.json", {"id": case})
        char = manifest["character_id"]
        try:
            state = api.call("GET", f"/agents/{char}/generation-settings")
            limits = api.call("GET", "/media/usage-settings")
            options = {"resolution": "1024*1024"} if case == "NG03" else {"resolution": "1k", "aspect_ratio": "1:1"}
            saved = api.call("POST", f"/agents/{char}/generation-settings/check", {"expected_revision": state["revision"],
                "provider": "nanogpt", "model": model, "auto_enabled": True, "daily_limit": 5, "installation_daily_limit": 5,
                "installation_expected_revision": limits["revision"], "appearance": "" if case == "NG03" else APPEARANCE,
                "style": "" if case == "NG03" else STYLE, "negative": NEGATIVE, "reference_enabled": reference,
                "reference_asset_id": manifest["reference_asset"], "options": options, "api_key": key})
            result.update(settings_revision=saved["revision"], options=options, reference_state=saved.get("reference_state"))
            prepared = api.call("GET", f"/characters/{char}/worlds/{manifest['world_id']}/daily-preparation")
            if not resume_routine:
                prepared = api.call("POST", f"/characters/{char}/worlds/{manifest['world_id']}/daily-preparation", {
                    "request_id": args.evidence.name + "-" + case, "expected_version": prepared["plan_version"]})
            if prepared["plan_state"] != "ready":
                raise RuntimeError("daily_preparation_not_ready")
            before_posts = {row["id"] for row in read_db(args.private_root, "SELECT id FROM posts WHERE author_character_id=?", (char,))}
            api.call("POST", f"/agents/{char}/activate")
            tick = api.call("POST", "/_diagnostics/tick")
            result.update(scheduler_started=tick.get("started_count"), run_ids=tick.get("run_ids"))
            api.call("POST", f"/agents/{char}/deactivate")
            posts = [row for row in read_db(args.private_root, "SELECT id FROM posts WHERE author_character_id=? AND activity_beat_id IS NOT NULL", (char,)) if row["id"] not in before_posts]
            if len(posts) != 1:
                raise RuntimeError("routine_new_post_not_unique")
            result["post_id"] = posts[0]["id"]; atomic_json(path, report)
            for _ in range(180):
                jobs = read_db(args.private_root, "SELECT status FROM post_image_generation_jobs WHERE post_id=?", (result["post_id"],))
                if not jobs or jobs[0]["status"] not in {"queued", "running", "result_pending", "result_ready"}:
                    break
                time.sleep(1)
            evidence_for_received(api, args, manifest, result)
        except Exception as exc:
            safe = str(exc) if isinstance(exc, RuntimeError) and re.fullmatch(r"[a-zA-Z0-9_.:-]{1,160}", str(exc)) else type(exc).__name__
            result.update(status="FAILED", reason=safe)
            try:
                api.call("POST", f"/agents/{char}/deactivate")
            except Exception:
                pass
        finally:
            after = json.loads((args.evidence / "request-counters.json").read_text("utf8"))
            result.update(text_requests=sum(r["case"] == case and r["kind"] == "text" for r in after["requests"]),
                image_submissions=sum(r["case"] == case and r["kind"] == "image" for r in after["requests"]), finished_at=datetime.now(UTC).isoformat())
            atomic_json(path, report)
            print(json.dumps({k: result.get(k) for k in ("id", "status", "reason", "format", "text_requests", "image_submissions")}), flush=True)
        if result["status"] != "PASS":
            break
    if key:
        atomic_json(args.evidence / "usage-after.json", usage(key))


if __name__ == "__main__":
    main()
