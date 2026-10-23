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
    for relative in ("backend/app/domains/media/samples/comfy-api-text.json","backend/app/domains/media/samples/comfy-api-reference.json","docs/agent_guide.md","docs/agent_guide.ko.md"):
        target=tmp_path/relative;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(ROOT/relative,target)
        assert target.read_bytes()==(ROOT/relative).read_bytes()
        assert b"synthetic-private-sentinel" not in target.read_bytes()
    assert not list(tmp_path.rglob("app-secret*"))


def test_docker_frontend_copies_both_current_guide_sources(tmp_path):
    """Evaluate the explicit source COPY inputs without building an image."""
    instructions = [line.split() for line in (ROOT / "Dockerfile.frontend").read_text(encoding="utf-8").splitlines()
                    if line.startswith("COPY ") and line.split()[-1] == "/docs/"]
    assert len(instructions) == 2  # development and production build stages
    for index, fields in enumerate(instructions):
        sources = [part for part in fields[1:-1] if not part.startswith("--")]
        assert set(sources) == {"docs/agent_guide.md", "docs/agent_guide.ko.md"}
        stage = tmp_path / str(index)
        stage.mkdir()
        for source in sources:
            shutil.copyfile(ROOT / source, stage / Path(source).name)
            assert (stage / Path(source).name).read_bytes() == (ROOT / source).read_bytes()
