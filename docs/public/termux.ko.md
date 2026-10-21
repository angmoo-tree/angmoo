# Termux에서 ARM64 배포물 실험 실행

**검증한 ARM64 backend·frontend 이미지와 같은 배포물**을 재사용합니다.
Android에서 Docker를 실행하는 방식은 아닙니다. PRoot-Distro가 두 OCI
파일시스템을 각각 가져와 backend의 Debian/Python과 frontend의 Debian/Node를
유지합니다. 기존 앱 진입점을 실행하며 앱 라이브러리 재설치, 이미지 수정,
포트·환경 파일 수동 편집을 요구하지 않습니다.

**공개 경계:** 아래 공식 설치 명령은 실제 `release-v0.1.0` 공개 후 사용합니다.
P1/P2 구현만으로 공개하지 않습니다. Linux ARM64·QEMU 성공은 Android의
절전·Doze·백그라운드 실행 성공을 의미하지 않습니다. 실제 기기 확인은 P4이며,
그 근거를 확보하기 전 Android 지원은 실험 범위입니다.

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
어느 단계든 실패하면 후속 단계를 실행하지 않습니다. 쉘 초기화 파일은 수정하지 않습니다.

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

## 수동 설치와 통제 검증

단계를 직접 확인하려면 공식 `angmoo-tree/angmoo` Release에서
`angmoo-termux-tools.zip`을 받고 `RELEASE-SHA256SUMS`의 해시를 확인하세요.
Termux 내부 전용 저장소에 압축을 풀고 해당 폴더에서 최초 한 번 준비합니다.

```sh
sh setup.sh
export PATH="$HOME/.local/bin:$PATH"
```

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

공개 전 P1/P4 통제 검증은 검증한 manifest와 ARM64 `.oci.tar` 두 개를 Linux
전용 저장소에 복사해 아래와 같이 수행합니다.

```sh
angmoo --home "$HOME/.local/share/angmoo-rehearsal" install --candidate-manifest /absolute/candidate.json
angmoo --home "$HOME/.local/share/angmoo-rehearsal" start
angmoo --home "$HOME/.local/share/angmoo-rehearsal" status
angmoo --home "$HOME/.local/share/angmoo-rehearsal" stop
angmoo --home "$HOME/.local/share/angmoo-rehearsal" restart
```

로컬 manifest에는 ARM64 backend/frontend 쌍만 정확한 해시와 함께 있어야 합니다.
공식 release 설치와 `--manifest`는 여전히 amd64/ARM64 네 항목을 요구합니다.
로컬 후보 확인을 공식 출시 검증으로 취급하지 않습니다. 소스·archive/config/diff-ID,
PRoot 버전, 호스트·QEMU/native 구분, 기동·종료 시간, readiness, 재시작 데이터
보존, 오래된 PID·포트 충돌·부분 실패 검증을 기록합니다. 실제 Android의
T01–T05/T11은 최초 준비 명령 수·권한·저장소·SNS/Chat 전경 실행·절전·복구를
추가 확인합니다. Linux 컨테이너 리허설로 실제 기기 항목을 통과 처리하지 않습니다.
# Linux 리허설에서 확인한 제한

로컬 OCI 가져오기는 PRoot-Distro 5.10.0이 읽을 수 있도록 임시 archive의
index만 평탄화합니다. 실행 manifest·압축 layer·config·SBOM/provenance의
원래 hash와 원본 후보는 유지합니다. registry 설치는 실행 digest를 직접 선택합니다.

최초 Linux 리허설에서는 ARM64 두 배포물 가져오기를 통과했습니다. 다만 Debian의
PRoot 5.1.0과 QEMU 조합은 bind 경로에 파일을 생성할 수 있어도 statx·쓰기권한
검사가 해당 경로를 사용할 수 없다고 판정했습니다. 앱은 데이터 경로를 거부하고
시작을 중단했습니다. Android 통과 결과가 아니며, 실제 Termux 기동·브라우저·재시작은
P4 실기기 검증이 필요합니다. 이 리허설을 통과시키려고 쓰기권한 검사를 우회하거나
사용자 데이터 권한을 완화하지 않습니다.

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

상세 기간의 기본값은 15분이며 정수 `1m`~`60m`만 허용합니다. 서비스 기동 시간도
포함하며 만료되면 재시작 없이 basic으로 돌아옵니다. 다음 실행도 기본은 basic입니다.
잘못된 restart 옵션은 현재 서비스를 종료하기 전에 거절합니다. 실행 중인 서비스에
start를 다시 호출해도 모드는 바뀌지 않습니다. 이 옵션은 Chat/SNS 상세 캡처나 기억
진단을 자동으로 켜지 않습니다.

basic은 기동·종료, 경고·실패·복구를 보존합니다. detailed는 허용된 접근 종류와
작업자·실행권·프록시 요약을 추가합니다. 본문·검색어·키·SQL 매개변수나 전역 DEBUG는
추가하지 않습니다. status·diagnostics는 요청 정책, UTC 기준 유효 모드 추정값과
서비스별 적용 확인을 구분합니다. 늦게 초기화되는 frontend나 과거 이미지는
unconfirmed일 수 있으며, 이것만으로 서비스 실패로 판단하지 않습니다. 각 서비스는
자기 monotonic 시계로도 한 방향 만료를 적용하며 이 내부 시계는 호스트 추정값에서
직접 확인할 수 없습니다.

두 수집 스레드는 무출력일 때 대기하며 출력·수명 변경 시 깨어납니다. 변경된 파일만
첫 미반영 쓰기부터 최대 1초 안에 flush합니다. supervisor의 프로세스 확인과 사용자가
연 logs --follow의 비용은 별도입니다. 이 변경이 휴대폰 배터리 사용량을 입증하지는 않습니다.

`start`는 서비스를 백그라운드에서 실행합니다. 다음 명령으로 저장된 출력을 봅니다.

```sh
angmoo logs --service all --tail 200
angmoo logs --service backend --follow
angmoo diagnostics
angmoo logs --session <launch-id> --service frontend
```

Ctrl+C는 로그 보기만 종료합니다. 기동 실패 시 최초 실패 서비스·단계·UTC 관측 시각·
안전하게 가린 원래 오류·관측된 종료 코드를 `logs/<launch-id>/session.json`에 남깁니다.
종료 코드는 PRoot 명령 기준이며, 그 값만으로 guest 충돌이나 Android OOM을 확정하지
않습니다. 준비 상태 조회 실패와 정리 실패는 별도로 보존합니다. `diagnostics`에는
supervisor 초기 실행 중 로그 누락 여부도 포함됩니다.

로그는 전용 저장소에 디렉터리 0700·파일 0600으로 저장합니다. 민감한 필드와 알려진
자격증명 형식은 파일 기록 전에 가립니다. 앱 출력에 개인적인 내용이 있을 수 있으므로
공유 전 확인하세요. backend/frontend는 각각 2MiB 파일 3개, supervisor/초기 실행 로그는
각각 1MiB 파일 2개를 유지합니다. 전체는 최대 4세션·64MiB입니다. 순환 삭제·긴 줄 생략·
수집 큐 초과·디스크 오류는 기록 공백으로 남기며 완전 수집으로 표시하지 않습니다.
로그 조회에는 서비스 실행·설치된 배포물·제품 DB 접근이 필요하지 않습니다.
