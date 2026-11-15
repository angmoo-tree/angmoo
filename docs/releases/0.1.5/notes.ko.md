# Angmoo 0.1.5

의존성을 갱신하고 보안·호환성 수정을 포함하며, 지원 설치 경로를 Docker와 실험 지원 Termux에 집중하는 릴리즈입니다.

## 주요 변경 사항

- **보안 수정:** PDF 처리, Next.js 웹 실행 기반, 암호화·WebSocket 의존성과 영향을 받는 컨테이너 패키지를 갱신했습니다.
- **호환성:** Google GenAI 3, SQLAlchemy 2.1, Ladybug 0.22와 관련 의존성을 갱신했습니다. 갱신된 라이브러리에서 기존 Chat·SNS·기억·관계 처리 방식을 유지하도록 맞췄습니다.
- **PostgreSQL 설치:** 설치·업데이트 시 누락된 검색 구조를 준비하면서, 기존 기억과 서비스 계정의 제한된 권한을 유지합니다.
- **문서 개선:** 설치·업데이트·지원 범위와 Termux에서 화면을 열 수 있는 시점을 이해하기 쉽도록 영어·한국어 안내를 정리했습니다.

## 다운로드와 업데이트

- **Docker — Linux amd64·ARM64:** [설치·업데이트 안내](https://github.com/angmoo-tree/angmoo/blob/release-v0.1.5/docs/public/container-release.ko.md)를 따르세요. Windows에서는 Docker Desktop을 사용할 수 있습니다.
- **Android ARM64 — Termux:** [Termux 안내](https://github.com/angmoo-tree/angmoo/blob/release-v0.1.5/docs/public/termux.ko.md)를 따르세요. Android는 계속 실험 지원입니다.

**기존 Docker·Termux 0.1.4 사용자:** 먼저 전체 설치 데이터를 백업하고 PostgreSQL 업데이트 절차를 따르세요. 기존 데이터 디렉터리나 Docker 볼륨은 유지하세요. SQLite 이전을 다시 수행하지 않습니다.

**Windows 네이티브 설치판 사용자:** 0.1.5부터 Windows 네이티브 설치본 신규 배포와 공식 지원을 중단합니다. 과거 릴리즈·소스·수동 개발 워크플로는 보존합니다. Windows 설치판에서 Docker로 옮기는 이전 도구는 제공하지 않습니다. Docker는 별도의 빈 환경으로 시작하며 기존 대화·기억·관계·설정은 자동으로 이어지지 않습니다. 해당 기록이 필요하면 원래 설치와 백업을 보존하세요.

## 안내 사항

- 기존 SQLite 0.1.3 사용자는 먼저 [0.1.4의 이전 안내](https://github.com/angmoo-tree/angmoo/blob/release-v0.1.4/docs/public/postgresql-migration.ko.md)에 따라 이전해야 합니다.
- [검증 범위와 알려진 제한](https://github.com/angmoo-tree/angmoo/blob/aa5cbfe665eae47f8e219c86aabd28449bf6111a/docs/releases/0.1.5/verification.md), [소스·배포 파일 확인 안내](https://github.com/angmoo-tree/angmoo/blob/aa5cbfe665eae47f8e219c86aabd28449bf6111a/docs/releases/0.1.5/verification.md#source-and-artifact-integrity)를 확인하세요.

[전체 변경 내역](https://github.com/angmoo-tree/angmoo/compare/release-v0.1.4...release-v0.1.5)
