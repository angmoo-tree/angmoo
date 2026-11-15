"""Native Docker PostgreSQL 0.1.4 update qualification; no external AI calls.

Uses verified candidate originals, fresh task-owned volumes and an internal
network. Existing installations are never discovered or adopted. Only the two
sanitized records are public; database backups remain local to the runner.
"""
import argparse
import copy
import hashlib
import ipaddress
import json
from pathlib import Path
import platform
import re
import socket
import subprocess
import uuid

from launcher.termux.payload import read_manifest, verify_archive
from scripts.release.candidate import candidate_ref, load
from scripts.release.github import GitHub, successful_images

REPO = Path(__file__).resolve().parents[2]
SERVICES = ("backend", "frontend", "postgres")


def run(*args, input=None, timeout=600):
    result = subprocess.run(list(map(str, args)), input=input, text=True,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout)
    if result.returncode:
        # Do not export service logs, SQL parameters or generated credentials.
        raise RuntimeError(f"qualification_command_failed:{args[0]}:{result.returncode}")
    return result.stdout.strip()


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def validate_inputs(args):
    if not re.fullmatch("[0-9a-f]{40}", args.source):
        raise ValueError("source_invalid")
    for value in (args.candidate_run, args.candidate_attempt, args.candidate_artifact):
        if not re.fullmatch("[1-9][0-9]*", value):
            raise ValueError("producer_identity_invalid")
    native = {"amd64": {"amd64", "x86_64"}, "arm64": {"aarch64", "arm64"}}[args.architecture]
    if platform.machine().lower() not in native:
        raise ValueError("native_host_architecture_required")
    engine_arch = run("docker", "info", "--format", "{{.Architecture}}")
    if engine_arch.lower() not in native:
        raise ValueError("native_docker_architecture_required")


def bind_candidate(args, root):
    github = GitHub()
    github.main_source(args.source)
    producer = github.run(args.candidate_run, args.candidate_attempt,
        workflow="container-candidate.yml", source=args.source)
    artifact = github.artifact(args.candidate_artifact, producer,
        name=f"release-candidate-{args.source}-{args.candidate_attempt}")
    directory = github.download(artifact, root / "artifacts/candidate")
    manifest = read_manifest(directory / "candidate.json")
    successful_images(manifest)
    assert manifest["source_sha"] == args.source and manifest["version"] == "0.1.5"
    selected = {**manifest, "images": [v for v in manifest["images"] if v["platform"] == "linux/" + args.architecture]}
    assert {v["service"] for v in selected["images"]} == set(SERVICES)
    for image in selected["images"]:
        verify_archive(directory / image["archive"], image)
    path = directory / "native.json"
    write(path, selected)
    load(path)
    write(root / "records/source.json", {"source_sha": args.source, "version": "0.1.5",
        "architecture": args.architecture, "candidate_run": args.candidate_run,
        "candidate_attempt": args.candidate_attempt, "candidate_artifact": args.candidate_artifact,
        "artifact_digest": artifact["digest"], "images": {v["service"]: v["manifest_digest"] for v in selected["images"]}})
    return {v["service"]: candidate_ref(v) for v in selected["images"]}


def new_project(root, name, base, images, *, volumes=None, subnet=None):
    document = copy.deepcopy(base)
    document["name"] = name
    document["networks"] = {"default": {"internal": True}}
    if subnet:
        document["networks"]["default"]["ipam"] = {"config": [{"subnet": subnet}]}
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    for service, value in document["services"].items():
        value["image"] = images[service]
        value["pull_policy"] = "never"
        value["restart"] = "no"
        value["labels"] = {"io.angmoo.task": name}
        value.pop("ports", None)
    backend = document["services"]["backend"]
    backend["command"] = ["postgresql-api", "--validation"]
    backend["environment"].pop("ANGMOO_VERSION", None)
    backend["environment"]["ANGMOO_FRONTEND_ORIGIN"] = f"http://127.0.0.1:{port}"
    document["services"]["frontend"]["ports"] = [f"127.0.0.1:{port}:3000"]
    for key in document["volumes"]:
        document["volumes"][key] = ({"external": True, "name": volumes[key]} if volumes else
            {"name": name + "-" + key, "labels": {"io.angmoo.task": name}})
    path = root / (name + ".json")
    write(path, document)
    return path, document, port


def compose(path, *args):
    return run("docker", "compose", "-f", path, *args)


def fixture(path, operation, source):
    compose(path, "cp", str(REPO / "scripts/ci/postgresql_update_fixture.py"), "backend:/tmp/update_fixture.py")
    return json.loads(compose(path, "exec", "-T", "-e", "PYTHONPATH=/app", "backend",
        "python", "/tmp/update_fixture.py", operation, "--source", source))["data"]


def inventory(image, volume):
    code = """import hashlib,json,os,stat
from pathlib import Path
root=Path('/data');rows=[]
for p in sorted(root.rglob('*')):
 s=p.lstat();v=[str(p.relative_to(root)),stat.S_IFMT(s.st_mode),stat.S_IMODE(s.st_mode),s.st_uid,s.st_gid]
 if p.is_symlink():v.append(os.readlink(p))
 elif p.is_file():
  with p.open('rb') as f:v.extend([s.st_size,hashlib.file_digest(f,'sha256').hexdigest()])
 rows.append(v)
print(json.dumps(rows,separators=(',',':')))
"""
    return json.loads(run("docker", "run", "--rm", "--network", "none", "--user", "0:0",
        "--entrypoint", "python", "--mount", f"type=volume,src={volume},dst=/data,readonly", image, "-c", code))


def cold_backup(root, document, helper):
    directory = root / "backups"
    directory.mkdir()
    receipts = {}
    for key, settings in document["volumes"].items():
        rows = inventory(helper, settings["name"])
        run("docker", "run", "--rm", "--network", "none", "--user", "0:0", "--entrypoint", "tar",
            "--mount", f"type=volume,src={settings['name']},dst=/data,readonly",
            "--mount", f"type=bind,src={directory},dst=/backup", helper,
            "-czpf", f"/backup/{key}.tar.gz", "-C", "/data", ".")
        receipts[key] = rows
    write(directory / "inventory.json", receipts)
    return receipts


def qualify(args, root, images):
    # Optional task-only address space for hosts whose default Docker pools are
    # exhausted. Never prune existing networks or change daemon configuration.
    network_range = getattr(args, "network_range", None)
    subnets = [None] * 3
    if network_range:
        block = ipaddress.ip_network(network_range)
        assert block.version == 4 and block.is_private and block.prefixlen == 24
        ids = run("docker", "network", "ls", "-q").splitlines()
        existing = json.loads(run("docker", "network", "inspect", *ids))
        assert not any(block.overlaps(ipaddress.ip_network(v["Subnet"])) for n in existing
            for v in (n.get("IPAM", {}).get("Config") or []) if v.get("Subnet") and ":" not in v["Subnet"])
        subnets = [str(v) for v in list(block.subnets(new_prefix=28))[:3]]
    previous = json.loads((REPO / "docs/releases/0.1.4/p5.json").read_text())
    old = {service: "ghcr.io/angmoo-tree/angmoo-" + service + "@" + previous["images"][service + "/linux/" + args.architecture] for service in SERVICES}
    for service, image in old.items():
        run("docker", "pull", "--platform", "linux/" + args.architecture, image)
        actual = json.loads(run("docker", "image", "inspect", image))[0]
        assert actual["Architecture"] == args.architecture
        assert actual["Config"]["Labels"]["org.opencontainers.image.revision"] == previous["source_sha"]
    original_compose = root / "official-014.yml"
    original_compose.write_text(run("git", "-C", REPO, "show", previous["source_sha"] + ":compose.yml"), encoding="utf-8")
    base = json.loads(run("docker", "compose", "-f", original_compose, "config", "--format", "json"))
    name = "angmoo-pg-update-" + args.architecture + "-" + uuid.uuid4().hex[:10]
    path, document, port = new_project(root, name, base, old, subnet=subnets[0])
    paths = [path]
    report = {"source_sha": args.source, "previous_source_sha": previous["source_sha"],
        "architecture": args.architecture, "provider_transmissions": 0, "synthetic_only": True}
    try:
        compose(path, "up", "-d", "--wait", "--wait-timeout", "300")
        before = fixture(path, "seed", previous["source_sha"])
        report["fixture_counts"] = {k: v["count"] for k, v in before.items() if isinstance(v, dict) and "count" in v}
        compose(path, "stop", "--timeout", "200")
        for service in SERVICES:
            document["services"][service]["image"] = images[service]
        write(path, document)
        compose(path, "up", "-d", "--wait", "--wait-timeout", "300")
        assert fixture(path, "probe", args.source) == before, "update_changed_fixture"
        # An internal network deliberately has no host-published access on
        # some Docker engines. Check the real frontend HTTP server in place;
        # interactive browser verification remains separate release evidence.
        response = compose(path, "exec", "-T", "frontend", "node", "-e",
            "fetch('http://127.0.0.1:3000/').then(r=>{console.log(r.status);if(!r.ok)process.exit(1)})")
        assert response == "200", "frontend_http_failed"
        report["update"] = report["data_preserved"] = report["frontend_http"] = True
        after = fixture(path, "write", args.source)
        assert after["write_marker"] == "updated / 업데이트 🪴"
        compose(path, "stop", "--timeout", "200")
        compose(path, "up", "-d", "--wait", "--wait-timeout", "300")
        assert fixture(path, "probe", args.source) == after, "restart_changed_fixture"
        report["new_write"] = report["restart"] = True
        compose(path, "kill", "-s", "SIGKILL", "backend")
        compose(path, "up", "-d", "--wait", "--wait-timeout", "300")
        assert fixture(path, "probe", args.source) == after, "backend_recovery_changed_fixture"
        report["backend_recovery"] = True
        compose(path, "stop", "--timeout", "200")
        saved = cold_backup(root, document, images["backend"])
        restore_path, restored, _ = new_project(root, name + "-restore", base, images, subnet=subnets[1])
        paths.append(restore_path)
        for key, settings in restored["volumes"].items():
            run("docker", "volume", "create", "--label", "io.angmoo.task=" + name, settings["name"])
            run("docker", "run", "--rm", "--network", "none", "--user", "0:0", "--entrypoint", "tar",
                "--mount", f"type=volume,src={settings['name']},dst=/data",
                "--mount", f"type=bind,src={root / 'backups'},dst=/backup,readonly", images["backend"],
                "-xzpf", f"/backup/{key}.tar.gz", "-C", "/data")
            assert inventory(images["backend"], settings["name"]) == saved[key], "restore_inventory_mismatch"
        compose(restore_path, "up", "-d", "--wait", "--wait-timeout", "300")
        assert fixture(restore_path, "probe", args.source) == after, "restored_data_mismatch"
        report["backup_restore"] = True
        compose(restore_path, "stop", "--timeout", "200")
        fresh_path, _, _ = new_project(root, name + "-fresh", base, images, subnet=subnets[2])
        paths.append(fresh_path)
        compose(fresh_path, "up", "-d", "--wait", "--wait-timeout", "300")
        fixture(fresh_path, "seed", args.source)
        report["fresh_install"] = True
        report["status"] = "PASS"
    finally:
        for owned_path in reversed(paths):
            compose(owned_path, "stop", "--timeout", "200")
        report["test_services_stopped"] = True
        write(root / "records/qualification.json", report)
    print(json.dumps(report))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--architecture", choices=("amd64", "arm64"), required=True)
    for field in ("source", "candidate-run", "candidate-attempt", "candidate-artifact"):
        parser.add_argument("--" + field, required=True)
    parser.add_argument("--work-root", type=Path, required=True)
    parser.add_argument("--network-range", help="Unused private /24, checked against host routes by the operator; never used in hosted CI")
    args = parser.parse_args()
    validate_inputs(args)
    root = args.work_root.resolve()
    root.mkdir(parents=True, exist_ok=False)
    (root / "records").mkdir()
    images = bind_candidate(args, root)
    qualify(args, root, images)


if __name__ == "__main__":
    main()
