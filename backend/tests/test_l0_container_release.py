from __future__ import annotations

import importlib.util
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[2]


def _load(name: str, relative: str):
    path = ROOT / relative
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


CONTRACT = _load(
    "angmoo_l0_container_release_contract",
    "scripts/ci/check_container_release_contract.py",
)
IMAGES = _load(
    "angmoo_l0_container_images",
    "scripts/ci/check_container_images.py",
)
RELEASE_TAG = _load(
    "angmoo_l0_release_tag",
    "scripts/ci/check_release_tag.py",
)
SMOKE = _load(
    "angmoo_l0_container_smoke",
    "scripts/ci/run_l0_container_smoke.py",
)


def _image_document(*, user: str = "10001:10001", environment: list[str] | None = None):
    return {
        "Architecture": "amd64",
        "Os": "linux",
        "Config": {
            "User": user,
            "Env": environment or ["PATH=/usr/local/bin"],
            "Healthcheck": {"Test": ["CMD", "true"]},
            "Labels": {
                "org.opencontainers.image.source": IMAGES.EXPECTED_SOURCE,
                "org.opencontainers.image.revision": "revision-1",
                "org.opencontainers.image.version": "v0.3.0",
                "org.opencontainers.image.licenses": "GPL-3.0-only",
            },
        },
    }


def test_repository_container_release_contract_passes() -> None:
    assert CONTRACT.validate_contract(ROOT) == []


def test_release_tag_matches_both_application_versions() -> None:
    assert RELEASE_TAG.expected_release_tag(ROOT) == "v0.3.0"
    assert RELEASE_TAG.validate_release_tag("v0.3.0", ROOT) == []
    assert "release tag mismatch" in RELEASE_TAG.validate_release_tag(
        "v0.2.1", ROOT
    )[0]


def test_image_contract_accepts_non_root_metadata() -> None:
    assert (
        IMAGES.validate_image_document(
            _image_document(),
            image="angmoo-backend-ci:test",
            expected_revision="revision-1",
            expected_version="v0.3.0",
        )
        == []
    )


def test_image_contract_rejects_root_and_baked_secret() -> None:
    errors = IMAGES.validate_image_document(
        _image_document(user="root", environment=["APP_SECRET=unsafe"]),
        image="angmoo-backend-ci:test",
        expected_revision="revision-1",
        expected_version="v0.3.0",
    )
    assert "runtime image must use a non-root user" in errors[0]
    assert any("runtime secret environment is baked into image" in error for error in errors)


def test_runtime_failure_classifier_is_fail_closed() -> None:
    assert SMOKE.classify_runtime_failure("port is already allocated") == "port_conflict"
    assert (
        SMOKE.classify_runtime_failure("docker: not found")
        == "container_engine_unavailable"
    )
    assert SMOKE.classify_runtime_failure("manifest unknown") == "image_pull_failed"
    assert SMOKE.classify_runtime_failure("unexpected") == "runtime_state_stale"
