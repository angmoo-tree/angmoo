# Docker로 Angmoo 실행하기

[English](container-release.md) | 한국어

이 안내는 0.1.4 소스의 Linux amd64·ARM64 실행 구성입니다. 아래 파일과 태그는
정식 공개 후 사용할 수 있습니다. 기존 0.1.3 데이터는 **이미지 교체 전에
[이전 도구](postgresql-migration.ko.md)를 실행**하세요.

## 새 설치

Git과 Linux 엔진의 Docker, Compose 2.23.0 이상을 준비합니다.

```sh
git clone --branch release-v0.1.4 --depth 1 https://github.com/angmoo-tree/angmoo.git
cd angmoo
docker compose up -d --wait
```

http://127.0.0.1:3000 을 엽니다. frontend·backend·PostgreSQL 세 서비스가 실행되며
세 이미지의 버전·소스가 일치해야 합니다. PostgreSQL의 포트는 호스트에 공개하지
않습니다. DB 데이터·앱 미디어와 비밀값·초기 DB 인증은 각각 영속 볼륨에 보관합니다.
상세 구조는 [실행 계약](postgresql-runtime.ko.md)을 참고하세요.

## 상태와 종료

```sh
docker compose ps
docker compose logs --tail 100 postgres backend frontend
docker compose stop
docker compose up -d --wait
```

`stop`·`down`은 데이터를 보존합니다. 필요한 볼륨에 `down --volumes`를 사용하지
마세요. 이미지를 삭제하는 것과 데이터 볼륨을 삭제하는 것은 다른 작업입니다.

## 기존 사용자 이전과 복구

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
