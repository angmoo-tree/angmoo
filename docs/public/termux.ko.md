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

지원되는 최신 Termux를 설치한 뒤 공식 `angmoo-tree/angmoo` Release에서
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
angmoo --home "$HOME/.local/share/angmoo-rehearsal" install --manifest /absolute/candidate.json
angmoo --home "$HOME/.local/share/angmoo-rehearsal" start
angmoo --home "$HOME/.local/share/angmoo-rehearsal" status
angmoo --home "$HOME/.local/share/angmoo-rehearsal" stop
angmoo --home "$HOME/.local/share/angmoo-rehearsal" restart
```

manifest에는 완전한 쌍과 정확한 해시가 필요합니다. 소스·archive/config/diff-ID,
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
