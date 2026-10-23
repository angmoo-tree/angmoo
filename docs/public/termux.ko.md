# Termux에서 ARM64 배포물 실험 실행

**검증한 ARM64 backend·frontend 이미지와 같은 배포물**을 재사용합니다.
Android에서 Docker를 실행하는 방식은 아닙니다. PRoot-Distro가 두 OCI
파일시스템을 각각 가져와 backend의 Debian/Python과 frontend의 Debian/Node를
유지합니다. 기존 앱 진입점을 실행하며 앱 라이브러리 재설치, 이미지 수정,
포트·환경 파일 수동 편집을 요구하지 않습니다.

**릴리스:** [Angmoo 0.1.0](https://github.com/angmoo-tree/angmoo/releases/tag/release-v0.1.0)을 사용할 수 있습니다.
Android는 계속 실험 지원입니다. Linux ARM64·QEMU 검사는 실제 휴대폰의
전원 관리·백그라운드 실행·성능 인증이 아닙니다.

시험한 Samsung Android 14 기기에서는 partial wake-lock과 배터리 최적화
제외를 적용한 상태에서도 화면 꺼짐 중 시스템이 Termux 자식 프로세스를
종료했습니다. 해당 설정만으로 지속 실행을 보장하지 않습니다. 특정 기기의
관측 결과이며 모든 Android에 공통인 메모리 제한을 의미하지 않습니다.
브라우저를 닫는 것 자체가 서버를 종료하지는 않지만 Android가 중단할 수 있습니다.

## 처음 설치하고 실행하기: 두 명령

지원되는 ARM64 Android 기기에 Termux를 설치하고 아래 두 명령을 각각 실행합니다.
두 번째 명령은 공식 버전별 Release의 설치 파일을 내려받은 뒤 실행합니다.
아직 공개하지 않은 버전의 다운로드 실패를 다른 버전이나 main 코드로 우회하지 않습니다.

```sh
pkg update && pkg install -y python curl proot
```

```sh
curl --fail --location --proto '=https' --proto-redir '=https' --max-time 120 -o "$HOME/install-angmoo.py" https://github.com/angmoo-tree/angmoo/releases/download/release-v0.1.0/install-termux.py && python "$HOME/install-angmoo.py"
```

설치기는 실행기 ZIP 다운로드, `RELEASE-SHA256SUMS` 대조, 압축 해제, 최초 준비,
이미지 설치, backend·frontend 시작을 차례로 처리합니다. 배포 시 설치 파일에
고정한 ZIP의 SHA-256·크기와 체크섬 목록이 모두 일치해야 실행기 코드를 실행합니다.
기존 이미지 아키텍처·소스·버전·digest 검증과 데이터 보존, 중복 실행·포트 검사는 유지합니다.
어느 단계든 실패하면 후속 단계를 실행하지 않습니다. 셸 초기화 파일은 수정하지 않습니다.

최초 설치 파일의 신뢰 출처는 위 공식 GitHub Release의 HTTPS 주소입니다.
설치 파일 자체의 SHA-256도 `RELEASE-SHA256SUMS`에 포함되므로 별도 검토·대조할 수 있습니다.
이 절차를 배포 서명 검증이나 Android 실기기 인증으로 해석하지 않습니다.

성공하면 **http://127.0.0.1:3000**을 엽니다. 다음부터 설치 과정을 반복하지 않고
아래 명령을 사용합니다. 전체 경로를 쓰므로 PATH 등록 명령이 필요하지 않습니다.

```sh
~/.local/bin/angmoo start
~/.local/bin/angmoo status
~/.local/bin/angmoo stop
```

## 개발 소스의 단축 명령 등록

이 절의 명령 등록 기능은 **공개된 0.1.0 도구에는 포함되어 있지 않습니다.**
0.1.0에서는 위 전체 경로 명령을 그대로 사용할 수 있습니다.

`command_registration.py`가 포함된 검토한 새 도구의 `sh setup.sh`는
기존 `$HOME/.local/bin/angmoo` wrapper를 가리키는 링크를
`$PREFIX/bin/angmoo`에 등록합니다. `Command ready: angmoo`를 확인하면
현재·새 Termux 셸에서 `angmoo start`, `angmoo status`, `angmoo stop`을
사용합니다. alias나 셸 초기화 파일 수정은 필요하지 않습니다. 내부 설치 호출은
검증된 전체 경로를 유지하며 두 서비스가 준비된 뒤에만 준비 완료를 안내합니다.

이미 완전하게 설치된 환경에는 검토한 **새 도구 폴더**에서 명령만 등록할 수 있습니다.

```sh
sh setup.sh --register-command-only
```

이 모드는 pkg/pip 실행, 도구·이미지 교체, 서비스 재시작을 하지 않고 앱 데이터·키·로그를
읽지 않습니다. 설치 간 경쟁을 막는 private setup 잠금만 사용합니다. custom home
설치에 명령을 등록하려고 최초 설치 bootstrap 전체를 다시 실행하지 마세요.
기존 데이터 home을 계속 지정합니다.

```sh
angmoo --home "$HOME/.local/share/angmoo-custom" status
```

같은 wrapper를 가리키는 기존 링크는 재사용합니다. 다른 명령·수정한 wrapper·안전하지
않은 prefix·PATH 앞쪽의 동명 명령은 덮어쓰지 않고 오류로 안내합니다. 불완전한 설치에는
등록 전용 모드를 사용할 수 없습니다. `setup_busy`는 다른 setup이 잠금을 소유한다는
뜻이므로 그 작업이 끝난 뒤 다시 실행합니다. 충돌 대상을 먼저 확인하고 변경하세요.
기존 설치가 온전하다면 전체 경로 실행을 유지할 수 있습니다. prefix 등록은 native
Termux 환경을 확인한 경우에만 수행하며 비 Termux 검증 환경은 전체 경로를 사용합니다.
이 등록은 전원 관리 설정을 변경하지 않습니다.

## 수동 설치와 통제 검증

단계를 직접 확인하려면 공식 `angmoo-tree/angmoo` Release에서
`angmoo-termux-tools.zip`을 받고 `RELEASE-SHA256SUMS`의 해시를 확인하세요.
Termux 내부 전용 저장소에 압축을 풀고 해당 폴더에서 최초 한 번 준비합니다.

```sh
sh setup.sh
export PATH="$HOME/.local/bin:$PATH"
```

공개 0.1.0의 이 export는 현재 셸에만 적용됩니다. 위 prefix 등록을 검증한 새 도구에는
별도 export가 필요하지 않습니다.

준비 도구는 없는 Python·PRoot를 플랫폼 패키지로 설치하고, 해시를 고정한
PRoot-Distro 5.10.0을 전용 가상 환경에 설치합니다. root·Docker daemon은
필요하지 않습니다. 도구의 라이선스와 고정 버전 원본 안내를 보존하세요.
이후 설치와 시작은 각각 한 명령입니다.

```sh
angmoo install --release 0.1.0
angmoo start
```

Android 브라우저에서 **http://127.0.0.1:3000**을 엽니다. backend는 loopback
8080을 사용합니다. 다른 프로세스가 포트를 사용하면 해당 프로세스를 채택하거나
종료하지 않고 시작을 거부합니다. `angmoo status`, `angmoo diagnostics`는 안전한
실행 식별자·상태만 읽습니다. `angmoo stop`, `angmoo restart`로 종료·재시작하며
backend 작업 종료에는 최대 200초를 기다립니다. 데이터는 보존됩니다.
자료를 쓰는 중 Termux를 강제 종료하지 마세요.

상태와 데이터는 두 rootfs 밖의 `~/.local/share/angmoo`에 0700 권한으로 둡니다.
backend에만 데이터 경로를 연결합니다. Android 공유 저장소로 이동하지 마세요.
자격 증명·데이터는 이미지에 넣지 않습니다. 두 서비스의 버전·소스를 일치시키며,
가져오기 실패 시 불완전한 쌍을 선택하거나 기존 설치를 지우지 않습니다.
이전 세션 프로세스가 남으면 backend 중복 실행을 거부하고 진단 상태를 남깁니다.

## 로컬 후보 검증

관리자는 검증한 ARM64 backend·frontend 쌍을 `install --candidate-manifest`와
별도 `--home`으로 시험할 수 있습니다. 후보와 공개판의 데이터 root를 섞거나
기동을 위해 이미지 검증을 완화하지 않습니다. 동일성 검사는
[후보 가져오기](../operations/release-candidate-import.md)를 참고합니다.
로컬·에뮬레이션 성공은 실기기 인증이 아닙니다.

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
