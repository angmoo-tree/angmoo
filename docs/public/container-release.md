# Container image release

Angmoo publishes user-facing runtime images only from an owner-approved
semantic release tag in the canonical `angmoo-tree/angmoo` repository. Pull
requests and ordinary `main` pushes build and scan images but never publish a
stable GHCR tag.

## Published images

An approved `vX.Y.Z` tag publishes the currently verified `linux/amd64`
images:

```text
ghcr.io/angmoo-tree/angmoo-backend:vX.Y.Z
ghcr.io/angmoo-tree/angmoo-frontend:vX.Y.Z
```

The workflow also publishes immutable `sha-<full source commit>` tags. The
release summary records both registry digests. `latest` is intentionally not a
Quickstart or compatibility contract.

## Release Gate

Before creating a tag, the owner verifies that:

1. the release commit is on `main` and all required checks pass;
2. `backend/pyproject.toml` and `frontend/package.json` contain the same
   version;
3. the default image tag in `compose.yml`, the Dockerfile image metadata,
   contributor overlay version, and Windows launcher default all match that
   version;
4. the tagged images satisfy every worker readiness and lifecycle contract in
   the same source revision, including scheduler and projector health markers;
5. the tag is exactly `v<version>`;
6. no open code, dependency, or secret alert blocks the release; and
7. the Windows clean-clone user scenario is ready to run after publication.

When a source change strengthens a runtime health or lifecycle contract, do
not point the default Quickstart at an older image that predates that contract.
Merge the coordinated version change first, publish the matching semantic tag,
and perform the anonymous Windows clean-clone check against those new images.

The tag-only `Release Images` workflow then:

- rebuilds both runtime images from the tagged source;
- rejects root runtime users, missing healthchecks, label drift, and secret
  markers in environment or image history;
- scans fixable high and critical vulnerabilities and image secrets with a
  digest-pinned Trivy image;
- generates and validates SPDX 2.3 SBOMs with a digest-pinned Syft image;
- runs the isolated six-service full-stack, reduced-mode, repeat-start,
  stop/restart persistence, and port-conflict fixtures;
- publishes semantic and exact source-SHA tags to GHCR;
- attaches BuildKit SBOM/provenance and GitHub build provenance to each image.

Only the release job receives `packages: write`, `id-token: write`, and
`attestations: write`. It uses the repository-scoped `GITHUB_TOKEN`; no PAT or
repository secret is required.

## First publication visibility Gate

GitHub creates a new organization container package as private by default.
After the first successful publication, an organization owner must open each
package settings page and change `angmoo-backend` and `angmoo-frontend` to
**Public**. This is a one-way public-release decision and is not performed by a
pull request.

After the visibility change, verify an anonymous pull in a signed-out or clean
environment:

```powershell
docker logout ghcr.io
docker pull ghcr.io/angmoo-tree/angmoo-backend:v0.3.0
docker pull ghcr.io/angmoo-tree/angmoo-frontend:v0.3.0
```

Record the tag, source commit, workflow URL, both image digests, anonymous-pull
result, and Windows clean-clone result without recording credentials or local
user data. L0 is not final PASS until those checks and the user Quickstart
judgment pass.
