# Release candidate import compatibility / 출시 후보 가져오기 호환성

The candidate loader selects Docker's supported image transport before loading.
Containerd stores consume the verified OCI archive directly. Classic stores use
the pinned Skopeo converter to create a temporary Docker archive, then load it
through the host Docker CLI. Conversion has no network or Docker socket access.
The original OCI archive, provenance and SBOM remain the promotion inputs.

후보 로더는 Docker 이미지 저장소에 맞는 가져오기 방식을 선택한다.
containerd 저장소는 검증된 OCI를 직접 읽고, 기존 저장소는 고정된 Skopeo로
임시 Docker archive를 만든 뒤 호스트 Docker CLI로 읽는다. 변환 컨테이너는
네트워크나 Docker 소켓에 접근하지 않는다. 공식 승격에 사용할 원본 OCI와
provenance·SBOM은 그대로 보존한다.

## Identity and failure contract / 동일성·실패 계약

- Verify source, archive hash and OCI payload before importing.
- After importing, verify architecture, config digest and every rootfs diff ID.
- Use platform selectors only when both CLI and daemon support API 1.49.
  Older engines still undergo the same identity checks on the architecture-specific tag.
- Any conversion/load/storage failure stops the operation. Do not switch transports
  after an arbitrary failure or write a success receipt.
- The temporary transport file needs space beside the candidate and is removed
  after import. Only one image is converted at a time.

가져오기 전 원본 출처와 해시를, 가져온 뒤 CPU·설정 해시·모든 레이어를 검사한다.
CLI와 daemon의 API가 모두 1.49 이상일 때만 플랫폼 선택 옵션을 사용한다.
이전 엔진에서도 CPU별 고유 태그에 같은 내용 검증을 수행한다. 변환·저장 공간·로드
오류는 실패로 남긴다. 임시 변환 파일은 후보 옆의 공간을 사용하고 이미지별로 제거한다.

## 2026-10-18 regression evidence / 회귀 검증

The first P3 [Container Candidate run](https://github.com/angmoo-tree/angmoo/actions/runs/39089560507)
at source `d39d4327ffd8598a9d37e12e65c6fb44c1f85176` built both service pairs but
failed loading them on Docker 28.0.4/classic overlay2. Its OCI loader error named
`docker-import-*/blobs/json`; the old stderr allowlist did not recognize it.
Docker 28 also lacks `image inspect --platform` (API 1.49).

첫 P3 실행은 두 플랫폼의 이미지 빌드 후 Docker 28의 기존 저장소로 가져오는
단계에서 실패했다. 일시적인 다운로드 장애로 분류하거나 같은 소스를 반복 재시도하지
않고 저장소·API 호환성을 수정했다.

- Focused tests: `python -m pytest -q tests/test_release_candidate.py
  tests/test_l0_container_release.py tests/test_release_gitleaks_provenance.py`
  from `backend`: 30 passed. Import failures and altered platform/rootfs/config
  remain rejected; publication verify still performs zero remote writes.
- Including `tests/test_t2_ci_policy.py` and
  `tests/test_refactor_backend_checkpoint.py`: 106 passed (8.43 seconds).
- Real isolated Docker 28.0.4/vfs reproduction: direct OCI load failed, then the
  revised loader imported the existing frontend amd64 archive successfully.
  Config and runtime image ID both matched
  `sha256:cc14aae3eff8d60af6356542f610abd26b9d256911d33fef8137c6efe127e890`;
  all 12 rootfs diff IDs matched. Original archive SHA-256 remained
  `0a3f0dee4fc70301505bd02b92f244ee04f700e398f3063dd9bb6cc9eda09b18`.
- That reproduction uses an older source (`aa4a9e9b44ff78005cecf6fea78d43360064f799`)
  only to test import compatibility. It is not the new P3 release candidate.
  Produce and validate both architectures again from the corrected main source.
- No application dependency, SQLite behavior, local encryption, Windows installer
  contract, registry tag or GitHub Release is changed by this fix.

실제 격리 Docker 28에서 이전 후보 파일을 사용한 호환성 검증이며, 이전 파일을
새 출시 후보로 재표기하지 않는다. 수정이 병합된 main에서 두 플랫폼과 Windows EXE를
같은 소스로 다시 준비한다. 공식 태그·이미지·Release 공개는 P6에 남긴다.
