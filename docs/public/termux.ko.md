# ARM64 Termux / PRoot로 Angmoo 실행하기

[English](termux.md) | 한국어

0.1.4는 검증된 ARM64 frontend·backend·PostgreSQL 세 이미지의 파일시스템을
PRoot로 실행합니다. 휴대폰에 Docker daemon은 필요하지 않습니다. 아래 배포물은
정식 공개 후 사용할 수 있습니다. Android 지원은 실험적이며 Linux·QEMU 통과가
화면 꺼짐·절전 중 실행을 보장하지 않습니다. 기존 Samsung Android 14 관측에서는
wake lock과 배터리 최적화 제외 상태에서도 자식 프로세스가 종료됐습니다.

## 처음 설치

ARM64 Termux의 비공개 저장소에서 실행합니다.

```sh
pkg update && pkg install -y python curl proot clang make libandroid-shmem
curl --fail --location --proto '=https' --proto-redir '=https' --max-time 120 -o "$HOME/install-angmoo.py" https://github.com/angmoo-tree/angmoo/releases/download/release-v0.1.4/install-termux.py
python "$HOME/install-angmoo.py"
```

설치기는 버전·소스·해시를 확인하고 세 서비스를 시작합니다. tools ZIP의 고정
해시·크기와 `RELEASE-SHA256SUMS`가 일치해야 도구를 실행합니다. 최초 installer의
신뢰 근거는 공식 HTTPS Release이며 별도 배포 서명이나 Android 인증을 뜻하지 않습니다.
완료되면 http://127.0.0.1:3000 을 엽니다.

```sh
angmoo start
angmoo status
angmoo diagnostics
angmoo stop
angmoo restart
```

시작은 PostgreSQL 준비 확인 → backend → frontend, 종료는 역순입니다. 기본 앱
포트는 8080·3000, DB는 loopback 5432입니다. 다른 프로세스를 채택하거나 종료해
포트를 확보하지 않습니다. 기동 실패 시 로그를 확인하며 기존 데이터를 지우지 않습니다.

## 기존 0.1.3 데이터 이전

새 tools ZIP과 checksum을 검증하고 풀어 `sh setup.sh`로 실행기만 업데이트한 뒤:

```sh
angmoo migrate --release 0.1.4 --language ko
angmoo start
```

원본을 보존하고 `<기존-home>-postgresql`에 백업·변환·검증합니다. 성공 후에만
선택을 전환합니다. 사용자 지정 home은 모든 명령에 같은 `--home`을 지정합니다.
[이전·재개·복귀 사용법](postgresql-migration.ko.md)을 따르세요. 일반 `install`로
SQLite 데이터를 덮어쓰지 않습니다. 기존 비공개 PG 실험 데이터는 지원 입력이 아닙니다.

## 호스트 도구와 데이터

PRoot-Distro 5.10.0은 해시를 고정한 전용 Python 환경에 설치합니다. Play Store
Termux는 SysV 공유 메모리 helper를 지원하는 고정 upstream PRoot를 설치 home의
전용 도구로 빌드합니다. 패키지 PRoot나 전역 설정, 앱 이미지 파일은 수정하지
않습니다. 빌드 출처·패치·해시는 `records/proot-build.json`에 남습니다. 짧은 비공개
IPC 임시 경로는 `.cache/angmoo-pg` 아래 설치별 소유권 표식으로 구분하며 DB가 아닙니다.

PGDATA·미디어·비밀값·결과 저널은 rootfs 밖에 둡니다. 설치 home은 mode 0700을
유지하고 `/sdcard` 같은 공용 저장소로 옮기지 않습니다. DB 파일만 복사하거나
구형 이미지를 새 PG 데이터에 연결하지 마세요. [전체 백업·복원](postgresql-backup.ko.md)을
따르고 이전 이미지·원본·백업을 검증 전에 지우지 않습니다.

## 명령 등록과 후보 시험

`setup.sh`는 기존 wrapper에 연결된 `angmoo` 명령을 등록하며 shell 시작 파일을
수정하지 않습니다. 이미 완성된 설치의 명령만 등록할 때는 새 도구 디렉터리에서
`sh setup.sh --register-command-only`를 사용합니다. 다른 명령이나 수정된 wrapper를
덮어쓰지 않습니다. 기존 0.1.0 직접 이전은 이번 지원 범위가 아닙니다.

관리자는 별도 `--home`에서 `install --candidate-manifest`로 동일 소스의 세 후보를
시험할 수 있습니다. 로컬 검증을 정식 CI나 실기기 인증으로 표시하지 않습니다.

## 저장된 서비스 로그

Angmoo가 작성한 고정 터미널 안내는 웹 언어와 관계없이 영어입니다. 웹 화면과
설치 문서는 한국어·영어를 지원합니다. 서비스 원문·외부 도구 출력·사용자 파일명은
기존 민감 정보 가림 규칙을 적용하며 원래 언어를 보존합니다.

새 실행은 자동으로 `basic` 로그를 사용합니다. 일시적으로 안전한 상세 서비스
진단을 남기려면 시작 전에 다음처럼 선택합니다.

```sh
~/.local/bin/angmoo start --log-mode detailed --log-duration 15m
~/.local/bin/angmoo restart --log-mode detailed --log-duration 15m
```

상세 로그 기간의 기본값은 15분이며 `1m`부터 `60m`까지 1분 단위로 지정할 수 있습니다. 서비스 기동 시간도
포함하며 기간이 끝나면 재시작 없이 `basic`으로 돌아옵니다. 다음 실행의 기본 모드도 `basic`입니다.
잘못된 `restart` 옵션은 현재 서비스를 종료하기 전에 거절합니다. 실행 중인 서비스에
`start`를 다시 호출해도 모드는 바뀌지 않습니다. 이 옵션은 Chat/SNS 상세 캡처나 기억
진단을 자동으로 켜지 않습니다.

`basic`은 기동·종료, 경고·실패·복구를 보존합니다. `detailed`는 허용된 접근 종류와
작업자·실행권·프록시 요약을 추가합니다. 본문·검색어·키·SQL 매개변수나 전역 DEBUG는
추가하지 않습니다. `status`·`diagnostics`는 요청 정책, UTC 기준 유효 모드 추정값과
서비스별 적용 확인을 구분합니다. 늦게 초기화되는 frontend나 과거 이미지는
`unconfirmed`일 수 있으며, 이것만으로 서비스 실패로 판단하지 않습니다. 각 서비스는
자체 단조 시계(monotonic clock)로 만료를 적용합니다. 한 번 만료된 상세 모드는 다시 활성화되지
않으며, 이 내부 시계의 상태를 호스트의 추정값만으로 직접 확인할 수는 없습니다.

두 수집 스레드는 무출력일 때 대기하며 출력·수명 변경 시 깨어납니다. 변경된 파일만
반영되지 않은 첫 쓰기 이후 최대 1초 안에 버퍼를 파일에 반영(flush)합니다. supervisor의 프로세스 확인과 사용자가
연 `logs --follow`의 비용은 별도입니다. 이 변경이 휴대폰 배터리 사용량을 입증하지는 않습니다.

`start`는 서비스를 백그라운드에서 실행합니다. 다음 명령으로 저장된 출력을 봅니다.

```sh
angmoo logs --service all --tail 200
angmoo logs --service backend --follow
angmoo diagnostics
angmoo logs --session <launch-id> --service frontend
```

`Ctrl+C`는 로그 보기만 종료합니다. 기동 실패 시 최초 실패 서비스·단계·UTC 관측 시각·
안전하게 가린 원래 오류·관측된 종료 코드를 `logs/<launch-id>/session.json`에 남깁니다.
종료 코드는 PRoot 명령 기준이며, 그 값만으로 guest 충돌이나 Android OOM을 확정하지
않습니다. 준비 상태 조회 실패와 정리 실패는 별도로 보존합니다. `diagnostics`에는
supervisor 초기 실행 중 로그 누락 여부도 포함됩니다.

로그는 전용 저장소에 디렉터리 0700·파일 0600으로 저장합니다. 민감한 필드와 알려진
자격 증명 형식은 파일 기록 전에 가립니다. 앱 출력에 개인적인 내용이 있을 수 있으므로
공유 전 확인하세요. backend/frontend는 각각 2 MiB 파일 3개, supervisor/초기 실행 로그는
각각 1 MiB 파일 2개를 유지합니다. 전체는 최대 4개 세션·64 MiB입니다. 순환 삭제·긴 줄 생략·
수집 큐 초과·디스크 오류는 기록 공백으로 남기며 완전 수집으로 표시하지 않습니다.
로그 조회에는 서비스 실행·설치된 배포물·제품 DB 접근이 필요하지 않습니다.

Android나 강제 종료로 로그에 종료 기록이 남지 않았다면, 다음 `angmoo start`가
설치 경로의 실행 잠금 아래 이전 프로세스를 확인합니다. 모두 종료된 것이 확인되면
해당 세션을 중단된 실행으로 기록하고 새 시작을 계속합니다. 알 수 없는 종료 시각을
만들어 넣거나 로그가 완전히 수집됐다고 표시하지 않습니다. 기존 최대 4개 세션 보존
정책은 유지하므로, 정상 종료 또는 중단이 확인된 오래된 세션은 보존 정책에 따라
정리될 수 있습니다. 진단에 필요한 로그는 별도로 복사해 보관하세요.

이전 프로세스가 살아 있거나 확인할 수 없으면 두 번째 서버를 시작하지 않습니다.
기존 로그와 데이터를 유지하고 `angmoo diagnostics`를 확인하세요. 검사를 통과하려고
로그 폴더를 삭제하거나 앱 데이터를 초기화하지 마세요. 이름 변경이나 삭제 도중
로그 정리가 중단되면 다음 시작에서 저장된 정리 기록을 다시 확인합니다. 이전 실행기는
복구된 중단 세션을 이해하지 못하므로 버전 내리기를 복구 절차로 사용하지 않습니다.

`installation_complete_start_failed`는 이미지 설치는 끝났지만 자동 시작에 실패했다는
뜻입니다. 앞서 나온 오류와 `angmoo diagnostics`를 확인하고, 원인을 해결한 뒤 같은
데이터 home에서 `angmoo start`를 다시 실행하세요. 파일을 다시 내려받거나 캐릭터·API 키를
삭제할 필요는 없습니다.
