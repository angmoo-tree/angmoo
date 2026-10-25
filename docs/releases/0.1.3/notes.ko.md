# Angmoo 0.1.3

실행이 중단된 뒤 Termux에서 Angmoo를 다시 시작하지 못할 수 있던 문제를 수정했습니다.

## 주요 변경 사항

- **Termux 시작:** 이전 프로세스가 종료된 것을 확인한 뒤 미종료 로그 세션을 복구합니다. 중단으로 종료 시각이 남지 않은 과거 로그만으로 새 시작이 막히는 문제를 해결했습니다.
- **설치 안내 개선:** 설치는 완료됐지만 서버를 시작하지 못한 경우, 실패한 단계와 저장된 로그를 확인하는 방법을 구분해 안내합니다.
- **문서 개선:** 복구와 데이터 보존 방법을 이해하기 쉽도록 한국어·영어 설치 안내를 정리했습니다.

## 다운로드와 업데이트

- **Windows x64:** [설치 파일 다운로드](https://github.com/angmoo-tree/angmoo/releases/download/release-v0.1.3/Angmoo_0.1.3_x64-setup.exe).
- **Docker — amd64·ARM64:** [설치 안내](https://github.com/angmoo-tree/angmoo/blob/release-v0.1.3/docs/public/container-release.ko.md)를 따라 진행하세요.
- **Android ARM64 — Termux:** [Termux 안내](https://github.com/angmoo-tree/angmoo/blob/release-v0.1.3/docs/public/termux.ko.md)를 따라 진행하세요. Android는 실험 지원입니다.

업데이트하기 전에 Angmoo 데이터를 백업하고 사용 중인 설치 방식에 맞는 안내를 따르세요. 기존 데이터 디렉터리나 Docker 볼륨은 유지하세요.

## 안내 사항

- Windows 설치 파일에는 게시자 코드 서명이 없어 알 수 없는 게시자 경고가 표시될 수 있습니다. 이 공식 릴리즈에서 다운로드하세요.
- 이전 프로세스가 살아 있거나 상태를 확인할 수 없다면 로그를 보존하고 두 번째 서버의 시작을 막습니다. 중단된 로그는 일부 기록이 누락될 수 있으며 기존 보존 한도가 적용됩니다.
- Android의 전원·메모리 정책으로 백그라운드 실행이 중단될 수 있습니다. 이번 수정이 Android의 Termux 종료를 막는 것은 아닙니다.

[전체 변경 내역](https://github.com/angmoo-tree/angmoo/compare/release-v0.1.2...release-v0.1.3)
