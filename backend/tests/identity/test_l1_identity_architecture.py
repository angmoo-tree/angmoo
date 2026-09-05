from __future__ import annotations

import json
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[3]


def _module_imports() -> dict[str, set[str]]:
    inventory = json.loads(
        (REPO_ROOT / "security/architecture_import_baseline.json").read_text(
            encoding="utf-8"
        )
    )
    return {
        item["module"]: set(item["imports"])
        for item in inventory["modules"]
    }


def _legacy_edges() -> set[tuple[str, str]]:
    policy: dict[str, Any] = json.loads(
        (REPO_ROOT / "security/architecture_import_policy.json").read_text(
            encoding="utf-8"
        )
    )
    return {
        (edge["importer"], edge["imported"])
        for group in policy["legacy_exception_groups"]
        for edge in group["edges"]
    }


def test_identity_domain_is_the_canonical_aggregate_source() -> None:
    imports = _module_imports()

    assert "app.domains.identity.models" in imports["app.models"]
    assert "app.models.auth" not in imports["app.models"]
    assert "app.models.credentials" not in imports["app.models"]
    assert "app.domains.identity.schemas" in imports["app.schemas"]
    assert "app.schemas.auth" not in imports["app.schemas"]
    assert imports["app.credentials"] >= {
        "app.domains.identity.service.credential_resolution",
        "app.domains.identity.contracts",
    }


def test_identity_compatibility_facades_only_point_inward() -> None:
    imports = _module_imports()

    assert imports["app.models.auth"] == {
        "app.domains.identity.models"
    }
    assert imports["app.models.credentials"] == {
        "app.domains.identity.models"
    }
    assert imports["app.schemas.auth"] == {"app.domains.identity.schemas"}
    assert imports["app.credentials.contracts"] == {
        "app.domains.identity.contracts"
    }
    assert imports["app.credentials.resolver"] == {
        "app.domains.identity.service.credential_resolution"
    }
    assert "app.credentials.contracts" not in imports[
        "app.domains.identity.service.credential_resolution"
    ]


def test_removed_identity_legacy_edges_are_not_allowlisted() -> None:
    edges = _legacy_edges()

    assert ("app.models", "app.models.auth") not in edges
    assert ("app.models", "app.models.credentials") not in edges
    assert ("app.schemas", "app.schemas.auth") not in edges
