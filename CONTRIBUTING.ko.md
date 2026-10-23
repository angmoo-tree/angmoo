# Angmoo 기여 안내

[English](CONTRIBUTING.md) | 한국어

Angmoo는 로컬 AI 캐릭터 SNS입니다. 기여할 때는 기존 사용자 데이터, World 경계,
지원 실행 환경의 동작을 보존합니다. 배포된 앱의 설치는 [README](README.ko.md)를 참고하세요.

## 코드 변경 전

[기여 지도](docs/public/contribution-map.md)에서 기능의 소유자를 찾습니다.
기능 추가와 구조 변경은 Issue로 범위를 논의하고, 작은 문서·오타 수정은 바로 PR을
만들 수 있습니다. Issue와 PR은 한국어 또는 영어로 작성할 수 있습니다.

백엔드는 [ARCHITECTURE](backend/ARCHITECTURE.md), 프론트엔드는
[ARCHITECTURE](frontend/ARCHITECTURE.md)·[DESIGN](frontend/DESIGN.md)와 해당
디렉터리 지침을 따릅니다. 버그 수정에 무관한 의존성·스키마·스타일·소유권 변경을 섞지 않습니다.

## 기여 환경 실행

기여용 백엔드는 `CONTRIBUTOR_EMBEDDED` 프로필을 사용합니다. SQLite가 유일한
원본 저장소이며 FTS5와 LadybugDB는 다시 만들 수 있는 파생 저장소입니다.

Git, Linux 엔진을 사용하는 Docker, Compose 2.22.0 이상을 준비하고 저장소 루트에서 실행합니다.

```sh
docker compose -f compose.yml -f compose.dev.yml up --watch
```

http://127.0.0.1:3000 을 엽니다. 개발 프론트엔드와 embedded 백엔드가 실행되며
SQLite·검색·그래프 투영은 백엔드의 로컬 구성 요소입니다. PostgreSQL·Neo4j 서버는 필요하지 않습니다.

```sh
docker compose -f compose.yml -f compose.dev.yml logs --tail 100 backend frontend
docker compose -f compose.yml -f compose.dev.yml down
```

종료해도 기여 환경의 데이터 볼륨은 유지됩니다. 보존할 데이터가 있으면 `--volumes`를
추가하지 않습니다. 설치 앱의 사용자 데이터를 개발·테스트에 연결하지 않습니다.
호스트 도구와 격리 시험은 [개발 안내](docs/public/development.md)를 참고하세요.

실제 native 창을 변경할 때만 [Windows Host Tauri dev](docs/public/windows-host-tauri-dev.md)를
사용합니다. 기여 Docker와 별도 WebView 프로필을 사용하며 설치 앱의 백엔드를 하나 더 띄우지 않습니다.

## 코드 소유권

- 백엔드 도메인은 HTTP·service·model·schema·저장 역할을 소유합니다. 허용된 진입점의
  실제 소유 파일을 사용합니다. 여러 도메인의 협력은 runtime에서 조립하며, 도메인이
  runtime을 역으로 가져오거나 다른 업무의 저장 규칙을 우회하지 않습니다.
- 호출자의 Session과 transaction 소유권을 유지합니다. AI 호출·대기·재시도 동안 SQLite
  쓰기 transaction을 유지하지 않습니다. 늦은 결과 적용 전에 owner·scope·원본 revision·lease를 재검증합니다.
- 프론트엔드 기능은 API·DTO·component·수명을 소유합니다. 기능 사이 연결은 composition의
  props·callback·slot으로 처리합니다. 실제 역할 파일을 import하며 없어진 `public.ts`·`shared`를 복원하지 않습니다.
- Next와 static/Tauri는 같은 기능 컴포넌트를 사용합니다. 공용 UI와 통신 코드에 제품 권한이나 업무 판단을 넣지 않습니다.
- 사용자에게 보이는 웹 문구는 영어·한국어 번역 목록에 함께 반영합니다. Termux의 고정 터미널 안내는
  영어이며, 공개 Termux 설치 문서는 두 언어를 제공합니다.
- 새 자산·의존성에는 출처·라이선스·고지가 필요합니다. [BRANDING](BRANDING.md)을 따르고 기존 시맨틱 토큰과 공용 UI 요소를 사용합니다.
  회귀를 숨기려고 색상이나 스냅샷 기준을 완화하지 않습니다.

## 변경 범위 검증

수정한 기능, 호출자, 실패 경계를 검증하는 테스트부터 실행합니다. 합성 사용자와 fake provider를
사용합니다. 개인 DB·운영 키·비공개 패키지·유료 provider 요청을 CI에 넣지 않습니다.

| 변경 | 선택할 로컬 검증 |
| --- | --- |
| 백엔드 service·조회 | 해당 domain/runtime 회귀, scope·권한·실패 경계 |
| transaction·lease·migration | 경합·취소·재개·보존과 지원 업그레이드 |
| 프론트엔드 상호작용 | 타입·lint와 관련 브라우저 시나리오, 공통 소비자의 Next/static 경로 |
| 공용 프론트엔드·빌드 | 두 빌드와 영향을 받는 공용 소비자 |
| native·설치기 | 해당 계약, 격리 설치·복구, 직접 사용자 확인 |
| 문서 | 경로·명령·한영 일치·실제 구현과의 일치 |

원격 검사의 선택과 필수 결과는 [CI 안내](docs/operations/ci-validation.md)를 따릅니다.
로컬 범위 검증이 더 넓은 CI를 면제하지 않습니다. 영향이 불확실하면 범위를 넓히되,
문서 변경만을 이유로 전체 백엔드·프론트엔드 검증을 일괄 실행하지 않습니다.

구조 변경 시 저장소 루트에서 필요한 검사를 선택합니다.

```sh
uv run --project backend python scripts/ci/generate_architecture_inventory.py --check
uv run --project backend python scripts/ci/check_architecture_boundaries.py
uv run --project backend python scripts/ci/check_frontend_architecture_boundaries.py
uv run --project backend python scripts/ci/check_frontend_design_contract.py --check
```

의존성 목록을 다시 생성하면 현재 코드의 관계가 기록됩니다. 이 작업이 새 의존 관계를 허용하는 것은 아닙니다. 과거 전환 근거는 Git에 보존하고,
일상 검증은 현재 동작과 지원 데이터 업그레이드를 보호합니다.

## PR 제출

사람의 기여에는 Developer Certificate of Origin 1.1(DCO 1.1)이 적용됩니다.
`git commit -s`로 자신의 `Signed-off-by` 문구를 추가합니다. embedded 데이터
migration 계약을 변경하면 `embedded-data-migration` 라벨을 적용합니다.

1. fork 또는 범위가 명확한 브랜치에서 작업하고 무관한 변경을 보존합니다.
2. `git commit -s`로 DCO 1.1의 `Signed-off-by` 문구를 포함합니다.
3. 문제, 변경 후 동작, 관련 계약과 실행한 검증을 설명합니다.
4. 관련 Issue와 아직 확인하지 못한 항목을 기록합니다.
5. UI는 화면·출처·언어·경로·의도한 시각 차이를, 데이터는 migration·보존·복구를 설명합니다.
6. 해당 검사와 관리자 검토를 기다립니다. 재현되는 오류는 고치고 검사·해시·단언·데이터 보호를 끄지 않습니다.

사람이 작성한 각 커밋에 `Signed-off-by` 문구가 필요합니다. 동의 없이 다른 기여자의 이력을 재작성하지 않습니다.
한정된 자동화 예외는 사람의 커밋에 적용되지 않습니다. DCO와 플랫폼·코드 소유자 검토는 별개입니다.

번역 내용이 다르면 영어 기여 안내를 기준으로 합니다. 네이티브 창 동작·라우팅·탐색·sidecar
경계를 변경하면 관련 Hosted Windows 검사 뒤 플랫폼 shell maintainer의 검토 기록이 필요합니다.
1인 maintainer 기간의 필수 승인 수 0 설정은 해당 소유자 검토 기록을 대신하지 않습니다.

로컬 검사·원격 CI·main 병합·후보 검증·실사용 확인은 나누어 기록합니다.
릴리스 공개나 교체는 별도 작업이며 PR 통과만으로 설치 파일·이미지가 배포되지는 않습니다.

## 보안과 라이선스

취약점은 [SECURITY](SECURITY.md)의 비공개 경로로 신고합니다. 키·토큰·백업·원문 로그를
Issue나 PR에 올리지 않습니다. [행동 규범](CODE_OF_CONDUCT.md)을 따릅니다.
별도로 명시된 구성 요소를 제외한 기여에는 `GPL-3.0-only`를 적용합니다.
