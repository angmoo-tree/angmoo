#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$repo_root"

revision="${ANGMOO_SOURCE_SHA:-${GITHUB_SHA:-$(git rev-parse HEAD)}}"
actual_revision="$(git rev-parse HEAD)"
if [[ "$actual_revision" != "$revision" ]]; then
  echo "Container Gate source mismatch: expected=${revision} actual=${actual_revision}" >&2
  exit 1
fi
if [[ -n "$(git status --porcelain --untracked-files=all)" ]]; then
  echo "Container Gate requires a clean exact-source checkout." >&2
  exit 1
fi
short_revision="${revision:0:12}"
version="${ANGMOO_IMAGE_VERSION:-sha-${short_revision}}"
tag="${ANGMOO_CI_IMAGE_TAG:-${short_revision}}"
project="${ANGMOO_CI_PROJECT:-angmoo-l0-${short_revision}}"
backend_image="angmoo-backend-ci:${tag}"
frontend_image="angmoo-frontend-ci:${tag}"
trivy_image="ghcr.io/aquasecurity/trivy:0.74.0@sha256:62b1e65e8869bc4b4c6aa4fa2b21595256c7c2f6018a9d9ad61caf87187c1969"
syft_image="anchore/syft:v1.51.0@sha256:678bfa565b60f747aac0f8e964fe5588a24445b8d0a480e91f6efd70020dfbb0"
report_root="${RUNNER_TEMP:-${TMPDIR:-/tmp}}/angmoo-l0-container-${short_revision}"
trivy_cache_volume="${project}-trivy-cache"
mkdir -p "$report_root"
docker volume create "$trivy_cache_volume" >/dev/null
cleanup_supply_chain() {
  if [[ "${ANGMOO_KEEP_SUPPLY_CHAIN_CACHE:-0}" != "1" ]]; then
    docker volume rm --force "$trivy_cache_volume" >/dev/null 2>&1 || true
  fi
}
trap cleanup_supply_chain EXIT

download_trivy_db() {
  local attempt
  for attempt in 1 2 3; do
    if MSYS_NO_PATHCONV=1 docker run --rm \
      --volume "$trivy_cache_volume:/root/.cache/" \
      "$trivy_image" image --download-db-only --quiet; then
      return 0
    fi
    echo "Trivy DB download failed (attempt ${attempt}/3)." >&2
    sleep 5
  done
  return 1
}

docker build \
  --file Dockerfile.backend \
  --target runtime \
  --build-arg "VCS_REF=${revision}" \
  --build-arg "VERSION=${version}" \
  --tag "$backend_image" \
  .

docker build \
  --file Dockerfile.frontend \
  --target runtime \
  --build-arg "VCS_REF=${revision}" \
  --build-arg "VERSION=${version}" \
  --tag "$frontend_image" \
  .

python scripts/ci/check_container_images.py \
  --image "$backend_image" \
  --image "$frontend_image" \
  --revision "$revision" \
  --version "$version" \
  --report "$report_root/images.json"

download_trivy_db

for image in "$backend_image" "$frontend_image"; do
  safe_name="${image//[:\/]/-}"
  trivy_report="$report_root/${safe_name}.trivy.json"
  MSYS_NO_PATHCONV=1 docker run --rm \
    --volume /var/run/docker.sock:/var/run/docker.sock \
    --volume "$trivy_cache_volume:/root/.cache/" \
    --volume "$repo_root/security/trivy-secret.yaml:/etc/trivy-secret.yaml:ro" \
    "$trivy_image" image \
      --quiet \
      --skip-db-update \
      --exit-code 0 \
      --ignore-unfixed \
      --scanners vuln,secret \
      --secret-config /etc/trivy-secret.yaml \
      --severity HIGH,CRITICAL \
      --format json \
      "$image" >"$trivy_report"
  python - "$trivy_report" "$image" <<'PY'
import json
from pathlib import Path
import sys

path = Path(sys.argv[1])
image = sys.argv[2]
payload = json.loads(path.read_text(encoding="utf-8"))
findings: list[str] = []
results = payload.get("Results") or []
for result in results:
    target = result.get("Target", "unknown")
    for vuln in result.get("Vulnerabilities") or []:
        findings.append(
            f"vulnerability target={target} id={vuln.get('VulnerabilityID')} "
            f"package={vuln.get('PkgName')} installed={vuln.get('InstalledVersion')} "
            f"fixed={vuln.get('FixedVersion')}"
        )
    for secret in result.get("Secrets") or []:
        findings.append(
            f"secret target={target} rule={secret.get('RuleID')} "
            f"category={secret.get('Category')}"
        )
if findings:
    print(f"Trivy Gate failed: image={image} findings={len(findings)}", file=sys.stderr)
    for finding in findings:
        print(f"- {finding}", file=sys.stderr)
    raise SystemExit(1)
print(f"Trivy passed: image={image} targets={len(results)} findings=0")
PY
  MSYS_NO_PATHCONV=1 docker run --rm \
    --volume /var/run/docker.sock:/var/run/docker.sock \
    "$syft_image" "docker:${image}" --output spdx-json \
    >"$report_root/${safe_name}.spdx.json"
  python - "$report_root/${safe_name}.spdx.json" <<'PY'
import json
from pathlib import Path
import sys

path = Path(sys.argv[1])
payload = json.loads(path.read_text(encoding="utf-8"))
packages = payload.get("packages")
if payload.get("spdxVersion") != "SPDX-2.3" or not isinstance(packages, list) or not packages:
    raise SystemExit(f"invalid SBOM: {path}")
print(f"SBOM passed: file={path.name} packages={len(packages)}")
PY
done

ANGMOO_CI_IMAGE_TAG="$tag" python scripts/ci/run_l0_container_smoke.py \
  --tag "$tag" \
  --project "$project"

ANGMOO_CI_IMAGE_TAG="$tag" \
ANGMOO_VCS_REF="$revision" \
ANGMOO_VERSION="$version" \
  python scripts/ci/run_l0_container_smoke.py \
    --tag "$tag" \
    --project "${project}-dev" \
    --development

echo "Container Gate passed: revision=${revision} version=${version} production=true contributor_dev=true"
