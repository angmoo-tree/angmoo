# Docker로 Angmoo 실행하기

> **0.1.5 지원 정책:** Docker(Linux amd64·ARM64, Windows Docker Desktop 포함)와 실험 지원 Termux ARM64를 유지합니다. 0.1.5부터 Windows 네이티브 설치본 신규 배포·공식 지원을 중단합니다. 기존 EXE·코드·수동 workflow는 보존합니다. Windows 설치판 → Docker 데이터 이전 도구는 제공하지 않으며 Docker는 별도의 빈 환경으로 시작합니다. 기존 데이터가 필요하면 원래 설치와 백업을 보존하세요. Docker·Termux 0.1.4 사용자는 데이터를 보존하여 업데이트하며 SQLite 이전을 다시 실행하지 않습니다.

[English](container-release.md) | 한국어

이 안내는 공개된 0.1.5의 Linux amd64·ARM64 실행 구성입니다. 기존 0.1.3 데이터는 먼저 [기존 이전 도구](postgresql-migration.ko.md)로 0.1.4에 이전한 뒤 아래 업데이트 절차를 따르세요.

## 새 설치

Git과 Linux 엔진의 Docker, Compose 2.23.0 이상을 준비합니다.
기존 Angmoo가 없는 환경에서 실행하세요. 기존 0.1.4 사용자는 아래 **업데이트** 절차를 따릅니다.

```sh
git clone --branch release-v0.1.5 --depth 1 https://github.com/angmoo-tree/angmoo.git
cd angmoo
docker compose up -d --wait
```

http://127.0.0.1:3000 을 엽니다. frontend·backend·PostgreSQL 세 서비스가 실행되며
세 이미지의 버전·소스가 일치해야 합니다. PostgreSQL의 포트는 호스트에 공개하지
않습니다. DB 데이터·앱 미디어와 비밀값·초기 DB 인증은 각각 영속 볼륨에 보관합니다.
상세 구조는 [실행 계약](postgresql-runtime.ko.md)을 참고하세요.

## 0.1.4에서 업데이트

0.1.4는 이미 PostgreSQL을 사용합니다. 먼저 [DB·미디어·비밀값 전체를 백업](postgresql-backup.ko.md)하세요. SQLite 이전 도구는 다시 실행하지 않습니다. 아래 두 방법 중 현재 설치에 맞는 **하나만** 따르세요. 명령은 한 줄씩 실행하고 오류가 나면 다음 단계로 넘어가지 마세요.

### A. Git으로 새로 설치했던 일반 0.1.4

1. 터미널에서 **기존에 설치할 때 사용한 `angmoo` 폴더**로 이동합니다. 새 폴더에 다시 복제하지 않습니다.
2. `docker compose ls --all`로 기존 프로젝트와 설정 파일을 확인합니다. 기본 프로젝트는 `angmoo`입니다. 이전에 `-p`로 다른 이름을 사용했다면 아래 모든 `docker compose` 명령에도 같은 `-p 이름`을 넣습니다. `.env`와 기존 볼륨을 유지하세요.
3. `.env` 또는 셸 환경에서 버전을 따로 지정했다면 `ANGMOO_IMAGE_TAG=release-v0.1.5`, `ANGMOO_VERSION=0.1.5`로 맞춥니다. 버전 지정이 없다면 추가할 필요가 없습니다.
4. 다음 명령을 차례로 실행합니다. Git 명령에서 로컬 수정 충돌이 나면 멈추고 수정 내용을 보존하세요. 강제 초기화하지 않습니다. Compose를 직접 수정했거나 여러 설정 파일을 쓰는 경우에는 아래 B를 사용하세요.

```sh
git fetch origin tag release-v0.1.5
git switch --detach release-v0.1.5
docker compose pull
docker compose up -d --wait
docker compose ps
```

기존 주소(기본 http://127.0.0.1:3000)에서 World·캐릭터·기억·대화를 확인합니다. `up`은 같은 프로젝트의 서비스를 새 이미지로 교체하며 기존 데이터 볼륨을 다시 연결합니다. 기존 폴더가 있는데 `git clone`을 다시 실행하면 실패하므로, 새 설치 명령을 반복하는 대신 위 절차로 Compose 버전을 갱신합니다.

### B. 0.1.3 이전 도구로 전환했거나 Compose를 직접 구성한 경우

`docker compose ls --all`로 기존 프로젝트와 실제 설정 파일을 확인합니다. 0.1.3에서 이전한 설치는 도구가 출력한 `installation/compose.json`을 사용합니다. 기존 파일·프로젝트 이름·데이터 볼륨·포트·비밀값 연결을 유지합니다. 새 프로젝트를 만들면 별도의 빈 환경이 나타납니다.

기존 Compose 파일 옆에 다음 내용을 `angmoo-0.1.5.yml`로 저장합니다.

```yaml
services:
  postgres:
    image: ghcr.io/angmoo-tree/angmoo-postgres:release-v0.1.5
  backend:
    image: ghcr.io/angmoo-tree/angmoo-backend:release-v0.1.5
    environment:
      ANGMOO_VERSION: 0.1.5
  frontend:
    image: ghcr.io/angmoo-tree/angmoo-frontend:release-v0.1.5
```

아래 `EXISTING_PROJECT`와 `EXISTING_COMPOSE`를 확인한 기존 값으로 바꾸세요. 공백이 있는 경로는 따옴표로 감쌉니다. 기존에 여러 `-f` 파일을 썼다면 같은 순서로 모두 넣고 새 파일을 마지막에 추가합니다. 첫 명령에서 세 이미지를 모두 받은 뒤 기존 서비스를 종료합니다.

```sh
docker compose -p EXISTING_PROJECT -f EXISTING_COMPOSE -f angmoo-0.1.5.yml pull
docker compose -p EXISTING_PROJECT -f EXISTING_COMPOSE stop
docker compose -p EXISTING_PROJECT -f EXISTING_COMPOSE -f angmoo-0.1.5.yml up -d --wait
```

이후 상태 확인·종료·시작에도 같은 `-p`와 모든 `-f` 파일을 함께 사용합니다. 예를 들어 상태 확인은 다음과 같습니다.

```sh
docker compose -p EXISTING_PROJECT -f EXISTING_COMPOSE -f angmoo-0.1.5.yml ps
```

기존 주소로 접속해 World·캐릭터·저장 데이터를 확인하고, 확인 전까지 백업과 이전 이미지를 유지하세요. 복귀할 때는 0.1.4 전체 백업과 그 버전의 이미지를 함께 복원합니다. 바뀐 데이터에 구형 이미지만 연결하거나 `down --volumes`·비밀값 삭제를 실행하지 마세요.

## 상태와 종료

아래는 기본 프로젝트·단일 `compose.yml`의 명령입니다. 다른 프로젝트 이름을 사용했다면 같은 `-p`를, 위 B로 업데이트했다면 같은 `-p`와 모든 `-f`를 각 명령에 넣으세요.

```sh
docker compose ps
docker compose logs --tail 100 postgres backend frontend
docker compose stop
docker compose up -d --wait
```

`stop`·`down`은 데이터를 보존합니다. 필요한 볼륨에 `down --volumes`를 사용하지
마세요. 이미지를 삭제하는 것과 데이터 볼륨을 삭제하는 것은 다른 작업입니다.

## 과거 0.1.3 SQLite 데이터 이전과 복구

이전 도구는 기존 프로젝트·실제 볼륨 연결을 자동 탐색합니다. 하나면 확인, 여러
개면 선택 후 확인하고, 발견하지 못할 때만 직접 지정합니다. 원본을 정상 종료하고
백업·복사본 변환·검증을 마친 뒤 새 구성으로 전환합니다. 사용법과 중단 후 재개는
[한글 이전 안내](postgresql-migration.ko.md)에 있습니다.

이전 뒤에는 도구가 출력한 `installation/compose.json`으로 실행합니다. 기존
0.1.3 checkout에서 `up`만 실행하면 전환되지 않습니다. PG에서 추가한 데이터는
구형 SQLite로 자동 합쳐지지 않습니다. 업데이트 전에는
[DB·미디어·비밀값을 포함한 전체 백업](postgresql-backup.ko.md)을 준비하세요.

개발은 별도 데이터의 [기여 환경](development.md), Android는 Docker 없이
[Termux/PRoot](termux.ko.md)를 사용합니다. ARM64 검증은 Android 절전 동작 인증과
구분합니다. 배포 관리자는 [동일 소스 공개 절차](../operations/release-publishing.md)를 따릅니다.
