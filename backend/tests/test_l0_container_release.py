from __future__ import annotations

import importlib.util
from pathlib import Path
import sys

import pytest
import yaml


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


@pytest.mark.parametrize("changed", [None, "backend-image", "frontend-image",
                                    "backend-build", "frontend-build", "backend-runtime"])
def test_container_default_versions_reject_drift(tmp_path, changed) -> None:
    version = RELEASE_TAG.expected_release_tag(ROOT).removeprefix("release-v")
    for name in ("Dockerfile.backend", "Dockerfile.frontend", "compose.dev.yml"):
        text = (ROOT / name).read_text(encoding="utf-8")
        if changed in ("backend-image", "frontend-image") and name == "Dockerfile." + changed.split("-")[0]:
            text = text.replace("ARG VERSION=" + version, "ARG VERSION=0.0.0")
        (tmp_path / name).write_text(text, encoding="utf-8")
    if changed and changed.endswith(("-build", "-runtime")):
        path = tmp_path / "compose.dev.yml"
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
        service = changed.split("-")[0]
        if changed.endswith("-build"):
            document["services"][service]["build"]["args"]["VERSION"] = "${ANGMOO_VERSION:-0.0.0-dev}"
        else:
            document["services"][service]["environment"]["ANGMOO_VERSION"] = "${ANGMOO_VERSION:-0.0.0-dev}"
        path.write_text(yaml.safe_dump(document), encoding="utf-8")
    errors = CONTRACT.validate_build_defaults(tmp_path, version)
    if changed is None:
        assert errors == []
    else:
        assert len(errors) == 1 and "default version must match product" in errors[0]


def test_release_tag_matches_both_application_versions() -> None:
    assert RELEASE_TAG.expected_release_tag(ROOT) == "release-v0.1.3"
    assert RELEASE_TAG.validate_release_tag("release-v0.1.3", ROOT) == []
    assert "release tag mismatch" in RELEASE_TAG.validate_release_tag(
        "v0.2.1", ROOT
    )[0]
    assert "release tag mismatch" in RELEASE_TAG.validate_release_tag("release-v0.1.0", ROOT)[0]


@pytest.mark.parametrize("changed", [
    "backend/pyproject.toml", "backend/uv.lock", "backend/app/runtime/product_identity.py",
    "frontend/package.json", "desktop/package.json", "desktop/package-lock.json",
    "desktop/src-tauri/tauri.conf.json", "desktop/src-tauri/Cargo.toml", "desktop/src-tauri/Cargo.lock",
])
def test_mixed_product_or_self_lock_version_is_rejected(tmp_path, changed) -> None:
    paths = (
        "backend/pyproject.toml", "backend/uv.lock", "backend/app/runtime/product_identity.py",
        "frontend/package.json", "desktop/package.json", "desktop/package-lock.json",
        "desktop/src-tauri/tauri.conf.json", "desktop/src-tauri/Cargo.toml", "desktop/src-tauri/Cargo.lock",
    )
    for relative in paths:
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        contents = (ROOT / relative).read_text(encoding="utf-8")
        if relative == changed:
            # Change only the product/self package occurrence, not dependency versions.
            if relative.endswith("uv.lock"):
                old = 'name = "backend"\nversion = "0.1.3"'
            elif relative.endswith("Cargo.lock"):
                old = 'name = "angmoo-desktop"\nversion = "0.1.3"'
            else:
                old = '"0.1.3"'
            assert old in contents
            contents = contents.replace(old, old.replace("0.1.3", "0.1.0"), 1)
        target.write_text(contents, encoding="utf-8")
    errors = RELEASE_TAG.validate_release_tag("release-v0.1.3", tmp_path)
    assert len(errors) == 1 and "product versions must be identical" in errors[0]


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
