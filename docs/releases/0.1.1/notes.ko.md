# Angmoo 0.1.1

이번 업데이트는 Termux 실행 명령을 간단하게 하고 설치·사용 안내를 정리했습니다.

## 주요 변경 사항

- **Termux 실행:** 설치 후 현재 셸이나 새 Termux 셸에서 `angmoo start`,
  `angmoo status`, `angmoo stop`을 바로 사용할 수 있습니다. 셸 설정 파일을
  수정할 필요가 없으며 기존 전체 경로 명령도 계속 사용할 수 있습니다.
- **기존 설치 호환:** 새 도구는 기존 0.1.0 설치의 버전 정보를 기준으로 실행 상태를
  확인합니다. 사용자 지정 home을 포함해 같은 데이터 디렉터리를 유지하는
  업데이트 절차를 안내합니다.
- **문서 개선:** 설치와 사용 방법을 이해하기 쉽도록 한국어·영어 README와 설치
  안내를 정리했습니다.

## 다운로드와 업데이트

- **Windows x64:** [설치 파일 다운로드](https://github.com/angmoo-tree/angmoo/releases/download/release-v0.1.1/Angmoo_0.1.1_x64-setup.exe).
- **Docker — amd64·ARM64:** [설치 안내](https://github.com/angmoo-tree/angmoo/blob/release-v0.1.1/docs/public/container-release.ko.md)를 따라 진행하세요.
- **Android ARM64 — Termux:** [Termux 안내](https://github.com/angmoo-tree/angmoo/blob/release-v0.1.1/docs/public/termux.ko.md)를 따라 진행하세요. Android는 실험 지원입니다.

업데이트하기 전에 Angmoo 데이터를 백업하고 사용 중인 설치 방식에 맞는 안내를
따르세요. 기존 데이터 디렉터리나 Docker 볼륨은 유지하세요. 기본 Termux 설치기는
이전의 사용자 지정 데이터 home을 자동으로 선택하지 않습니다.

## 안내 사항

- Windows 설치 파일에는 게시자 코드 서명이 없어 알 수 없는 게시자 경고가
  나타날 수 있습니다. 이 공식 릴리즈에서 다운로드하세요.
- Android의 전원·메모리 정책에 따라 백그라운드 활동이 중단될 수 있습니다.
  이번 출시는 모든 휴대폰에서 화면 꺼짐 중 연속 실행을 인증한 것이 아닙니다.

[전체 변경 내역](https://github.com/angmoo-tree/angmoo/compare/release-v0.1.0...release-v0.1.1)
