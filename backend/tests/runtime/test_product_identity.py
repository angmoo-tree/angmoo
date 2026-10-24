"""Reject legacy image-selection values before touching a user's data root."""
from pathlib import Path

import pytest

from app.runtime.product_identity import runtime_identity, validate_product_version


@pytest.mark.parametrize("version", ["0.1.2", "0.1.2-dev", "0.1.2-dev-a123456"])
def test_product_versions_are_separate_from_tags(monkeypatch, version):
    monkeypatch.setenv("ANGMOO_VERSION", version)
    assert validate_product_version() == version


@pytest.mark.parametrize("version", ["0.1.0", "0.1.1", "0.1.3", "0.1.2-dev-WRONG", "0.1.2-extra", "v0.3.0", "0.3.0", "release-v0.1.2", "", "sha-a123456"])
def test_bad_version_cannot_create_or_migrate_data(tmp_path, monkeypatch, version):
    from app.runtime.contributor_backend import create_contributor_runtime_app
    monkeypatch.setenv("ANGMOO_VERSION", version)
    root = tmp_path / "untouched"
    with pytest.raises(ValueError, match="product_version_mismatch"):
        create_contributor_runtime_app(data_root=root, frontend_origin="http://127.0.0.1:3000")
    assert not root.exists()


def test_identity_never_returns_untrusted_environment_text(monkeypatch):
    monkeypatch.setenv("ANGMOO_SOURCE_SHA", "credential-like-value")
    monkeypatch.setenv("ANGMOO_LAUNCH_ID", "wrong")
    assert runtime_identity() == {"version": "0.1.2", "source_sha": "unknown", "launch_id": ""}
