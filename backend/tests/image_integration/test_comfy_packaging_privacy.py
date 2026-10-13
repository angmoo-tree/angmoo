"""Stage actual public assets; reject synthetic runtime/key sentinels."""
from pathlib import Path
import importlib.util
import shutil
import pytest
ROOT=Path(__file__).resolve().parents[3]


@pytest.mark.parametrize("private",["secrets/app-secret","secrets/app-secret.tmp-test","canonical/angmoo.sqlite3",".env","backups/release-candidate-backup.json",
    "runtime/sidecar-runtime.json","canonical/graph/database.lbug","secrets/explicit-migration.txt","private-image-assets/received-results/one.asset","backups/one.dat"])
def test_metadata_refuses_runtime_and_secret_files_before_writing_reports(tmp_path,private):
    spec=importlib.util.spec_from_file_location("metadata",ROOT/"scripts/ci/build_desktop_release_metadata.py")
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    (tmp_path/"Angmoo-0.3.0.exe").write_bytes(b"synthetic installer")
    (tmp_path/"Angmoo-0.3.0.msi").write_bytes(b"synthetic installer")
    sentinel=tmp_path/private;sentinel.parent.mkdir(parents=True,exist_ok=True);sentinel.write_bytes(b"synthetic-private-sentinel")
    with pytest.raises(SystemExit,match="Private migration artifact refused"):
        module._artifact_files(tmp_path,version="0.3.0")


def test_actual_samples_and_guides_are_deterministic_public_staging_inputs(tmp_path):
    for relative in ("backend/app/domains/media/samples/comfy-api-text.json","backend/app/domains/media/samples/comfy-api-reference.json","docs/agent_guide.md","docs/agent_guide.en.md"):
        target=tmp_path/relative;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(ROOT/relative,target)
        assert target.read_bytes()==(ROOT/relative).read_bytes()
        assert b"synthetic-private-sentinel" not in target.read_bytes()
    assert not list(tmp_path.rglob("app-secret*"))
