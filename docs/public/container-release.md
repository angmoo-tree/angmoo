# Container candidates and official release

Product metadata is `0.1.0`. The first official Git/image tag is
`release-v0.1.0`. This implementation prepares publication; it does not claim
that tag, GHCR images or a GitHub Release already exists.

The two repositories remain `ghcr.io/angmoo-tree/angmoo-backend` and
`ghcr.io/angmoo-tree/angmoo-frontend`. Each official tag will contain exactly
`linux/amd64` and `linux/arm64` execution manifests plus their original
BuildKit provenance/SBOM attachments. Both services share one source SHA.
Backend and frontend use their own pinned Debian bases and frozen dependency
locks; platform-native wheels/binaries differ without selecting different app
library versions. No Linux desktop installer is introduced.

## P1/P2 implementation; P3/P5 candidates; P6 publication

1. On the selected main SHA, manually run **Container Candidate**. It builds
   backend/frontend once per architecture on native hosted runners, exports OCI
   archives, verifies hashes/config/rootfs, executes real native checks, scans
   vulnerabilities/secrets, generates SPDX, and tests the service pair and restart.
   The workflow has read-only permissions and never creates a tag or pushes GHCR.
2. Keep the complete `release-candidate-<sha>-<attempt>` artifact and the four
   archives. Record exact run/attempt/artifact IDs before its 14-day expiration.
   Local equivalents are `python -m scripts.release.candidate build/load/combine`
   and `python -m scripts.release.validate`. Use a docker-container buildx
   builder if the default engine cannot export OCI. Do not rebuild to work around
   an import failure; compare config and rootfs identities after any conversion.
3. Run the existing Windows Installer with **full** scope for the same SHA.
   Its final `windows-release-validation-<sha>-<attempt>` receipt binds successful
   clean install, recovery and all supported predecessor partitions to the actual
   tested EXE hash and build artifact ID. The build artifact alone is insufficient.
4. Complete P5, retain the exact files, and record the reviewed P5 report/KO/EN
   notes as described in [Release publishing](../operations/release-publishing.md).
5. **P6 only:** create the already-reviewed official tag on that source. Release
   Images consumes the successful main candidate and uses pinned Skopeo to copy
   its original compressed blobs with `--preserve-digests`. It does not rebuild.
   Each service index also receives a GitHub attestation. Record both registry
   indexes and the publication receipt; a partial pair is not a completed release.
6. Run Release Publish in `verify`, then the explicitly requested `draft` or
   `publish` mode. It verifies Windows and image evidence and uploads only the
   allowed original files, not an Actions ZIP or private test artifacts.

Existing official tags with different digests fail. Identical completed content
is reusable. No tag replacement, asset clobber, deletion, `latest` movement or
old development-package cleanup occurs automatically. Registry package visibility
must permit intended user downloads; do not infer public accessibility from a
successful authenticated push.

## User configuration after P6

`ANGMOO_IMAGE_TAG=release-v0.1.0` selects the image pair.
`ANGMOO_VERSION=0.1.0` is the product version; remove old
`ANGMOO_VERSION=v0.3.0` overrides. Startup rejects incompatible product identity
before data preparation/migration. It does not erase old data to make it pass.

```sh
docker compose up -d --wait
```

The browser is at http://127.0.0.1:3000. Backend remains internal to Compose.
The default user runtime has two services, with backend owning SQLite/LadybugDB
and frontend acting as the HTTP transport. New data and encryption secrets are
stored in the named data volume, not image layers. See [Termux reuse](termux.en.md)
for the same ARM64 payloads on a PRoot host.

## 한국어 요약

제품 버전은 `0.1.0`, 공식 Git·이미지 태그는 `release-v0.1.0`입니다.
후보 생성은 읽기 전용 수동 workflow이며 공식 공개 완료를 의미하지 않습니다.
backend·frontend 각각 amd64·ARM64 후보를 한 번 빌드한 뒤 같은 바이트로 실제
네이티브 실행·보안·SBOM·기동·재시작을 확인합니다. Windows는 빌드 성공 외에
같은 EXE로 전체 설치 검증을 마친 최종 자료가 필요합니다.

P6에서만 공식 태그를 만들고 검증한 OCI 원본을 GHCR로 승격한 다음 Release를
공개합니다. `verify`는 원격 쓰기가 없으며, 다른 내용의 기존 태그·파일을
덮어쓰거나 옛 개발 배포를 삭제하지 않습니다. 14일 artifact 만료 전에 후보를
확보하세요. Termux의 실제 Android 확인은 Linux/QEMU 결과와 별도로 기록합니다.
