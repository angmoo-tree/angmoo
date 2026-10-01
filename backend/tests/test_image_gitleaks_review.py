"""Reviewed public evidence must not exempt other credential values or paths."""
import json
import hashlib
from pathlib import Path
import re
import tomllib

import pytest


ROOT = Path(__file__).resolve().parents[2]
DESCRIPTIONS = (
    "Exact public image source Git blobs verified",
    "Exact bundled T5 SentencePiece resource SHA256",
    "Exact synthetic Chat image recovery idempotency markers",
    "Exact SQLAlchemy lease expiry expressions",
)


def reviewed_groups():
    groups = tomllib.loads((ROOT / ".gitleaks.toml").read_text(encoding="utf-8"))["allowlists"]
    return [g for g in groups if g["description"].startswith(DESCRIPTIONS)]


def allowed(path, line):
    return any(any(re.search(pattern, path) for pattern in group["paths"])
        and any(re.search(pattern, line) for pattern in group["regexes"])
        for group in reviewed_groups())


def fingerprint():
    source = "backend/app/integrations/image_api.py"
    records = json.loads((ROOT / "security/refactor_backend_additions.json").read_text(encoding="utf-8"))["records"]
    for record in records:
        value = record.get("tracked_files", {}).get(source)
        if value:
            line = json.dumps(source) + ": " + json.dumps(value) + ","
            if allowed("security/refactor_backend_additions.json", line):
                return value, line
    raise AssertionError("exact committed public fingerprint not found")


def test_image_review_keeps_exact_rule_path_and_line_conditions():
    groups = reviewed_groups()
    assert len(groups) == 4
    assert all(group["targetRules"] == ["generic-api-key"] for group in groups)
    assert all(group["condition"] == "AND" and group["regexTarget"] == "line" for group in groups)
    assert all(pattern.startswith("^\\s*") or pattern.startswith("^TOKENIZER_HASH")
        for group in groups for pattern in group["regexes"])
    assert all(pattern.endswith("$") for group in groups for pattern in group["regexes"])


def test_public_blob_is_allowed_only_as_the_reviewed_source_field():
    value, line = fingerprint()
    assert allowed("security/refactor_backend_additions.json", line)
    assert allowed("security/post_refactor_contract_changes.json", line)
    assert not allowed("backend/app/integrations/image_api.py", line)
    assert not allowed("security/refactor_backend_additions.json", line.replace(value, "0" * 40))
    assert not allowed("security/refactor_backend_additions.json", line.replace("backend/app/integrations/image_api.py", "api_key"))
    assert not allowed("security/refactor_backend_additions.json", line + ' "api_key": "unrelated-value"')


def test_tokenizer_exception_matches_only_the_bundled_resource_digest():
    value = hashlib.sha256((ROOT / "backend/app/integrations/novelai_resources/t5.spiece.model").read_bytes()).hexdigest()
    path = "backend/app/integrations/novelai_images.py"
    line = f'TOKENIZER_HASH = "{value}"\n'
    assert allowed(path, line)
    assert not allowed(path, line.replace(value, "0" * 64))
    assert not allowed(path, line.replace("TOKENIZER_HASH", "api_key"))
    assert not allowed("backend/app/config.py", line)


@pytest.mark.parametrize("mutation", ["path", "value", "extra"])
def test_synthetic_idempotency_exception_does_not_cover_other_values(mutation):
    path = "backend/tests/image_integration/test_chat_attachments.py"
    line = 'WorldChatMessageCreate(content="keep this message", attachment_asset_id=asset, idempotency_key="synthetic-cancel-001"))'
    assert allowed(path, line)
    if mutation == "path":
        path = "backend/app/runtime/chat/image_attachments.py"
    elif mutation == "value":
        line = line.replace("synthetic-cancel-001", "synthetic-cancel-002")
    else:
        line += ' api_key="unrelated-value"'
    assert not allowed(path, line)


def test_lease_expression_exception_does_not_cover_a_credential_literal():
    path = "backend/app/domains/social/service/image_intent_generation.py"
    line = '.values(status="running", lease_token=token, lease_until=now + timedelta(minutes=5)))'
    assert allowed(path, line)
    assert not allowed(path, line.replace("minutes=5", "minutes=10"))
    assert not allowed(path, line.replace("token, lease_until", '"unrelated-value", lease_until'))
    assert not allowed("backend/app/integrations/image_api.py", line)
