# Termux 공통 구현의 로컬 통합 검증

## 통합 결과와 범위

2026-10-21, 로컬 `main`의 `6927ce4b86aa577360e23a4a572cf9fa08ff3526`에서 `feat/termux-release-common`을 만들었다. 작업 폴더는 `E:/angmoo-local/termux-release-common`이다. 공통 구현 9개를 각각 `cherry-pick -x`하고 원래 작업 폴더에 남아 있던 CI 테스트 발견 범위 변경을 별도 커밋으로 통합했다. 시험용 시간 변경 3개는 가져오지 않았다.

제품 동작 변경은 아래 공통 커밋의 패치와 동일하다. 통합 검증에서 추가 모듈 3개와 변경된 import 4곳이 기존 아키텍처 목록에 빠진 것을 발견해 `security/architecture_import_baseline.json`을 실제 코드에서 다시 생성했다. 이 목록 갱신과 본 검증 문서는 통합 정합성 기록이며, 시간 계약이나 제품 동작을 추가로 바꾸지 않는다.

push, PR 생성, GitHub Actions 실행, main 병합, 이미지 빌드·교체, 서비스 재기동은 수행하지 않았다. 실제 Android 기기 검증, 새 릴리스 후보 검증, 실사용 AI 호출도 이번 결과에 포함하지 않는다.

## 가져온 공통 커밋

| 원본 커밋 | 새 브랜치 커밋 | 내용 |
|---|---|---|
| `3d435876` | `daa20e0c` | 간편 설치기, 릴리스 패키징, 한국어·영어 설치 안내 |
| `0120c704` | `96a9a1c4` | 용량이 제한된 서비스 로그 보존·조회, 실패 기록, 작업자 준비 계측 |
| `7fd609f7` | `618b1bca` | 작업자 준비 요약의 콘솔 로깅 연결 |
| `93fdc017` | `e5694a62` | 로그 누락 표시와 준비 실패 소요 시간 |
| `c27c10e5` | `bb856d5d` | 실행 세션 로그를 불변 시작 시각으로 정렬 |
| `ba226fb6` | `7e66e907` | Android Python의 플랫폼 판별 |
| `0acd7981` | `727c8dff` | 도구 import 전후 비공개 파일 권한 유지 |
| `c50b7848` | `d1eec10d` | 기존 서비스 기동 예산을 명시적 상수·진단으로 표현 |
| `5bffc643` | `d2cd962a` | heartbeat 기한 초과 분류와 실제 작업 정리 후 스케줄러 복구 |

9개 모두 `git patch-id --stable`로 원본과 새 커밋의 패치 동일성을 확인했다. `-x` 메시지에 원본 전체 SHA를 보존했다.

CI 설정은 `1fc3eb4f`에 기록했다. `.github/workflows/ci.yml`의 로컬 unittest 발견 패턴만 `test_host.py`에서 `'test_*.py'`로 바꿔 설치기·로그 테스트도 포함한다. CI 파일 수정과 CI 실행은 구별하며, 원격 CI는 실행하지 않았다.

## 제외한 시험 변경과 정상 시간 계약

| 제외 커밋 | 시험 변경 |
|---|---|
| `9da6b012` | 작업자 개별·라운드 준비 60초·130초 |
| `80db718c` | backend 기동 600초·상위 시작 대기 790초 |
| `639eaf80` | 작업자 180초·420초, Chat 검색 600초·요청 1,200초 등 연결 예산 확대와 프론트엔드 시험 연결 설정 |

제외한 커밋이 새 브랜치의 조상이 아님을 확인했다. 시험 전용 파일은 main과 동일하며, 새 trial 모듈과 frontend 직접 의존성 변경도 포함하지 않는다. frontend 전체 Git tree는 기준 main과 같다.

| 계약 | 통합 브랜치 값 |
|---|---:|
| 작업자 개별 준비 | 30초 |
| 작업자 준비 라운드 | 60초 |
| backend 준비 | 180초 |
| frontend 준비 | 180초 |
| 상위 시작 대기 | 370초 |
| Chat 기억 검색 | 최대 20초 |
| SNS 기억 검색 | 최대 30초 |
| Chat 요청 전체 | 180초 |
| Chat 실행권 | 기본 180초, 설정 상한 300초 |

Chat 선택·응답 생성·임베딩·최종 재검증 및 다른 시험 전용 경로도 기준 main과 파일 단위로 일치한다. timeout 확대가 공통 구현에 섞이지 않았다는 근거는 단순 커밋 제외뿐 아니라 이 파일·상수 대조를 함께 사용한다.

## 관련 범위의 로컬 검증

백엔드는 기존 Python 3.13.12 의존성 환경을 이용하되 새 작업 폴더를 cwd로 사용했다. `ANGMOO_DENY_EXTERNAL_NETWORK=1`로 테스트의 외부 네트워크 차단 fixture를 활성화했다. 임시 SQLite와 모의 작업을 사용하며 실제 사용자 DB를 연결하지 않았다.

| 검증 | 결과 |
|---|---|
| heartbeat deadline·복구·singleton, SQLite 경합·복구, 로그, 검색 작업자 재사용·취소, 릴리스 패키징 9개 테스트 파일 | **109 passed**, 177.61초 |
| 변경된 import 목록의 최신성·결정성 회귀 | **2 passed**, 5.70초 |
| Termux 설치기·프로세스 수명·로그 테스트를 실제 Linux에서 발견·실행 | **32 passed**, 3.060초, skip 없음 |
| 갱신한 architecture inventory 검사 | 통과: 모듈 1,597개, 내부 의존성 6,929개 |
| architecture boundary 검사 | 통과, legacy exact exception 0개 |
| container release contract 정적 검사 | 통과 |
| `sh -n launcher/termux/setup.sh` | 통과 |
| 변경 diff의 공백 오류 검사 | 통과 |

백엔드 109개 검증에는 Starlette/httpx와 AnyIO 기존 사용 중단 예정 경고 2개가 있었다. Linux ZIP 공격 입력 회귀에서 중복 파일 이름 경고 1개는 의도한 중복 멤버 입력에서 발생했다.

Linux 검증은 이미 존재하던 `angmoo-proot-harness:20261018`의 amd64 Python 환경을 이용했다. 이미지 ID는 `sha256:69a9c8f0a60b541635722bc6a7f65cb97dca8181581bf40c68f7c23c815050b8`이다. 네트워크 차단, 소스 읽기 전용 mount, 전용 tmpfs, 일회성 컨테이너로 실행했으며 제품 서버나 기존 볼륨을 시작하지 않았다. 패키징 의존성 `proot-distro==5.10.0`이 설치된 환경이다. 실제 PRoot 이미지 실행과 Android 실기기 설치 성공을 의미하지 않는다.

최초 Linux 시도는 일반 backend 이미지에 `proot-distro`가 없고 임시 파일 실행이 차단돼 실패했다. 테스트나 제품 코드를 완화하지 않고, 준비된 host-test 이미지와 실행 가능한 전용 임시 디렉터리로 검증 환경을 바로잡아 동일한 32개 테스트를 다시 통과시켰다. 최초 실패 로그도 보존했다.

전체 백엔드·전체 프론트엔드 검증은 수행하지 않았다. frontend는 코드·패키지·잠금 파일의 main 동일성을 확인했다. CI workflow를 실행하거나 이를 CI 통과로 판정하지 않는다.

### 재실행 명령

새 작업 폴더의 backend에서 설치된 Python 3.13 의존성 환경으로 실행한다.

```powershell
$env:ANGMOO_DENY_EXTERNAL_NETWORK = '1'
python -m pytest -q tests/test_scheduler_heartbeat_deadline.py tests/test_creator_scheduler_recovery.py tests/routines/test_scheduler_singleton.py tests/test_l3_er2_sqlite_concurrency.py tests/runtime/test_sqlite_recovery_contracts.py tests/logging/test_runtime_logging.py tests/memory/test_search_worker_pool.py tests/memory/test_search_worker_transport_cancel.py tests/test_release_candidate.py
python -m pytest -q tests/test_t2_architecture_inventory.py
```

저장소 루트에서 실행하는 정적 검사:

```powershell
python scripts/ci/generate_architecture_inventory.py --check
python scripts/ci/check_architecture_boundaries.py
python scripts/ci/check_container_release_contract.py
git diff --check main...HEAD
```

Linux에서 실제 프로세스·pipe·flock을 검증하는 명령:

```sh
python -m unittest discover -s launcher/termux -p 'test_*.py' -v
sh -n launcher/termux/setup.sh
```

Linux 테스트 환경에는 `launcher/termux/requirements.txt`의 고정 의존성과 POSIX shell이 필요하며, 임시 디렉터리에서 테스트용 실행 파일을 실행할 수 있어야 한다. 정확한 이번 실행 인자·환경·종료 코드는 아래 증거 폴더의 각 검사 JSON에 저장했다.

## 보존 및 후속 작업 경계

- `feat/termux-simple-install` 원래 작업 폴더의 미커밋 8개 파일은 그대로 두었다. 변경 전 원본 복사본·patch·SHA-256을 저장했고, 통합 후 동일성을 대조한다. 그중 CI 이외 7개는 첫 공통 커밋에 이미 반영된 내용이므로 최신 통합 파일 위에 다시 덮어쓰지 않았다.
- `test/termux-scheduler-recovery-power`와 기존 시험 브랜치·커밋, 로컬 main은 유지한다. 원격 main 확인을 위한 fetch도 실행하지 않았으며 이번 기준은 현재 로컬 main이다.
- 기존 Android/Termux 서버, 사용자 데이터, 로그, 전원 설정에는 접근·변경하지 않았다. 새 브랜치의 구현이 현재 실행 중인 시험 이미지나 공개 릴리스에 자동 반영됐다고 판단하지 않는다.
- 기본 로그 비용 개선 및 일시적 상세 로그 선택 옵션은 별도 계획이다. 이번 통합으로 구현됐다고 표현하지 않는다. `finish_tick` 후속 개선이나 404 상태 계약도 이 9개 커밋의 구현 범위를 넘어선다.
- 함께 가져온 `termux-scheduler-heartbeat-deadline-local-20261021.md`는 기존 시험 브랜치에서의 수정·검증 기록이다. 그 문서의 확대된 시험 예산·기준 SHA를 이번 통합 브랜치의 현재 계약으로 사용하지 않는다.

증거 폴더: `D:/project_code/angmoo-workspace/.task-output/termux-release-common-20261021/run-01`

주요 파일은 `preservation-before.json`, `integration-audit.json`, `architecture-diff.json`, `backend-scoped.json/.log`, `architecture-regression.json/.log`, `launcher-linux-configured.json/.log`, `architecture-boundaries.json/.log`, `release-contract.json/.log`이다. 최종 브랜치·HEAD·보존 검사 결과는 `integration-audit.json`에 기록한다.
