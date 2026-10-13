"""Exact public Git-source proof must never exempt credentials or other paths."""
from pathlib import Path
import re
import subprocess
import tomllib

ROOT = Path(__file__).resolve().parents[2]
DESCRIPTION = "Exact release-integration public source Git blobs"
EVIDENCE = (
    ('security/post_refactor_contract_changes.json', 'backend/app/domains/identity/router/auth.py', 'c179b5be953030242bf9cb626e1b86c0b3275293', 'dd96e488b578c061d1226247b1a093a400ce83e4'),
    ('security/post_refactor_contract_changes.json', 'backend/app/domains/identity/service/auth.py', '081df2d94c5d3ac0a0c182c6946772f94936d727', 'dd96e488b578c061d1226247b1a093a400ce83e4'),
    ('security/post_refactor_contract_changes.json', 'backend/tests/chat/test_p8_l_d_world_chat_api.py', '3d9dfdd39629eb24c5cc1062d5db7934032220eb', 'd2ada054d0c979794daecaca25907b6ac84947a6'),
    ('security/post_refactor_contract_changes.json', 'backend/tests/chat/test_p8_l_d_world_chat_api.py', '92b26bacfd0a38287a985ae0ba1eb9d8d5c4cca4', '8551ea27c5b521504b9c22e22646b9637f5af758'),
    ('security/post_refactor_contract_changes.json', 'backend/tests/memory/test_p8_l_r_memory_batch_api.py', 'a4523cc3f1b857e87adcc29197549ab443bb806f', 'dd96e488b578c061d1226247b1a093a400ce83e4'),
    ('security/post_refactor_contract_changes.json', 'browser-tests/playwright.world-character-api.config.ts', 'ac228d6d97249b6b5262bf8d22601a9d10c4e114', '8551ea27c5b521504b9c22e22646b9637f5af758'),
    ('security/post_refactor_contract_changes.json', 'browser-tests/world-character-configuration-api.spec.ts', '51b0aec04167bfb00e085a262d09da2e5975c54b', '8551ea27c5b521504b9c22e22646b9637f5af758'),
    ('security/post_refactor_contract_changes.json', 'frontend/src/features/characters/components/activity-credential-form.tsx', '9a369e1c8da10ddbb4d4c358dfac533c57fd4c83', '77aa85f75e3f8ae6157d0aa41ac07a3018cc058c'),
    ('security/post_refactor_contract_changes.json', 'frontend/src/lib/auth/auth-context.ts', '16eb25cdf26923a2b3feb047e1fda4df0f5366aa', '77aa85f75e3f8ae6157d0aa41ac07a3018cc058c'),
    ('security/post_refactor_contract_changes.json', 'frontend/src/lib/http/api-request.ts', '1fea05cbc02605d24ce98c1c2b92aa6cf13770b6', 'b9e6142e826fba5a7110d8ffcb422003142df261'),
    ('security/post_refactor_contract_changes.json', 'frontend/src/lib/http/api-request.ts', '2a70207309b02ccb2c24e41b2138468cbd0c6066', '77aa85f75e3f8ae6157d0aa41ac07a3018cc058c'),
    ('security/refactor_backend_additions.json', 'browser-tests/playwright.world-character-api.config.ts', 'ac228d6d97249b6b5262bf8d22601a9d10c4e114', '8551ea27c5b521504b9c22e22646b9637f5af758'),
    ('security/refactor_backend_additions.json', 'browser-tests/world-character-configuration-api.spec.ts', '51b0aec04167bfb00e085a262d09da2e5975c54b', '8551ea27c5b521504b9c22e22646b9637f5af758'),
    ('security/post_refactor_contract_changes.json', 'backend/tests/test_t2_secret_allowlist.py', '05f9d788ddaa1d35b6cf6647668121fc1eba1881', 'b19eca0196f92f7d48bf258df5ea3c466a1767c8'),
    ('security/post_refactor_contract_changes.json', 'backend/security/secret_scan_allowlist.json', 'cdfa774f0fa21b50ab29e7ed9ae345f79a737729', 'c10ee037a1b13851d54b52e38be1a8fac4d28607'),
    ('security/post_refactor_contract_changes.json', 'backend/tests/test_t2_secret_allowlist.py', 'fd6be4d63213ad086e7096d9a7c2f4d23cba13fc', 'c10ee037a1b13851d54b52e38be1a8fac4d28607'),
    ('security/post_refactor_contract_changes.json', 'backend/security/secret_scan_allowlist.json', '238944f9a08254cb18035aab4d58d9ae18900ee9', '20332573326b98ec66fc57f6d3b728ec4156b9b1'),
    ('security/post_refactor_contract_changes.json', 'backend/tests/world_characters/test_world_key_execution.py', '6266e382e8a87f9f534bd048e935adc9427340f5', '6482483a0995321fc5525d8e5db3df349c8e6df4'),
)

def groups():
    config = tomllib.loads((ROOT / ".gitleaks.toml").read_text(encoding="utf-8"))
    return [group for group in config["allowlists"] if group["description"].startswith(DESCRIPTION)]

def allowed(path, line):
    return any(any(re.search(pattern, path) for pattern in group["paths"])
        and any(re.search(pattern, line) for pattern in group["regexes"])
        for group in groups())

def test_release_provenance_review_keeps_rule_path_and_full_line_conditions():
    reviewed = groups()
    assert len(reviewed) == 1
    assert reviewed[0]["targetRules"] == ["generic-api-key"]
    assert reviewed[0]["condition"] == "AND"
    assert reviewed[0]["regexTarget"] == "line"
    assert reviewed[0]["paths"] == [
        r"(^|/)security/refactor_backend_additions\.json$",
        r"(^|/)security/post_refactor_contract_changes\.json$",
    ]
    assert len(reviewed[0]["regexes"]) == len({(row[1], row[2]) for row in EVIDENCE})
    assert all(pattern.startswith(r"^\s*") and pattern.endswith("$")
        for pattern in reviewed[0]["regexes"])

def test_reviewed_public_source_blobs_match_actual_committed_objects_and_ancestry():
    for manifest, source, blob, commit in EVIDENCE:
        actual = subprocess.check_output(
            ["git", "rev-parse", f"{commit}:{source}"], cwd=ROOT, text=True).strip()
        assert actual == blob
        subprocess.run(["git", "merge-base", "--is-ancestor", commit, "HEAD"],
            cwd=ROOT, check=True)
        line = f'"{source}": "{blob}",'
        assert allowed(manifest, line)

def test_release_provenance_exceptions_reject_changed_value_key_path_or_extra_data():
    for manifest, source, blob, _commit in EVIDENCE:
        line = f'"{source}": "{blob}",'
        assert not allowed("backend/app/config.py", line)
        assert not allowed(manifest + ".backup", line)
        assert not allowed(manifest, line.replace(blob, "0" * 40))
        assert not allowed(manifest, line.replace(source, "api_key"))
        assert not allowed(manifest, line + ' "api_key": "unrelated-value"')
    config = tomllib.loads((ROOT / ".gitleaks.toml").read_text(encoding="utf-8"))
    vectors = [group for group in config["allowlists"]
        if group["description"].startswith("Exact release-integration provenance test vectors")]
    assert len(vectors) == 1
    group = vectors[0]
    assert group["targetRules"] == ["generic-api-key"]
    assert group["condition"] == "AND" and group["regexTarget"] == "line"
    assert group["paths"] == [r"(^|/)backend/tests/test_release_gitleaks_provenance\.py$"]
    assert len(group["regexes"]) == len(EVIDENCE)
    assert all(pattern.startswith(r"^\s*") and pattern.endswith("$") for pattern in group["regexes"])
    for row in EVIDENCE:
        line = repr(row) + ","
        assert any(re.search(pattern, line) for pattern in group["regexes"])
        assert not any(re.search(pattern, line.replace(row[2], "0" * 40)) for pattern in group["regexes"])
        assert not any(re.search(pattern, line + ' api_key="unrelated-value"') for pattern in group["regexes"])
    assert not any(re.search(pattern, "backend/app/config.py") for pattern in group["paths"])
