# Angmoo 0.1.4

로컬 데이터와 검색을 PostgreSQL로 전환하고, 정식 0.1.3 사용자가 데이터를 이어 쓸 수 있는 명시적인 이전 절차를 제공합니다.

## 주요 변경 사항

- **로컬 저장과 검색:** 앱 데이터·활동 체크포인트·키워드 검색에 PostgreSQL을 사용합니다. 의미 기억 검색에는 pgvector 정확 유사도 검색을 사용합니다. Docker와 Termux는 frontend·backend·PostgreSQL을 실행하며, Windows 설치판은 전용 PostgreSQL 서버를 포함해 관리합니다.
- **기억·관계 처리:** 기억 저장과 관계 검토가 공용 대기열을 사용합니다. 완료된 결과를 유지하며, 실패한 작업은 사용자가 다시 시도하거나 재시도 없이 종료할 수 있습니다. SNS와 Chat은 활동 시작 시점에 확정한 입력을 유지합니다.
- **설치와 복구:** Docker·Termux용 0.1.3 이전 도구와 Windows 첫 실행 이전 안내를 제공합니다. Windows 최초 준비·중단된 이전 복구와 PostgreSQL 읽기 트랜잭션 처리를 개선했습니다.
- **문서 개선:** 한국어·영어 README, 기억 저장·검색 도표와 설치·이전·복구 안내를 정리했습니다.

## 다운로드와 업데이트

- **Windows x64:** [설치 파일 다운로드](https://github.com/angmoo-tree/angmoo/releases/download/release-v0.1.4/Angmoo_0.1.4_x64-setup.exe). 프로그램을 설치한 뒤 Angmoo를 실행하고 데이터 이전에 동의하세요. 프로그램 설치와 데이터 이전은 별도 단계입니다. [Windows 이전 안내](https://github.com/angmoo-tree/angmoo/blob/release-v0.1.4/docs/public/postgresql-migration.ko.md#windows-x64-설치판)를 따라 진행하세요.
- **Docker — amd64·ARM64:** [설치 안내](https://github.com/angmoo-tree/angmoo/blob/release-v0.1.4/docs/public/container-release.ko.md)를 따라 진행하세요. 기존 0.1.3 사용자는 [이전 도구](https://github.com/angmoo-tree/angmoo/blob/release-v0.1.4/docs/public/postgresql-migration.ko.md)를 실행합니다. 도구가 기존 프로젝트를 찾아 확인하거나 선택하도록 안내합니다.
- **Android ARM64 — Termux:** [Termux 안내](https://github.com/angmoo-tree/angmoo/blob/release-v0.1.4/docs/public/termux.ko.md)와 이전 절차를 따라 진행하세요. Android는 계속 실험 지원입니다.

업데이트 전에 Angmoo 전체 데이터를 백업하세요. 직접 이전은 정식 0.1.3만 지원합니다. 새 환경의 동작을 확인할 때까지 원본 SQLite 데이터와 백업을 보관하세요. PostgreSQL에서 새로 만든 변경 사항은 0.1.3으로 복사되지 않습니다.

## 안내 사항

- 이전 시 원문을 검증할 수 없는 기존 기억은 상황기억 본문과 원문 부족 상태를 유지합니다. 새 기억에는 README에서 설명한 원문 스냅샷 정책을 적용합니다.
- macOS 호스트의 이전은 아직 공식 지원 검증을 하지 않았습니다. ARM64 이미지를 제공하는 것과 해당 호스트의 이전 검증은 구분합니다.
- 기존에 보고한 Chat 이미지 크기와 새 World의 기본 언어 문제는 이번 수정 범위에서 제외했습니다.
- Windows 설치본에는 Authenticode 코드 서명이 없습니다. 해시와 GitHub 빌드 출처 attestation을 함께 제공하며, 이는 Windows 게시자 서명과 구분합니다. 시험한 플랫폼과 확인 범위는 [검증 기록](https://github.com/angmoo-tree/angmoo/blob/main/docs/releases/0.1.4/verification.md)을 참고하세요.

[전체 변경 내역](https://github.com/angmoo-tree/angmoo/compare/release-v0.1.3...release-v0.1.4)
