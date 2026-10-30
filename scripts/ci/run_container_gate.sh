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
version="$(python -c 'from scripts.ci.check_release_tag import expected_release_tag; print(expected_release_tag().removeprefix("release-v"))')"
tag="${ANGMOO_CI_IMAGE_TAG:-${short_revision}}"
project="${ANGMOO_CI_PROJECT:-angmoo-l0-${short_revision}}"
backend_image="angmoo-backend-ci:${tag}"
frontend_image="angmoo-frontend-ci:${tag}"
postgres_image="angmoo-postgres-ci:${tag}"
report_root="${RUNNER_TEMP:-${TMPDIR:-/tmp}}/angmoo-l0-container-${short_revision}"
mkdir -p "$report_root"

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

docker build --file Dockerfile.postgres --build-arg "VCS_REF=${revision}" --build-arg "VERSION=${version}" --tag "$postgres_image" .

python scripts/ci/check_container_images.py \
  --image "$backend_image" \
  --image "$frontend_image" \
  --image "$postgres_image" \
  --revision "$revision" \
  --version "$version" \
  --report "$report_root/images.json"

python -m scripts.release.scan --image "$backend_image" --image "$frontend_image" --image "$postgres_image" --output "$report_root"

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
