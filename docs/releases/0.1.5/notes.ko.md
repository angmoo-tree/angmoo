# Angmoo 0.1.5

의존성을 갱신하고 보안·호환성 수정을 포함하며, 지원 설치 경로를 Docker와 실험 지원 Termux에 집중하는 릴리즈입니다.

## 주요 변경 사항

- **보안 수정:** PDF 처리, Next.js 웹 실행 기반, 암호화·WebSocket 의존성과 영향을 받는 컨테이너 패키지를 갱신했습니다.
- **호환성:** Google GenAI 3, SQLAlchemy 2.1, Ladybug 0.22와 관련 의존성을 갱신했습니다. 갱신된 라이브러리에서 기존 Chat·SNS·기억·관계 처리 방식을 유지하도록 맞췄습니다.
- **PostgreSQL 설치:** 설치·업데이트 시 누락된 검색 구조를 준비하면서, 기존 기억과 서비스 계정의 제한된 권한을 유지합니다.
- **문서 개선:** 설치·업데이트·지원 범위와 Termux에서 화면을 열 수 있는 시점을 이해하기 쉽도록 영어·한국어 안내를 정리했습니다.

## 다운로드와 업데이트

- **새 설치:** [Docker 새 설치](https://github.com/angmoo-tree/angmoo/blob/2f6555b9d52f28b3b723673d49d9f4d4b6ed2588/docs/public/container-release.ko.md#새-설치) 또는 [Termux 새 설치](https://github.com/angmoo-tree/angmoo/blob/2f6555b9d52f28b3b723673d49d9f4d4b6ed2588/docs/public/termux.ko.md#처음-설치)를 따르세요. Docker는 Linux amd64·ARM64와 Windows Docker Desktop을 지원하며 Android ARM64는 실험 지원입니다.
- **Docker 0.1.4 → 0.1.5 업데이트:** 먼저 백업한 뒤 **기존 설치 폴더**에서 [업데이트 절차](https://github.com/angmoo-tree/angmoo/blob/2f6555b9d52f28b3b723673d49d9f4d4b6ed2588/docs/public/container-release.ko.md#014에서-업데이트)를 따르세요. 같은 프로젝트·볼륨·설정을 유지하며 `git clone`을 반복하지 않습니다. 일반 Git 설치와 이전 도구가 만든 Compose의 절차를 구분해 안내합니다.
- **Termux 0.1.4 → 0.1.5 업데이트:** 백업 → `angmoo stop` → [새 설치와 같은 공식 설치기 실행](https://github.com/angmoo-tree/angmoo/blob/2f6555b9d52f28b3b723673d49d9f4d4b6ed2588/docs/public/termux.ko.md#같은-데이터-home을-유지하며-업데이트) 순서입니다. 기존 선택 데이터 경로를 유지하고 자동으로 시작합니다. `--home`을 직접 지정한다면 별도 안내를 따르세요. `Installed; run angmoo start.` 이후에도 준비가 이어지므로 `Ready`와 접속 주소를 기다립니다.

위 PostgreSQL 업데이트에는 SQLite 이전을 다시 실행하지 않습니다. 기존 주소에서 World·캐릭터·기억·대화를 확인하세요.

**Windows 네이티브 설치판 사용자:** 0.1.5부터 Windows 네이티브 설치본 신규 배포와 공식 지원을 중단합니다. 과거 릴리즈·소스·수동 개발 워크플로는 보존합니다. Windows 설치판에서 Docker로 옮기는 이전 도구는 제공하지 않습니다. Docker는 별도의 빈 환경으로 시작하며 기존 대화·기억·관계·설정은 자동으로 이어지지 않습니다. 해당 기록이 필요하면 원래 설치와 백업을 보존하세요.

## 안내 사항

- 설치·업데이트 안내를 공개 후 명확히 정리했습니다. 위 링크는 수정된 문서로 연결하며, 0.1.5 제품 태그·이미지·다운로드 파일은 그대로입니다. 첨부된 노트 파일은 최초 공개 당시 내용입니다.
- 기존 SQLite 0.1.3 사용자는 먼저 [0.1.4의 이전 안내](https://github.com/angmoo-tree/angmoo/blob/release-v0.1.4/docs/public/postgresql-migration.ko.md)에 따라 이전해야 합니다.
- [검증 범위와 알려진 제한](https://github.com/angmoo-tree/angmoo/blob/a1bea4355af19e38b96dab25bc7d13981dd21430/docs/releases/0.1.5/verification.md), [소스·배포 파일 확인 안내](https://github.com/angmoo-tree/angmoo/blob/a1bea4355af19e38b96dab25bc7d13981dd21430/docs/releases/0.1.5/verification.md#source-and-artifact-integrity)를 확인하세요.

[전체 변경 내역](https://github.com/angmoo-tree/angmoo/compare/release-v0.1.4...release-v0.1.5)
